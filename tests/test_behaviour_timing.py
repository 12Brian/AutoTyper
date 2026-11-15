"""Tests for dwell time and the human-behaviour timing models.

These live apart from ``test_timing.py`` because they cover the *upgraded*
engine: randomised key holds, burstiness, word-difficulty pauses and typo
error-correction loops. Determinism still comes from an injected RNG.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import replace

import pytest
from autotyper.config.models import TypingSettings
from autotyper.core.keyboard import NullKeyboard
from autotyper.core.runner import TypingRunner
from autotyper.core.timing import BACKSPACE, MAX_DWELL_FRACTION, TimingEngine


def engine(**overrides: object) -> TimingEngine:
    """Build a deterministic engine with sensible test defaults."""
    values: dict[str, object] = {"wpm": 300, "variability": 0, "humanize_pauses": False}
    values.update(overrides)
    return TimingEngine(TypingSettings(**values), random.Random(1234))  # type: ignore[arg-type]


def fast(**overrides: object) -> TypingSettings:
    """Settings tuned for quick runner tests."""
    values: dict[str, object] = {
        "wpm": 1200,
        "variability": 0,
        "countdown": 0,
        "humanize_pauses": False,
    }
    values.update(overrides)
    return TypingSettings(**values)  # type: ignore[arg-type]


# ------------------------------------------------------------------ dwell time
def test_dwell_is_off_by_default() -> None:
    """The historical behaviour is preserved: zero holds, atomic taps."""
    strokes = list(engine().keystrokes("abcdef"))
    assert all(stroke.hold == 0.0 for stroke in strokes)
    assert all(stroke.flight == stroke.interval for stroke in strokes)
    assert engine().profile.has_dwell is False


def test_dwell_is_drawn_from_the_configured_window() -> None:
    """Holds vary per keystroke inside the requested range (before clamping)."""
    eng = engine(dwell_min_ms=20, dwell_max_ms=60)
    holds = [stroke.hold for stroke in eng.keystrokes("abcdefghij" * 20)]
    assert all(0.0 < hold <= 0.060 for hold in holds)
    assert len({round(hold, 6) for hold in holds}) > 5, "holds must vary per keystroke"


def test_dwell_never_exceeds_the_gap_it_belongs_to() -> None:
    """A hold is clamped to a fraction of the gap, so flight time stays real."""
    eng = engine(
        wpm=300, variability=100, humanize_pauses=True, dwell_min_ms=200, dwell_max_ms=200
    )
    for stroke in eng.keystrokes("hello world, again.\n"):
        assert stroke.hold <= stroke.interval * MAX_DWELL_FRACTION + 1e-9
        assert stroke.flight >= 0.0


def test_flight_plus_hold_equals_interval() -> None:
    """The dwell is carved out of the gap, not added to it."""
    eng = engine(dwell_min_ms=30, dwell_max_ms=90)
    for stroke in eng.keystrokes("abcdefghij"):
        assert stroke.flight + stroke.hold == pytest.approx(stroke.interval)


def test_dwell_does_not_change_measured_speed() -> None:
    """Keydown-to-keydown timing - and therefore WPM - is unaffected."""
    plain = engine()
    held = engine(dwell_min_ms=40, dwell_max_ms=90)
    assert plain.profile.base_gap == pytest.approx(held.profile.base_gap)
    assert list(plain.delays("abcde")) == pytest.approx(list(held.delays("abcde")))


def test_dwell_does_not_change_the_time_estimate() -> None:
    """The UI estimate must not jump when only the hold time changes."""
    text = "The quick brown fox jumps over the lazy dog."
    plain = engine().estimate_duration(text, repeats=2, loop_delay=1.0)
    held = engine(dwell_min_ms=50, dwell_max_ms=120).estimate_duration(
        text, repeats=2, loop_delay=1.0
    )
    assert plain == pytest.approx(held)


def test_reversed_dwell_window_is_swapped_not_rejected() -> None:
    """A hand-edited or dragged-to-front window still runs."""
    settings = TypingSettings(dwell_min_ms=90, dwell_max_ms=30).normalized()
    assert (settings.dwell_min_ms, settings.dwell_max_ms) == (30, 90)


def test_equal_dwell_bounds_produce_a_constant_hold() -> None:
    """A zero-width window is legal and yields exactly one hold value."""
    holds = {
        round(stroke.hold, 6)
        for stroke in engine(dwell_min_ms=50, dwell_max_ms=50).keystrokes("abc")
    }
    assert len(holds) == 1


# ---------------------------------------------------------------- burstiness
def _lag1_autocorrelation(values: list[float]) -> float:
    """Pearson correlation between each gap and the one before it."""
    mean = statistics.mean(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator == 0.0:
        return 0.0
    numerator = sum(
        (values[i] - mean) * (values[i + 1] - mean) for i in range(len(values) - 1)
    )
    return numerator / denominator


def test_burstiness_makes_neighbouring_gaps_correlated() -> None:
    """This is the core property: bursts of similar speed, not white noise."""
    text = "abcdefghij" * 80
    plain = TimingEngine(TypingSettings(wpm=300, variability=60), random.Random(7))
    bursty = TimingEngine(
        TypingSettings(wpm=300, variability=60, burstiness=95), random.Random(7)
    )
    # Remove independent thinking pauses so only the cadence remains.
    plain.profile = replace(plain.profile, extra_probability=0.0)
    bursty.profile = replace(bursty.profile, extra_probability=0.0)

    plain_rho = _lag1_autocorrelation(list(plain.delays(text)))
    bursty_rho = _lag1_autocorrelation(list(bursty.delays(text)))

    assert abs(plain_rho) < 0.15, "plain jitter should be memoryless"
    assert bursty_rho > 0.4, "bursty typing must autocorrelate strongly"


def test_burstiness_preserves_the_overall_speed_and_spread() -> None:
    """Variance is redistributed into bursts, not inflated or flattened."""
    text = "abcdefghij" * 80
    plain = list(
        TimingEngine(TypingSettings(wpm=300, variability=60), random.Random(3)).delays(text)
    )
    bursty = list(
        TimingEngine(
            TypingSettings(wpm=300, variability=60, burstiness=90), random.Random(3)
        ).delays(text)
    )
    assert statistics.mean(plain) == pytest.approx(statistics.mean(bursty), rel=0.15)
    assert statistics.stdev(bursty) > statistics.stdev(plain) * 0.5


def test_burstiness_zero_is_memoryless() -> None:
    """Burstiness 0 must not silently change the classic engine."""
    assert engine().profile.mood_carry == 0.0
    assert engine(burstiness=0).profile.mood_strength == 0.0
    assert engine().profile.bursty is False


# ------------------------------------------------------- difficulty weighting
def test_hard_words_stretch_the_pause_before_them() -> None:
    """A maximal difficulty score lengthens the separator's gap."""
    eng = engine(difficulty_weight=100)
    easy = eng.keystroke(" ", 0.0).interval
    hard = eng.keystroke(" ", 1.0).interval
    assert hard > easy * 2


def test_difficulty_weight_zero_ignores_the_score() -> None:
    """With the weight at 0 the difficulty argument changes nothing."""
    eng = engine(difficulty_weight=0)
    assert eng.keystroke(" ", 0.0).interval == pytest.approx(
        eng.keystroke(" ", 1.0).interval
    )


def test_difficulty_pauses_land_before_long_words() -> None:
    """The separator before a long word gets the longest gap in the stream."""
    text = "go extraordinary"
    eng = engine(difficulty_weight=100, humanize_pauses=True)
    gaps = [stroke.interval for stroke in eng.keystrokes(text)]
    assert gaps[2] == max(gaps), "the pause before the long word must dominate"


def test_difficulty_weight_lengthens_the_estimate() -> None:
    """The UI estimate must reflect the extra pauses."""
    text = "antidisestablishmentarianism is a word"
    plain = engine(difficulty_weight=0).estimate_duration(text)
    weighted = engine(difficulty_weight=100).estimate_duration(text)
    assert weighted > plain


# ------------------------------------------------------- typos and corrections
def test_typos_are_off_by_default() -> None:
    """No behaviour change unless explicitly enabled."""
    assert engine().profile.typo_probability == 0.0
    text = "hello"
    assert len(list(engine().keystrokes(text))) == len(text)


def test_a_correction_loop_is_wrong_key_backspace_correct_key() -> None:
    """Each slip must be repaired with exactly one Backspace."""
    eng = engine(typo_rate=5)
    stream = list(eng.keystrokes("the quick brown fox jumps over the lazy dog" * 3))
    backspace_indices = [i for i, stroke in enumerate(stream) if stroke.char == BACKSPACE]
    assert backspace_indices, "no typos were generated"
    for index in backspace_indices:
        wrong = stream[index - 1].char
        correct = stream[index + 1].char
        assert wrong != correct
        assert correct.isalpha() or correct.isdigit()


def test_the_final_text_is_exact_despite_typos() -> None:
    """Replaying the stream with backspaces must reproduce the payload."""
    text = "The quick brown fox jumps over the lazy dog. Extraordinary!"
    sink = NullKeyboard()
    # Seeded: this test asserts that typos *occur*, so an unseeded run would
    # flake on the rare sample with no slips at all.
    runner = TypingRunner(text, fast(typo_rate=5), sink, rng=random.Random(424242))
    result = runner.run()

    reconstructed: list[str] = []
    for char in sink.typed:
        if char == "\b":
            reconstructed.pop()
        else:
            reconstructed.append(char)

    assert "".join(reconstructed) == text
    assert result.completed is True
    assert result.typos == sink.backspaces
    assert result.typos > 0


def test_typo_corrections_do_not_inflate_the_progress_counter() -> None:
    """The character budget must still match the payload length."""
    text = "abcdefghij" * 5
    sink = NullKeyboard()
    result = TypingRunner(text, fast(typo_rate=5), sink).run()
    assert result.typed_chars == len(text)


def test_typos_are_never_attempted_on_whitespace() -> None:
    """A space has no neighbouring key, so it is typed verbatim."""
    stream = list(engine(typo_rate=5).keystrokes("     " * 40))
    assert all(stroke.char == " " for stroke in stream)


def test_typo_rate_lengthens_the_estimate() -> None:
    """Corrections cost time, so the estimate must grow with the error rate."""
    text = "a reasonably long sentence to type out"
    plain = engine(typo_rate=0).estimate_duration(text)
    typo = engine(typo_rate=5).estimate_duration(text)
    assert typo > plain


@pytest.mark.parametrize("rate", [0.0, 1.0, 2.5, 5.0])
def test_typo_rate_is_clamped_and_never_negative(rate: float) -> None:
    """The model accepts the documented range and rejects nonsense."""
    settings = TypingSettings(typo_rate=rate).normalized()
    assert 0.0 <= settings.typo_rate <= 5.0
    assert TypingSettings(typo_rate=-4).normalized().typo_rate == 0.0


# ------------------------------------------------- runner: dwell choreography
def test_runner_presses_and_releases_every_key() -> None:
    """With dwell enabled each character is a matched press/release pair."""
    sink = NullKeyboard()
    result = TypingRunner("abcde", fast(dwell_min_ms=5, dwell_max_ms=15), sink).run()

    assert result.completed is True
    assert sink.pressed == ["a", "b", "c", "d", "e"]
    assert sink.pressed == sink.released
    assert "".join(sink.typed) == "abcde"


def test_runner_taps_atomically_without_dwell() -> None:
    """Dwell 0 keeps using the single-call tap path (no press/release pair)."""
    sink = NullKeyboard()
    TypingRunner("abc", fast(), sink).run()

    assert sink.pressed == []
    assert sink.released == []
    assert "".join(sink.typed) == "abc"


def test_stop_during_a_hold_releases_the_key() -> None:
    """A panic stop mid-hold must never leave a key stuck down.

    This is the safety property that makes dwell time viable: the underlying
    sleep is the same interruptible one used everywhere else, and the release is
    issued from a ``finally`` block.
    """
    import threading
    import time

    sink = NullKeyboard()
    runner = TypingRunner(
        "abcdefghijklmnopqrstuvwxyz",
        fast(wpm=60, countdown=0, dwell_min_ms=100, dwell_max_ms=100),
        sink,
    )

    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3.0
    while not sink.pressed and time.monotonic() < deadline:
        time.sleep(0.01)

    runner.request_stop()
    thread.join(2.0)

    assert not thread.is_alive(), "runner thread did not exit after stop"
    assert len(sink.pressed) == len(sink.released), "a key was left stuck down"
    assert len(sink.typed) < 26, "stop did not interrupt mid-text"


def test_dwell_holds_do_not_change_the_emitted_text() -> None:
    """Payload fidelity is independent of the hold time."""
    text = "Line one\n\tLine two — with ünïcödé ✓\n"
    plain_sink, held_sink = NullKeyboard(), NullKeyboard()
    TypingRunner(text, fast(), plain_sink).run()
    TypingRunner(text, fast(dwell_min_ms=5, dwell_max_ms=20), held_sink).run()

    assert "".join(plain_sink.typed) == "".join(held_sink.typed) == text


def test_dwell_respects_strip_indent_mode() -> None:
    """Indent stripping still runs after newlines when keys are held."""
    from tests.test_indentation import AutoIndentEditor

    editor = AutoIndentEditor()
    TypingRunner(
        "def f():\n    return 1\n",
        fast(indent_mode="strip", dwell_min_ms=2, dwell_max_ms=6),
        editor,
    ).run()

    assert editor.text() == "def f():\n    return 1\n"
    assert editor.strips == 2, "one strip per newline"


def test_legacy_sink_without_hold_support_still_types_everything() -> None:
    """A sink predating dwell time must not silently drop characters."""

    class LegacySink:
        """Only the original three-method sink interface."""

        def __init__(self) -> None:
            self.typed: list[str] = []

        def type_character(self, char: str) -> None:
            self.typed.append(char)

        def release_modifiers(self) -> None:
            return None

        def flush(self) -> None:
            return None

        def strip_line_indent(self) -> None:
            return None

        def settle(self) -> None:
            return None

    sink = LegacySink()
    result = TypingRunner("abc", fast(dwell_min_ms=5, dwell_max_ms=10), sink).run()

    assert "".join(sink.typed) == "abc"
    assert result.completed is True


def test_legacy_sink_without_backspace_helper_still_corrects() -> None:
    """Corrections fall back to typing ``\\b`` when no helper exists."""

    class LegacySink:
        def __init__(self) -> None:
            self.typed: list[str] = []

        def type_character(self, char: str) -> None:
            self.typed.append(char)

        def release_modifiers(self) -> None:
            return None

        def flush(self) -> None:
            return None

        def strip_line_indent(self) -> None:
            return None

        def settle(self) -> None:
            return None

    sink = LegacySink()
    # Seeded so the run always contains at least one slip: 30 characters at a
    # 5 % rate could otherwise legitimately produce zero typos.
    runner = TypingRunner(
        "abcdefghij" * 3, fast(typo_rate=5), sink, rng=random.Random(20241114)
    )
    result = runner.run()

    reconstructed: list[str] = []
    for char in sink.typed:
        if char == "\b":
            reconstructed.pop()
        else:
            reconstructed.append(char)

    assert "".join(reconstructed) == "abcdefghij" * 3
    assert result.typos > 0

