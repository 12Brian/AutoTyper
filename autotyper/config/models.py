"""Typed settings models shared by the UI and the persistence layer.

All models are plain dataclasses: they validate and clamp incoming values so a
hand-edited or older JSON file can never put the app into an impossible state
(e.g. a zero-speed typing run that would hang).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

#: Hard bounds. The UI sliders use the same values, so keep them in one place.
MIN_WPM = 10
MAX_WPM = 1200
DEFAULT_WPM = 300

MIN_VARIABILITY = 0
MAX_VARIABILITY = 100
DEFAULT_VARIABILITY = 35

MIN_COUNTDOWN = 0.0
MAX_COUNTDOWN = 15.0
DEFAULT_COUNTDOWN = 3.0

MIN_REPEAT = 1
MAX_REPEAT = 999
DEFAULT_REPEAT = 1

MIN_LOOP_DELAY = 0.0
MAX_LOOP_DELAY = 3600.0
DEFAULT_LOOP_DELAY = 2.0

#: How long each key is physically held down (dwell time), in milliseconds.
#:
#: Real dwell time is measurable per keystroke: nobody taps a key for exactly
#: 0 ms, and the distribution is right-skewed - most presses last 60-120 ms with
#: an occasional long one. ``0`` keeps the historical behaviour (a single
#: atomic tap) and is the safe default, because a nonzero hold briefly blocks
#: the target application's event loop for every character.
MIN_DWELL_MS = 0
MAX_DWELL_MS = 200
DEFAULT_DWELL_MIN_MS = 0
DEFAULT_DWELL_MAX_MS = 0

#: Proportion of typable characters that are deliberately mistyped, in percent.
#: Each error is followed by a short "oops" pause, a Backspace, and a retype
#: delay, which is the error-correction loop real typists exhibit.
MIN_TYPO_RATE = 0.0
MAX_TYPO_RATE = 5.0
DEFAULT_TYPO_RATE = 0.0

#: Burstiness of the typing rhythm: how strongly each keystroke's speed carries
#: over to the next one. ``0`` is memoryless (every gap independently jittered,
#: which reads as mechanical); ``100`` produces long fast bursts separated by
#: slower recoveries.
MIN_BURSTINESS = 0
MAX_BURSTINESS = 100
DEFAULT_BURSTINESS = 0

#: How much word difficulty stretches the pause before a hard word, in percent.
MIN_DIFFICULTY_WEIGHT = 0
MAX_DIFFICULTY_WEIGHT = 100
DEFAULT_DIFFICULTY_WEIGHT = 0

#: How to handle indentation on new lines when typing into a code editor.
#:
#: ``"auto"``
#:     Type the newline, then the leading whitespace from the payload. Correct
#:     for plain text fields and terminals, but *doubles* indentation in editors
#:     that auto-indent (Colab, VS Code, most IDEs), because the editor supplies
#:     its own indent and the payload's indent is added on top.
#: ``"strip"``
#:     After the newline, press Home then Delete to remove whatever the editor
#:     auto-inserted, then type the payload's own indentation. Produces exactly
#:     one indent level - the one from your text - regardless of the editor.
INDENT_MODES = ("auto", "strip")
DEFAULT_INDENT_MODE = "auto"

VALID_THEMES = ("system", "light", "dark")


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return max(low, min(high, value))


def _as_float(value: Any, fallback: float) -> float:
    """Best-effort numeric coercion that never raises."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float("inf"), float("-inf")):  # NaN/inf guard
        return fallback
    return number


def _as_int(value: Any, fallback: int) -> int:
    """Best-effort integer coercion that never raises."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any, fallback: bool) -> bool:
    """Tolerant truthiness coercion for JSON values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


@dataclass(slots=True)
class TypingSettings:
    """Everything that shapes how a run types.

    Attributes:
        wpm: Target typing speed in words per minute. One "word" is five
            characters, the standard typing-test convention.
        variability: 0-100 "human-like" randomness. 0 disables jitter and
            pauses entirely (metronomic typing); 100 is the most irregular.
        countdown: Seconds to wait after Start before the first keystroke.
        repeat_count: How many times to type the text.
        loop_forever: When true, ignore ``repeat_count`` and loop until stopped.
        loop_delay: Pause in seconds between repetitions.
        humanize_pauses: Insert slightly longer breaks at spaces and sentence
            punctuation, which helps slow form fields keep up.
        dwell_min_ms / dwell_max_ms: How long each key is physically held, in
            milliseconds. ``0`` for both keeps the instant-tap behaviour; a
            range such as ``40``-``90`` produces a measurable, varying hold
            time per keystroke.
        typo_rate: Percentage of characters to deliberately mistype and then
            correct (backspace and retype), imitating human error-correction.
        burstiness: How strongly consecutive keystrokes share a speed
            (0 = memoryless jitter, 100 = long fast bursts).
        difficulty_weight: How much the pause before a hard word is stretched
            (0 = uniform, 100 = pauses track word difficulty strongly).
    """

    wpm: int = DEFAULT_WPM
    variability: int = DEFAULT_VARIABILITY
    countdown: float = DEFAULT_COUNTDOWN
    repeat_count: int = DEFAULT_REPEAT
    loop_forever: bool = False
    loop_delay: float = DEFAULT_LOOP_DELAY
    humanize_pauses: bool = True
    indent_mode: str = DEFAULT_INDENT_MODE
    dwell_min_ms: int = DEFAULT_DWELL_MIN_MS
    dwell_max_ms: int = DEFAULT_DWELL_MAX_MS
    typo_rate: float = DEFAULT_TYPO_RATE
    burstiness: int = DEFAULT_BURSTINESS
    difficulty_weight: int = DEFAULT_DIFFICULTY_WEIGHT

    def normalized(self) -> TypingSettings:
        """Return a copy with every field coerced and clamped into range."""
        dwell_min = int(
            _clamp(_as_int(self.dwell_min_ms, DEFAULT_DWELL_MIN_MS), MIN_DWELL_MS, MAX_DWELL_MS)
        )
        dwell_max = int(
            _clamp(_as_int(self.dwell_max_ms, DEFAULT_DWELL_MAX_MS), MIN_DWELL_MS, MAX_DWELL_MS)
        )
        if dwell_max < dwell_min:
            # A reversed range would make uniform() raise; swap instead of
            # silently discarding the user's intent.
            dwell_min, dwell_max = dwell_max, dwell_min

        return replace(
            self,
            wpm=int(_clamp(_as_int(self.wpm, DEFAULT_WPM), MIN_WPM, MAX_WPM)),
            variability=int(
                _clamp(
                    _as_int(self.variability, DEFAULT_VARIABILITY),
                    MIN_VARIABILITY,
                    MAX_VARIABILITY,
                )
            ),
            countdown=round(
                _clamp(_as_float(self.countdown, DEFAULT_COUNTDOWN), MIN_COUNTDOWN, MAX_COUNTDOWN),
                2,
            ),
            repeat_count=int(
                _clamp(_as_int(self.repeat_count, DEFAULT_REPEAT), MIN_REPEAT, MAX_REPEAT)
            ),
            loop_forever=bool(self.loop_forever),
            loop_delay=round(
                _clamp(
                    _as_float(self.loop_delay, DEFAULT_LOOP_DELAY),
                    MIN_LOOP_DELAY,
                    MAX_LOOP_DELAY,
                ),
                2,
            ),
            humanize_pauses=bool(self.humanize_pauses),
            indent_mode=(
                self.indent_mode if self.indent_mode in INDENT_MODES else DEFAULT_INDENT_MODE
            ),
            dwell_min_ms=dwell_min,
            dwell_max_ms=dwell_max,
            typo_rate=round(
                _clamp(_as_float(self.typo_rate, DEFAULT_TYPO_RATE), MIN_TYPO_RATE, MAX_TYPO_RATE),
                2,
            ),
            burstiness=int(
                _clamp(
                    _as_int(self.burstiness, DEFAULT_BURSTINESS),
                    MIN_BURSTINESS,
                    MAX_BURSTINESS,
                )
            ),
            difficulty_weight=int(
                _clamp(
                    _as_int(self.difficulty_weight, DEFAULT_DIFFICULTY_WEIGHT),
                    MIN_DIFFICULTY_WEIGHT,
                    MAX_DIFFICULTY_WEIGHT,
                )
            ),
        )

    @property
    def chars_per_minute(self) -> float:
        """Typing speed expressed in characters per minute."""
        return self.wpm * 5.0

    @property
    def dwell_seconds(self) -> tuple[float, float]:
        """Return the dwell-time window as ``(low, high)`` seconds.

        Timing code works in seconds throughout, so this converts the stored
        millisecond window once instead of at every keystroke.
        """
        return (self.dwell_min_ms / 1000.0, self.dwell_max_ms / 1000.0)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible mapping."""
        return {
            "wpm": self.wpm,
            "variability": self.variability,
            "countdown": self.countdown,
            "repeat_count": self.repeat_count,
            "loop_forever": self.loop_forever,
            "loop_delay": self.loop_delay,
            "humanize_pauses": self.humanize_pauses,
            "indent_mode": self.indent_mode,
            "dwell_min_ms": self.dwell_min_ms,
            "dwell_max_ms": self.dwell_max_ms,
            "typo_rate": self.typo_rate,
            "burstiness": self.burstiness,
            "difficulty_weight": self.difficulty_weight,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> TypingSettings:
        """Build a normalized instance from untyped JSON data."""
        source = data or {}
        defaults = cls()
        return cls(
            wpm=_as_int(source.get("wpm"), defaults.wpm),
            variability=_as_int(source.get("variability"), defaults.variability),
            countdown=_as_float(source.get("countdown"), defaults.countdown),
            repeat_count=_as_int(source.get("repeat_count"), defaults.repeat_count),
            loop_forever=_as_bool(source.get("loop_forever"), defaults.loop_forever),
            loop_delay=_as_float(source.get("loop_delay"), defaults.loop_delay),
            humanize_pauses=_as_bool(source.get("humanize_pauses"), defaults.humanize_pauses),
            indent_mode=str(source.get("indent_mode") or defaults.indent_mode),
            dwell_min_ms=_as_int(source.get("dwell_min_ms"), defaults.dwell_min_ms),
            dwell_max_ms=_as_int(source.get("dwell_max_ms"), defaults.dwell_max_ms),
            typo_rate=_as_float(source.get("typo_rate"), defaults.typo_rate),
            burstiness=_as_int(source.get("burstiness"), defaults.burstiness),
            difficulty_weight=_as_int(
                source.get("difficulty_weight"), defaults.difficulty_weight
            ),
        ).normalized()


#: Default bindings.
#:
#: These deliberately use function keys rather than letter combinations. A
#: ``Ctrl+Alt+T``-style trigger can leak its letter into the target window when
#: the hotkey is swallowed imperfectly, and a leaked ``Ctrl+T`` opens a new tab
#: in browsers and Notepad - silently destroying the text being typed. Function
#: keys have no such shortcut meaning, so a leak is harmless.
DEFAULT_HOTKEYS: dict[str, str] = {
    "start": "f8",
    "pause": "f7",
    "stop": "f9",
}


@dataclass(slots=True)
class HotkeySettings:
    """Global hotkey bindings, stored as canonical ``ctrl+alt+t`` strings.

    An empty string disables a binding. Validation of the actual key names is
    performed by :mod:`autotyper.core.hotkeys`; this model only stores text so
    it stays importable without pynput.
    """

    start: str = DEFAULT_HOTKEYS["start"]
    pause: str = DEFAULT_HOTKEYS["pause"]
    stop: str = DEFAULT_HOTKEYS["stop"]

    def normalized(self) -> HotkeySettings:
        """Return a copy with whitespace-stripped, lower-case bindings."""
        return HotkeySettings(
            start=self.start.strip().lower(),
            pause=self.pause.strip().lower(),
            stop=self.stop.strip().lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible mapping."""
        return {"start": self.start, "pause": self.pause, "stop": self.stop}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> HotkeySettings:
        """Build a normalized instance from untyped JSON data."""
        source = data or {}
        defaults = cls()
        return cls(
            start=str(source.get("start", defaults.start) or ""),
            pause=str(source.get("pause", defaults.pause) or ""),
            stop=str(source.get("stop", defaults.stop) or ""),
        ).normalized()


@dataclass(slots=True)
class AppSettings:
    """Application-wide settings persisted to ``settings.json``.

    Attributes:
        theme: One of ``"system"``, ``"light"`` or ``"dark"``.
        typing: Defaults applied when no profile is selected.
        hotkeys: Global hotkey bindings.
        active_profile_id: Last used profile, restored on launch.
        geometry: Base64 window geometry blob produced by Qt.
    """

    theme: str = "system"
    typing: TypingSettings = field(default_factory=TypingSettings)
    hotkeys: HotkeySettings = field(default_factory=HotkeySettings)
    active_profile_id: str | None = None
    geometry: str | None = None

    def normalized(self) -> AppSettings:
        """Return a copy with every nested model clamped/validated."""
        theme = self.theme if self.theme in VALID_THEMES else "system"
        return AppSettings(
            theme=theme,
            typing=self.typing.normalized(),
            hotkeys=self.hotkeys.normalized(),
            active_profile_id=self.active_profile_id or None,
            geometry=self.geometry or None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible mapping."""
        return {
            "version": 1,
            "theme": self.theme,
            "typing": self.typing.to_dict(),
            "hotkeys": self.hotkeys.to_dict(),
            "active_profile_id": self.active_profile_id,
            "geometry": self.geometry,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> AppSettings:
        """Build a normalized instance from untyped JSON data."""
        source = data or {}
        return cls(
            theme=str(source.get("theme") or "system"),
            typing=TypingSettings.from_dict(source.get("typing")),
            hotkeys=HotkeySettings.from_dict(source.get("hotkeys")),
            active_profile_id=(
                str(source["active_profile_id"]) if source.get("active_profile_id") else None
            ),
            geometry=str(source["geometry"]) if source.get("geometry") else None,
        ).normalized()
