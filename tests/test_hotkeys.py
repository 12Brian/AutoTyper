"""Tests for hotkey parsing, validation and conflict detection."""

from __future__ import annotations

import pytest
from autotyper.config.models import DEFAULT_HOTKEYS, HotkeySettings
from autotyper.core.hotkeys import (
    HotkeyError,
    find_conflicts,
    parse_hotkey,
    to_pynput_spec,
    validate_hotkey,
)


# -------------------------------------------------------------------- parsing
@pytest.mark.parametrize(
    ("spec", "canonical", "display"),
    [
        ("ctrl+alt+t", "ctrl+alt+t", "Ctrl + Alt + T"),
        ("Ctrl+Alt+T", "ctrl+alt+t", "Ctrl + Alt + T"),
        ("alt+ctrl+t", "ctrl+alt+t", "Ctrl + Alt + T"),
        ("f9", "f9", "F9"),
        ("F12", "f12", "F12"),
        ("shift+space", "shift+space", "Shift + Space"),
        ("ctrl+shift+pageup", "ctrl+shift+page_up", "Ctrl + Shift + Page Up"),
        ("escape", "esc", "Esc"),
        ("control+return", "ctrl+enter", "Ctrl + Enter"),
        ("  ctrl + alt + p  ", "ctrl+alt+p", "Ctrl + Alt + P"),
    ],
)
def test_parse_hotkey_normalises(spec: str, canonical: str, display: str) -> None:
    """Modifier order, aliases and casing are all canonicalised."""
    parsed = parse_hotkey(spec)
    assert parsed.canonical == canonical
    assert parsed.display == display


def test_parse_hotkey_round_trips_its_own_output() -> None:
    """Canonical strings must be re-parseable (they are stored in JSON)."""
    for spec in ("ctrl+alt+t", "f9", "shift+page_up", "ctrl+shift+esc"):
        first = parse_hotkey(spec)
        second = parse_hotkey(first.canonical)
        assert second.canonical == first.canonical
        assert second.display == first.display


@pytest.mark.parametrize(
    "spec",
    ["", "   ", "ctrl+", "+", "ctrl+alt", "ctrl+t+u", "ctrl+ctrl+t", "ctrl+nosuchkey", None],
)
def test_parse_hotkey_rejects_invalid_specs(spec: str | None) -> None:
    """Invalid bindings raise ``HotkeyError`` with a helpful message."""
    with pytest.raises(HotkeyError):
        parse_hotkey(spec)  # type: ignore[arg-type]


def test_validate_hotkey_returns_message_or_none() -> None:
    """The settings dialog shows the returned string inline."""
    assert validate_hotkey("ctrl+alt+t") is None
    message = validate_hotkey("ctrl+")
    assert message is not None
    assert "non-modifier" in message or "key" in message.lower()


# ----------------------------------------------------------------- conflicts
def test_find_conflicts_detects_duplicates() -> None:
    """Two actions bound to the same combination are reported."""
    problems = find_conflicts({"start": "ctrl+alt+t", "stop": "CTRL+ALT+T"})
    assert len(problems) == 1
    assert "Ctrl + Alt + T" in problems[0]


def test_find_conflicts_ignores_empty_bindings() -> None:
    """Disabled bindings never conflict with each other."""
    assert find_conflicts({"start": "f9", "pause": "", "stop": ""}) == []


def test_find_conflicts_ignores_unparseable_bindings() -> None:
    """A broken binding is reported by validation, not as a conflict."""
    assert find_conflicts({"start": "f9", "stop": "not a key"}) == []


def test_defaults_are_unique_and_valid() -> None:
    """The shipped defaults must not collide."""
    assert find_conflicts(DEFAULT_HOTKEYS) == []
    for spec in DEFAULT_HOTKEYS.values():
        assert validate_hotkey(spec) is None


def test_hotkey_settings_normalises() -> None:
    """Stored bindings are lower-cased and trimmed."""
    settings = HotkeySettings(start=" Ctrl+Alt+T ", pause="F8", stop="")
    normalised = settings.normalized()
    assert normalised.start == "ctrl+alt+t"
    assert normalised.pause == "f8"
    assert normalised.stop == ""


def test_hotkey_settings_round_trip() -> None:
    """``to_dict``/``from_dict`` preserves the bindings."""
    original = HotkeySettings(start="ctrl+shift+f1", pause="ctrl+alt+p", stop="esc")
    restored = HotkeySettings.from_dict(original.to_dict())
    assert restored == original


# --------------------------------------------------------------- pynput bridge
def test_to_pynput_spec_uses_pynput_syntax() -> None:
    """pynput expects ``<ctrl>+<alt>+t``-style strings."""
    assert to_pynput_spec("ctrl+alt+t") == "<ctrl>+<alt>+t"
    assert to_pynput_spec("f9") == "<f9>"
    assert to_pynput_spec("shift+page_up") == "<shift>+<page_up>"


def test_to_pynput_spec_rejects_unparseable_bindings() -> None:
    """Broken bindings raise rather than silently binding nothing."""
    with pytest.raises(HotkeyError):
        to_pynput_spec("ctrl+alt+")
