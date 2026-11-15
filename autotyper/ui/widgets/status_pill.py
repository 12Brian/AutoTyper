"""A compact, colour-coded run-state indicator.

The pill is a small painted widget rather than a styled QLabel so it can draw a
softly glowing dot next to the text, and so colour changes are animated without
fighting the stylesheet cascade.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...core.runner import RunState
from ..theme import Theme, tokens_for

#: Accent colour token used for each state.
_STATE_TOKENS: dict[RunState, str] = {
    RunState.IDLE: "text_subtle",
    RunState.COUNTDOWN: "warning",
    RunState.TYPING: "success",
    RunState.PAUSED: "warning",
    RunState.STOPPED: "text_muted",
    RunState.COMPLETED: "success",
    RunState.ERROR: "danger",
}


class StatusPill(QWidget):
    """Draw a rounded pill showing the current run state.

    Args:
        theme: Theme used to resolve colours (updated via :meth:`set_theme`).

    The dot pulses while typing, which makes it obvious at a glance that the app
    is driving the keyboard.
    """

    def __init__(self, theme: Theme = Theme.LIGHT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = RunState.IDLE
        self._theme = theme
        self._pulse = 0.0
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(30)

        self._animation = QPropertyAnimation(self, b"pulse", self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(1100)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setLoopCount(-1)

    # ------------------------------------------------------------- properties
    def state(self) -> RunState:
        """Current displayed state."""
        return self._state

    def set_state(self, state: RunState) -> None:
        """Update the displayed state and start/stop the typing pulse."""
        if state is self._state:
            return
        self._state = state
        if state is RunState.TYPING:
            if self._animation.state() != QPropertyAnimation.State.Running:
                self._animation.start()
        else:
            self._animation.stop()
            self._pulse = 0.0
        self.updateGeometry()
        self.update()

    def set_theme(self, theme: Theme) -> None:
        """Switch palette without rebuilding the widget."""
        self._theme = theme
        self.update()

    def get_pulse(self) -> float:
        """Animation hook used by ``QPropertyAnimation``."""
        return self._pulse

    def set_pulse(self, value: float) -> None:
        """Animation hook used by ``QPropertyAnimation``."""
        self._pulse = value
        if self._state is RunState.TYPING:
            self.update()

    pulse = Property(float, get_pulse, set_pulse)  # noqa: A003 - Qt property name

    # ------------------------------------------------------------------ layout
    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Reserve room for the dot, gap and label."""
        metrics = self.fontMetrics()
        width = metrics.horizontalAdvance(self._state.label) + 46
        return QSize(width, 30)

    def _colors(self) -> tuple[QColor, QColor, QColor]:
        """Return ``(background, border, dot)`` colours for the current state."""
        tokens = tokens_for(self._theme)
        dot = QColor(tokens[_STATE_TOKENS[self._state]])
        background = QColor(tokens["surface_alt"])
        border = QColor(tokens["border"])
        return background, border, dot

    # ----------------------------------------------------------------- painting
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Paint the pill, its dot and the state label."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        background, border, dot_color = self._colors()

        rect = self.rect().adjusted(0, 3, -1, -3)
        radius = rect.height() / 2.0

        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, radius, radius)

        # Pulse: grow the halo while typing so the dot looks alive.
        glow_alpha = int(70 * (1.0 - self._pulse)) if self._state is RunState.TYPING else 0
        if glow_alpha > 0:
            halo = QColor(dot_color)
            halo.setAlpha(glow_alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(
                rect.left() + 10, rect.center().y() - 6, 12, 12
            )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)
        painter.drawEllipse(rect.left() + 13, rect.center().y() - 3, 7, 7)

        tokens = tokens_for(self._theme)
        painter.setPen(QColor(tokens["text"]))
        text_rect = rect.adjusted(28, 0, -12, 0)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._state.label,
        )
        painter.end()
