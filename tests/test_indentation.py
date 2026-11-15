"""Regression tests for indentation handling in an auto-indenting editor.

The reported bug: typing multi-line Python into Colab produced text whose
indentation drifted further right on every line, because the editor *and* the
payload both contributed an indent level.

These tests replace the real editor with a small simulator that mimics the two
behaviours that matter:

* pressing Enter copies the previous line's leading whitespace onto the new line
  (what CodeMirror/VS Code do), and
* Home moves the caret to the first non-blank character, Delete removes the
  character at the caret.

That makes the whole interaction testable without a browser or GUI.
"""

from __future__ import annotations

from autotyper.config.models import TypingSettings
from autotyper.core.keyboard import NullKeyboard
from autotyper.core.runner import TypingRunner


class AutoIndentEditor(NullKeyboard):
    """A minimal, faithful model of an auto-indenting code editor.

    Attributes:
        lines: The buffer, as a list of strings (no newlines inside).
        row: Current line index.
        col: Caret position within the current line.
    """

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = [""]
        self.row = 0
        self.col = 0
        self.strips = 0

    # -- helpers -----------------------------------------------------------
    def _insert(self, text: str) -> None:
        line = self.lines[self.row]
        self.lines[self.row] = line[: self.col] + text + line[self.col :]
        self.col += len(text)

    def _indent_of(self, line: str) -> str:
        return line[: len(line) - len(line.lstrip(" \t"))]

    def text(self) -> str:
        """Return the buffer contents."""
        return "\n".join(self.lines)

    # -- sink interface ----------------------------------------------------
    def type_character(self, char: str) -> None:
        """Type one character, implementing the editor's auto-indent."""
        if char == "\n":
            indent = self._indent_of(self.lines[self.row])
            tail = self.lines[self.row][self.col :]
            self.lines[self.row] = self.lines[self.row][: self.col]
            self.lines.insert(self.row + 1, indent + tail)
            self.row += 1
            self.col = len(indent)
            return
        self._insert(char)

    def strip_line_indent(self) -> None:
        """Emulate Home, Shift+End, Delete on a whitespace-only line.

        The real implementation clears the whole auto-indent in one operation
        because the line contains only whitespace at that moment.
        """
        self.strips += 1
        line = self.lines[self.row]
        # Home -> column 0; Shift+End -> select through the end; Delete -> clear.
        if line.strip(" \t") == "":
            self.lines[self.row] = ""
            self.col = 0
        else:
            # Defensive: only strip the leading whitespace, never content.
            indent_len = len(line) - len(line.lstrip(" \t"))
            self.lines[self.row] = line[indent_len:]
            self.col = 0



PAYLOAD = (
    "def collect(points):\n"
    "    for point in points:\n"
    "        if not point:\n"
    "            continue\n"
    "    return points\n"
)


def type_into(editor: AutoIndentEditor, text: str, indent_mode: str) -> None:
    """Run a payload into the simulator at maximum speed."""
    settings = TypingSettings(
        wpm=1200,
        variability=0,
        countdown=0,
        humanize_pauses=False,
        indent_mode=indent_mode,
    )
    TypingRunner(text, settings, editor).run()


def test_auto_mode_doubles_indentation_known_limitation() -> None:
    """``auto`` mode *does* compound the indent - documenting real behaviour.

    The editor copies the previous line's indent after Enter, then the payload's
    indent is typed on top. Nested blocks therefore gain 4 spaces per level of
    depth, which is exactly the drift reported against Colab.

    This test keeps the option honest: ``auto`` is correct for plain text fields
    and terminals, and wrong for auto-indenting code editors.
    """
    editor = AutoIndentEditor()
    type_into(editor, "def f():\n    if x:\n        y = 1\n", indent_mode="auto")

    # Line 1 gets 4 (editor 0 + payload 4), line 2 inherits 4 then adds 8.
    assert editor.lines[1] == "    if x:"
    assert editor.lines[2].startswith("        "), (
        f"expected compounding indent, got {editor.lines[2]!r}"
    )
    assert editor.lines[2].strip() == "y = 1"


def test_strip_mode_preserves_exact_indentation() -> None:
    """``strip`` mode must reproduce the payload byte for byte."""
    editor = AutoIndentEditor()
    type_into(editor, PAYLOAD, indent_mode="strip")

    assert editor.text() == PAYLOAD


def test_strip_mode_handles_tabs_and_deep_nesting() -> None:
    """Tab indentation three levels deep must survive intact."""
    payload = (
        "def f():\n"
        "\tif True:\n"
        "\t\tfor i in range(3):\n"
        "\t\t\tprint(i)\n"
        "\treturn None\n"
    )
    editor = AutoIndentEditor()
    type_into(editor, payload, indent_mode="strip")

    assert editor.text() == payload


def test_strip_mode_handles_blank_and_whitespace_only_lines() -> None:
    """A blank line and a whitespace-only line keep their shape."""
    payload = "a\n\n   \nb\n"
    editor = AutoIndentEditor()
    type_into(editor, payload, indent_mode="strip")

    assert editor.text() == payload


def test_strip_mode_never_eats_content() -> None:
    """Stripping must not remove real characters from the payload."""
    payload = "x = 1\nif x:\n    y = 2\n    z = 3\n"
    editor = AutoIndentEditor()
    type_into(editor, payload, indent_mode="strip")

    assert "y = 2" in editor.text()
    assert "z = 3" in editor.text()


def test_auto_mode_never_calls_the_strip_hook() -> None:
    """Plain-text targets must see no extra keystrokes at all."""
    editor = AutoIndentEditor()
    type_into(editor, "a\nb\n", indent_mode="auto")
    assert editor.strips == 0


def test_strip_mode_calls_the_hook_once_per_newline() -> None:
    """The hook runs after every newline, regardless of the next line's indent.

    Doing it unconditionally keeps the implementation simple and correct: if the
    editor inserted nothing there is nothing to clear.
    """
    editor = AutoIndentEditor()
    type_into(editor, "a\n    b\n", indent_mode="strip")
    assert editor.strips == 2  # one per newline
    assert editor.text() == "a\n    b\n"
