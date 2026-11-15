"""The typing run loop.

``TypingRunner`` is pure Python: it owns the state machine (countdown →
typing → paused/completed/stopped), the repeat/loop logic and the interruptible
sleeping, but knows nothing about Qt. The UI drives it from a worker thread via
:meth:`TypingRunner.request_pause`, :meth:`~TypingRunner.request_resume` and
:meth:`~TypingRunner.request_stop`, all of which are plain ``threading.Event``
operations so they take effect within one 20 ms sleep slice.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from ..config.models import TypingSettings
from .keyboard import KeyboardSink
from .timing import BACKSPACE, Keystroke, TimingEngine

LOGGER = logging.getLogger(__name__)

#: Slice length used while sleeping so stop/pause feel instantaneous.
SLEEP_SLICE = 0.02

#: Characters that may be deleted by an error-correction loop. A correction
#: only ever follows a character we typed ourselves in this run.
_CORRECTABLE = frozenset("\b\x7f")

#: The sentinel the timing engine uses for "press Backspace".
BACKSPACE_SENTINEL = BACKSPACE


class RunState(str, Enum):
    """Lifecycle states reported to the UI.

    ``str`` is mixed in so states compare equal to their string values (handy in
    logs and tests) and can cross the Qt signal boundary unchanged.
    """

    IDLE = "idle"
    COUNTDOWN = "countdown"
    TYPING = "typing"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"

    @property
    def label(self) -> str:
        """Human-readable label for the status bar."""
        return {
            RunState.IDLE: "Idle",
            RunState.COUNTDOWN: "Counting down",
            RunState.TYPING: "Typing",
            RunState.PAUSED: "Paused",
            RunState.STOPPED: "Stopped",
            RunState.COMPLETED: "Completed",
            RunState.ERROR: "Error",
        }[self]


@dataclass(frozen=True, slots=True)
class RunProgress:
    """Immutable snapshot of run progress, safe to hand to another thread.

    Attributes:
        state: Current state.
        typed_chars: Characters typed across all completed passes.
        total_chars: Overall character budget, or ``None`` when looping forever.
        pass_index: 1-based index of the current repetition.
        total_passes: Configured repetitions, or ``None`` when looping forever.
        elapsed: Wall-clock seconds since the run started.
    """

    state: RunState
    typed_chars: int
    total_chars: int | None
    pass_index: int
    total_passes: int | None
    elapsed: float

    @property
    def fraction(self) -> float:
        """Completion fraction in ``[0, 1]`` (``0`` for infinite runs)."""
        if not self.total_chars:
            return 0.0
        return min(1.0, self.typed_chars / self.total_chars)


@dataclass(frozen=True, slots=True)
class RunResult:
    """Outcome of a finished run.

    Attributes:
        completed: True when every requested repetition finished.
        stopped: True when the user (or panic hotkey) aborted the run.
        typed_chars: Characters actually emitted.
        passes_completed: Repetitions that ran to completion.
        elapsed: Wall-clock seconds of the whole run, countdown included.
        skipped: Characters the keyboard backend could not send.
        typos: Deliberate mistakes that were typed and then corrected.
        error: Message when the run failed, otherwise ``None``.
    """

    completed: bool
    stopped: bool
    typed_chars: int
    passes_completed: int
    elapsed: float
    skipped: int = 0
    typos: int = 0
    error: str | None = None


@dataclass(slots=True)
class RunCallbacks:
    """Optional callbacks invoked from the worker thread.

    The Qt bridge republishes these as queued signals; tests can leave them
    ``None`` or collect values into a list.
    """

    on_state: Callable[[RunState], None] | None = None
    on_progress: Callable[[RunProgress], None] | None = None
    on_countdown: Callable[[float], None] | None = None
    on_log: Callable[[str], None] | None = None
    _last_progress: float = field(default=0.0, repr=False)



class TypingRunner:
    """Drive one typing run to completion, with pause/resume/stop support.

    Args:
        text: Payload to type (already newline-normalised).
        settings: Speed, variability, countdown and repeat configuration.
        sink: Keyboard backend receiving the characters.
        callbacks: Optional progress/state callbacks (worker thread!).
        rng: Optional RNG used by the timing engine (deterministic tests).

    The runner is single-use: create a new instance for each Start press so
    pause/stop state can never leak between runs.
    """

    def __init__(
        self,
        text: str,
        settings: TypingSettings,
        sink: KeyboardSink,
        callbacks: RunCallbacks | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.text = text
        self.settings = settings.normalized()
        self._sink = sink
        self._cb = callbacks or RunCallbacks()
        self._clock = clock

        self._pause_gate = threading.Event()
        self._pause_gate.set()  # set == running
        self._stop_flag = threading.Event()

        self._state = RunState.IDLE
        self._typed = 0
        self._pass = 0
        self._passes_completed = 0
        self._typos = 0
        self._held: str | None = None
        self._started_at: float | None = None
        self._paused_at: float | None = None
        self._paused_total = 0.0

        self.engine = TimingEngine(self.settings, rng)

    # -------------------------------------------------------------- properties
    @property
    def state(self) -> RunState:
        """Current lifecycle state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """True while the worker should keep going."""
        return not self._stop_flag.is_set() and self._state not in (
            RunState.COMPLETED,
            RunState.STOPPED,
            RunState.ERROR,
        )

    def _total_chars(self) -> int | None:
        """Overall character budget, or ``None`` for infinite loops."""
        if self.settings.loop_forever:
            return None
        return len(self.text) * max(1, self.settings.repeat_count)

    def _total_passes(self) -> int | None:
        """Configured repetition count, or ``None`` for infinite loops."""
        return None if self.settings.loop_forever else max(1, self.settings.repeat_count)

    def _elapsed(self) -> float:
        """Seconds since the run started, excluding paused time."""
        if self._started_at is None:
            return 0.0
        paused = self._paused_total
        if self._paused_at is not None:
            paused += self._clock() - self._paused_at
        return max(0.0, self._clock() - self._started_at - paused)

    # ------------------------------------------------------------- control API
    def request_pause(self) -> bool:
        """Pause typing at the next character boundary.

        Returns:
            True if the runner transitioned to paused.
        """
        if self._state is not RunState.TYPING:
            return False
        self._pause_gate.clear()
        self._paused_at = self._clock()
        self._set_state(RunState.PAUSED)
        self._log("Paused")
        return True

    def request_resume(self) -> bool:
        """Resume a paused run.

        Returns:
            True if the runner left the paused state.
        """
        if self._state is not RunState.PAUSED:
            return False
        if self._paused_at is not None:
            self._paused_total += self._clock() - self._paused_at
            self._paused_at = None
        self._pause_gate.set()
        self._set_state(RunState.TYPING)
        self._log("Resumed")
        return True

    def request_stop(self) -> None:
        """Abort immediately; safe to call from any thread or signal handler."""
        if self._stop_flag.is_set():
            return
        self._stop_flag.set()
        self._pause_gate.set()  # release a paused worker so it can exit
        LOGGER.debug("Stop requested")

    # ------------------------------------------------------------------ run
    def run(self) -> RunResult:
        """Blocking entry point: run the countdown, then type until finished.

        Returns:
            A :class:`RunResult` describing why the run ended. Never raises:
            backend failures are converted into ``RunResult.error`` so the UI
            can display them instead of crashing the worker thread.
        """
        self._started_at = self._clock()
        try:
            if not self.text:
                self._set_state(RunState.COMPLETED)
                self._log("Nothing to type")
                return self._result(completed=True)

            if self.settings.countdown > 0 and not self._countdown(self.settings.countdown):
                return self._result(stopped=True)

            # Called *after* the countdown so it runs as late as possible: by
            # then the user has released the trigger hotkey, and any leaked
            # keystroke from it can be discarded before the first character.
            self._sink.settle()
            self._set_state(RunState.TYPING)
            total = self._total_passes()
            self._log(
                f"Typing {len(self.text)} characters at {self.settings.wpm} WPM"
                + ("" if total is None else f" × {total}")
                + self._behaviour_summary()
            )

            while not self._stop_flag.is_set():
                self._pass += 1
                if not self._type_pass():
                    return self._result(stopped=True)
                self._passes_completed += 1
                if not self.settings.loop_forever and self._pass >= (total or 1):
                    break
                if not self._idle(self.settings.loop_delay):
                    return self._result(stopped=True)

            if self._stop_flag.is_set():
                return self._result(stopped=True)

            self._set_state(RunState.COMPLETED)
            self._emit_progress()
            LOGGER.info("Run complete: %d characters in %.1fs", self._typed, self._elapsed())
            return self._result(completed=True)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Typing run failed")
            self._set_state(RunState.ERROR)
            self._log(f"Error: {exc}")
            return self._result(error=str(exc))
        finally:
            self._release_held()
            self._sink.release_modifiers()

    def _release_held(self) -> None:
        """Release a key left held by a stop during its dwell time."""
        char = self._held
        if char is None:
            return
        self._held = None
        try:
            self._sink.release_character(char)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Could not release held key %r", char, exc_info=True)

    def _behaviour_summary(self) -> str:
        """Describe the enabled human-like behaviour in one short suffix.

        Kept on the runner (rather than the UI) so the activity log always
        explains *why* a run looks irregular, whichever front end started it.
        """
        settings = self.settings
        parts: list[str] = []
        if settings.dwell_max_ms > 0:
            parts.append(f"hold {settings.dwell_min_ms}-{settings.dwell_max_ms} ms")
        if settings.typo_rate > 0:
            parts.append(f"{settings.typo_rate:g}% typos")
        if settings.burstiness > 0:
            parts.append(f"burstiness {settings.burstiness}%")
        if settings.difficulty_weight > 0:
            parts.append(f"word-difficulty pauses {settings.difficulty_weight}%")
        return " · " + ", ".join(parts) if parts else ""

    def _countdown(self, seconds: float) -> bool:
        """Show a countdown, returning False if the user stopped during it."""
        self._set_state(RunState.COUNTDOWN)
        self._log(f"Starting in {seconds:.0f}s - click into the target window")
        remaining = float(seconds)
        while remaining > 0:
            if self._stop_flag.is_set():
                return False
            if self._cb.on_countdown is not None:
                self._cb.on_countdown(remaining)
            step = min(0.1, remaining)
            if not self._idle(step, allow_pause=False):
                return False
            remaining -= step
        if self._cb.on_countdown is not None:
            self._cb.on_countdown(0.0)
        return True

    def _type_pass(self) -> bool:
        """Type the payload once. Returns False when stopped mid-pass.

        Indentation is handled differently in each mode:

        ``auto``
            Every character is sent verbatim. Correct for plain text fields and
            terminals, but **doubles indentation** in editors that auto-indent:
            the editor inserts its own indent after Enter, then the payload's
            indent is typed on top of it, so successive lines drift right.
        ``strip``
            After each newline the editor's auto-inserted indent is cleared, then
            the payload's characters (including its own leading whitespace) are
            typed verbatim. The result is exactly one indent level, taken from
            your text, whatever the editor's indent style is.

        The engine's keystroke stream may be longer than the payload when typo
        simulation is on; :meth:`_emit_keystroke` handles the extra Backspaces
        and corrects the character counters accordingly.
        """
        strip = self.settings.indent_mode == "strip"

        for stroke in self.engine.keystrokes(self.text):
            if self._stop_flag.is_set():
                return False
            if not self._pause_gate.is_set():
                self._set_state(RunState.PAUSED)
                self._pause_gate.wait()
                if self._stop_flag.is_set():
                    return False
                self._set_state(RunState.TYPING)

            if not self._emit_keystroke(stroke):
                return False

            if strip and stroke.char == "\n":
                # The editor has just auto-indented the new line; remove that so
                # the payload's own indent is the only one applied.
                self._sink.strip_line_indent()

            self._emit_progress()
            if not self._idle(stroke.flight):
                return False

        self._sink.flush()
        return True

    def _emit_keystroke(self, stroke: Keystroke) -> bool:
        """Send one keystroke, honouring its dwell time. False when stopped.

        When ``hold`` is zero the key is tapped atomically, which is the
        historical behaviour. Otherwise the key is pressed, held for the drawn
        duration (through the interruptible sleep, so the panic stop still works
        within one sleep slice) and released in a ``finally`` block so a stop
        mid-hold can never leave a key stuck down.
        """
        char = stroke.char
        if char in _CORRECTABLE:
            self._typed = max(0, self._typed - 1)
            self._typos += 1
            if hasattr(self._sink, "press_backspace"):
                self._sink.press_backspace()
            else:
                # A sink without a Backspace helper still gets a correction:
                # ``\b`` is what ``type_character`` maps to the Backspace key
                # on every backend that has one.
                self._sink.type_character(BACKSPACE_SENTINEL)
            return True

        if stroke.hold <= 0.0 or not self._supports_hold:
            self._sink.type_character(char)
            self._typed += 1
            return True

        self._held = char
        try:
            self._sink.press_character(char)
        except Exception:  # pragma: no cover - defensive
            self._held = None
            raise
        try:
            if not self._idle(stroke.hold):
                return False
        finally:
            self._sink.release_character(char)
            self._held = None
        self._typed += 1
        return True

    @property
    def _supports_hold(self) -> bool:
        """True when the sink implements the press/release pair.

        Third-party or legacy sinks may predate dwell time. Falling back to an
        atomic tap keeps their payload intact instead of silently emitting
        nothing, which is what a missing ``press_character`` would otherwise
        cause.
        """
        sink = self._sink
        return hasattr(sink, "press_character") and hasattr(sink, "release_character")

    def _idle(self, seconds: float, allow_pause: bool = True) -> bool:
        """Sleep for ``seconds`` in small slices, honouring stop and pause.

        Args:
            seconds: Duration to wait.
            allow_pause: When False (countdown) only stop is honoured, so a
                paused state can never be entered before typing begins.

        Returns:
            False when the run must abort.
        """
        remaining = max(0.0, seconds)
        if remaining <= 0:
            return not self._stop_flag.is_set()
        deadline = self._clock() + remaining
        while True:
            if self._stop_flag.is_set():
                return False
            if allow_pause and not self._pause_gate.is_set():
                self._set_state(RunState.PAUSED)
                remaining = max(0.0, deadline - self._clock())
                self._pause_gate.wait()
                if self._stop_flag.is_set():
                    return False
                self._set_state(RunState.TYPING)
                deadline = self._clock() + remaining
            now = self._clock()
            left = deadline - now
            if left <= 0:
                return True
            time.sleep(min(SLEEP_SLICE, left))

    # ------------------------------------------------------------- reporting
    def _set_state(self, state: RunState) -> None:
        """Update the state and notify the UI exactly once per transition."""
        if state is self._state:
            return
        self._state = state
        if self._cb.on_state is not None:
            try:
                self._cb.on_state(state)
            except Exception:  # pragma: no cover - callback safety
                LOGGER.exception("on_state callback failed")

    def _emit_progress(self) -> None:
        """Publish a progress snapshot to the UI callback."""
        if self._cb.on_progress is None:
            return
        snapshot = RunProgress(
            state=self._state,
            typed_chars=self._typed,
            total_chars=self._total_chars(),
            pass_index=max(1, self._pass),
            total_passes=self._total_passes(),
            elapsed=self._elapsed(),
        )
        try:
            self._cb.on_progress(snapshot)
        except Exception:  # pragma: no cover - callback safety
            LOGGER.exception("on_progress callback failed")

    def _log(self, message: str) -> None:
        """Emit a human-readable activity log line."""
        LOGGER.info(message)
        if self._cb.on_log is not None:
            try:
                self._cb.on_log(message)
            except Exception:  # pragma: no cover - callback safety
                LOGGER.exception("on_log callback failed")

    def _result(
        self,
        completed: bool = False,
        stopped: bool = False,
        error: str | None = None,
    ) -> RunResult:
        """Assemble the final :class:`RunResult`."""
        skipped = getattr(self._sink, "skipped", 0)
        return RunResult(
            completed=completed,
            stopped=stopped and not completed,
            typed_chars=self._typed,
            passes_completed=self._passes_completed,
            elapsed=self._elapsed(),
            skipped=skipped if isinstance(skipped, int) else 0,
            typos=self._typos,
            error=error,
        )

    def snapshot(self) -> RunProgress:
        """Return a progress snapshot usable by other threads."""
        return RunProgress(
            state=self._state,
            typed_chars=self._typed,
            total_chars=self._total_chars(),
            pass_index=max(1, self._pass),
            total_passes=self._total_passes(),
            elapsed=self._elapsed(),
        )
