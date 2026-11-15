"""Tests for the typing run loop: ordering, repeats, pause and instant stop."""

from __future__ import annotations

import threading
import time

from autotyper.config.models import TypingSettings
from autotyper.core.keyboard import NullKeyboard
from autotyper.core.runner import RunCallbacks, RunResult, RunState, TypingRunner


def fast_settings(**overrides: object) -> TypingSettings:
    """Settings tuned for quick tests: max speed, no jitter, no countdown."""
    values: dict[str, object] = {
        "wpm": 1200,
        "variability": 0,
        "countdown": 0,
        "humanize_pauses": False,
    }
    values.update(overrides)
    return TypingSettings(**values)  # type: ignore[arg-type]


def test_runner_types_exactly_the_payload() -> None:
    """Every character, including newlines and tabs, is emitted once."""
    sink = NullKeyboard()
    text = "Hello, world!\n\tIndented line — with ünïcödé ✓"

    result = TypingRunner(text, fast_settings(), sink).run()

    assert isinstance(result, RunResult)
    assert "".join(sink.typed) == text
    assert result.completed is True
    assert result.stopped is False
    assert result.typed_chars == len(text)
    assert result.passes_completed == 1
    assert result.error is None


def test_empty_payload_completes_without_touching_the_keyboard() -> None:
    """An empty payload completes immediately rather than hanging."""
    sink = NullKeyboard()
    result = TypingRunner("", fast_settings(), sink).run()

    assert result.completed is True
    assert result.typed_chars == 0
    assert sink.typed == []


def test_repeat_count_types_the_payload_n_times() -> None:
    """Repeats produce n concatenated copies."""
    sink = NullKeyboard()
    settings = fast_settings(repeat_count=3, loop_delay=0.0)

    result = TypingRunner("ab", settings, sink).run()

    assert "".join(sink.typed) == "ababab"
    assert result.passes_completed == 3
    assert result.typed_chars == 6


def test_stop_is_effective_within_a_sleep_slice() -> None:
    """A panic stop must interrupt mid-text, not after the current pass."""
    sink = NullKeyboard()
    settings = fast_settings(wpm=60, humanize_pauses=False)  # 0.2 s per character
    runner = TypingRunner("abcdefghijklmnopqrstuvwxyz", settings, sink)

    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3.0
    while len(sink.typed) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)

    started = time.monotonic()
    runner.request_stop()
    thread.join(2.0)
    elapsed = time.monotonic() - started

    assert not thread.is_alive(), "runner thread did not exit after stop"
    assert elapsed < 0.5, f"stop took {elapsed:.3f}s"
    assert len(sink.typed) < 26, "stop did not interrupt mid-text"



def test_pause_holds_and_resume_continues() -> None:
    """While paused no characters are emitted; resuming finishes the text."""
    sink = NullKeyboard()
    settings = fast_settings(wpm=60, humanize_pauses=False)
    runner = TypingRunner("abcdefgh", settings, sink)

    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3.0
    while len(sink.typed) < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert runner.request_pause() is True
    time.sleep(0.3)
    frozen = len(sink.typed)
    time.sleep(0.3)
    assert len(sink.typed) == frozen, "characters were typed while paused"
    assert runner.state is RunState.PAUSED

    assert runner.request_resume() is True
    thread.join(5.0)
    assert "".join(sink.typed) == "abcdefgh"


def test_pause_and_resume_are_no_ops_when_not_applicable() -> None:
    """Mis-ordered hotkeys must not corrupt the state machine."""
    runner = TypingRunner("abc", fast_settings(), NullKeyboard())

    assert runner.request_pause() is False  # not started yet
    assert runner.request_resume() is False  # nothing to resume
    assert runner.request_stop() is None  # safe no-op before starting


def test_stop_during_countdown_aborts_before_typing() -> None:
    """The panic key must work during the countdown too."""
    sink = NullKeyboard()
    runner = TypingRunner("abc", fast_settings(countdown=5.0), sink)

    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 2.0
    while runner.state is not RunState.COUNTDOWN and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runner.state is RunState.COUNTDOWN

    runner.request_stop()
    thread.join(2.0)

    assert not thread.is_alive()
    assert sink.typed == []


def test_countdown_reports_remaining_seconds() -> None:
    """The UI shows a live countdown, so ticks must reach zero."""
    ticks: list[float] = []
    callbacks = RunCallbacks(on_countdown=ticks.append)
    TypingRunner("a", fast_settings(countdown=0.4), NullKeyboard(), callbacks).run()

    assert ticks, "no countdown ticks were reported"
    assert max(ticks) <= 0.4
    assert min(ticks) <= 0.0
    assert ticks == sorted(ticks, reverse=True)


def test_state_transitions_are_reported_in_order() -> None:
    """The UI pill depends on an ordered typing → completed sequence."""
    states: list[RunState] = []
    TypingRunner(
        "ab", fast_settings(), NullKeyboard(), RunCallbacks(on_state=states.append)
    ).run()

    assert states == [RunState.TYPING, RunState.COMPLETED]


def test_progress_snapshots_are_monotonic() -> None:
    """Progress must never move backwards, including across repeats."""
    seen: list[int] = []
    TypingRunner(
        "abc",
        fast_settings(repeat_count=2),
        NullKeyboard(),
        RunCallbacks(on_progress=lambda progress: seen.append(progress.typed_chars)),
    ).run()

    assert seen == sorted(seen)
    assert seen[-1] == 6


def test_progress_reports_totals_and_fraction() -> None:
    """The progress bar needs a total plus a 0..1 fraction."""
    snapshots: list[object] = []
    TypingRunner(
        "abcd",
        fast_settings(repeat_count=2),
        NullKeyboard(),
        RunCallbacks(on_progress=snapshots.append),
    ).run()

    last = snapshots[-1]
    assert last.total_chars == 8  # type: ignore[attr-defined]
    assert last.typed_chars == 8  # type: ignore[attr-defined]
    assert last.fraction == 1.0  # type: ignore[attr-defined]


def test_infinite_loop_reports_no_total() -> None:
    """Looping forever must not claim a percentage."""
    seen: list[object] = []
    runner = TypingRunner(
        "ab",
        fast_settings(loop_forever=True, loop_delay=0.0),
        NullKeyboard(),
        RunCallbacks(on_progress=seen.append),
    )

    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    time.sleep(0.3)
    runner.request_stop()
    thread.join(2.0)

    assert seen
    assert seen[0].total_chars is None  # type: ignore[attr-defined]
    assert seen[0].fraction == 0.0  # type: ignore[attr-defined]


def test_failed_keyboard_is_reported_not_raised() -> None:
    """A backend that raises must produce an error result, not a crash."""

    class BrokenKeyboard(NullKeyboard):
        """Sink that fails after the first character."""

        def type_character(self, char: str) -> None:  # noqa: D102
            if self.typed:
                raise OSError("simulated backend failure")
            super().type_character(char)

    result = TypingRunner("abcde", fast_settings(), BrokenKeyboard()).run()

    assert result.completed is False
    assert result.error is not None
    assert "simulated backend failure" in result.error



# ----------------------------------------------------------------- settle/guard
class _SettleRecordingKeyboard(NullKeyboard):
    """Sink that records the order of lifecycle calls."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def settle(self) -> None:  # noqa: D102
        self.events.append("settle")

    def type_character(self, char: str) -> None:  # noqa: D102
        self.events.append(f"type:{char}")
        super().type_character(char)


def test_settle_runs_before_the_first_character() -> None:
    """Modifier residue must be cleared before any payload is sent.

    This is the regression guard for the reported bug: when ``settle()`` ran
    before the countdown (or not at all), a still-held Ctrl made the target
    application treat typed letters as shortcuts and silently drop the text.
    """
    sink = _SettleRecordingKeyboard()
    TypingRunner("abc", fast_settings(), sink).run()

    assert sink.events[0] == "settle", "settle() must be the first keyboard action"
    assert sink.events.count("settle") == 1
    assert sink.events[1:] == ["type:a", "type:b", "type:c"]


def test_settle_runs_after_the_countdown() -> None:
    """Settle must happen as late as possible, i.e. after the countdown."""
    events: list[str] = []

    class Recording(NullKeyboard):
        def settle(self) -> None:  # noqa: D102
            events.append("settle")

        def type_character(self, char: str) -> None:  # noqa: D102
            events.append("type")

    callbacks = RunCallbacks(on_countdown=lambda remaining: events.append("tick"))
    TypingRunner(
        "a", fast_settings(countdown=0.25), Recording(), callbacks
    ).run()

    assert "tick" in events, "countdown never ran"
    first_tick = events.index("tick")
    settle_index = events.index("settle")
    assert settle_index > first_tick, "settle() must not run before the countdown"
    assert settle_index < events.index("type"), "settle() must precede typing"


def test_settle_is_not_called_for_empty_payloads() -> None:
    """Nothing to type means nothing to settle (and no keystroke side effects)."""
    sink = _SettleRecordingKeyboard()
    TypingRunner("", fast_settings(), sink).run()

    assert "settle" not in sink.events


def test_stop_during_countdown_skips_settle() -> None:
    """An aborted countdown must not touch the keyboard at all."""
    sink = _SettleRecordingKeyboard()
    runner = TypingRunner("abc", fast_settings(countdown=5.0), sink)

    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 2.0
    while runner.state is not RunState.COUNTDOWN and time.monotonic() < deadline:
        time.sleep(0.01)

    runner.request_stop()
    thread.join(2.0)

    assert sink.events == []


def test_result_reports_skipped_characters() -> None:
    """Unsupported glyphs are counted so the UI can warn the user."""

    class SkippingKeyboard(NullKeyboard):
        """Sink that records a skip instead of typing the letter 'b'."""

        def __init__(self) -> None:
            super().__init__()
            self.skipped = 0

        def type_character(self, char: str) -> None:  # noqa: D102
            if char == "b":
                self.skipped += 1
                return
            super().type_character(char)

    sink = SkippingKeyboard()
    result = TypingRunner("abc", fast_settings(), sink).run()

    assert result.skipped == 1
    assert "".join(sink.typed) == "ac"
