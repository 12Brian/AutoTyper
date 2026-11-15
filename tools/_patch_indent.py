"""One-off patch: wire the indentation mode into the main window."""

import pathlib

p = pathlib.Path("autotyper/ui/main_window.py")
s = p.read_text(encoding="utf-8")

# 1) include indent_combo in the signal-suppression list
s = s.replace(
    """            self.loop_delay_spin,
        ):
            widget.blockSignals(suppress)""",
    """            self.loop_delay_spin,
            self.indent_combo,
        ):
            widget.blockSignals(suppress)""",
    1,
)

# 2) include indent_mode when collecting settings
s = s.replace(
    """            humanize_pauses=self.humanize_check.isChecked(),
        ).normalized()""",
    """            humanize_pauses=self.humanize_check.isChecked(),
            indent_mode=str(self.indent_combo.currentData()),
        ).normalized()""",
    1,
)

# 3) restore the saved mode in both restore paths
s = s.replace(
    """        self.humanize_check.setChecked(typing.humanize_pauses)""",
    """        self.humanize_check.setChecked(typing.humanize_pauses)
        _select_combo(self.indent_combo, typing.indent_mode)""",
)

# 4) helper used above
s = s.replace(
    '''def _display_hotkey(spec: str) -> str:''',
    '''def _select_combo(combo, value: str) -> None:
    """Select the combo entry whose data equals ``value`` (first item if none)."""
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


def _display_hotkey(spec: str) -> str:''',
    1,
)

p.write_text(s, encoding="utf-8")
print("patched:", s.count("indent_combo"), "references")
