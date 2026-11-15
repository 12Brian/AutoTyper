"""The preferences dialog: appearance, hotkeys and platform information."""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __author__, __version__
from ..config.models import (
    MAX_COUNTDOWN,
    MIN_COUNTDOWN,
    AppSettings,
    HotkeySettings,
    TypingSettings,
)
from ..config.paths import app_data_dir, log_file
from ..core import platform as platform_info
from ..core.hotkeys import find_conflicts, validate_hotkey
from .theme import Theme
from .widgets.banner import Banner
from .widgets.hotkey_edit import HotkeyEdit


class SettingsDialog(QDialog):
    """Modal preferences editor.

    The dialog edits a copy of the settings and only exposes them through
    :meth:`result_settings`, so cancelling can never partially apply a change.

    Args:
        settings: Current application settings.
        platform_report: Result of the startup capability probe.
        parent: Standard Qt parent.
    """

    def __init__(
        self,
        settings: AppSettings,
        platform_report: platform_info.PlatformReport,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumWidth(580)
        self._initial = settings
        self._report = platform_report

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(), "General")
        self.tabs.addTab(self._build_hotkeys_tab(), "Hotkeys")
        self.tabs.addTab(self._build_about_tab(), "About")
        outer.addWidget(self.tabs, 1)

        self.hint = QLabel("")
        self.hint.setProperty("role", "muted")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------ general
    def _build_general_tab(self) -> QWidget:
        """Appearance and default-timing controls."""
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Match system", Theme.SYSTEM.value)
        self.theme_combo.addItem("Light", Theme.LIGHT.value)
        self.theme_combo.addItem("Dark", Theme.DARK.value)
        index = self.theme_combo.findData(self._initial.theme)
        self.theme_combo.setCurrentIndex(max(0, index))
        form.addRow("Theme", self.theme_combo)

        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(int(MIN_COUNTDOWN), int(MAX_COUNTDOWN))
        self.countdown_spin.setSuffix(" s")
        self.countdown_spin.setValue(int(round(self._initial.typing.countdown)))
        self.countdown_spin.setToolTip(
            "Delay before typing starts, so you can focus the target window."
        )
        form.addRow("Default countdown", self.countdown_spin)

        self.data_path_label = QLabel(str(app_data_dir()))
        self.data_path_label.setWordWrap(True)
        self.data_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.data_path_label.setProperty("role", "muted")
        form.addRow("Settings folder", self.data_path_label)

        hint = QLabel(
            "Speed, variability, dwell time and repetition are edited on the main "
            "window and saved with each profile."
        )
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        form.addRow(hint)
        return page


    # ------------------------------------------------------------------ hotkeys
    def _build_hotkeys_tab(self) -> QWidget:
        """Global hotkey bindings."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)

        hotkeys = self._initial.hotkeys
        self.start_edit = HotkeyEdit(hotkeys.start)
        self.pause_edit = HotkeyEdit(hotkeys.pause)
        self.stop_edit = HotkeyEdit(hotkeys.stop)

        form.addRow("Start typing", self.start_edit)
        form.addRow("Pause / resume", self.pause_edit)
        form.addRow("Emergency stop", self.stop_edit)
        layout.addLayout(form)

        note = QLabel(
            "Hotkeys work while another window is focused. Leave a field empty to "
            "disable it. The emergency stop key always halts typing immediately."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)

        reset = QPushButton("Restore defaults")
        reset.setProperty("variant", "ghost")
        reset.clicked.connect(self._reset_hotkeys)
        layout.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

        for edit in (self.start_edit, self.pause_edit, self.stop_edit):
            edit.hotkeyChanged.connect(self._validate_hotkeys)
        return page

    def _reset_hotkeys(self) -> None:
        """Restore the shipped default bindings."""
        defaults = HotkeySettings()
        self.start_edit.set_spec(defaults.start)
        self.pause_edit.set_spec(defaults.pause)
        self.stop_edit.set_spec(defaults.stop)
        self._validate_hotkeys()


    # -------------------------------------------------------------------- about
    def _build_about_tab(self) -> QWidget:
        """Version, data locations and platform diagnostics."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel(f"AutoTyper {__version__}")
        title.setProperty("role", "title")
        layout.addWidget(title)

        credit = QLabel(f"Developer: {__author__}")
        credit.setProperty("role", "credit")
        credit.setToolTip(f"AutoTyper {__version__} — built by {__author__}")
        # Left-aligned and width-fitted so the pill hugs its text instead of
        # stretching across the whole dialog.
        credit_row = QHBoxLayout()
        credit_row.setContentsMargins(0, 0, 0, 0)
        credit_row.addWidget(credit)
        credit_row.addStretch(1)
        layout.addLayout(credit_row)

        description = QLabel(
            "A cross-platform auto-typing utility. Text is typed with realistic "
            "timing so slow web forms keep up, and global hotkeys let you start, "
            "pause or abort without leaving the target window."
        )
        description.setWordWrap(True)
        description.setProperty("role", "muted")
        layout.addWidget(description)

        self.platform_banner = Banner()
        if self._report.keyboard_available and not self._report.needs_attention:
            self.platform_banner.show_message("Keyboard ready", self._report.summary, "ok")
        else:
            self.platform_banner.show_report(
                self._report, title=f"{self._report.platform} keyboard status"
            )
        layout.addWidget(self.platform_banner)

        details = QFormLayout()
        details.setSpacing(8)
        details.addRow("Platform", QLabel(self._report.platform))
        details.addRow("Session", QLabel(self._report.session_type))
        details.addRow("Interpreter", QLabel(platform_info.interpreter_hint()))

        log_path = QLabel(str(log_file()))
        log_path.setWordWrap(True)
        log_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        log_path.setProperty("role", "muted")
        details.addRow("Log file", log_path)
        layout.addLayout(details)

        open_button = QPushButton("Open settings folder")
        open_button.clicked.connect(self._open_data_dir)
        layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _open_data_dir(self) -> None:
        """Reveal the app-data folder in the system file manager."""
        try:
            webbrowser.open(app_data_dir().as_uri())
        except Exception:
            self.hint.setText(f"Open this folder manually: {app_data_dir()}")


    # ------------------------------------------------------------------ actions
    def _validate_hotkeys(self) -> list[str]:
        """Validate the three bindings and show problems inline.

        Returns:
            A list of problems; empty when everything is valid.
        """
        problems: list[str] = []
        for label, edit in (
            ("Start typing", self.start_edit),
            ("Pause / resume", self.pause_edit),
            ("Emergency stop", self.stop_edit),
        ):
            if not edit.spec:
                continue
            message = validate_hotkey(edit.spec)
            if message:
                problems.append(f"{label}: {message}")

        specs = {
            "start": self.start_edit.spec,
            "pause": self.pause_edit.spec,
            "stop": self.stop_edit.spec,
        }
        problems.extend(find_conflicts(specs))
        if not specs["stop"]:
            problems.append(
                "Emergency stop is disabled - bind a panic key so you can always halt typing."
            )

        self.hint.setText("   ".join(problems))
        _restyle(self.hint)
        return problems

    def _on_accept(self) -> None:
        """Validate before closing so a bad hotkey cannot be saved."""
        problems = self._validate_hotkeys()
        blocking = [p for p in problems if "Emergency stop is disabled" not in p]
        if blocking:
            self.tabs.setCurrentIndex(1)
            return
        self.accept()

    def result_settings(self) -> AppSettings:
        """Return the edited settings, normalized.

        Only meaningful after the dialog was accepted.
        """
        typing = TypingSettings.from_dict(
            {
                **self._initial.typing.to_dict(),
                "countdown": float(self.countdown_spin.value()),
            }
        )
        return AppSettings(
            theme=str(self.theme_combo.currentData()),
            typing=typing,
            hotkeys=HotkeySettings(
                start=self.start_edit.spec,
                pause=self.pause_edit.spec,
                stop=self.stop_edit.spec,
            ),
            active_profile_id=self._initial.active_profile_id,
            geometry=self._initial.geometry,
        ).normalized()


def _restyle(widget: QWidget) -> None:
    """Re-evaluate QSS selectors that depend on dynamic properties."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()
