"""The profile manager dialog.

Profiles bundle a snippet with its typing settings. The dialog edits a working
copy of the collection and, on accept, hands the caller the selected profile so
the main window can apply it.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.text import preview_text
from ..core.timing import TimingEngine, describe_speed, format_duration
from ..profiles import Profile, ProfileCollection, ProfileError, ProfileRepository
from .widgets.cards import SectionLabel


class ProfilesDialog(QDialog):
    """Manage saved snippets: load, rename, reorder, update and delete.

    Args:
        repository: Persistence gateway for the collection.
        current_text: Text currently in the editor (used by "New").
        current_typing: Typing settings selected on the main window.
        active_profile_id: Profile that should be pre-selected.
        parent: Standard Qt parent.
    """

    def __init__(
        self,
        repository: ProfileRepository,
        current_text: str,
        current_typing: object,
        active_profile_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Snippets")
        self.setModal(True)
        self.resize(640, 500)

        self._repository = repository
        self._current_text = current_text
        self._current_typing = current_typing
        self._collection: ProfileCollection = repository.load()
        self._selected: Profile | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        header = QLabel("Reusable snippets and their typing settings")
        header.setProperty("role", "subtitle")
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addLayout(self._build_list_column(), 3)
        body.addLayout(self._build_detail_column(), 4)
        outer.addLayout(body, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.load_button = self.buttons.addButton(
            "Load snippet", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.load_button.setProperty("variant", "primary")
        self.close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        if self.close_button is not None:
            self.close_button.setToolTip("Return to the editor; snippets stay saved")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self._reload_list(active_profile_id)

    # ---------------------------------------------------------------- building
    def _build_list_column(self) -> QVBoxLayout:
        """List of snippets plus New/Load/Delete buttons."""
        column = QVBoxLayout()
        column.setSpacing(6)
        column.addWidget(SectionLabel("Saved snippets"))

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._on_accept())
        column.addWidget(self.list_widget, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        for label, slot, tooltip in (
            ("New", self._on_new, "Save the editor text as a new snippet"),
            ("Load", self._on_accept, "Load the selected snippet into the editor"),
            ("Delete", self._on_delete, "Delete the selected snippet"),
        ):
            button = QPushButton(label)
            button.setToolTip(tooltip)
            button.clicked.connect(slot)
            row.addWidget(button)
        column.addLayout(row)
        return column

    def _build_detail_column(self) -> QVBoxLayout:
        """Metadata, preview and per-snippet actions."""
        column = QVBoxLayout()
        column.setSpacing(6)
        column.addWidget(SectionLabel("Details"))

        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setProperty("role", "muted")
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)
        column.addWidget(self.details)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a snippet to preview its text.")
        self.preview.setMaximumBlockCount(200)
        self.preview.setObjectName("Editor")
        column.addWidget(self.preview, 1)

        self.update_button = QPushButton("Update with current text")
        self.update_button.setToolTip(
            "Overwrite the selected snippet with the editor text and settings"
        )
        self.update_button.clicked.connect(self._on_update)
        column.addWidget(self.update_button)

        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self._on_rename)
        column.addWidget(self.rename_button)

        move_row = QHBoxLayout()
        move_row.setSpacing(6)
        self.up_button = QPushButton("Move up")
        self.up_button.clicked.connect(lambda: self._on_move(-1))
        self.down_button = QPushButton("Move down")
        self.down_button.clicked.connect(lambda: self._on_move(1))
        move_row.addWidget(self.up_button)
        move_row.addWidget(self.down_button)
        column.addLayout(move_row)
        return column

    # ------------------------------------------------------------------- state
    @property
    def selected_profile(self) -> Profile | None:
        """Profile the user chose to load (``None`` when nothing was loaded)."""
        return self._selected

    def _current_id(self) -> str | None:
        """Id of the highlighted profile."""
        item = self.list_widget.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _reload_list(self, select_id: str | None = None) -> None:
        """Rebuild the list widget from the in-memory collection."""
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for profile in self._collection:
            item = QListWidgetItem(profile.name)
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            item.setToolTip(preview_text(profile.text, limit=60) or "(empty snippet)")
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)

        if self.list_widget.count() == 0:
            self._show_details(None)
            return

        row = self._collection.index_of(select_id) if select_id else 0
        self.list_widget.setCurrentRow(max(0, row))

    def _show_details(self, profile: Profile | None) -> None:
        """Render the detail pane for ``profile``."""
        enabled = profile is not None
        for widget in (
            self.update_button,
            self.rename_button,
            self.up_button,
            self.down_button,
            self.load_button,
        ):
            widget.setEnabled(enabled)

        if profile is None:
            self.details.setText("No snippets yet. Click New to save the current text.")
            self.preview.setPlainText("")
            return

        estimate = format_duration(
            TimingEngine(profile.typing).estimate_passes_duration(profile.text)
        )
        updated = profile.updated_at.replace("T", " ").replace("Z", " UTC")
        self.details.setText(
            f"<b>{profile.name}</b><br>"
            f"{len(profile.text):,} characters · {describe_speed(profile.typing)}<br>"
            f"About {estimate} per run<br>"
            f"Updated {updated}"
        )
        self.preview.setPlainText(profile.text)

    # ----------------------------------------------------------------- actions
    def _on_selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Update the detail pane when the highlight moves."""
        if current is None:
            self._show_details(None)
            return
        self._show_details(self._collection.get(str(current.data(Qt.ItemDataRole.UserRole))))

    def _on_new(self) -> None:
        """Create a snippet from the current editor text."""
        if not self._current_text.strip():
            QMessageBox.information(
                self, "Nothing to save", "Type or load some text in the editor first."
            )
            return
        profile = Profile(
            name=self._collection.unique_name("New snippet"),
            text=self._current_text,
            typing=self._current_typing,  # type: ignore[arg-type]
        )
        self._collection = self._collection.upsert(profile)
        self._persist()
        self._reload_list(profile.id)

    def _on_update(self) -> None:
        """Overwrite the selected snippet with the editor text and settings."""
        profile = self._collection.get(self._current_id() or "")
        if profile is None:
            return
        if not self._current_text.strip():
            QMessageBox.information(
                self, "Nothing to save", "The editor is empty - nothing to store."
            )
            return
        updated = replace(
            profile,
            text=self._current_text,
            typing=self._current_typing,  # type: ignore[arg-type]
        ).touch()
        self._collection = self._collection.upsert(updated)
        self._persist()
        self._reload_list(updated.id)

    def _on_rename(self) -> None:
        """Prompt for a new name."""
        profile = self._collection.get(self._current_id() or "")
        if profile is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename snippet", "Name:", text=profile.name
        )
        if not accepted or not name.strip():
            return
        self._collection = self._collection.rename(profile.id, name)

    def _on_delete(self) -> None:
        """Delete the selected snippet after confirmation."""
        profile = self._collection.get(self._current_id() or "")
        if profile is None:
            return
        confirm = QMessageBox.question(
            self,
            "Delete snippet",
            f"Delete '{profile.name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        index = self._collection.index_of(profile.id)
        remaining = self._collection.remove(profile.id)
        next_id: str | None = None
        if len(remaining):
            next_id = remaining.profiles[min(index, len(remaining) - 1)].id
        self._collection = remaining
        self._persist()
        self._reload_list(next_id)

    def _on_move(self, delta: int) -> None:
        """Reorder the selected snippet."""
        profile_id = self._current_id()
        if profile_id is None:
            return
        moved = self._collection.move(profile_id, delta)
        if moved.profiles == self._collection.profiles:
            return
        self._collection = moved
        self._persist()
        self._reload_list(profile_id)

    def _on_accept(self) -> None:
        """Load the highlighted snippet into the main window."""
        profile = self._collection.get(self._current_id() or "")
        if profile is None:
            self.reject()
            return
        self._selected = profile
        self.accept()

    # ------------------------------------------------------------- persistence
    def _persist(self) -> None:
        """Save the working collection, reporting failures inline."""
        try:
            self._repository.save(self._collection)
        except ProfileError as exc:
            QMessageBox.critical(self, "Could not save snippets", str(exc))
