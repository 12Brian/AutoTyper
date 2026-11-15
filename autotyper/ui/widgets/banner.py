"""An inline, dismissible notice used for permission and error guidance."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.platform import PlatformReport


class Banner(QFrame):
    """A severity-coloured notice with a title, body text and dismiss button.

    Signals:
        dismissed: Emitted when the user closes the banner.

    Args:
        parent: Standard Qt parent.
    """

    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setProperty("severity", "error")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 11, 10, 11)
        outer.setSpacing(10)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(4)

        self.title_label = QLabel("")
        self.title_label.setObjectName("BannerTitle")
        self.title_label.setWordWrap(True)
        text_column.addWidget(self.title_label)

        self.body_label = QLabel("")
        self.body_label.setObjectName("BannerBody")
        self.body_label.setWordWrap(True)
        self.body_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text_column.addWidget(self.body_label)
        outer.addLayout(text_column, 1)

        self.close_button = QPushButton("✕")
        self.close_button.setProperty("variant", "ghost")
        self.close_button.setFixedWidth(30)
        self.close_button.setToolTip("Dismiss")
        self.close_button.clicked.connect(self._on_dismiss)
        outer.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)

        self.hide()

    # ------------------------------------------------------------------ content
    def show_report(self, report: PlatformReport, title: str = "") -> None:
        """Display a :class:`PlatformReport` with its remediation steps.

        Args:
            report: Result of :func:`autotyper.core.platform.check_keyboard_access`.
            title: Optional heading override.
        """
        heading = title or {
            "error": "Keyboard access needed",
            "warning": "Limited keyboard support",
            "ok": "All set",
        }.get(report.severity, "Notice")
        body = report.summary
        steps = report.steps_text()
        if steps:
            body = f"{body}\n\n{steps}"
        self.show_message(heading, body, report.severity)

    def show_message(self, title: str, body: str, severity: str = "error") -> None:
        """Display an arbitrary message.

        Args:
            title: Bold heading.
            body: Explanation, optionally with numbered steps.
            severity: ``"error"``, ``"warning"`` or ``"ok"``.
        """
        self.setProperty("severity", severity)
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.body_label.setVisible(bool(body))
        _restyle(self)
        self.show()

    def clear(self) -> None:
        """Hide and forget the current message."""
        self.title_label.clear()
        self.body_label.clear()
        self.hide()

    def _on_dismiss(self) -> None:
        """Hide the banner and notify listeners."""
        self.hide()
        self.dismissed.emit()


def _restyle(widget: QWidget) -> None:
    """Re-evaluate QSS selectors that depend on dynamic properties."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()
