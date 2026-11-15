"""Card/divider/section-label building blocks for the layout."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QSlider, QVBoxLayout, QWidget


class Card(QFrame):
    """A rounded surface that groups related controls.

    Args:
        title: Optional heading rendered in the card's top-left.
        subtitle: Optional muted description under the heading.
        parent: Standard Qt parent.
    """

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        # ``Minimum`` makes sizeHint a floor: a cramped layout must not squash a
        # card's controls into invisibility (the scroll area handles overflow).
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 11, 14, 12)
        self._layout.setSpacing(7)

        self.title_label: QLabel | None = None
        self.subtitle_label: QLabel | None = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setProperty("role", "section")
            self._layout.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setProperty("role", "muted")
            self.subtitle_label.setWordWrap(True)
            self._layout.addWidget(self.subtitle_label)

    def body(self) -> QVBoxLayout:
        """Return the content layout so callers can add widgets."""
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        """Append ``widget`` to the card contents and return it."""
        self._layout.addWidget(widget, stretch)
        return widget

    def set_subtitle(self, text: str) -> None:
        """Update (or create) the muted description line."""
        if self.subtitle_label is None:
            self.subtitle_label = QLabel(text)
            self.subtitle_label.setProperty("role", "muted")
            self.subtitle_label.setWordWrap(True)
            self._layout.insertWidget(1, self.subtitle_label)
            return
        self.subtitle_label.setText(text)


class Divider(QFrame):
    """A one-pixel horizontal rule that matches the active theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


class SectionLabel(QLabel):
    """A small, uppercase caption used to separate groups of fields."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "section")


class MetricLabel(QLabel):
    """A prominent value paired with a dim caption (e.g. the time estimate)."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "metric")
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)


class ValueReadout(QLabel):
    """A fixed-width numeric readout for sliders.

    Right-aligned and minimum-width so the layout does not jitter as digits
    change while dragging.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.setMinimumWidth(66)
        self.setProperty("role", "metric")


class Slider(QSlider):
    """A horizontal slider with sensible defaults for the control cards.

    Args:
        minimum: Lowest selectable value.
        maximum: Highest selectable value.
        value: Initial value.
        parent: Standard Qt parent.
    """

    def __init__(
        self,
        minimum: int = 0,
        maximum: int = 100,
        value: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setTracking(True)
        self.setMinimumHeight(24)
        # Keyboard access: arrows nudge one step, Page Up/Down jump further.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSingleStep(1)
        self.setPageStep(max(1, (maximum - minimum) // 10))

