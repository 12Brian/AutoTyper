"""Parsing, validation and registration of global hotkeys.

Hotkeys are stored as canonical, human-readable strings such as ``ctrl+alt+t``
or ``f9``. Keeping the storage format independent of pynput means settings stay
valid across platforms and can be edited by hand.

This module imports pynput lazily so that parsing/validation (used by the
settings UI and by tests) works on headless machines.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)

#: Modifier aliases accepted in the settings file.
_MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "ctl": "ctrl",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "shift": "shift",
    "cmd": "cmd",
    "command": "cmd",
    "win": "cmd",
    "super": "cmd",
    "meta": "cmd",
}

#: Canonical modifier order used when normalising a binding.
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "cmd")

#: Named keys accepted as the non-modifier part of a binding.
_SPECIAL_KEYS: dict[str, str] = {
    "space": "space",
    "spacebar": "space",
    "tab": "tab",
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "insert": "insert",
    "home": "home",
    "end": "end",
    "pageup": "page_up",
    "pgup": "page_up",
    "pagedown": "page_down",
    "pgdn": "page_down",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "pause": "pause",
    "printscreen": "print_screen",
    "prtsc": "print_screen",
    "scrolllock": "scroll_lock",
    "capslock": "caps_lock",
    "numlock": "num_lock",
}

#: Canonical names accepted verbatim, so ``parse_hotkey`` can round-trip its own
#: output (e.g. ``parse_hotkey("page_up")``).
_CANONICAL_KEYS: frozenset[str] = frozenset(
    {
        "space",
        "tab",
        "enter",
        "esc",
        "backspace",
        "delete",
        "insert",
        "home",
        "end",
        "page_up",
        "page_down",
        "up",
        "down",
        "left",
        "right",
        "pause",
        "print_screen",
        "scroll_lock",
        "caps_lock",
        "num_lock",
    }
)

_FKEY_RE = re.compile(r"^f([1-9]|1[0-9]|2[0-4])$")
_SINGLE_CHAR_RE = re.compile(r"^[a-z0-9`\-=\[\]\\;',./]$")

#: Pretty names for modifiers in the "Ctrl + Alt + T" display form.
_MODIFIER_LABELS: dict[str, str] = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "cmd": "Cmd" if sys.platform == "darwin" else "Win",
}


class HotkeyError(ValueError):
    """Raised when a hotkey string cannot be parsed or is not registerable."""


@dataclass(frozen=True, slots=True)
class ParsedHotkey:
    """A validated hotkey.

    Attributes:
        modifiers: Canonical modifier names in fixed order (``ctrl``, ``alt``,
            ``shift``, ``cmd``).
        key: Canonical key name: a single character, ``f1``-``f24``, or one of
            the names in :data:`_SPECIAL_KEYS`.
        display: Human-friendly rendering, e.g. ``"Ctrl + Alt + T"``.
    """

    modifiers: tuple[str, ...]
    key: str
    display: str

    @property
    def canonical(self) -> str:
        """Re-serialised binding, e.g. ``"ctrl+alt+t"``."""
        return "+".join((*self.modifiers, self.key))


def parse_hotkey(spec: str) -> ParsedHotkey:
    """Parse and validate a hotkey string.

    Args:
        spec: Binding text such as ``"Ctrl+Alt+T"``, ``"f9"`` or
            ``"shift+space"``. An empty string is not a valid binding.

    Returns:
        The parsed binding with canonical modifier order.

    Raises:
        HotkeyError: If the string is empty, has no key part, contains unknown
            tokens, or repeats a modifier.

    Example:
        >>> parse_hotkey("Alt+Ctrl+F9").canonical
        'ctrl+alt+f9'
    """
    if spec is None:
        raise HotkeyError("Hotkey is empty.")
    raw = spec.strip()
    if not raw:
        raise HotkeyError("Hotkey is empty.")

    parts = [part.strip().lower() for part in raw.split("+") if part.strip()]
    if not parts:
        raise HotkeyError(f"'{raw}' does not contain any keys.")

    modifiers: set[str] = set()
    key: str | None = None
    for part in parts:
        normalized_modifier = _MODIFIER_ALIASES.get(part)
        if normalized_modifier is not None:
            if key is not None:
                raise HotkeyError(f"'{raw}' has a modifier after the key.")
            if normalized_modifier in modifiers:
                raise HotkeyError(f"'{raw}' repeats the '{normalized_modifier}' modifier.")
            modifiers.add(normalized_modifier)
            continue

        if key is not None:
            raise HotkeyError(f"'{raw}' has more than one non-modifier key.")

        if _FKEY_RE.match(part):
            key = part
        elif part in _SPECIAL_KEYS:
            key = _SPECIAL_KEYS[part]
        elif part in _CANONICAL_KEYS or _SINGLE_CHAR_RE.match(part):
            key = part
        else:
            raise HotkeyError(
                f"'{part}' is not a supported key. Use a letter, digit, F1-F24 or a "
                "named key such as Space, Tab, Enter or Esc."
            )

    if key is None:
        raise HotkeyError(f"'{raw}' needs a non-modifier key (e.g. ctrl+alt+t).")

    ordered = tuple(name for name in _MODIFIER_ORDER if name in modifiers)
    labels = [_MODIFIER_LABELS[name] for name in ordered]
    labels.append(_key_label(key))
    return ParsedHotkey(modifiers=ordered, key=key, display=" + ".join(labels))


def _key_label(key: str) -> str:
    """Render the non-modifier part of a binding for display.

    Args:
        key: Canonical key name (``"t"``, ``"f9"``, ``"page_up"``).

    Returns:
        A display label such as ``"T"``, ``"F9"`` or ``"Page Up"``.
    """
    if len(key) == 1:
        return key.upper()
    if key.startswith("f") and key[1:].isdigit():
        return key.upper()
    return " ".join(word.capitalize() for word in key.split("_"))


def validate_hotkey(spec: str) -> str | None:
    """Validate a binding for the settings dialog.

    Args:
        spec: Binding text from a line edit.

    Returns:
        ``None`` when the binding is valid, otherwise a user-facing message.

    Example:
        >>> validate_hotkey("ctrl+alt+t") is None
        True
        >>> bool(validate_hotkey("ctrl+"))
        True
    """
    try:
        parse_hotkey(spec)
    except HotkeyError as exc:
        return str(exc)
    return None


def find_conflicts(bindings: dict[str, str]) -> list[str]:
    """Report duplicate bindings among the start/pause/stop actions.

    Args:
        bindings: Mapping of action name to binding text.

    Returns:
        A list of human-readable conflict descriptions (empty when unique).
    """
    seen: dict[str, str] = {}
    problems: list[str] = []
    for action, spec in bindings.items():
        if not spec.strip():
            continue
        try:
            parsed = parse_hotkey(spec)
        except HotkeyError:
            continue
        if parsed.canonical in seen:
            problems.append(f"'{action}' and '{seen[parsed.canonical]}' both use {parsed.display}.")
        else:
            seen[parsed.canonical] = action
    return problems


def to_pynput_spec(spec: str) -> str:
    """Convert a canonical binding into pynput's ``<ctrl>+<alt>+t`` format.

    ``pynput.keyboard.GlobalHotKeys`` accepts strings in this format and parses
    them itself, which is more robust than constructing ``HotKey`` objects by
    hand (its constructor takes a keys *set* plus a callback).

    Args:
        spec: Canonical binding such as ``"ctrl+alt+t"`` or ``"f9"``.

    Returns:
        A pynput-compatible specification string.

    Raises:
        HotkeyError: If the binding cannot be parsed or validated by pynput.

    Example:
        >>> to_pynput_spec("ctrl+alt+t")
        '<ctrl>+<alt>+t'
    """
    parsed = parse_hotkey(spec)
    tokens = [f"<{modifier}>" for modifier in parsed.modifiers]
    if len(parsed.key) == 1:
        tokens.append(parsed.key)
    else:
        tokens.append(f"<{parsed.key}>")
    pynput_spec = "+".join(tokens)

    try:
        from pynput import keyboard  # noqa: PLC0415 - lazy import
    except Exception as exc:  # pragma: no cover - platform dependent
        raise HotkeyError(f"Global hotkeys are unavailable: {exc}") from exc

    try:
        keyboard.HotKey.parse(pynput_spec)
    except Exception as exc:  # pragma: no cover - platform dependent
        raise HotkeyError(
            f"{parsed.display} is not supported on this system ({exc})."
        ) from exc
    return pynput_spec


class GlobalHotkeyManager:
    """Register global hotkeys on a single shared pynput listener.

    One ``keyboard.GlobalHotKeys`` listener handles every binding, which keeps
    the process footprint small and makes a rebind a simple stop/start cycle.
    Callbacks run on pynput's listener thread, so they must be cheap and
    thread-safe - the UI bridge re-emits them as queued Qt signals.
    """

    def __init__(self) -> None:
        self._listener: object | None = None
        self._lock = threading.Lock()
        self._active: dict[str, str] = {}
        self._errors: list[str] = []

    @property
    def active_bindings(self) -> dict[str, str]:
        """Currently registered action → canonical binding mapping."""
        with self._lock:
            return dict(self._active)

    @property
    def errors(self) -> list[str]:
        """Non-fatal problems encountered while registering bindings."""
        return list(self._errors)

    def start(self, bindings: dict[str, Callable[[], None]], specs: dict[str, str]) -> bool:
        """(Re)register all hotkeys.

        Args:
            bindings: Mapping of action name (``start``/``pause``/``stop``) to a
                zero-argument callback.
            specs: Mapping of action name to binding text; an empty string
                disables that binding.

        Returns:
            True when the listener is running with at least one binding.
            Individual failures are collected in :attr:`errors` so the app keeps
            working without global hotkeys.
        """
        self.stop()
        self._errors = []
        hotkey_map: dict[str, Callable[[], None]] = {}
        active: dict[str, str] = {}

        for action, spec in specs.items():
            if not spec.strip():
                continue
            callback = bindings.get(action)
            if callback is None:
                continue
            try:
                pynput_spec = to_pynput_spec(spec)
                parsed = parse_hotkey(spec)
            except HotkeyError as exc:
                self._errors.append(f"{action}: {exc}")
                continue
            if pynput_spec in hotkey_map:
                self._errors.append(
                    f"{action}: {parsed.display} is already used by another action."
                )
                continue
            hotkey_map[pynput_spec] = self._wrap(callback)
            active[action] = parsed.canonical

        if not hotkey_map:
            LOGGER.info("No global hotkeys registered")
            return False

        try:
            from pynput import keyboard  # noqa: PLC0415 - lazy import

            listener = keyboard.GlobalHotKeys(hotkey_map)
            listener.daemon = True
            listener.start()
        except Exception as exc:  # pragma: no cover - platform dependent
            message = str(exc) or exc.__class__.__name__
            self._errors.append(f"Global hotkey listener failed: {message}")
            LOGGER.warning("Could not start global hotkeys: %s", message)
            return False

        with self._lock:
            self._listener = listener
            self._active = active
        LOGGER.info("Registered global hotkeys: %s", active)
        return True

    @staticmethod
    def _wrap(callback: Callable[[], None]) -> Callable[[], None]:
        """Wrap a callback so listener-thread exceptions cannot kill the listener."""

        def handler() -> None:
            try:
                callback()
            except Exception:  # pragma: no cover - defensive
                LOGGER.exception("Hotkey callback failed")

        return handler

    def stop(self) -> None:
        """Stop the listener, releasing the OS-level key hooks."""
        with self._lock:
            listener = self._listener
            self._listener = None
            self._active = {}
        if listener is None:
            return
        try:
            listener.stop()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - platform dependent
            LOGGER.debug("Hotkey listener stop() raised", exc_info=True)

    def is_running(self) -> bool:
        """Return whether a listener thread is currently alive."""
        listener = self._listener
        if listener is None:
            return False
        try:
            return bool(listener.running)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - platform dependent
            return False
