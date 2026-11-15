"""The application's main window.

Layout (top to bottom):

* header — app title, theme toggle, "Snippets" and "Preferences" actions
* permission banner — shown only when keyboard control needs attention
* split body — text editor (left) and a control column (right) with speed,
  human-like timing, repetition and the primary transport buttons
* footer — status pill, progress bar, counters and the activity log

The window is a pure view/controller over :class:`RunController` and the
config/profile repositories; it performs no timing or typing logic of its own.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import __author__, __version__
from ..config.models import (
    MAX_BURSTINESS,
    MAX_DIFFICULTY_WEIGHT,
    MAX_DWELL_MS,
    MAX_REPEAT,
    MAX_TYPO_RATE,
    MAX_VARIABILITY,
    MAX_WPM,
    MIN_BURSTINESS,
    MIN_DIFFICULTY_WEIGHT,
    MIN_DWELL_MS,
    MIN_REPEAT,
    MIN_TYPO_RATE,
    MIN_VARIABILITY,
    MIN_WPM,
    AppSettings,
    TypingSettings,
)
from ..config.paths import ensure_app_data_dir
from ..core import platform as platform_info
from ..core.hotkeys import GlobalHotkeyManager
from ..core.runner import RunProgress, RunResult, RunState
from ..core.text import (
    TextLoadError,
    character_breakdown_preview,
    load_text_file,
    prepare_payload,
)
from ..core.timing import TimingEngine, describe_speed, format_duration
from ..profiles import Profile, ProfileRepository
from .bridge import ACTIVE_STATES, RunController
from .log_panel import LogPanel
from .profiles_dialog import ProfilesDialog
from .settings_dialog import SettingsDialog
from .theme import Theme, apply_theme, detect_system_theme
from .widgets.banner import Banner
from .widgets.cards import Card, Slider
from .widgets.status_pill import StatusPill

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """The AutoTyper main window.

    Args:
        settings: Loaded application settings (persisted on close).
        platform_report: Startup capability probe result.
        parent: Standard Qt parent.
    """

    themeChanged = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        platform_report: platform_info.PlatformReport,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.platform_report = platform_report
        self._resolved_theme = detect_system_theme()

        self.profile_repository = ProfileRepository()
        self._active_profile_id: str | None = settings.active_profile_id
        self._loading_profile = False

        self.run_controller = RunController(self)
        self.hotkeys = GlobalHotkeyManager()

        self.setWindowTitle("AutoTyper")
        self.setMinimumSize(QSize(880, 620))
        self.resize(1140, 880)

        self._build_ui()
        self._connect_signals()
        self._install_shortcuts()
        self._restore_state()
        self._register_hotkeys()

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._reset_transient_status)

        self._log(f"AutoTyper {__version__} ready on {self.platform_report.platform}")
        self._apply_state(RunState.IDLE)
        self.refresh_estimate()

    # ------------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        """Assemble the widget tree."""
        root = QWidget()
        root.setObjectName("Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 12)
        outer.setSpacing(12)

        outer.addWidget(self._build_header())

        self.banner = Banner()
        if self.platform_report.needs_attention:
            self.banner.show_report(self.platform_report)
        outer.addWidget(self.banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_editor_card())
        splitter.addWidget(self._build_control_column())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([560, 520])
        self.splitter = splitter
        outer.addWidget(splitter, 1)

        outer.addWidget(self._build_footer())
        self.setCentralWidget(root)

        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(True)
        self.hotkey_status_label = QLabel("")
        self.hotkey_status_label.setProperty("role", "muted")
        self.status_bar.addPermanentWidget(self.hotkey_status_label)

    def _build_header(self) -> QWidget:
        """Title, subtitle, developer credit and the top-right actions."""
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(10)

        title_column = QVBoxLayout()
        title_column.setSpacing(1)

        # Title and credit share a row so the developer name sits right beside
        # "AutoTyper" rather than on its own line, which would push the subtitle
        # down and steal vertical space from the editor.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title = QLabel("AutoTyper")
        title.setProperty("role", "title")
        title_row.addWidget(title)

        self.credit_label = QLabel(f"Developer: {__author__}")
        self.credit_label.setProperty("role", "credit")
        self.credit_label.setToolTip(
            f"AutoTyper {__version__} — built by {__author__}"
        )
        # Spelled out for screen readers, whose "role" has no visual meaning.
        self.credit_label.setAccessibleName(f"Developer: {__author__}")
        title_row.addWidget(self.credit_label)
        title_row.addStretch(1)
        title_column.addLayout(title_row)

        subtitle = QLabel("Type anywhere — with timing that feels human")
        subtitle.setProperty("role", "muted")
        title_column.addWidget(subtitle)
        row.addLayout(title_column)
        row.addStretch(1)

        self.snippets_button = QPushButton("Snippets")
        self.snippets_button.setToolTip("Save and load reusable text snippets")
        row.addWidget(self.snippets_button)

        self.settings_button = QPushButton("Preferences")
        self.settings_button.setToolTip("Theme, hotkeys and platform information")
        row.addWidget(self.settings_button)

        self.theme_button = QPushButton()
        self.theme_button.setToolTip("Switch between light and dark theme")
        self.theme_button.setFixedWidth(104)
        row.addWidget(self.theme_button)

        return header

    # -------------------------------------------------------------- editor card
    def _build_editor_card(self) -> QWidget:
        """The text editor with its load/clear toolbar and counters."""
        card = Card("Text to type")
        body = card.body()

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.load_button = QPushButton("Load from file…")
        self.load_button.setToolTip("Load a .txt file (UTF-8, UTF-16 or ANSI)")
        self.save_button = QPushButton("Save to file…")
        self.save_button.setToolTip("Export the current text as a .txt file")
        self.paste_button = QPushButton("Paste")
        self.paste_button.setToolTip("Paste from the clipboard (preserves tabs and newlines)")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setProperty("variant", "ghost")
        for button in (self.load_button, self.save_button, self.paste_button):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.clear_button)
        body.addLayout(toolbar)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText(
            "Type or paste the text to send to the active window…\n\n"
            "Newlines, tabs and Unicode characters are preserved."
        )
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setTabChangesFocus(False)
        self.editor.setMinimumHeight(190)
        self.editor.setAccessibleName("Text to type")
        body.addWidget(self.editor, 1)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.char_count_label = QLabel("0 characters")
        self.char_count_label.setProperty("role", "muted")
        self.word_count_label = QLabel("0 words")
        self.word_count_label.setProperty("role", "muted")
        self.line_count_label = QLabel("0 lines")
        self.line_count_label.setProperty("role", "muted")
        for label in (self.char_count_label, self.word_count_label, self.line_count_label):
            stats.addWidget(label)
        stats.addStretch(1)

        # Indentation mode is about *what the target window does with Enter*, so
        # it belongs next to the text rather than buried among the timing knobs.
        indent_label = QLabel("Indentation")
        indent_label.setProperty("role", "muted")
        stats.addWidget(indent_label)
        self.indent_combo = QComboBox()
        self.indent_combo.addItem("Plain text / Notepad", "auto")
        self.indent_combo.addItem("Code editor (Colab, VS Code)", "strip")
        self.indent_combo.setToolTip(
            "Code editors re-indent after Enter. Choose \"Code editor\" so AutoTyper "
            "clears that indent instead of adding a second one, which otherwise "
            "makes each line drift further right."
        )
        self.indent_combo.setAccessibleName("Indentation mode")
        self.indent_combo.setMinimumWidth(230)
        stats.addWidget(self.indent_combo)

        self.profile_badge = QLabel("")
        self.profile_badge.setProperty("role", "muted")
        stats.addWidget(self.profile_badge)
        body.addLayout(stats)
        return card

    # ------------------------------------------------------------ control column
    def _build_control_column(self) -> QWidget:
        """Speed, timing, repetition and transport controls.

        Only the three settings cards scroll: the transport card is pinned to the
        bottom of the column so **Start** and especially **Stop** are always
        reachable, even in a short window or with a large system font.
        """
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("ControlScroll")
        scroll.setMinimumWidth(400)

        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_speed_card())
        layout.addWidget(self._build_timing_card())
        layout.addWidget(self._build_behaviour_card())
        layout.addWidget(self._build_repeat_card())
        layout.addStretch(1)

        scroll.setWidget(column)
        outer.addWidget(scroll, 1)

        # Pinned, always-visible transport controls.
        outer.addWidget(self._build_transport_card(), 0)
        return wrapper

    def _build_speed_card(self) -> Card:
        """WPM slider plus a numeric field and the live time estimate."""
        card = Card("Typing speed")
        body = card.body()

        row = QHBoxLayout()
        row.setSpacing(10)
        self.speed_slider = Slider(MIN_WPM, MAX_WPM, TypingSettings().wpm)
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(50)
        self.speed_slider.setToolTip("Words per minute (a word is five characters)")
        self.speed_slider.setAccessibleName("Typing speed in words per minute")
        row.addWidget(self.speed_slider, 1)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(MIN_WPM, MAX_WPM)
        self.speed_spin.setSingleStep(10)
        self.speed_spin.setSuffix(" WPM")
        self.speed_spin.setKeyboardTracking(False)
        self.speed_spin.setFixedWidth(112)
        self.speed_spin.setToolTip("Exact speed; the slider snaps to this value")
        row.addWidget(self.speed_spin)
        body.addLayout(row)

        readout = QHBoxLayout()
        readout.setSpacing(6)
        self.cpm_label = QLabel("")
        self.cpm_label.setProperty("role", "muted")
        readout.addWidget(self.cpm_label)
        readout.addStretch(1)
        self.estimate_label = QLabel("")
        self.estimate_label.setProperty("role", "estimate")
        self.estimate_label.setToolTip("Estimated time for the current settings")
        readout.addWidget(self.estimate_label)
        body.addLayout(readout)
        return card

    def _build_timing_card(self) -> Card:
        """Variability slider and the human-like pause switch."""
        card = Card("Human-like timing")
        body = card.body()

        row = QHBoxLayout()
        row.setSpacing(10)
        self.variability_slider = Slider(MIN_VARIABILITY, MAX_VARIABILITY, 0)
        self.variability_slider.setToolTip(
            "0 = metronomic, 100 = very irregular. Adds jitter plus extra pauses at "
            "spaces and punctuation, which helps slow input fields keep up."
        )
        self.variability_slider.setAccessibleName("Timing variability")
        row.addWidget(self.variability_slider, 1)

        self.variability_spin = QSpinBox()
        self.variability_spin.setRange(MIN_VARIABILITY, MAX_VARIABILITY)
        self.variability_spin.setSuffix(" %")
        self.variability_spin.setKeyboardTracking(False)
        self.variability_spin.setFixedWidth(96)
        row.addWidget(self.variability_spin)
        body.addLayout(row)

        self.humanize_check = QCheckBox("Pause naturally at spaces and punctuation")
        self.humanize_check.setToolTip(
            "Gives slow web forms time to register each keystroke."
        )
        body.addWidget(self.humanize_check)
        return card

    def _build_behaviour_card(self) -> Card:
        """Dwell time, typos, burstiness and word-difficulty pauses."""
        card = Card("Human behaviour")
        body = card.body()

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        dwell_label = QLabel("Key hold")
        dwell_label.setProperty("role", "muted")
        dwell_label.setToolTip(
            "Dwell time: how long each key stays pressed. 0 ms taps instantly."
        )
        grid.addWidget(dwell_label, 0, 0)

        self.dwell_min_spin = QSpinBox()
        self.dwell_min_spin.setRange(MIN_DWELL_MS, MAX_DWELL_MS)
        self.dwell_min_spin.setSuffix(" ms")
        self.dwell_min_spin.setFixedWidth(92)
        self.dwell_min_spin.setKeyboardTracking(False)
        self.dwell_min_spin.setToolTip("Shortest key hold (dwell time)")
        grid.addWidget(self.dwell_min_spin, 0, 1)

        dwell_to = QLabel("to")
        dwell_to.setProperty("role", "muted")
        grid.addWidget(dwell_to, 0, 2)

        self.dwell_max_spin = QSpinBox()
        self.dwell_max_spin.setRange(MIN_DWELL_MS, MAX_DWELL_MS)
        self.dwell_max_spin.setSuffix(" ms")
        self.dwell_max_spin.setFixedWidth(92)
        self.dwell_max_spin.setKeyboardTracking(False)
        self.dwell_max_spin.setToolTip("Longest key hold (dwell time)")
        grid.addWidget(self.dwell_max_spin, 0, 3)

        typo_label = QLabel("Typos")
        typo_label.setProperty("role", "muted")
        typo_label.setToolTip(
            "Share of characters deliberately mistyped and corrected with Backspace."
        )
        grid.addWidget(typo_label, 1, 0)

        self.typo_spin = QDoubleSpinBox()
        self.typo_spin.setRange(MIN_TYPO_RATE, MAX_TYPO_RATE)
        self.typo_spin.setDecimals(1)
        self.typo_spin.setSingleStep(0.5)
        self.typo_spin.setSuffix(" %")
        self.typo_spin.setFixedWidth(92)
        self.typo_spin.setKeyboardTracking(False)
        self.typo_spin.setToolTip(
            "Most real typing runs 1-4 % errors. Each slip is corrected, so the "
            "final text is still exact."
        )
        grid.addWidget(self.typo_spin, 1, 1)

        burst_label = QLabel("Burstiness")
        burst_label.setProperty("role", "muted")
        burst_label.setToolTip(
            "How strongly consecutive keystrokes share a speed. 0 = independent "
            "jitter, 100 = long fast bursts with slower recoveries."
        )
        grid.addWidget(burst_label, 2, 0)

        self.burst_slider = Slider(MIN_BURSTINESS, MAX_BURSTINESS, 0)
        self.burst_slider.setToolTip(burst_label.toolTip())
        self.burst_slider.setAccessibleName("Rhythm burstiness")
        grid.addWidget(self.burst_slider, 2, 1, 1, 2)

        self.burst_spin = QSpinBox()
        self.burst_spin.setRange(MIN_BURSTINESS, MAX_BURSTINESS)
        self.burst_spin.setSuffix(" %")
        self.burst_spin.setFixedWidth(92)
        self.burst_spin.setKeyboardTracking(False)
        self.burst_spin.setToolTip(burst_label.toolTip())
        grid.addWidget(self.burst_spin, 2, 3)

        diff_label = QLabel("Hard-word pauses")
        diff_label.setProperty("role", "muted")
        diff_label.setToolTip(
            "Stretch pauses before long, unusual or mixed-case words, the way real "
            "typists slow down to plan them."
        )
        grid.addWidget(diff_label, 3, 0)

        self.difficulty_slider = Slider(MIN_DIFFICULTY_WEIGHT, MAX_DIFFICULTY_WEIGHT, 0)
        self.difficulty_slider.setToolTip(diff_label.toolTip())
        self.difficulty_slider.setAccessibleName("Word difficulty pause weighting")
        grid.addWidget(self.difficulty_slider, 3, 1, 1, 2)

        self.difficulty_spin = QSpinBox()
        self.difficulty_spin.setRange(MIN_DIFFICULTY_WEIGHT, MAX_DIFFICULTY_WEIGHT)
        self.difficulty_spin.setSuffix(" %")
        self.difficulty_spin.setFixedWidth(92)
        self.difficulty_spin.setKeyboardTracking(False)
        self.difficulty_spin.setToolTip(diff_label.toolTip())
        grid.addWidget(self.difficulty_spin, 3, 3)

        grid.setColumnStretch(4, 1)
        body.addLayout(grid)

        self.behaviour_note = QLabel("")
        self.behaviour_note.setProperty("role", "muted")
        self.behaviour_note.setWordWrap(True)
        body.addWidget(self.behaviour_note)
        return card

    def _build_repeat_card(self) -> Card:
        """Repetition count, infinite loop and the delay between runs."""
        card = Card("Repeat")
        body = card.body()

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        self.repeat_check = QCheckBox("Repeat")
        self.repeat_check.setToolTip("Type the text more than once")
        grid.addWidget(self.repeat_check, 0, 0)

        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(MIN_REPEAT, MAX_REPEAT)
        self.repeat_spin.setSuffix(" ×")
        self.repeat_spin.setFixedWidth(96)
        self.repeat_spin.setKeyboardTracking(False)
        self.repeat_spin.setToolTip("Number of repetitions")
        grid.addWidget(self.repeat_spin, 0, 1)

        self.loop_check = QCheckBox("Loop until stopped")
        self.loop_check.setToolTip("Ignores the repeat count and keeps going")
        grid.addWidget(self.loop_check, 0, 2)

        delay_label = QLabel("Delay between runs")
        delay_label.setProperty("role", "muted")
        grid.addWidget(delay_label, 1, 0)

        self.loop_delay_spin = QDoubleSpinBox()
        self.loop_delay_spin.setRange(0.0, 3600.0)
        self.loop_delay_spin.setDecimals(1)
        self.loop_delay_spin.setSingleStep(0.5)
        self.loop_delay_spin.setSuffix(" s")
        self.loop_delay_spin.setFixedWidth(96)
        self.loop_delay_spin.setKeyboardTracking(False)
        grid.addWidget(self.loop_delay_spin, 1, 1)

        grid.setColumnStretch(3, 1)
        body.addLayout(grid)
        return card

    def _build_transport_card(self) -> Card:
        """Start / pause / stop controls plus the countdown readout."""
        card = Card("Run")
        body = card.body()

        self.countdown_label = QLabel("")
        self.countdown_label.setProperty("role", "subtitle")
        self.countdown_label.setWordWrap(True)
        body.addWidget(self.countdown_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.start_button = QPushButton("Start typing")
        self.start_button.setProperty("variant", "primary")
        self.start_button.setToolTip("Start after the countdown (Ctrl+Alt+T by default)")
        self.start_button.setMinimumHeight(38)
        buttons.addWidget(self.start_button, 1)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setToolTip("Pause or resume (Ctrl+Alt+P by default)")
        self.pause_button.setMinimumHeight(38)
        buttons.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("variant", "danger")
        self.stop_button.setToolTip("Halt immediately (F9 by default)")
        self.stop_button.setMinimumHeight(38)
        buttons.addWidget(self.stop_button)
        body.addLayout(buttons)
        return card

    def _build_footer(self) -> QWidget:
        """Status pill, progress bar, counters and the activity log."""
        footer = QWidget()
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.status_pill = StatusPill(self._resolved_theme)
        row.addWidget(self.status_pill)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAccessibleName("Typing progress")
        row.addWidget(self.progress_bar, 1)

        self.progress_label = QLabel("0 / 0 characters")
        self.progress_label.setProperty("role", "muted")
        self.progress_label.setMinimumWidth(160)
        self.progress_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.progress_label)
        layout.addLayout(row)

        log_card = Card()
        log_card.body().setContentsMargins(8, 4, 8, 4)
        self.log_panel = LogPanel(max_lines=200)
        self.log_panel.setFixedHeight(44)
        log_card.add(self.log_panel, 1)
        layout.addWidget(log_card, 0)
        return footer

    # ------------------------------------------------------------------ wiring
    def _connect_signals(self) -> None:
        """Connect widget signals to handlers (one place per concern)."""
        self.editor.textChanged.connect(self._on_text_changed)
        self.load_button.clicked.connect(self._on_load_file)
        self.save_button.clicked.connect(self._on_save_file)
        self.paste_button.clicked.connect(self._on_paste)
        self.clear_button.clicked.connect(self._on_clear_text)

        self.speed_slider.valueChanged.connect(self._on_speed_slider)
        self.speed_spin.valueChanged.connect(self._on_speed_spin)
        self.variability_slider.valueChanged.connect(self._on_variability_slider)
        self.variability_spin.valueChanged.connect(self._on_variability_spin)
        self.humanize_check.toggled.connect(self.refresh_estimate)
        self.dwell_min_spin.valueChanged.connect(self._on_dwell_changed)
        self.dwell_max_spin.valueChanged.connect(self._on_dwell_changed)
        self.typo_spin.valueChanged.connect(self.refresh_estimate)
        self.burst_slider.valueChanged.connect(self._on_burst_slider)
        self.burst_spin.valueChanged.connect(self._on_burst_spin)
        self.difficulty_slider.valueChanged.connect(self._on_difficulty_slider)
        self.difficulty_spin.valueChanged.connect(self._on_difficulty_spin)
        self.repeat_check.toggled.connect(self._on_repeat_toggled)
        self.repeat_spin.valueChanged.connect(self.refresh_estimate)
        self.loop_check.toggled.connect(self._on_loop_toggled)
        self.loop_delay_spin.valueChanged.connect(self.refresh_estimate)

        self.start_button.clicked.connect(self.start_typing)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_typing)

        self.snippets_button.clicked.connect(self.open_profiles)
        self.settings_button.clicked.connect(self.open_settings)
        self.theme_button.clicked.connect(self.toggle_theme)
        self.banner.dismissed.connect(self._on_banner_dismissed)

        self.run_controller.stateChanged.connect(self._on_run_state)
        self.run_controller.progress.connect(self._on_progress)
        self.run_controller.countdownTick.connect(self._on_countdown)
        self.run_controller.logMessage.connect(self._log)
        self.run_controller.finished.connect(self._on_run_finished)

    def _install_shortcuts(self) -> None:
        """Window-level shortcuts (active while AutoTyper has focus)."""
        for sequence, slot in (
            (QKeySequence.StandardKey.Open, self._on_load_file),
            (QKeySequence.StandardKey.Save, self._on_save_file),
            (QKeySequence("Ctrl+Return"), self.start_typing),
            (QKeySequence("Ctrl+."), self.stop_typing),
            (QKeySequence("Ctrl+P"), self.toggle_pause),
            (QKeySequence("Ctrl+,"), self.open_settings),
            (QKeySequence("Ctrl+Shift+S"), self.open_profiles),
            (QKeySequence("Escape"), self._on_escape),
        ):
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(slot)

    def _on_escape(self) -> None:
        """Escape aborts an active run (and does nothing when idle)."""
        if self.run_controller.state in ACTIVE_STATES:
            self.stop_typing()

    # ------------------------------------------------------------ state restore
    def _restore_state(self) -> None:
        """Push persisted settings into the widgets without firing side effects."""
        self.apply_theme(self.settings.theme, persist=False)

        typing = self.settings.typing
        self._suppress_controls(True)
        self.speed_slider.setValue(typing.wpm)
        self.speed_spin.setValue(typing.wpm)
        self.variability_slider.setValue(typing.variability)
        self.variability_spin.setValue(typing.variability)
        self.humanize_check.setChecked(typing.humanize_pauses)
        self._apply_behaviour_widgets(typing)
        _select_combo(self.indent_combo, typing.indent_mode)
        self.repeat_check.setChecked(typing.repeat_count > 1 or typing.loop_forever)
        self.repeat_spin.setValue(max(MIN_REPEAT, typing.repeat_count))
        self.loop_check.setChecked(typing.loop_forever)
        self.loop_delay_spin.setValue(typing.loop_delay)
        self._suppress_controls(False)

        if self.settings.geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.settings.geometry.encode()))

        self._sync_repeat_enabled()
        self._refresh_counts()
        self._update_countdown_label()

    def _apply_behaviour_widgets(self, typing: TypingSettings) -> None:
        """Push behaviour settings into their widgets (callers block signals)."""
        self.dwell_min_spin.setValue(typing.dwell_min_ms)
        self.dwell_max_spin.setValue(typing.dwell_max_ms)
        self.typo_spin.setValue(typing.typo_rate)
        self.burst_slider.setValue(typing.burstiness)
        self.burst_spin.setValue(typing.burstiness)
        self.difficulty_slider.setValue(typing.difficulty_weight)
        self.difficulty_spin.setValue(typing.difficulty_weight)

    def _suppress_controls(self, suppress: bool) -> None:
        """Block control signals while restoring persisted values."""
        for widget in (
            self.speed_slider,
            self.speed_spin,
            self.variability_slider,
            self.variability_spin,
            self.humanize_check,
            self.dwell_min_spin,
            self.dwell_max_spin,
            self.typo_spin,
            self.burst_slider,
            self.burst_spin,
            self.difficulty_slider,
            self.difficulty_spin,
            self.repeat_check,
            self.repeat_spin,
            self.loop_check,
            self.loop_delay_spin,
            self.indent_combo,
        ):
            widget.blockSignals(suppress)

    # -------------------------------------------------------------- text events
    def _on_text_changed(self) -> None:
        """Refresh counters, estimate and the profile badge."""
        self._refresh_counts()
        self.refresh_estimate()
        self._update_profile_badge()

    def _refresh_counts(self) -> None:
        """Update the character/word/line counters under the editor."""
        text = self.editor.toPlainText()
        chars, words, lines = character_breakdown_preview(text)
        self.char_count_label.setText(f"{chars:,} characters")
        self.word_count_label.setText(f"{words:,} words")
        self.line_count_label.setText(f"{lines:,} lines")

    def _on_load_file(self) -> None:
        """Prompt for a text file and replace the editor contents."""
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Load text to type",
            "",
            "Text files (*.txt);;Markdown (*.md);;All files (*)",
        )
        if not path:
            return
        try:
            text = load_text_file(path)
        except TextLoadError as exc:
            QMessageBox.warning(self, "Could not load file", str(exc))
            self._log(f"Load failed: {exc}")
            return
        self.editor.setPlainText(text)
        self._log(f"Loaded {len(text):,} characters from {path.rsplit('/', 1)[-1]}")
        self._flash_status("File loaded")

    def _on_save_file(self) -> None:
        """Export the current text to a .txt file."""
        text = self.editor.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "Nothing to save", "The editor is empty.")
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save text", "snippet.txt", "Text files (*.txt)"
        )
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path += ".txt"
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(prepare_payload(text))
        except OSError as exc:
            QMessageBox.warning(self, "Could not save file", f"{path}\n\n{exc}")
            return
        self._log(f"Saved {len(text):,} characters to {path}")
        self._flash_status("File saved")

    def _on_paste(self) -> None:
        """Paste clipboard text, preserving tabs and newlines."""
        clipboard = QApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        if not text:
            self._flash_status("Clipboard is empty")
            return
        self.editor.insertPlainText(prepare_payload(text))
        self._log(f"Pasted {len(text):,} characters")

    def _on_clear_text(self) -> None:
        """Clear the editor, asking first when it has content."""
        if self.editor.toPlainText().strip():
            confirm = QMessageBox.question(
                self,
                "Clear text",
                "Clear the editor? The text is not saved anywhere else.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        self.editor.clear()

    # ------------------------------------------------------------ control events
    def _on_speed_slider(self, value: int) -> None:
        """Mirror the slider into the numeric field."""
        if self.speed_spin.value() != value:
            self.speed_spin.blockSignals(True)
            self.speed_spin.setValue(value)
            self.speed_spin.blockSignals(False)
        self.refresh_estimate()

    def _on_speed_spin(self, value: int) -> None:
        """Mirror the numeric field into the slider."""
        if self.speed_slider.value() != value:
            self.speed_slider.blockSignals(True)
            self.speed_slider.setValue(value)
            self.speed_slider.blockSignals(False)
        self.refresh_estimate()

    def _on_variability_slider(self, value: int) -> None:
        """Mirror the variability slider into its numeric field."""
        if self.variability_spin.value() != value:
            self.variability_spin.blockSignals(True)
            self.variability_spin.setValue(value)
            self.variability_spin.blockSignals(False)
        self.refresh_estimate()

    def _on_variability_spin(self, value: int) -> None:
        """Mirror the variability field into the slider."""
        if self.variability_slider.value() != value:
            self.variability_slider.blockSignals(True)
            self.variability_slider.setValue(value)
            self.variability_slider.blockSignals(False)
        self.refresh_estimate()

    def _on_dwell_changed(self, _value: int) -> None:
        """Keep the dwell window ordered, then refresh the readouts.

        A minimum above the maximum would be rejected by the model anyway (it
        swaps the pair), but pushing the other spin box here keeps what the user
        sees consistent with what will actually run.
        """
        sender = self.sender()
        low = self.dwell_min_spin.value()
        high = self.dwell_max_spin.value()
        if low > high:
            if sender is self.dwell_min_spin:
                self._set_dwell_max(low)
            else:
                self._set_dwell_min(high)
        self.refresh_estimate()

    def _set_dwell_min(self, value: int) -> None:
        """Set the minimum dwell without re-entering the handler."""
        self.dwell_min_spin.blockSignals(True)
        self.dwell_min_spin.setValue(value)
        self.dwell_min_spin.blockSignals(False)

    def _set_dwell_max(self, value: int) -> None:
        """Set the maximum dwell without re-entering the handler."""
        self.dwell_max_spin.blockSignals(True)
        self.dwell_max_spin.setValue(value)
        self.dwell_max_spin.blockSignals(False)

    def _on_burst_slider(self, value: int) -> None:
        """Mirror the burstiness slider into its numeric field."""
        if self.burst_spin.value() != value:
            self.burst_spin.blockSignals(True)
            self.burst_spin.setValue(value)
            self.burst_spin.blockSignals(False)
        self.refresh_estimate()

    def _on_burst_spin(self, value: int) -> None:
        """Mirror the burstiness field into the slider."""
        if self.burst_slider.value() != value:
            self.burst_slider.blockSignals(True)
            self.burst_slider.setValue(value)
            self.burst_slider.blockSignals(False)
        self.refresh_estimate()

    def _on_difficulty_slider(self, value: int) -> None:
        """Mirror the difficulty-weight slider into its numeric field."""
        if self.difficulty_spin.value() != value:
            self.difficulty_spin.blockSignals(True)
            self.difficulty_spin.setValue(value)
            self.difficulty_spin.blockSignals(False)
        self.refresh_estimate()

    def _on_difficulty_spin(self, value: int) -> None:
        """Mirror the difficulty-weight field into the slider."""
        if self.difficulty_slider.value() != value:
            self.difficulty_slider.blockSignals(True)
            self.difficulty_slider.setValue(value)
            self.difficulty_slider.blockSignals(False)
        self.refresh_estimate()

    def _on_repeat_toggled(self, enabled: bool) -> None:
        """Keep repeat controls consistent when the checkbox flips."""
        if not enabled:
            self.loop_check.blockSignals(True)
            self.loop_check.setChecked(False)
            self.loop_check.blockSignals(False)
        self._sync_repeat_enabled()
        self.refresh_estimate()

    def _on_loop_toggled(self, enabled: bool) -> None:
        """Looping implies repetition, so tick the parent checkbox."""
        if enabled and not self.repeat_check.isChecked():
            self.repeat_check.blockSignals(True)
            self.repeat_check.setChecked(True)
            self.repeat_check.blockSignals(False)
        self._sync_repeat_enabled()
        self.refresh_estimate()

    def _sync_repeat_enabled(self) -> None:
        """Enable count/delay fields only when repetition is on."""
        repeating = self.repeat_check.isChecked()
        looping = self.loop_check.isChecked()
        self.repeat_spin.setEnabled(repeating and not looping)
        self.loop_check.setEnabled(repeating)
        self.loop_delay_spin.setEnabled(repeating)
        self.repeat_spin.setToolTip(
            "Ignored while looping until stopped"
            if looping
            else "Number of repetitions"
        )

    # --------------------------------------------------------------- settings IO
    def current_typing_settings(self) -> TypingSettings:
        """Collect the typing settings currently shown in the UI."""
        repeating = self.repeat_check.isChecked()
        return TypingSettings(
            wpm=self.speed_spin.value(),
            variability=self.variability_spin.value(),
            countdown=self.settings.typing.countdown,
            repeat_count=self.repeat_spin.value() if repeating else 1,
            loop_forever=self.loop_check.isChecked(),
            loop_delay=self.loop_delay_spin.value(),
            humanize_pauses=self.humanize_check.isChecked(),
            indent_mode=str(self.indent_combo.currentData()),
            dwell_min_ms=self.dwell_min_spin.value(),
            dwell_max_ms=self.dwell_max_spin.value(),
            typo_rate=self.typo_spin.value(),
            burstiness=self.burst_spin.value(),
            difficulty_weight=self.difficulty_spin.value(),
        ).normalized()

    def refresh_estimate(self, *_args: object) -> None:
        """Recompute the speed readout, time estimate and note text."""
        settings = self.current_typing_settings()
        self.cpm_label.setText(f"{settings.chars_per_minute:.0f} characters / minute")

        text = self.editor.toPlainText()
        engine = TimingEngine(settings)
        repeats = 1 if settings.loop_forever else max(1, settings.repeat_count)
        duration = engine.estimate_duration(text, repeats, settings.loop_delay)

        if not text:
            self.estimate_label.setText("No text yet")
        elif settings.loop_forever:
            self.estimate_label.setText(
                f"≈ {format_duration(engine.estimate_passes_duration(text))} per loop"
            )
        else:
            label = f"≈ {format_duration(duration)} total"
            if repeats > 1:
                label += f"  ({repeats} × {format_duration(duration / repeats)})"
            self.estimate_label.setText(label)

        self.estimate_label.setToolTip(
            f"{describe_speed(settings)}"
            + ("" if settings.loop_forever else f" · {repeats} run(s)")
            + f" · variability {settings.variability}%"
        )

        # Fold the plain-language variability explanation into the slider's
        # tooltip so it is discoverable without spending vertical space.
        self.variability_slider.setToolTip(
            self._variability_note(settings)
            + "\n\n0 = metronomic, 100 = very irregular. Extra pauses at spaces "
            "and punctuation help slow input fields keep up."
        )
        self.behaviour_note.setText(self._behaviour_note(settings))
        self._update_countdown_label()

    @staticmethod
    def _behaviour_note(settings: TypingSettings) -> str:
        """Summarise the enabled behaviour models in one sentence."""
        parts: list[str] = []
        if settings.dwell_max_ms > 0:
            parts.append(
                f"Keys are held {settings.dwell_min_ms}-{settings.dwell_max_ms} ms."
            )
        if settings.typo_rate > 0:
            parts.append(f"{settings.typo_rate:g} % of characters are mistyped and corrected.")
        if settings.burstiness > 0:
            parts.append("The rhythm comes in bursts rather than even noise.")
        if settings.difficulty_weight > 0:
            parts.append("Pauses stretch before hard words.")
        if not parts:
            return (
                "All behaviour models are off: typing is evenly paced, with no "
                "holds, slips or word-based pauses."
            )
        return " ".join(parts)

    @staticmethod
    def _variability_note(settings: TypingSettings) -> str:
        """Explain the current variability level in plain language."""
        if settings.variability == 0:
            return "Metronomic — every keystroke is evenly spaced."
        if settings.variability < 25:
            return "Slight variation in keystroke spacing."
        if settings.variability < 60:
            return "Natural rhythm with short breaks at spaces and punctuation."
        if settings.variability < 85:
            return "Pronounced rhythm: expect the occasional longer pause."
        return "Very irregular — best for slow fields that drop fast input."

    def _update_countdown_label(self) -> None:
        """Show the countdown and hotkeys in a compact two-line hint."""
        countdown = self.settings.typing.countdown
        hotkeys = self.settings.hotkeys

        lead = (
            f"Starts {countdown:g}s after you press Start."
            if countdown > 0
            else "Typing begins immediately."
        )
        hints = [
            f"{label} {_display_hotkey(spec)}"
            for label, spec in (
                ("start", hotkeys.start),
                ("pause", hotkeys.pause),
                ("stop", hotkeys.stop),
            )
            if spec
        ]
        self.countdown_label.setText(
            lead + ("   " + " · ".join(hints) if hints else "")
        )
        self.countdown_label.setToolTip("\n".join([lead, *hints]))

    # -------------------------------------------------------------------- theme
    def apply_theme(self, theme: str, persist: bool = True) -> None:
        """Apply ``theme`` to the application and update dependent widgets.

        Args:
            theme: ``"system"``, ``"light"`` or ``"dark"``.
            persist: Store the choice in ``self.settings`` (skipped while
                restoring saved state).
        """
        app = QApplication.instance()
        if app is None:  # pragma: no cover - defensive
            return
        self._resolved_theme = apply_theme(app, theme)
        self.status_pill.set_theme(self._resolved_theme)
        self.theme_button.setText(
            "☀ Light" if self._resolved_theme is Theme.DARK else "🌙 Dark"
        )
        if persist:
            self.settings.theme = theme
        self.themeChanged.emit(self._resolved_theme)

    def toggle_theme(self) -> None:
        """Flip between light and dark."""
        target = Theme.LIGHT if self._resolved_theme is Theme.DARK else Theme.DARK
        self.apply_theme(target.value)
        self._log(f"Theme: {target.value}")

    # ---------------------------------------------------------------- transport
    def start_typing(self) -> None:
        """Validate input, then start a run (honouring the countdown)."""
        if self.run_controller.state in ACTIVE_STATES:
            return
        text = prepare_payload(self.editor.toPlainText())
        if not text.strip():
            self._flash_status("Nothing to type — add some text first")
            self.editor.setFocus()
            return
        if not self.platform_report.keyboard_available:
            self.banner.show_report(self.platform_report)
            self._log("Cannot start: keyboard control is unavailable")
            return

        settings = self.current_typing_settings()
        self.settings.typing = settings
        if self.run_controller.start(text, settings):
            self._log(
                f"Starting: {len(text):,} chars · {describe_speed(settings)}"
                + (f" · {settings.repeat_count}×" if settings.repeat_count > 1 else "")
                + (" · looping" if settings.loop_forever else "")
            )

    def toggle_pause(self) -> None:
        """Pause a running run, or resume a paused one."""
        if self.run_controller.toggle_pause():
            return
        state = self.run_controller.state
        if state is RunState.COUNTDOWN:
            self._flash_status("Countdown cannot be paused — press Stop instead")

    def stop_typing(self) -> None:
        """Immediately abort the run (panic path)."""
        if self.run_controller.state not in ACTIVE_STATES:
            return
        self.run_controller.stop()
        self._log("Stop requested")

    # -------------------------------------------------------------- run signals
    def _on_run_state(self, state: RunState) -> None:
        """Reflect a state change in the UI."""
        self._apply_state(state)

    def _apply_state(self, state: RunState) -> None:
        """Enable/disable controls for ``state`` and update the status pill."""
        self.status_pill.set_state(state)
        active = state in ACTIVE_STATES
        typing_active = state is RunState.TYPING
        paused = state is RunState.PAUSED

        self.start_button.setEnabled(not active)
        self.start_button.setText("Starting…" if state is RunState.COUNTDOWN else "Start typing")
        self.pause_button.setEnabled(typing_active or paused)
        self.pause_button.setText("Resume" if paused else "Pause")
        self.stop_button.setEnabled(active)

        for widget in (
            self.editor,
            self.load_button,
            self.paste_button,
            self.clear_button,
            self.speed_slider,
            self.speed_spin,
            self.variability_slider,
            self.variability_spin,
            self.humanize_check,
            self.dwell_min_spin,
            self.dwell_max_spin,
            self.typo_spin,
            self.burst_slider,
            self.burst_spin,
            self.difficulty_slider,
            self.difficulty_spin,
            self.repeat_check,
            self.repeat_spin,
            self.loop_check,
            self.loop_delay_spin,
        ):
            widget.setEnabled(not active)

        if state is RunState.PAUSED:
            self._set_status("Paused — press Resume or the pause hotkey")
        elif state is RunState.TYPING:
            self._set_status("Typing…")
        elif state is RunState.COUNTDOWN:
            self._set_status("Counting down — click into the target window")

    def _on_progress(self, progress: RunProgress) -> None:
        """Update the progress bar and counter labels."""
        total = progress.total_chars
        if total:
            fraction = int(round(progress.fraction * 1000))
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(fraction)
            self.progress_bar.setFormat("%p%")
            self.progress_label.setText(f"{progress.typed_chars:,} / {total:,} characters")
        else:
            # Infinite loop: show movement without a percentage.
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText(f"{progress.typed_chars:,} characters")

        passes = progress.total_passes
        if passes and passes > 1:
            self.status_bar.showMessage(
                f"Pass {progress.pass_index} of {passes} · {progress.typed_chars:,} characters",
                3000,
            )

    def _on_countdown(self, remaining: float) -> None:
        """Show the countdown in the status bar and pill."""
        if remaining <= 0:
            self._set_status("Typing…", timeout=0)
            return
        self._set_status(f"Starting in {remaining:.0f}s — click into the target window", 0)

    def _on_run_finished(self, result: RunResult) -> None:
        """Summarise the run, reset the UI and log the outcome."""
        self.progress_bar.setRange(0, 1000)
        if result.completed:
            self.progress_bar.setValue(1000)
            summary = (
                f"Finished: {result.typed_chars:,} characters in "
                f"{format_duration(result.elapsed)}"
            )
            if result.passes_completed > 1:
                summary += f" ({result.passes_completed} runs)"
            if result.skipped:
                summary += f" · {result.skipped} character(s) could not be sent"
            if result.typos:
                summary += f" · {result.typos} typo(s) corrected"
            self._log(summary)
            self._set_status(summary, timeout=8000)
        elif result.error:
            self._log(f"Run failed: {result.error}")
            self._set_status("Run failed — see the activity log", timeout=8000)
            self.banner.show_message("Typing failed", result.error, "error")
        else:
            summary = f"Stopped after {result.typed_chars:,} characters"
            self._log(summary)
            self._set_status(summary, timeout=6000)

        self._apply_state(RunState.IDLE)
        self.refresh_estimate()

    # ------------------------------------------------------------------ hotkeys
    def _register_hotkeys(self) -> None:
        """(Re)register global hotkeys from the current settings."""
        if not self.platform_report.keyboard_available:
            self.hotkey_status_label.setText("Global hotkeys unavailable")
            return

        specs = self.settings.hotkeys
        registered = self.hotkeys.start(
            bindings={
                "start": self._hotkey_start,
                "pause": self._hotkey_pause,
                "stop": self._hotkey_stop,
            },
            specs={"start": specs.start, "pause": specs.pause, "stop": specs.stop},
        )
        errors = self.hotkeys.errors
        if errors:
            for error in errors:
                self._log(f"Hotkey problem: {error}")
            self.banner.show_message(
                "Some hotkeys are unavailable",
                "These bindings could not be registered:\n"
                + "\n".join(f"• {error}" for error in errors)
                + "\n\nChoose different combinations in Preferences → Hotkeys.",
                "warning",
            )

        if registered:
            active = self.hotkeys.active_bindings
            parts: list[str] = []
            for action in ("start", "pause", "stop"):
                if action in active:
                    parts.append(_display_hotkey(active[action]))
            self.hotkey_status_label.setText(
                "Global hotkeys: " + " · ".join(parts) if parts else ""
            )
        else:
            self.hotkey_status_label.setText("Global hotkeys inactive")

    def _hotkey_start(self) -> None:
        """Global Start binding: raise the window and begin a run."""
        if self.run_controller.state in ACTIVE_STATES:
            return
        self._restore_window()
        self.start_typing()

    def _hotkey_pause(self) -> None:
        """Global pause/resume binding."""
        self.toggle_pause()

    def _hotkey_stop(self) -> None:
        """Global panic binding: halt instantly, avoiding extra UI work."""

    # ------------------------------------------------------------------ dialogs
    def open_settings(self) -> None:
        """Show the preferences dialog and apply accepted changes."""
        if self.run_controller.state in ACTIVE_STATES:
            self._flash_status("Finish or stop the current run first")
            return

        dialog = SettingsDialog(self.settings, self.platform_report, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        previous_hotkeys = self.settings.hotkeys
        self.settings = dialog.result_settings()
        self._persist_settings()

        self.apply_theme(self.settings.theme)
        if self.settings.hotkeys != previous_hotkeys:
            self._register_hotkeys()
            self._log("Hotkeys updated")
        self._update_countdown_label()
        self.refresh_estimate()
        self._flash_status("Preferences saved")

    def open_profiles(self) -> None:
        """Show the snippet manager and load the chosen profile."""
        if self.run_controller.state in ACTIVE_STATES:
            self._flash_status("Finish or stop the current run first")
            return

        dialog = ProfilesDialog(
            self.profile_repository,
            self.editor.toPlainText(),
            self.current_typing_settings(),
            self._active_profile_id,
            self,
        )
        dialog.exec()
        profile = dialog.selected_profile
        if profile is not None:
            self._load_profile(profile)

    def _load_profile(self, profile: Profile) -> None:
        """Apply a profile's text and settings to the UI."""
        self._loading_profile = True
        try:
            self._suppress_controls(True)
            self.editor.setPlainText(profile.text)
            typing = profile.typing
            self.speed_slider.setValue(typing.wpm)
            self.speed_spin.setValue(typing.wpm)
            self.variability_slider.setValue(typing.variability)
            self.variability_spin.setValue(typing.variability)
            self.humanize_check.setChecked(typing.humanize_pauses)
            self._apply_behaviour_widgets(typing)
            _select_combo(self.indent_combo, typing.indent_mode)
            self.repeat_check.setChecked(typing.repeat_count > 1 or typing.loop_forever)
            self.repeat_spin.setValue(max(MIN_REPEAT, typing.repeat_count))
            self.loop_check.setChecked(typing.loop_forever)
            self.loop_delay_spin.setValue(typing.loop_delay)
            self._suppress_controls(False)
        finally:
            self._loading_profile = False

        self._active_profile_id = profile.id
        self.settings.active_profile_id = profile.id
        self.settings.typing = profile.typing
        if profile.hotkeys is not None and profile.hotkeys != self.settings.hotkeys:
            self.settings.hotkeys = profile.hotkeys
            self._register_hotkeys()

        self._sync_repeat_enabled()
        self._refresh_counts()
        self.refresh_estimate()
        self._update_profile_badge()
        self._persist_settings()
        self._log(f"Loaded snippet '{profile.name}' ({len(profile.text):,} chars)")
        self._flash_status(f"Loaded “{profile.name}”")

    def _update_profile_badge(self) -> None:
        """Show which snippet is loaded, flagging unsaved edits."""
        if self._loading_profile:
            return
        if not self._active_profile_id:
            self.profile_badge.setText("")
            return
        profile = self.profile_repository.load().get(self._active_profile_id)
        if profile is None:
            self._active_profile_id = None
            self.profile_badge.setText("")
            return
        modified = profile.text != self.editor.toPlainText()
        suffix = " · edited" if modified else ""
        self.profile_badge.setText(f"Snippet: {profile.name}{suffix}")

    # -------------------------------------------------------------------- status
    def _set_status(self, message: str, timeout: int = 0) -> None:
        """Show ``message`` in the status bar (``timeout`` in ms, 0 = sticky)."""
        self.status_bar.showMessage(message, timeout)

    def _flash_status(self, message: str, timeout: int = 4000) -> None:
        """Show a transient status message."""
        self._set_status(message, timeout)

    def _reset_transient_status(self) -> None:
        """Return the status bar to its idle text."""
        if self.run_controller.state not in ACTIVE_STATES:
            self._set_status("Ready", 0)

    def _log(self, message: str) -> None:
        """Append to the on-screen activity log."""
        LOGGER.info("%s", message)
        self.log_panel.append_line(message)

    def _on_banner_dismissed(self) -> None:
        """Hook for the dismissal (kept for debugging)."""
        LOGGER.debug("Permission banner dismissed by the user")

    def _restore_window(self) -> None:
        """Bring the window to the front (used by the global Start hotkey)."""
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------- persistence
    def _persist_settings(self) -> None:
        """Write ``settings.json``, reporting failures to the log."""
        try:
            ensure_app_data_dir()
            self.settings.to_dict()
            from ..config.jsonstore import JsonStore
            from ..config.paths import settings_file

            store = JsonStore(settings_file())
            store.save(self.settings.to_dict())
        except Exception as exc:
            LOGGER.warning("Could not save settings: %s", exc)
            self._log(f"Settings could not be saved: {exc}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        """Stop runs, persist state and release the global hotkeys."""
        if self.run_controller.state in ACTIVE_STATES:
            confirm = QMessageBox.question(
                self,
                "Quit AutoTyper",
                "Typing is still in progress. Stop it and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.run_controller.shutdown()
        self.hotkeys.stop()

        self.settings.geometry = bytes(
            self.saveGeometry().toBase64()
        ).decode("ascii")
        self.settings.typing = self.current_typing_settings()
        self._persist_settings()

        self._status_timer.stop()
        super().closeEvent(event)


def _select_combo(combo: QComboBox, value: str) -> None:
    """Select the entry whose data equals ``value`` (first entry if not found)."""
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


def _display_hotkey(spec: str) -> str:
    """Return the pretty form of ``spec``, falling back to the raw string."""
    try:
        from ..core.hotkeys import parse_hotkey

        return parse_hotkey(spec).display
    except Exception:
        return spec
