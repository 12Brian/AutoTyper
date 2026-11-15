"""End-to-end diagnostic: type into a real window via real SendInput.

Run with ``python tools/typing_diagnostic.py`` on a desktop session. It opens a
window, gives it focus, and types the payload through the production keyboard
backend twice - once with global hotkeys registered and once without - then
reports exactly which characters were lost.

This exists because the fast path can only be validated against a real OS input
queue; a NullKeyboard test cannot show event loss.
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

#: Deliberately includes the characters that were mangled in the report.
PAYLOAD = (
    "Function A wins here. The loop only goes to sqrt(n), builds an array of "
    "candidate divisors sized to n, then keeps removing entries from it as it "
    "loops, and those removals cost bad on memory and are bad on time"
)


def compare(sent: str, received: str) -> str:
    """Return a human-readable report of differences between two strings."""
    if sent == received:
        return f"PERFECT - {len(sent)} characters, no loss"

    lines = [f"sent {len(sent)} chars, received {len(received)} chars "
             f"({len(received) - len(sent):+d})"]
    for index, (a, b) in enumerate(zip(sent, received, strict=False)):
        if a != b:
            lines.append(f"  first difference at index {index}: {a!r} -> {b!r}")
            lines.append(f"  context sent:     {sent[max(0, index - 20):index + 20]!r}")
            lines.append(f"  context received: {received[max(0, index - 20):index + 20]!r}")
            break
    else:
        if len(sent) != len(received):
            lines.append(f"  identical prefix; tail sent: {sent[len(received):][:40]!r}")

    missing = sorted({ch for ch in sent if ch not in received})
    if missing:
        lines.append(f"  characters never received: {''.join(missing)!r}")
    return "\n".join(lines)


class Harness(QWidget):
    """A window with a text area that records what it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoTyper typing diagnostic")
        self.resize(900, 420)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        self.info = QLabel("Preparing…")
        self.info.setWordWrap(True)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Typed text will appear here…")
        layout.addWidget(self.info)
        layout.addWidget(self.editor, 1)

    def received(self) -> str:
        """Text the window actually received."""
        return self.editor.toPlainText()


def run_trial(
    app: QApplication,
    harness: Harness,
    label: str,
    use_hotkeys: bool,
    wpm: int,
    done,
) -> None:
    """Type the payload once and report the outcome."""
    harness.editor.clear()
    harness.info.setText(f"{label}: typing at {wpm} WPM…")
    app.processEvents()

    manager = GlobalHotkeyManager()
    if use_hotkeys:
        manager.start(
            bindings={"start": lambda: None, "pause": lambda: None, "stop": lambda: None},
            specs={"start": "ctrl+alt+t", "pause": "ctrl+alt+p", "stop": "f9"},
        )

    # Give the window focus and a moment to settle before injecting.
    harness.raise_()
    harness.activateWindow()
    harness.editor.setFocus()
    app.processEvents()
    time.sleep(0.6)
    app.processEvents()

    settings = TypingSettings(
        wpm=wpm, variability=0, countdown=0, humanize_pauses=False
    )
    started = time.monotonic()
    sink = PynputKeyboard()
    TypingRunner(PAYLOAD, settings, sink).run()
    elapsed = time.monotonic() - started

    app.processEvents()
    manager.stop()
    time.sleep(0.3)
    app.processEvents()

    print(f"\n=== {label} (hotkeys={'ON' if use_hotkeys else 'OFF'}, {wpm} WPM) ===")
    print(f"elapsed {elapsed:.1f}s, keyboard skipped={sink.skipped}")
    print(compare(PAYLOAD, harness.received()))
    done()


def main() -> int:
    """Run both trials sequentially."""
    app = QApplication(sys.argv)
    harness = Harness()
    harness.show()

    trials = [
        ("Trial 1 - global hotkeys registered", True),
        ("Trial 2 - no global hotkeys", False),
    ]
    results: list[None] = []

    def start_trial(index: int) -> None:
        if index >= len(trials):
            print("\nDone. Compare the two trials above.")
            app.quit()
            return

        label, use_hotkeys = trials[index]

        def finished() -> None:
            results.append(None)
            QTimer.singleShot(800, lambda: start_trial(index + 1))

        QTimer.singleShot(
            600, lambda: run_trial(app, harness, label, use_hotkeys, 380, finished)
        )

    QTimer.singleShot(1200, lambda: start_trial(0))
    QTimer.singleShot(90000, app.quit)
    code = app.exec()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
