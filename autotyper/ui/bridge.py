"""Threading bridge between the pure-Python runner and the Qt UI.

The runner calls plain callables from a worker thread. Qt widgets must only be
touched from the GUI thread, so this module wraps those callbacks in a
``QObject`` whose signals are emitted from the worker and delivered to the UI
through Qt's queued-connection mechanism (automatic, because the objects live in
different threads).

Two extra guarantees matter for a typing tool:

* **Immediacy.** ``request_stop``/``request_pause`` are plain event operations
  on the runner, called directly from the GUI thread - no queueing, so a panic
  press takes effect within one 20 ms sleep slice.
* **Coalescing.** Progress signals are throttled to ~30 Hz so a 1200 WPM run
  cannot flood the event loop and make the window feel sluggish.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..config.models import TypingSettings
from ..core.keyboard import KeyboardSink, KeyboardUnavailableError, PynputKeyboard
from ..core.runner import RunCallbacks, RunProgress, RunResult, RunState, TypingRunner

LOGGER = logging.getLogger(__name__)

#: Minimum seconds between progress repaints (about 30 fps).
PROGRESS_INTERVAL = 0.033

#: States during which a new run must not be started.
ACTIVE_STATES = frozenset({RunState.COUNTDOWN, RunState.TYPING, RunState.PAUSED})


class RunWorker(QObject):
    """Owns a :class:`TypingRunner` inside a dedicated ``QThread``.

    Signals:
        stateChanged: New :class:`RunState`.
        progress: Throttled :class:`RunProgress` snapshot.
        countdownTick: Remaining countdown seconds.
        logMessage: Human-readable activity text for the log panel.
        finished: Final :class:`RunResult`.
    """

    stateChanged = Signal(object)
    progress = Signal(object)
    countdownTick = Signal(float)
    logMessage = Signal(str)
    finished = Signal(object)

    def __init__(
        self,
        text: str,
        settings: TypingSettings,
        sink: KeyboardSink | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._settings = settings
        self._sink = sink
        self._runner: TypingRunner | None = None
        self._last_progress_emit = 0.0

    # --------------------------------------------------------------- lifecycle
    @Slot()
    def start_run(self) -> None:
        """Create the runner and block this thread until the run ends."""
        sink = self._sink
        if sink is None:
            try:
                sink = PynputKeyboard()
            except KeyboardUnavailableError as exc:
                self.logMessage.emit(f"Keyboard unavailable: {exc}")
                self.stateChanged.emit(RunState.ERROR)
                self.finished.emit(
                    RunResult(
                        completed=False,
                        stopped=False,
                        typed_chars=0,
                        passes_completed=0,
                        elapsed=0.0,
                        error=str(exc),
                    )
                )
                return

        callbacks = RunCallbacks(
            on_state=self.stateChanged.emit,
            on_progress=self._on_progress,
            on_countdown=self.countdownTick.emit,
            on_log=self.logMessage.emit,
        )
        runner = TypingRunner(
            text=self._text,
            settings=self._settings,
            sink=sink,
            callbacks=callbacks,
        )
        self._runner = runner
        result = runner.run()
        self._runner = None
        self.finished.emit(result)

    def _on_progress(self, snapshot: RunProgress) -> None:
        """Relay progress, coalescing bursts to at most ~30 signals per second."""
        now = time.monotonic()
        important = snapshot.state in (
            RunState.COMPLETED,
            RunState.STOPPED,
            RunState.ERROR,
            RunState.PAUSED,
        )
        if not important and (now - self._last_progress_emit) < PROGRESS_INTERVAL:
            return
        self._last_progress_emit = now
        self.progress.emit(snapshot)

    # ----------------------------------------------------------- control hooks
    # These run on the GUI thread; the runner's events are thread-safe.
    def request_pause(self) -> bool:
        """Pause the active run, if any."""
        runner = self._runner
        return runner.request_pause() if runner is not None else False

    def request_resume(self) -> bool:
        """Resume a paused run, if any."""
        runner = self._runner
        return runner.request_resume() if runner is not None else False

    def request_stop(self) -> None:
        """Abort the active run immediately."""
        runner = self._runner
        if runner is not None:
            runner.request_stop()

    def is_paused(self) -> bool:
        """True when the active run is paused."""
        runner = self._runner
        return runner is not None and runner.state is RunState.PAUSED



class RunController(QObject):
    """GUI-side handle for one typing run (thread + worker lifetime).

    Signals mirror :class:`RunWorker` and are re-emitted here so the main window
    connects once per run.

    Args:
        parent: Standard Qt parent.
    """

    stateChanged = Signal(object)
    progress = Signal(object)
    countdownTick = Signal(float)
    logMessage = Signal(str)
    finished = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: RunWorker | None = None
        self._state = RunState.IDLE

    # ------------------------------------------------------------- properties
    @property
    def state(self) -> RunState:
        """Last known run state."""
        return self._state

    @property
    def is_active(self) -> bool:
        """True while a worker thread is running."""
        return self._thread is not None and self._thread.isRunning()

    # ----------------------------------------------------------------- control
    def start(
        self,
        text: str,
        settings: TypingSettings,
        sink: KeyboardSink | None = None,
    ) -> bool:
        """Start a run on a new worker thread.

        Args:
            text: Payload to type.
            settings: Run configuration.
            sink: Optional keyboard backend override (used by tests).

        Returns:
            False when a run is already active.
        """
        if self.is_active:
            LOGGER.warning("Ignoring start: a run is already active")
            return False

        thread = QThread()
        worker = RunWorker(text, settings, sink)
        worker.moveToThread(thread)

        thread.started.connect(worker.start_run)
        worker.stateChanged.connect(self._on_state)
        worker.progress.connect(self.progress)
        worker.countdownTick.connect(self.countdownTick)
        worker.logMessage.connect(self.logMessage)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def pause(self) -> bool:
        """Pause the run; returns True when the state actually changed."""
        worker = self._worker
        return worker.request_pause() if worker is not None else False

    def resume(self) -> bool:
        """Resume the run; returns True when the state actually changed."""
        worker = self._worker
        return worker.request_resume() if worker is not None else False

    def toggle_pause(self) -> bool:
        """Pause when typing, resume when paused; returns True when handled."""
        worker = self._worker
        if worker is None:
            return False
        if worker.is_paused():
            return worker.request_resume()
        return worker.request_pause()

    def stop(self) -> None:
        """Abort the run immediately (panic path)."""
        worker = self._worker
        if worker is not None:
            worker.request_stop()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Stop any run and wait for the worker thread to finish.

        Called on window close so a thread never outlives the QApplication.

        Args:
            timeout_ms: How long to wait for the thread before forcing it to
                terminate.
        """
        self.stop()
        thread = self._thread
        if thread is None:
            return
        try:
            thread.quit()
        except RuntimeError:  # pragma: no cover - already destroyed
            return
        if thread.isRunning() and not thread.wait(timeout_ms):
            LOGGER.warning("Worker thread did not stop in time")
            thread.terminate()
            thread.wait(1000)

    # --------------------------------------------------------------- internals
    def _on_state(self, state: RunState) -> None:
        """Track the state locally and forward it to listeners."""
        self._state = state
        self.stateChanged.emit(state)

    def _on_finished(self, result: RunResult) -> None:
        """Forward the result and clear the active marker."""
        self._state = RunState.COMPLETED if result.completed else RunState.STOPPED
        self.finished.emit(result)

    def _on_thread_finished(self) -> None:
        """Drop references once Qt reports the thread has stopped."""
        self._thread = None
        self._worker = None

