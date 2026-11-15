"""The human-like timing engine.

The engine converts a target speed (WPM) plus a *variability* percentage into a
stream of keystrokes: for every character it yields the gap before it and the
time the key is held down. It is deliberately free of any I/O: the randomness
source and the clock are injected, which makes the behaviour fully
deterministic in tests and reproducible in bug reports.

Speed model
-----------
One "word" is five characters (the typing-test convention), so::

    base_gap = 60 / (wpm * 5)   # seconds between consecutive key presses

Gaps are measured **keydown to keydown**, which is what typing tests, typing
meters and the WPM readout in this app's own UI all measure. The dwell time
(how long a key stays pressed) is carved *out of* each gap rather than added on
top of it, so enabling a realistic hold time does not quietly slow the run:

    gap = hold + (time released before the next key goes down)

Variability (0-100) scales a symmetric jitter window of up to +/-70 % of the
base gap and progressively enables the extra behaviour models:

* punctuation/space pauses - extra time after ``. ``, ``,``, ``;`` etc., which
  also gives slow web forms time to register input, and
* occasional "thinking" pauses - a small probability of a 0.12-0.45 s gap.

Behaviour (all off by default, so the classic engine is unchanged)
------------------------------------------------------------------
* **Dwell time** - a randomised press duration per keystroke, drawn from
  ``dwell_min_ms``..``dwell_max_ms``.
* **Burstiness** - an autocorrelated speed "mood": a fast burst stays fast for
  a few keys and then recovers, instead of every gap being independent noise,
  which is what makes naive jitter sound mechanical.
* **Pauses correlated with word difficulty** - a planning pause lands before
  hard words (long, mixed case, symbols) rather than at a random offset.
* **Typos and error-correction loops** - occasional wrong-but-adjacent keys,
  each followed by a short pause, a Backspace and a retype.

At variability 0 with every behaviour off every gap equals ``base_gap`` exactly
(metronomic), which keeps ``estimate_duration`` and the actual run in lock-step.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass

from ..config.models import TypingSettings
from .behaviour import keyboard_neighbours, pause_difficulties

#: Maximum symmetric jitter as a fraction of the base gap (at variability 100).
MAX_JITTER = 0.70

#: Extra pause multipliers after particular characters (at variability 100).
_SENTENCE_END = frozenset(".!?")
_CLAUSE_END = frozenset(",;:)]}\"'")
_PAUSE_SPACE = 1.6
_PAUSE_SENTENCE = 4.0
_PAUSE_CLAUSE = 2.4
_PAUSE_TAB = 3.0
_PAUSE_NEWLINE = 6.0

#: Probability of an extra random pause per character at variability 100.
_MAX_THINK_PROBABILITY = 0.06
_THINK_PAUSE_RANGE = (0.12, 0.45)

#: Fraction of the following gap that a dwell time may consume. Keeping a real
#: flight time guarantees the application sees a release before the next press,
#: which is what key repeat detection and slow web forms need.
MAX_DWELL_FRACTION = 0.7

#: Correlation of the burstiness "speed mood" at burstiness 100. Consecutive
#: keys inherit this much of the previous speed, so bursts last several words.
_MAX_MOOD_CARRY = 0.85

#: Largest stretch a maximally difficult word may add to its planning pause.
_MAX_DIFFICULTY_BONUS = 3.0

#: Timing constants for the error-correction loop (all scaled by burstiness).
_TYPO_NOTICE_RANGE = (0.12, 0.42)
_TYPO_BACKSPACE_GAP = (0.09, 0.22)
_TYPO_RETYPE_GAP = (0.10, 0.26)

#: Sentinel character meaning "press Backspace" in generated keystroke streams.
#: It can never appear in a payload (``text.py`` normalises real text, and a
#: literal backspace is not typable in the editor), so it is unambiguous.
BACKSPACE = "\b"


@dataclass(frozen=True, slots=True)
class Keystroke:
    """One scheduled keystroke.

    Attributes:
        char: The character to send.
        interval: Seconds from the previous key press to this one. The first
            keystroke of a run carries the gap measured from the countdown.
        hold: Seconds the key stays pressed (dwell time). ``0.0`` means "tap":
            the runner presses and releases in one atomic operation.
        flight: Seconds between the release of the previous key and the press
            of this one. Derived as ``interval - hold`` and never negative, so
            the total time is unchanged when dwell time is enabled.
    """

    char: str
    interval: float
    hold: float = 0.0
    flight: float = 0.0

    @property
    def duration(self) -> float:
        """Total wall-clock time from the previous key press to this one."""
        return self.interval



@dataclass(frozen=True, slots=True)
class TimingProfile:
    """Derived, immutable timing constants for one run.

    Attributes:
        base_gap: Seconds between key presses before any modulation.
        jitter: Symmetric jitter fraction in ``[0, MAX_JITTER]``.
        extra_probability: Chance of an additional random pause per character.
        humanize_pauses: Whether character-class pauses are applied.
        dwell: ``(low, high)`` held-key duration in seconds; ``(0, 0)`` taps.
        mood_strength: 0-1 share of the cadence driven by the correlated mood.
        mood_carry: AR(1) coefficient that keeps neighbouring speeds alike.
        difficulty_weight: 0-1 pull that hard words stretch their pause by.
        typo_probability: Chance that any one character is mistyped.
    """

    base_gap: float
    jitter: float
    extra_probability: float
    humanize_pauses: bool
    dwell: tuple[float, float] = (0.0, 0.0)
    mood_strength: float = 0.0
    mood_carry: float = 0.0
    difficulty_weight: float = 0.0
    typo_probability: float = 0.0

    @property
    def base_delay(self) -> float:
        """Alias for :attr:`base_gap`, kept for older callers and tooling."""
        return self.base_gap

    @property
    def has_dwell(self) -> bool:
        """True when keystrokes are held rather than tapped."""
        return self.dwell[1] > 0.0

    @property
    def bursty(self) -> bool:
        """True when the rhythm is driven by the correlated mood."""
        return self.mood_strength > 0.0

    @property
    def min_hold(self) -> float:
        """Shortest dwell time in seconds."""
        return self.dwell[0]

    @property
    def max_hold(self) -> float:
        """Longest dwell time in seconds."""
        return self.dwell[1]

    @property
    def min_delay(self) -> float:
        """Shortest possible inter-keystroke gap in seconds."""
        return self.base_gap * (1.0 - self.jitter)

    @property
    def max_delay(self) -> float:
        """Longest possible inter-keystroke gap in seconds.

        Accounts for the widest jittered base gap, the largest character-class
        pause multiplier (a newline), a maximal difficulty bonus and the longest
        "thinking" pause, so the value is a true upper bound for
        :meth:`TimingEngine.keystroke`.
        """
        upper = self.base_gap * (1.0 + self.jitter)
        if self.humanize_pauses:
            upper *= _PAUSE_NEWLINE
        if self.difficulty_weight > 0.0:
            upper *= 1.0 + _MAX_DIFFICULTY_BONUS * self.difficulty_weight
        if self.extra_probability > 0.0:
            upper += _THINK_PAUSE_RANGE[1]
        return upper



class TimingEngine:
    """Produce a stream of keystrokes for a piece of text.

    Args:
        settings: Typing settings (speed, variability, dwell, behaviour).
        rng: Optional :class:`random.Random` for deterministic tests.

    Example:
        >>> engine = TimingEngine(TypingSettings(wpm=300, variability=0))
        >>> round(engine.profile.base_gap, 4)
        0.04
        >>> [round(k.interval, 4) for k in engine.keystrokes("ab")]
        [0.04, 0.04]
    """

    def __init__(self, settings: TypingSettings, rng: random.Random | None = None) -> None:
        self.settings = settings.normalized()
        self._rng = rng if rng is not None else random.Random()
        self.profile = self._build_profile(self.settings)
        #: Burstiness state: current "speed mood" in ``[-1, 1]``. ``0`` is the
        #: neutral cadence, positive is a fast burst, negative a slow recovery.
        self._mood = 0.0

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _build_profile(settings: TypingSettings) -> TimingProfile:
        """Derive timing constants from user settings."""
        wpm = max(1, settings.wpm)
        base_gap = 60.0 / (wpm * 5.0)
        scale = max(0.0, min(100, settings.variability)) / 100.0
        return TimingProfile(
            base_gap=base_gap,
            jitter=MAX_JITTER * scale,
            extra_probability=_MAX_THINK_PROBABILITY * scale,
            humanize_pauses=settings.humanize_pauses,
            dwell=settings.dwell_seconds,
            mood_strength=settings.burstiness / 100.0,
            mood_carry=_MAX_MOOD_CARRY * settings.burstiness / 100.0,
            difficulty_weight=settings.difficulty_weight / 100.0,
            typo_probability=settings.typo_rate / 100.0,
        )

    # ------------------------------------------------------------- primitives
    def _modulated_gap(self, char: str, difficulty: float | None = None) -> float:
        """Return one randomised gap in seconds, before dwell time is carved out.

        Args:
            char: The character typed at the *end* of this gap.
            difficulty: 0-1 difficulty of the word this separator precedes, used
                to stretch the pause. ``None`` disables the difficulty term.
        """
        profile = self.profile
        gap = profile.base_gap

        strength = profile.mood_strength
        if strength > 0.0:
            # AR(1) process: the mood decays towards neutral and is nudged by
            # fresh noise each keystroke. Nearby gaps therefore resemble each
            # other (bursts), which is the property pure per-key jitter lacks.
            carry = profile.mood_carry
            self._mood = carry * self._mood + (1.0 - carry) * self._rng.uniform(-1.0, 1.0)
            # Normalise to unit variance. An AR(1) fed by uniform(-1, 1) noise
            # settles at ``var = (1/3) * (1 - carry) ** 2 / (1 - carry ** 2)``;
            # dividing by its square root turns the mood into a standardised
            # signal, so the two variance contributions below can be mixed
            # without changing the overall spread at any burstiness setting.
            drift = 1.0 - carry
            stationary_sd = (1.0 / math.sqrt(3.0)) * drift / math.sqrt(
                max(1e-9, 1.0 - carry * carry)
            )
            mood_z = self._mood / stationary_sd if stationary_sd > 0.0 else 0.0
            mood_z = max(-3.0, min(3.0, mood_z))
            # Independent per-key noise keeps ``sqrt(1 - strength ** 2)`` of the
            # variance; the correlated mood takes the rest. The average speed is
            # untouched either way because both terms are zero-mean.
            unit = profile.jitter / math.sqrt(3.0)
            noise = self._rng.uniform(-profile.jitter, profile.jitter) * math.sqrt(
                max(0.0, 1.0 - strength * strength)
            )
            gap *= 1.0 + noise + unit * mood_z * strength
        elif profile.jitter > 0.0:
            gap *= 1.0 + self._rng.uniform(-profile.jitter, profile.jitter)

        if profile.humanize_pauses:
            gap *= self._pause_multiplier(char)

        if difficulty is not None and profile.difficulty_weight > 0.0:
            gap *= 1.0 + _MAX_DIFFICULTY_BONUS * profile.difficulty_weight * difficulty

        if profile.extra_probability > 0.0 and self._rng.random() < profile.extra_probability:
            low, high = _THINK_PAUSE_RANGE
            gap += self._rng.uniform(low, high)

        return max(gap, 0.001)

    def _draw_hold(self, gap: float) -> float:
        """Draw a dwell time for a gap, clamped so a real flight time remains."""
        profile = self.profile
        if not profile.has_dwell:
            return 0.0
        low, high = profile.dwell
        hold = self._rng.uniform(low, high) if high > low else low
        return max(0.0, min(hold, gap * MAX_DWELL_FRACTION))

    def _keystroke(self, char: str, gap: float) -> Keystroke:
        """Turn a gap into a :class:`Keystroke`, carving the dwell out of it."""
        hold = self._draw_hold(gap)
        return Keystroke(char=char, interval=gap, hold=hold, flight=max(0.0, gap - hold))

    @staticmethod
    def _pause_multiplier(char: str) -> float:
        """Return the multiplier applied to the base gap for ``char``."""
        if char == "\n":
            return _PAUSE_NEWLINE
        if char == "\t":
            return _PAUSE_TAB
        if char == " ":
            return _PAUSE_SPACE
        if char in _SENTENCE_END:
            return _PAUSE_SENTENCE
        if char in _CLAUSE_END:
            return _PAUSE_CLAUSE
        return 1.0


    # ------------------------------------------------------------- scheduling
    def keystroke(self, char: str, difficulty: float | None = None) -> Keystroke:
        """Return the randomised keystroke for ``char``.

        Args:
            char: The character that will be typed.
            difficulty: Optional 0-1 difficulty of the word this separator
                precedes; pass the value from
                :func:`autotyper.core.behaviour.pause_difficulties` to correlate
                the pause with word difficulty.

        Returns:
            A :class:`Keystroke` whose ``interval`` already contains ``hold``.
        """
        return self._keystroke(char, self._modulated_gap(char, difficulty))

    def delay_for(self, char: str) -> float:
        """Return the randomised gap (seconds) *after* ``char``.

        Convenience wrapper around :meth:`keystroke` for callers that only care
        about timing; the dwell time is included in the gap, never added to it.
        """
        return self.keystroke(char).interval

    def keystrokes(self, text: str) -> Iterator[Keystroke]:
        """Yield one :class:`Keystroke` per character of ``text``.

        The number of yields equals ``len(text)`` when ``typo_rate`` is zero,
        which keeps progress reporting trivial for the runner. With typos
        enabled the stream is longer, because each slip emits a wrong key, a
        Backspace and the corrected key.
        """
        if self.profile.typo_probability <= 0.0:
            for char, difficulty in zip(text, pause_difficulties(text), strict=True):
                yield self.keystroke(char, difficulty)
            return

        for char, difficulty in zip(text, pause_difficulties(text), strict=True):
            gap = self._modulated_gap(char, difficulty)
            if self._rng.random() < self.profile.typo_probability:
                wrong = self._wrong_key(char)
                if wrong is not None:
                    yield from self._error_loop(gap, wrong, char)
                    continue
            yield self._keystroke(char, gap)

    def _wrong_key(self, char: str) -> str | None:
        """Pick a plausible wrong key for ``char``, or ``None`` if none exists."""
        neighbours = keyboard_neighbours(char)
        if not neighbours:
            return None
        # Bias towards the nearest keys: horizontal slips dominate real errors.
        pool = neighbours[:2]
        return self._rng.choice(pool)

    def _error_loop(self, gap: float, wrong: str, correct: str) -> Iterator[Keystroke]:
        """Model noticing a slip, backspacing over it and retyping correctly.

        The loop is deliberately slower than the typing around it: real typists
        pause to *notice* the error, then correct it in a small burst. Both
        pauses scale with the base gap so the effect stays proportionate at any
        speed.

        Exactly one Backspace is emitted: it removes the single wrong character
        this loop just typed, leaving the preceding correct text untouched.
        """
        base = self.profile.base_gap
        notice = self._rng.uniform(*_TYPO_NOTICE_RANGE) + base
        backspace = max(base * 2.0, self._rng.uniform(*_TYPO_BACKSPACE_GAP))
        retype = max(base * 2.0, self._rng.uniform(*_TYPO_RETYPE_GAP))
        yield self._keystroke(wrong, gap)
        yield self._keystroke(BACKSPACE, notice)
        yield self._keystroke(correct, backspace + retype)

    def delays(self, text: str) -> Iterator[float]:
        """Yield one gap per character of ``text`` (dwell time included)."""
        for stroke in self.keystrokes(text):
            yield stroke.interval

    def expected_gap_for(self, char: str, difficulty: float | None = None) -> float:
        """Return the *mean* gap for ``char`` (no randomness).

        Used by the UI's live time estimate so the number stays stable while the
        user drags sliders. Dwell time never appears here because it is carved
        out of the gap rather than added to it - which is exactly why a user can
        raise the hold time without the estimate changing.
        """
        profile = self.profile
        gap = profile.base_gap
        if profile.humanize_pauses:
            gap *= self._pause_multiplier(char)
        if difficulty is not None and profile.difficulty_weight > 0.0:
            gap *= 1.0 + _MAX_DIFFICULTY_BONUS * profile.difficulty_weight * difficulty
        # Expected value of a uniform pause is its midpoint.
        gap += profile.extra_probability * (sum(_THINK_PAUSE_RANGE) / 2.0)
        return gap

    def expected_delay_for(self, char: str) -> float:
        """Alias for :meth:`expected_gap_for` with no difficulty weighting."""
        return self.expected_gap_for(char)

    def expected_keystrokes_per_char(self) -> float:
        """Mean number of physical keystrokes emitted per payload character.

        A character costs one press. A typo on it costs three extra (the wrong
        key, one Backspace and the correct key), so the mean is
        ``1 + 3 * typo_probability``.
        """
        return 1.0 + 3.0 * self.profile.typo_probability

    def estimate_duration(self, text: str, repeats: int = 1, loop_delay: float = 0.0) -> float:
        """Estimate wall-clock seconds needed to type ``text`` ``repeats`` times.

        Args:
            text: The payload.
            repeats: Number of repetitions; values below 1 are treated as 1.
            loop_delay: Idle seconds inserted *between* repetitions.

        Returns:
            Estimated duration in seconds, including between-loop delays and the
            extra time that typo corrections are expected to add.
        """
        if not text:
            return 0.0
        difficulties = pause_difficulties(text)
        per_pass = math.fsum(
            self.expected_gap_for(char, difficulty)
            for char, difficulty in zip(text, difficulties, strict=True)
        )
        if self.profile.typo_probability > 0.0:
            base = self.profile.base_gap
            correction_cost = (
                self._rng_mid(_TYPO_NOTICE_RANGE)
                + base
                + max(base * 2.0, self._rng_mid(_TYPO_BACKSPACE_GAP))
                + max(base * 2.0, self._rng_mid(_TYPO_RETYPE_GAP))
            )
            per_pass += correction_cost * self.profile.typo_probability * len(text)
        repeats = max(1, repeats)
        return per_pass * repeats + max(0.0, loop_delay) * (repeats - 1)

    @staticmethod
    def _rng_mid(window: tuple[float, float]) -> float:
        """Return the midpoint of a uniform window (the expected draw)."""
        return sum(window) / 2.0

    def estimate_passes_duration(self, text: str) -> float:
        """Estimate the duration of a single repetition."""
        return self.estimate_duration(text, repeats=1)


def format_duration(seconds: float) -> str:
    """Format a duration as a compact human string (``"1m 05s"``, ``"0.8s"``).

    Args:
        seconds: Duration in seconds. Negative values are treated as zero.

    Returns:
        A short label suitable for the status bar or an estimate label.
    """
    total = max(0.0, float(seconds))
    if total < 1.0:
        return f"{total * 1000:.0f} ms"
    if total < 60.0:
        return f"{total:.1f}s"
    minutes, secs = divmod(int(round(total)), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def describe_speed(settings: TypingSettings) -> str:
    """Return a ``"300 WPM · 1500 CPM"`` style summary for labels."""
    normalized = settings.normalized()
    return f"{normalized.wpm} WPM · {normalized.chars_per_minute:.0f} CPM"


def character_breakdown(text: str) -> tuple[int, int, int]:
    """Return ``(characters, words, lines)`` counts used by the editor footer.

    A trailing newline counts as starting a new (empty) line, matching what a
    text editor's line numbers show.
    """
    words = len(text.split())
    lines = text.count("\n") + (1 if text else 0)
    return (len(text), words, lines)
