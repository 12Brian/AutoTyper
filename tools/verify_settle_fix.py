"""Verify the ``settle()`` fix cures the stuck-modifier text loss.

This reproduces the reported failure the way it actually happens:

1. a modifier is physically held down,
2. a run starts (``settle()`` is what the real app relies on),
3. typing proceeds while the key is still down,
4. the key is released a moment later, as a human would.

Before the fix, characters sent while Ctrl was down were swallowed by the target
application as shortcuts, and characters sent while Shift was down arrived in
upper case. ``PynputKeyboard.settle()`` releases the modifiers and waits for the
physical keys to come up, so the typed text must be exact.

    python tools/verify_settle_fix.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autotyper.config.models import TypingSettings
from autotyper.core.keyboard import PynputKeyboard
from autotyper.core.runner import TypingRunner
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

PAYLOAD = "Function A wins here. The loop goes to sqrt(n) and keeps going."


class Harness(QWidget):
    """Typing target."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("settle() verification")
        self.resize(900, 380)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(self)
        self.info = QLabel("Preparing…")
        self.info.setWordWrap(True)
        self.editor = QPlainTextEdit()
        layout.addWidget(self.info)
        layout.addWidget(self.editor, 1)


def trial(app: QApplication, harness: Harness, label: str, latch: str, done) -> None:
    """Hold a modifier across the start of a run, then release it mid-typing."""
    from pynput.keyboard import Controller, Key

    harness.editor.clear()
    harness.info.setText(label)
    harness.raise_()
    harness.activateWindow()
    harness.editor.setFocus()
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    kb = Controller()
    held = {"shift": Key.shift, "ctrl": Key.ctrl}.get(latch)

    def release_later() -> None:
        # Human-like: the key comes up ~0.35 s after the run starts.
        time.sleep(0.35)
        kb.release(held)

    if held is not None:
        kb.press(held)
        time.sleep(0.2)
        threading.Thread(target=release_later, daemon=True).start()

    sink = PynputKeyboard()
    settings = TypingSettings(wpm=300, variability=0, countdown=0, humanize_pauses=False)
    TypingRunner(PAYLOAD, settings, sink).run()
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()

    received = harness.editor.toPlainText()
    ok = received == PAYLOAD
    print(f"\n=== {label} ===")
    print(f"  sent={len(PAYLOAD)} received={len(received)}")
    print(f"  RESULT: {'PERFECT - settle() worked' if ok else 'STILL BROKEN'}")
    if not ok:
        print(f"  received: {received[:120]!r}")
    done()


def main() -> int:
    """Run the no-modifier control and both modifier cases."""
    app = QApplication(sys.argv)
    harness = Harness()
    harness.show()

    trials = [
        ("Control - nothing held", ""),
        ("CTRL held at start (the reported bug)", "ctrl"),
        ("SHIFT held at start", "shift"),
    ]

    def start(index: int) -> None:
        if index >= len(trials):
            app.quit()
            return
        label, latch = trials[index]
        QTimer.singleShot(
            500,
            lambda: trial(
                app, harness, label, latch,
                lambda: QTimer.singleShot(700, lambda: start(index + 1)),
            ),
        )

    QTimer.singleShot(1200, lambda: start(0))
    QTimer.singleShot(60000, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
