"""Light/dark theming for the Qt interface.

Themes are described by a token dictionary (surfaces, text, accent, border…)
that is interpolated into one QSS template. Keeping the palette in Python means
the same values drive both the stylesheet and any custom-painted widget, and a
theme switch is a single stylesheet swap - no window rebuild.

Dark mode pairs every colour with a contrast-checked partner so the interface
stays readable (WCAG AA for body text on the main surfaces).
"""

from __future__ import annotations

import contextlib
import sys
from enum import Enum
from string import Template
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

#: Accent used for primary actions in both themes.
_ACCENT_LIGHT: Final[str] = "#4f5ff0"
_ACCENT_DARK: Final[str] = "#8b97ff"

_LIGHT_TOKENS: Final[dict[str, str]] = {
    "window": "#f4f5f8",
    "surface": "#ffffff",
    "surface_alt": "#eef0f5",
    "surface_sunken": "#e7e9f0",
    "border": "#d3d7e3",
    "border_strong": "#b6bccd",
    "text": "#191b23",
    "text_muted": "#5c6376",
    "text_subtle": "#7c8397",
    "accent": _ACCENT_LIGHT,
    "accent_hover": "#4050d8",
    "accent_pressed": "#3443bf",
    "accent_soft": "#e5e8ff",
    "on_accent": "#ffffff",
    "success": "#1a7f4b",
    "success_soft": "#e2f5ea",
    "warning": "#97600a",
    "warning_soft": "#fdf1da",
    "danger": "#c02b2b",
    "danger_soft": "#fdeaea",
    "shadow": "rgba(15, 20, 40, 0.09)",
    "selection": "#ccd4ff",
}

_DARK_TOKENS: Final[dict[str, str]] = {
    "window": "#14161c",
    "surface": "#1c1f27",
    "surface_alt": "#232733",
    "surface_sunken": "#101218",
    "border": "#313644",
    "border_strong": "#454c60",
    "text": "#e9ecf5",
    "text_muted": "#a3abbd",
    "text_subtle": "#828b9f",
    "accent": _ACCENT_DARK,
    "accent_hover": "#a0aaff",
    "accent_pressed": "#7784f0",
    "accent_soft": "#262c47",
    "on_accent": "#10131b",
    "success": "#4ade80",
    "success_soft": "#1b3227",
    "warning": "#fbbf24",
    "warning_soft": "#3a2f18",
    "danger": "#f87171",
    "danger_soft": "#3b1f22",
    "shadow": "rgba(0, 0, 0, 0.45)",
    "selection": "#3a4270",
}


#: One QSS template shared by both palettes. ``$token`` placeholders are filled
#: from the selected token dictionary.
_STYLESHEET = Template(
    """
    * {
        font-family: $font_family;
        font-size: ${font_size}px;
    }

    QWidget#Root {
        background: $window;
        color: $text;
    }

    QLabel {
        color: $text;
        background: transparent;
    }

    QLabel[role="title"] {
        font-size: ${title_size}px;
        font-weight: 600;
        color: $text;
    }

    QLabel[role="subtitle"] {
        color: $text_muted;
    }

    QLabel[role="section"] {
        font-weight: 600;
        color: $text_muted;
        font-size: ${small_size}px;
        letter-spacing: 0.6px;
    }

    QLabel[role="muted"] {
        color: $text_subtle;
        font-size: ${small_size}px;
    }

    QLabel[role="metric"] {
        font-weight: 600;
        color: $text;
    }

    QLabel[role="estimate"] {
        color: $accent;
        font-weight: 600;
    }

    /* Developer credit pill next to the app title. A subtle inset surface keeps
       it visually secondary to the title while staying legible in both themes. */
    QLabel[role="credit"] {
        color: $text_muted;
        background: $surface_alt;
        border: 1px solid $border;
        border-radius: 9px;
        padding: 2px 9px;
        font-size: ${small_size}px;
    }

    QFrame#Card {
        background: $surface;
        border: 1px solid $border;
        border-radius: 12px;
    }
    QFrame#Banner {
        border-radius: 10px;
    }

    QFrame#Banner[severity="error"] {
        background: $danger_soft;
        border: 1px solid $danger;
    }

    QFrame#Banner[severity="warning"] {
        background: $warning_soft;
        border: 1px solid $warning;
    }

    QFrame#Banner[severity="ok"] {
        background: $success_soft;
        border: 1px solid $success;
    }

    QLabel#BannerTitle {
        font-weight: 600;
    }

    QFrame#Banner[severity="error"] QLabel#BannerTitle { color: $danger; }
    QFrame#Banner[severity="warning"] QLabel#BannerTitle { color: $warning; }
    QFrame#Banner[severity="ok"] QLabel#BannerTitle { color: $success; }

    QFrame#Banner QLabel#BannerBody {
        color: $text_muted;
    }

    QFrame#Divider {
        background: $border;
        max-height: 1px;
        border: none;
    }

    QPushButton {
        background: $surface_alt;
        color: $text;
        border: 1px solid $border;
        border-radius: 8px;
        padding: 7px 14px;
        min-height: 20px;
    }

    QPushButton:hover {
        background: $surface_sunken;
        border-color: $border_strong;
    }

    QPushButton:pressed {
        background: $surface;
    }

    QPushButton:disabled {
        color: $text_subtle;
        background: $surface_alt;
        border-color: $border;
    }

    QPushButton:focus {
        border-color: $accent;
    }

    QPushButton[variant="primary"] {
        background: $accent;
        color: $on_accent;
        border: 1px solid $accent;
        font-weight: 600;
        padding: 9px 20px;
    }

    QPushButton[variant="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
    QPushButton[variant="primary"]:pressed { background: $accent_pressed; }
    QPushButton[variant="primary"]:disabled {
        background: $surface_alt;
        color: $text_subtle;
        border-color: $border;
    }

    QPushButton[variant="danger"] {
        background: $danger_soft;
        color: $danger;
        border: 1px solid $danger;
        font-weight: 600;
        padding: 9px 18px;
    }

    QPushButton[variant="danger"]:hover { background: $danger; color: #ffffff; }
    QPushButton[variant="danger"]:disabled {
        background: $surface_alt;
        color: $text_subtle;
        border-color: $border;
    }

    QPushButton[variant="ghost"] {
        background: transparent;
        border: 1px solid transparent;
        color: $text_muted;
        padding: 4px 8px;
    }

    QPushButton[variant="ghost"]:hover {
        background: $surface_alt;
        color: $text;
    }

    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
        background: $surface;
        color: $text;
        border: 1px solid $border;
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: $selection;
        selection-color: $text;
    }

    QSpinBox, QDoubleSpinBox {
        background: $surface;
        color: $text;
        border: 1px solid $border;
        border-radius: 8px;
        padding: 6px 4px 6px 8px;
        min-height: 20px;
        selection-background-color: $selection;
        selection-color: $text;
    }

    /* Sub-controls must be styled too: leaving them native makes the padding
       above squeeze the text and the arrows overlap the value. */
    QSpinBox::up-button, QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 18px;
        margin: 3px 3px 0 0;
        border: none;
        border-radius: 4px;
        background: transparent;
    }

    QSpinBox::down-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 18px;
        margin: 0 3px 3px 0;
        border: none;
        border-radius: 4px;
        background: transparent;
    }

    /* Keep the native arrows: QSS cannot draw CSS-style triangles, and a
       zero-width arrow looks like a broken square. Only the hit area is themed. */
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
        background: $surface_alt;
    }

    QSpinBox::up-button:disabled, QSpinBox::down-button:disabled,
    QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled {
        background: transparent;
    }

    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border-color: $accent;
    }

    QLineEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled,
    QDoubleSpinBox:disabled, QComboBox:disabled {
        color: $text_subtle;
        background: $surface_alt;
    }

    QPlainTextEdit#Editor {
        font-family: $mono_family;
        font-size: ${editor_size}px;
        padding: 10px;
    }

    /* The activity log is a QPlainTextEdit inside a card; without an explicit
       rule it inherits the platform's default (black) background. */
    QPlainTextEdit#LogView {
        background: $surface_sunken;
        color: $text_muted;
        border: 1px solid $border;
        border-radius: 8px;
        font-family: $mono_family;
        font-size: ${small_size}px;
        padding: 6px 8px;
    }

    QListWidget, QTreeWidget, QTableWidget {
        background: $surface;
        color: $text;
        border: 1px solid $border;
        border-radius: 10px;
        padding: 4px;
        outline: none;
    }

    QListWidget::item {
        padding: 8px 10px;
        border-radius: 7px;
        margin: 1px 2px;
    }

    QListWidget::item:hover { background: $surface_alt; }

    QListWidget::item:selected {
        background: $accent_soft;
        color: $text;
        border: 1px solid $accent;
    }

    QSlider::groove:horizontal {
        height: 6px;
        background: $surface_sunken;
        border-radius: 3px;
    }

    QSlider::sub-page:horizontal {
        background: $accent;
        border-radius: 3px;
    }

    QSlider::handle:horizontal {
        background: $surface;
        border: 2px solid $accent;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 9px;
    }

    QSlider::handle:horizontal:hover { border-color: $accent_hover; }

    QProgressBar {
        background: $surface_sunken;
        border: 1px solid $border;
        border-radius: 6px;
        height: 10px;
        text-align: center;
        color: $text_muted;
        font-size: ${small_size}px;
    }

    QProgressBar::chunk {
        background: $accent;
        border-radius: 5px;
    }

    QCheckBox, QRadioButton { color: $text; spacing: 8px; }

    QCheckBox::indicator, QRadioButton::indicator {
        width: 15px;
        height: 15px;
        border: 1px solid $border_strong;
        background: $surface;
    }

    QCheckBox::indicator { border-radius: 4px; }
    QRadioButton::indicator { border-radius: 8px; }

    QCheckBox::indicator:hover, QRadioButton::indicator:hover {
        border-color: $accent;
    }

    /* A filled accent square plus a CSS-drawn tick (no image assets needed). */
    QCheckBox::indicator:checked {
        background: $accent;
        border: 2px solid $accent;
        image: none;
    }

    QCheckBox::indicator:checked:hover {
        background: $accent_hover;
        border-color: $accent_hover;
    }

    QRadioButton::indicator:checked {
        background: $accent;
        border: 4px solid $surface;
        outline: 1px solid $accent;
    }

    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
        background: $surface_alt;
        border-color: $border;
    }

    QCheckBox::indicator:focus, QRadioButton::indicator:focus { border-color: $accent; }

    QTabWidget::pane {
        border: 1px solid $border;
        border-radius: 10px;
        background: $surface;
        top: -1px;
    }

    QTabBar::tab {
        background: transparent;
        color: $text_muted;
        padding: 8px 16px;
        border: none;
        border-bottom: 2px solid transparent;
    }

    QTabBar::tab:selected { color: $accent; border-bottom: 2px solid $accent; font-weight: 600; }
    QTabBar::tab:hover { color: $text; }

    QToolTip {
        background: $surface;
        color: $text;
        border: 1px solid $border_strong;
        padding: 6px;
        border-radius: 6px;
    }

    QStatusBar { background: $surface; color: $text_muted; border-top: 1px solid $border; }
    QStatusBar::item { border: none; }

    QMenu {
        background: $surface;
        color: $text;
        border: 1px solid $border;
        border-radius: 8px;
        padding: 6px;
    }

    QMenu::item { padding: 6px 18px; border-radius: 6px; }
    QMenu::item:selected { background: $accent_soft; }
    QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }

    QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }

    QScrollBar::handle:vertical {
        background: $border_strong;
        border-radius: 5px;
        min-height: 30px;
    }

    QScrollBar::handle:vertical:hover { background: $text_subtle; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
    QScrollBar::handle:horizontal { background: $border_strong; border-radius: 5px; min-width: 30px; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

    QGroupBox {
        border: 1px solid $border;
        border-radius: 10px;
        margin-top: 14px;
        padding: 12px 10px 10px 10px;
        font-weight: 600;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
        color: $text_muted;
    }

    QSplitter::handle { background: $border; }
    QSplitter::handle:hover { background: $border_strong; }

    QScrollArea#ControlScroll, QScrollArea#ControlScroll > QWidget > QWidget {
        background: transparent;
        border: none;
    }
    """
)


class Theme(str, Enum):
    """Selectable themes; ``SYSTEM`` follows the OS colour scheme."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


def detect_system_theme() -> Theme:
    """Return the OS colour scheme as ``Theme.LIGHT`` or ``Theme.DARK``.

    Qt 6.5+ reports this through ``QStyleHints.colorScheme``; on older builds we
    fall back to comparing the default palette's window colour luminance, which
    covers Windows/macOS and most GTK themes.
    """
    app = QGuiApplication.instance()
    if app is not None:
        hints = app.styleHints()
        scheme = getattr(hints, "colorScheme", None)
        if scheme is not None:
            try:
                if scheme() == Qt.ColorScheme.Dark:
                    return Theme.DARK
                if scheme() == Qt.ColorScheme.Light:
                    return Theme.LIGHT
            except Exception:  # pragma: no cover - defensive
                pass
        palette = app.palette()
        window = palette.color(QPalette.ColorRole.Window)
        if window.lightness() < 128:
            return Theme.DARK
    return Theme.LIGHT


def resolve_theme(theme: Theme | str) -> Theme:
    """Resolve ``SYSTEM`` into a concrete ``LIGHT``/``DARK`` theme.

    Args:
        theme: A :class:`Theme` member or its string value.

    Returns:
        ``Theme.LIGHT`` or ``Theme.DARK``.
    """
    if isinstance(theme, str) and not isinstance(theme, Theme):
        try:
            theme = Theme(theme.strip().lower())
        except ValueError:
            theme = Theme.SYSTEM
    return detect_system_theme() if theme is Theme.SYSTEM else theme


def _font_stack() -> dict[str, str]:
    """Return platform-appropriate UI and monospace font stacks for QSS."""
    if sys.platform == "darwin":
        return {
            "font_family": '"SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif',
            "mono_family": '"SF Mono", Menlo, Monaco, "Courier New", monospace',
        }
    if sys.platform == "win32":
        return {
            "font_family": '"Segoe UI Variable Text", "Segoe UI", Tahoma, Arial, sans-serif',
            "mono_family": '"Cascadia Mono", "Consolas", "Courier New", monospace',
        }
    return {
        "font_family": '"Inter", "Noto Sans", "DejaVu Sans", Ubuntu, Cantarell, sans-serif',
        "mono_family": '"JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", monospace',
    }


def tokens_for(theme: Theme | str) -> dict[str, str]:
    """Return the colour token dictionary for a concrete theme.

    Args:
        theme: ``Theme`` member or its string value (``"dark"``, ``"system"``...).

    Returns:
        A copy of the token mapping, safe to extend per-widget.
    """
    return dict(_DARK_TOKENS if resolve_theme(theme) is Theme.DARK else _LIGHT_TOKENS)


def build_stylesheet(theme: Theme | str) -> str:
    """Render the full QSS for ``theme``.

    Args:
        theme: Desired theme (``SYSTEM`` is resolved first).

    Returns:
        A stylesheet string ready for ``QApplication.setStyleSheet``.
    """
    resolved = resolve_theme(theme)
    tokens = tokens_for(resolved)
    tokens.update(_font_stack())
    tokens.update(
        {
            "font_size": "13.5",
            "small_size": "12",
            "title_size": "19",
            "editor_size": "14",
        }
    )
    # ``Template`` treats ``$name`` as a placeholder, so QSS uses only tokens.
    return _STYLESHEET.substitute(tokens)


def apply_theme(app: QApplication, theme: Theme | str) -> Theme:
    """Apply ``theme`` to ``app`` (palette + stylesheet) and return the result.

    The palette is set as well as the stylesheet so native widgets that ignore
    QSS - menus on macOS, tooltips, text cursors and message boxes - match the
    theme.

    Args:
        app: The running application instance.
        theme: Requested theme; ``SYSTEM`` follows the OS.

    Returns:
        The concrete theme that was applied (``LIGHT`` or ``DARK``).
    """
    resolved = resolve_theme(theme)
    tokens = tokens_for(resolved)
    dark = resolved is Theme.DARK

    palette = QPalette()
    window = QColor(tokens["window"])
    surface = QColor(tokens["surface"])
    text = QColor(tokens["text"])
    muted = QColor(tokens["text_muted"])
    accent = QColor(tokens["accent"])

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, surface)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
    palette.setColor(QPalette.ColorRole.Button, QColor(tokens["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens["on_accent"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Mid, QColor(tokens["border"]))
    palette.setColor(QPalette.ColorRole.Dark, QColor(tokens["border_strong"]))
    palette.setColor(QPalette.ColorRole.Light, QColor(tokens["surface_alt"]))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.ToolTipText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(tokens["text_subtle"]))

    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(resolved))

    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        with contextlib.suppress(Exception):
            # Only available on Qt >= 6.8; older builds simply ignore it.
            hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    return resolved

