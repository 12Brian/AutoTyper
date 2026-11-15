"""Isolate whether a held modifier changes what ``type_character`` produces.

Previous attempts were invalid: any test that goes through ``TypingRunner`` also
runs the runner's own modifier-release logic, which clears the very condition
being tested.

This script talks to the keyboard sink directly - no runner, no hotkey manager -
so the only variable is whether Shift/Ctrl is held while characters are sent.

    python tools/modifier_sensitivity.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autotyper.core.keyboard import PynputKeyboard
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

PAYLOAD = "Function A wins here. loop goes to sqrt(n)"


class Harness(QWidget):
    """Typing target."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Modifier sensitivity")
        self.resize(900, 380)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(self)
        self.info = QLabel("Preparing…")
        self.info.setWordWrap(True)
        self.editor = QPlainTextEdit()
        layout.addWidget(self.info)
        layout.addWidget(self.editor, 1)


def trial(app: QApplication, harness: Harness, label: str, latch: str, done) -> None:
    """Send characters with an optional modifier held, bypassing the runner."""
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
    if held is not None:
        kb.press(held)
        time.sleep(0.2)

    # Direct sink use: nothing releases the modifier for us.
    sink = PynputKeyboard()
    for char in PAYLOAD:
        sink.type_character(char)
        time.sleep(0.004)
    time.sleep(0.4)

    if held is not None:
        kb.release(held)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    received = harness.editor.toPlainText()
    print(f"\n=== {label} ===")
    print(f"  sent={len(PAYLOAD)} received={len(received)}")
    variants = {
        "identical": received == PAYLOAD,
        "upper-cased": received == PAYLOAD.upper(),
        "mixed case change": received.lower() == PAYLOAD.lower() and received != PAYLOAD,
        "text loss": len(received) < len(PAYLOAD),
    }
    for key, value in variants.items():
        if value:
            print(f"  effect: {key}")
    if received != PAYLOAD:
        print(f"  received: {received[:100]!r}")
    done()


def main() -> int:
    """Compare clean, Shift-held and Ctrl-held injection."""
    app = QApplication(sys.argv)
    harness = Harness()
    harness.show()

    trials = [
        ("No modifier held", ""),
        ("SHIFT held", "shift"),
        ("CTRL held", "ctrl"),
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
    QTimer.singleShot(45000, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
