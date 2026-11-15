"""A click-to-record hotkey input.

Recording lives in the widget (rather than the settings dialog) because it needs
key-press filtering, modifier tracking and a clear "listening" affordance. The
widget exposes a single ``hotkeyChanged`` signal carrying the canonical string,
so the dialog stays declarative.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from ...core.hotkeys import HotkeyError, parse_hotkey

#: Qt key → canonical modifier name.
_QT_MODIFIERS: dict[int, str] = {
    Qt.Key.Key_Control: "ctrl",
    Qt.Key.Key_Alt: "alt",
    Qt.Key.Key_Shift: "shift",
    Qt.Key.Key_Meta: "cmd",
    Qt.Key.Key_Super_L: "cmd",
    Qt.Key.Key_Super_R: "cmd",
}

#: Qt key → canonical non-modifier name, for keys whose text is empty.
_QT_SPECIAL: dict[int, str] = {
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Escape: "esc",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "page_up",
    Qt.Key.Key_PageDown: "page_down",
    Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down",
    Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right",
    Qt.Key.Key_Pause: "pause",
    Qt.Key.Key_Print: "print_screen",
    Qt.Key.Key_ScrollLock: "scroll_lock",
    Qt.Key.Key_CapsLock: "caps_lock",
    Qt.Key.Key_NumLock: "num_lock",
}

#: Modifier keys that must never be recorded on their own.
_MODIFIER_KEYS = frozenset(_QT_MODIFIERS)


def key_event_to_spec(event: QKeyEvent) -> str | None:
    """Convert a Qt key press into a canonical hotkey string.

    Args:
        event: The key press being recorded.

    Returns:
        A canonical binding such as ``"ctrl+alt+t"``, or ``None`` when the key
        is a lone modifier (the user is still holding it) or is not usable.
    """
    key = event.key()
    if key in _MODIFIER_KEYS or key == Qt.Key.Key_unknown:
        return None

    modifiers = event.modifiers()
    parts: list[str] = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("cmd")

    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        parts.append(f"f{key - Qt.Key.Key_F1 + 1}")
    elif key in _QT_SPECIAL:
        parts.append(_QT_SPECIAL[key])
    else:
        text = event.text().strip().lower()
        if len(text) != 1:
            return None
        parts.append(text)

    try:
        return parse_hotkey("+".join(parts)).canonical
    except HotkeyError:
        return None


class HotkeyEdit(QWidget):
    """A read-only line edit plus a "Record" button.

    Signals:
        hotkeyChanged: Emitted with the new canonical binding whenever the user
            records one or clears the field.
        recordingChanged: Emitted with True/False when capture starts/stops.
    """

    hotkeyChanged = Signal(str)
    recordingChanged = Signal(bool)

    def __init__(self, spec: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = (spec or "").strip().lower()
        self._recording = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.field = QLineEdit()
        self.field.setReadOnly(True)
        self.field.setPlaceholderText("Not set")
        self.field.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.field, 1)

        self.record_button = QPushButton("Record")
        self.record_button.setToolTip("Click, then press the key combination")
        self.record_button.clicked.connect(self.toggle_recording)
        layout.addWidget(self.record_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setProperty("variant", "ghost")
        self.clear_button.setToolTip("Disable this hotkey")
        self.clear_button.clicked.connect(self.clear)
        layout.addWidget(self.clear_button)

        self._refresh()

    # ------------------------------------------------------------- properties
    @property
    def spec(self) -> str:
        """Current canonical binding (empty when unset)."""
        return self._spec

    def set_spec(self, spec: str) -> None:
        """Set the binding without emitting ``hotkeyChanged``."""
        self._spec = (spec or "").strip().lower()
        self._refresh()

    @property
    def is_recording(self) -> bool:
        """True while the widget is capturing the next key press."""
        return self._recording

    # -------------------------------------------------------------- recording
    def toggle_recording(self) -> None:
        """Start recording, or cancel when already recording."""
        self.set_recording(not self._recording)

    def set_recording(self, recording: bool) -> None:
        """Enter or leave capture mode."""
        if recording == self._recording:
            return
        self._recording = recording
        self.record_button.setText("Press keys…" if recording else "Record")
        self.record_button.setProperty("variant", "primary" if recording else "")
        self.field.setText("" if recording else self._display())
        self.field.setPlaceholderText(
            "Listening for a key combination…" if recording else "Not set"
        )
        _restyle(self.record_button)
        self.recordingChanged.emit(recording)
        if recording:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self.record_button.setFocus()
            self.grabKeyboard()

    def clear(self) -> None:
        """Unbind the hotkey."""
        self.set_recording(False)
        if not self._spec:
            return
        self._spec = ""
        self._refresh()
        self.hotkeyChanged.emit("")

    # ------------------------------------------------------------------ events
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        """Capture the pressed combination while recording."""
        if not self._recording:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Escape:
            # Escape always cancels capture instead of becoming the binding,
            # so a mis-click can never bind the panic key.
            self.set_recording(False)
            self._refresh()
            event.accept()
            return

        spec = key_event_to_spec(event)
        if spec is None:
            self.field.setText("…")
            event.accept()
            return

        self.set_recording(False)
        self._spec = spec
        self._refresh()
        self.hotkeyChanged.emit(spec)
        event.accept()

    def focusOutEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Abandon capture when focus moves elsewhere."""
        if self._recording:
            self.set_recording(False)
            self._refresh()
        super().focusOutEvent(event)  # type: ignore[arg-type]

    # ----------------------------------------------------------------- helpers
    def _display(self) -> str:
        """Return the pretty form of the current binding for the field."""
        if not self._spec:
            return ""
        try:
            return parse_hotkey(self._spec).display
        except HotkeyError:
            return self._spec

    def _refresh(self) -> None:
        """Sync the field text and tooltip with the current binding."""
        self.field.setText(self._display())
        if not self._recording:
            self.field.setPlaceholderText("Not set")
        self.field.setToolTip(
            f"Active binding: {self._display()}" if self._spec else "No hotkey bound"
        )


def _restyle(widget: QWidget) -> None:
    """Re-apply the stylesheet after changing a dynamic property."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()
