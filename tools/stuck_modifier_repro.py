"""Reproduce the "stuck modifier" bug that mangles typed text.

The real failure path is:

1. the user physically presses Ctrl+Alt+T
2. pynput's GlobalHotKeys swallows the combination
3. typing starts while Ctrl/Alt may still be logically down in the target app

Step 3 turns ``Ctrl+T`` into "new tab", ``Ctrl+V`` into "paste" and so on, which
lossily inserts characters - exactly the reported symptom.

This script simulates the *physical* press with pynput itself (rather than
calling the callback directly), then types into a window and reports whether any
character was lost. Run it on a desktop session:

    python tools/stuck_modifier_repro.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autotyper.config.models import TypingSettings
from autotyper.core.hotkeys import GlobalHotkeyManager
from autotyper.core.keyboard import PynputKeyboard
from autotyper.core.runner import TypingRunner
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

#: Uppercase letters are the tell-tale sign of a stuck Shift; the letters here
#: are exactly the ones that form Notepad shortcuts when Ctrl is stuck.
PAYLOAD = (
    "Function A wins here. The loop only goes to sqrt(n), builds an array of "
    "candidate divisors sized to n, then keeps removing entries from it as it "
    "loops, and those removals cost bad on memory and are bad on time."
)


class Harness(QWidget):
    """Window that records what it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Stuck-modifier repro")
        self.resize(940, 460)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        self.info = QLabel("Preparing…")
        self.info.setWordWrap(True)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Typed text appears here…")
        layout.addWidget(self.info)
        layout.addWidget(self.editor, 1)

    def received(self) -> str:
        """Text the window actually received."""
        return self.editor.toPlainText()


def report(sent: str, received: str) -> None:
    """Print a diff-style summary of what went missing."""
    print(f"  sent={len(sent)} chars, received={len(received)} chars "
          f"({len(received) - len(sent):+d})")
    if sent == received:
        print("  RESULT: clean - no loss")
        return

    print("  RESULT: LOSS DETECTED")
    received_set = set(received)
    missing = "".join(dict.fromkeys(ch for ch in sent if ch not in received_set))
    if missing:
        print(f"  characters never received: {missing!r}")
    for index, (a, b) in enumerate(zip(sent, received, strict=False)):
        if a != b:
            print(f"  first divergence at {index}: sent {a!r} got {b!r}")
            print(f"    sent:     ...{sent[max(0, index - 25):index + 25]!r}")
            print(f"    received: ...{received[max(0, index - 25):index + 25]!r}")
            break



def simulate_physical_hotkey() -> None:
    """Press Ctrl+Alt+T with pynput, as a user would, then release.

    The releases are sent explicitly - if the hotkey listener swallows them the
    target application keeps the modifiers latched, which is the bug.
    """
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    time.sleep(0.15)
    keyboard.press(Key.ctrl)
    keyboard.press(Key.alt)
    time.sleep(0.05)
    keyboard.press("t")
    time.sleep(0.05)
    keyboard.release("t")
    keyboard.release(Key.alt)
    keyboard.release(Key.ctrl)


def trial(app: QApplication, harness: Harness, label: str, via_hotkey: bool, done) -> None:
    """Run one typing trial and print the result."""
    harness.editor.clear()
    harness.info.setText(f"{label}…")
    app.processEvents()

    manager = GlobalHotkeyManager()
    fired: list[float] = []

    if via_hotkey:
        manager.start(
            bindings={
                "start": lambda: fired.append(time.monotonic()),
                "pause": lambda: None,
                "stop": lambda: None,
            },
            specs={"start": "ctrl+alt+t", "pause": "ctrl+alt+p", "stop": "f9"},
        )

    harness.raise_()
    harness.activateWindow()
    harness.editor.setFocus()
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    if via_hotkey:
        # Simulate the real user gesture that starts a run.
        simulate_physical_hotkey()
        time.sleep(0.35)
        app.processEvents()

    sink = PynputKeyboard()
    settings = TypingSettings(wpm=380, variability=0, countdown=0, humanize_pauses=False)
    started = time.monotonic()
    TypingRunner(PAYLOAD, settings, sink).run()
    elapsed = time.monotonic() - started
    app.processEvents()

    manager.stop()
    time.sleep(0.25)
    app.processEvents()

    print(f"\n=== {label} ===")
    print(f"  hotkey callbacks fired: {len(fired)}")
    print(f"  elapsed {elapsed:.1f}s, skipped={sink.skipped}")
    report(PAYLOAD, harness.received())
    done()


def main() -> int:
    """Run the direct trial, then the hotkey-triggered trial."""
    app = QApplication(sys.argv)
    harness = Harness()
    harness.show()

    trials = [
        ("Control - typed directly, no hotkey", False),
        ("Repro - started via simulated Ctrl+Alt+T", True),
    ]

    def start(index: int) -> None:
        if index >= len(trials):
            print("\nCompare the two trials: if the second shows loss, the hotkey")
            print("path leaves modifiers latched and the fix belongs in the runner.")
            app.quit()
            return
        label, via_hotkey = trials[index]
        QTimer.singleShot(
            500,
            lambda: trial(
                app, harness, label, via_hotkey,
                lambda: QTimer.singleShot(700, lambda: start(index + 1)),
            ),
        )

    QTimer.singleShot(1200, lambda: start(0))
    QTimer.singleShot(80000, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
