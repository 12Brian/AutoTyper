"""A capped, read-only activity log.

Log lines are timestamped on arrival and trimmed to a maximum count so a
long-running loop session cannot exhaust memory. The widget also mirrors lines
to the rotating log file (via the ``logging`` module) when asked.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

#: Default maximum number of retained lines.
MAX_LINES = 500


class LogPanel(QPlainTextEdit):
    """A monospaced, auto-scrolling activity log.

    Args:
        max_lines: How many lines to keep before trimming the oldest.
        parent: Standard Qt parent.
    """

    def __init__(self, max_lines: int = MAX_LINES, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max_lines = max(50, max_lines)
        self.setReadOnly(True)
        self.setObjectName("LogView")
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setMaximumBlockCount(self._max_lines)
        self.setPlaceholderText("Activity will appear here…")
        self.setTabChangesFocus(True)

    def append_line(self, message: str, timestamp: bool = True) -> None:
        """Append one log line, scrolling to the bottom.

        Args:
            message: Text to add (newlines are flattened).
            timestamp: Prefix the line with a local ``HH:MM:SS`` stamp.
        """
        text = " ".join(str(message).splitlines()).strip()
        if not text:
            return
        prefix = f"[{time.strftime('%H:%M:%S')}] " if timestamp else ""
        self.appendPlainText(f"{prefix}{text}")
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()

    def clear_log(self) -> None:
        """Erase every line."""
        self.clear()

    def line_count(self) -> int:
        """Number of retained lines (excluding the trailing empty block)."""
        return max(0, self.blockCount() - 1)

    def as_text(self) -> str:
        """Return the log contents as plain text (used by "Copy log")."""
        return self.toPlainText()


class LogTextView(LogPanel):
    """Alias kept for readability where the widget is used purely for viewing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
