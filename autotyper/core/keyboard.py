"""Keyboard simulation backends.

The runner talks to a :class:`KeyboardSink` rather than pynput directly, so unit
tests can assert exactly which characters were emitted without touching a real
keyboard. :class:`PynputKeyboard` is the production implementation and is the
only module in ``core`` that imports pynput (besides ``hotkeys``).
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Protocol, runtime_checkable

LOGGER = logging.getLogger(__name__)


class KeyboardUnavailableError(RuntimeError):
    """Raised when the OS refuses to let us synthesise keyboard input."""


@runtime_checkable
class KeyboardSink(Protocol):
    """Minimal interface the typing runner needs from a keyboard."""

    def type_character(self, char: str) -> None:
        """Send a single printable character (or Tab/Enter for ``\\t``/``\\n``)."""

    def press_character(self, char: str) -> None:
        """Press and *hold* a key without releasing it.

        Used for realistic dwell time: the runner presses, waits the drawn hold
        duration, then calls :meth:`release_character`. Implementations must
        resolve the same key object for both calls so the release is not lost.
        """

    def release_character(self, char: str) -> None:
        """Release a key previously held with :meth:`press_character`."""

    def press_backspace(self) -> None:
        """Press and release Backspace once (used by error-correction loops)."""

    def release_modifiers(self) -> None:
        """Best-effort release of Shift/Ctrl/Alt/Cmd to avoid stuck keys."""

    def flush(self) -> None:
        """Hint that queued events should be delivered (no-op for most backends)."""

    def strip_line_indent(self) -> None:
        """Remove any indentation the editor inserted at the start of the line.

        Called immediately after a newline when ``indent_mode`` is ``"strip"``.
        Editors that auto-indent (Colab, VS Code, most IDEs) insert their own
        leading whitespace on Enter; leaving it in place makes the payload's own
        indentation add on top of it, so each line drifts further right.
        """

    def settle(self) -> None:
        """Discard pending modifier residue before the first character.

        Called once immediately before typing starts, after the user has let go
        of the hotkey. Implementations should wait briefly for the physical keys
        to be released and clear any half-delivered events, so a leaked trigger
        letter cannot end up at the start of the typed text.
        """


class NullKeyboard:
    """A no-op sink used for previews, tests and dry runs.

    Press/release pairs are recorded separately from :attr:`typed` so tests can
    assert the dwell-time choreography (every press must be matched by a
    release) without a real keyboard. The lists are deliberately *not* called
    ``events``: test doubles in the suite use that name for their own ordered
    log.
    """

    def __init__(self) -> None:
        self.typed: list[str] = []
        self.pressed: list[str] = []
        self.released: list[str] = []
        self.backspaces = 0
        self.strips = 0

    def type_character(self, char: str) -> None:  # noqa: D102 - protocol docstring
        self.typed.append(char)

    def press_character(self, char: str) -> None:  # noqa: D102
        # Recording the press *and* delegating to ``type_character`` means test
        # doubles that model an editor buffer (and therefore only override
        # ``type_character``) still receive the text when dwell time is on.
        self.pressed.append(char)
        self.type_character(char)

    def release_character(self, char: str) -> None:  # noqa: D102
        self.released.append(char)

    def press_backspace(self) -> None:  # noqa: D102
        self.backspaces += 1
        self.typed.append("\b")

    def strip_line_indent(self) -> None:  # noqa: D102
        self.strips += 1

    def release_modifiers(self) -> None:  # noqa: D102
        return None

    def flush(self) -> None:  # noqa: D102
        return None

    def settle(self) -> None:  # noqa: D102
        return None


class PynputKeyboard:
    """Type characters with pynput, degrading gracefully on unsupported glyphs.

    pynput can inject arbitrary Unicode on Windows (``KEYEVENTF_UNICODE``) and
    macOS (``CGEventKeyboardSetUnicodeString``); on X11 it remaps a spare
    keycode. Characters the platform still rejects are counted in
    :attr:`skipped` and reported instead of aborting the whole run, which keeps
    long batch jobs usable.

    Args:
        controller: Optional pre-built controller (used by tests).
    """

    def __init__(self, controller: object | None = None) -> None:
        self._controller = controller if controller is not None else self._build_controller()
        self._enter = self._lookup("enter")
        self._tab = self._lookup("tab")
        self._home = self._lookup("home")
        self._delete = self._lookup("delete")
        self._backspace = self._lookup("backspace")
        self.skipped = 0
        self._warned: set[str] = set()

    @staticmethod
    def _build_controller() -> object:
        """Create a pynput keyboard controller or raise a friendly error."""
        try:
            from pynput.keyboard import Controller  # noqa: PLC0415 - lazy import
        except Exception as exc:  # pragma: no cover - platform dependent
            raise KeyboardUnavailableError(
                "pynput could not initialise keyboard control. On Linux install the "
                "X11 dependencies (python3-xlib) or run under an X11 session; on macOS "
                "grant Accessibility permission."
            ) from exc

        try:
            return Controller()
        except Exception as exc:  # pragma: no cover - platform dependent
            raise KeyboardUnavailableError(
                f"Keyboard controller could not be created: {exc}"
            ) from exc

    def _lookup(self, name: str) -> object:
        """Resolve a pynput ``Key`` member by name (``enter``/``tab``)."""
        try:
            from pynput.keyboard import Key  # noqa: PLC0415 - lazy import

            return getattr(Key, name)
        except Exception:  # pragma: no cover - platform dependent
            return None

    def _tap(self, key: object) -> None:
        """Press and release a single special key."""
        if key is None:
            return
        self._controller.press(key)  # type: ignore[attr-defined]
        self._controller.release(key)  # type: ignore[attr-defined]

    def strip_line_indent(self) -> None:
        """Remove whatever indentation the editor auto-inserted.

        After Enter, editors such as Colab, VS Code and most IDEs insert their own
        leading whitespace. If the payload's indentation is then typed on top, each
        line gains an extra level and the text drifts rightwards line by line.

        The line is guaranteed to contain only whitespace at this point (the
        payload's own characters for that line have not been typed yet), so the
        whole indent can be cleared in one shot:

        * ``Home`` moves to column 0 on a whitespace-only line, and
        * ``Shift+End`` selects the rest of the line, and
        * ``Delete`` removes the selection.

        This is independent of indent width and of tabs-versus-spaces, which a
        single-character ``Delete`` loop would get wrong for deep nesting.
        """
        controller = self._controller
        end = self._lookup("end")
        shift = self._lookup("shift")
        if self._home is None or self._delete is None or shift is None or end is None:
            return
        try:
            controller.press(self._home)  # type: ignore[attr-defined]
            controller.release(self._home)  # type: ignore[attr-defined]
            controller.press(shift)  # type: ignore[attr-defined]
            controller.press(end)  # type: ignore[attr-defined]
            controller.release(end)  # type: ignore[attr-defined]
            controller.release(shift)  # type: ignore[attr-defined]
            controller.press(self._delete)  # type: ignore[attr-defined]
            controller.release(self._delete)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - platform dependent
            LOGGER.debug("Could not strip indentation", exc_info=True)

    # ------------------------------------------------------------------- sink
    def _resolve_key(self, char: str) -> object | None:
        """Return the pynput key object for ``char`` (or ``None`` if unusable).

        Both the press and the release of a dwell-time keystroke go through this
        one helper, so the pair always refers to the same key object. pynput's
        ``release`` resolves strings the same way ``press`` does, but keeping a
        single resolution point makes the symmetry explicit and lets the caller
        skip a key it already knows cannot be sent.
        """
        if char == "\n":
            return self._enter
        if char == "\t":
            return self._tab
        if char in ("\b", "\x7f"):
            return self._backspace
        if not char.isprintable():
            return None
        return char

    def type_character(self, char: str) -> None:
        """Send one character, mapping newlines/tabs to key presses.

        Args:
            char: A single character, ``"\\n"`` or ``"\\t"``.
        """
        controller = self._controller
        try:
            if char == "\n" and self._enter is not None:
                controller.press(self._enter)  # type: ignore[attr-defined]
                controller.release(self._enter)  # type: ignore[attr-defined]
                return
            if char == "\t" and self._tab is not None:
                controller.press(self._tab)  # type: ignore[attr-defined]
                controller.release(self._tab)  # type: ignore[attr-defined]
                return
            if char in ("\n", "\t"):
                # No Key enum available (very unusual); fall back to the char.
                controller.type(char)  # type: ignore[attr-defined]
                return
            if not char.isprintable():
                return
            controller.type(char)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - platform dependent
            self.skipped += 1
            label = repr(char)
            if label not in self._warned:
                self._warned.add(label)
                LOGGER.warning("Could not type %s: %s", label, exc)

    def press_character(self, char: str) -> None:
        """Press ``char`` and hold it (see :meth:`release_character`)."""
        key = self._resolve_key(char)
        if key is None:
            return
        try:
            self._controller.press(key)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - platform dependent
            self.skipped += 1
            label = repr(char)
            if label not in self._warned:
                self._warned.add(label)
                LOGGER.warning("Could not press %s: %s", label, exc)

    def release_character(self, char: str) -> None:
        """Release a key previously held with :meth:`press_character`."""
        key = self._resolve_key(char)
        if key is None:
            return
        try:
            self._controller.release(key)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - platform dependent
            LOGGER.debug("Could not release %r", char, exc_info=True)

    def press_backspace(self) -> None:
        """Press and release Backspace once (error correction)."""
        if self._backspace is None:
            return
        try:
            self._controller.press(self._backspace)  # type: ignore[attr-defined]
            self._controller.release(self._backspace)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - platform dependent
            LOGGER.debug("Could not press Backspace", exc_info=True)

    def release_modifiers(self) -> None:
        """Release Shift/Ctrl/Alt/Cmd so a held hotkey never leaks into the text."""
        try:
            from pynput.keyboard import Key  # noqa: PLC0415 - lazy import
        except Exception:  # pragma: no cover - platform dependent
            return
        for name in ("ctrl", "ctrl_l", "ctrl_r", "alt", "alt_l", "alt_r", "shift", "shift_l",
                     "shift_r", "cmd", "cmd_l", "cmd_r"):
            key = getattr(Key, name, None)
            if key is None:
                continue
            try:
                self._controller.release(key)  # type: ignore[attr-defined]
            except Exception:
                continue

    def flush(self) -> None:
        """No-op; pynput delivers events synchronously per call."""
        return None

    def settle(self) -> None:
        """Release modifiers, wait for the hotkey to be let go, clear residue.

        A global hotkey is fired while the user is still physically holding its
        keys. If typing began immediately, a late-delivered trigger keystroke
        would land in front of the text - and with a ``Ctrl``-based binding that
        single leaked letter becomes a shortcut (new tab, paste, save) that
        silently destroys text.

        This method therefore:

        1. explicitly releases Ctrl/Alt/Shift/Cmd,
        2. waits until the physical keys are actually up (a human needs up to
           ~1 s to release a hotkey), and
        3. on Windows, flushes the calling thread's input queue so any already
           queued leftover events are discarded instead of being consumed by the
           target application.
        """
        self.release_modifiers()
        self._wait_for_modifier_release()
        self._discard_queued_input()

    def _modifiers_down(self) -> bool:
        """Return whether any modifier is still physically held."""
        if sys.platform == "win32":
            try:
                import ctypes  # noqa: PLC0415 - platform specific

                vk = ctypes.windll.user32.GetAsyncKeyState
                for code in (0x11, 0x12, 0x5B, 0x5C, 0x10):  # Ctrl Alt LWin RWin Shift
                    if vk(code) & 0x8000:
                        return True
            except Exception:  # pragma: no cover - platform dependent
                return False
            return False

        if sys.platform.startswith("linux"):
            # X11 exposes real modifier state through the XQueryPointer mask.
            try:  # pragma: no cover - platform dependent
                from pynput._util.xorg import display_manager

                with display_manager() as display:
                    _, _, _, mask = display.screen().root.query_pointer()._data
                    return bool(mask & 0x0D)  # Shift|Control|Mod1
            except Exception:
                return False
        return False

    def _wait_for_modifier_release(self, timeout: float = 1.2) -> None:
        """Poll until no modifier is held (or ``timeout`` elapses)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._modifiers_down():
                return
            time.sleep(0.02)
        LOGGER.debug("Modifiers still held after %.1fs; continuing anyway", timeout)

    def _discard_queued_input(self) -> None:
        """Flush already-queued input events for this thread (Windows only).

        ``SendInput`` delivers into the input queue of the thread that owns the
        foreground window *and* the calling thread's own queue. Anything the
        hotkey left behind is stale by the time we get here, so dropping it
        prevents a leaked character from leading the typed text.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes  # noqa: PLC0415 - platform specific
            from ctypes import wintypes  # noqa: PLC0415

            user32 = ctypes.windll.user32
            PM_NOREMOVE = 0x0000
            WM_KEYFIRST = 0x0100
            WM_KEYLAST = 0x0109
            queued = wintypes.MSG()
            flushed = 0
            while user32.PeekMessageW(
                ctypes.byref(queued), None, WM_KEYFIRST, WM_KEYLAST, PM_NOREMOVE
            ):
                user32.GetMessageW(ctypes.byref(queued), None, WM_KEYFIRST, WM_KEYLAST)
                flushed += 1
                if flushed > 64:  # safety valve
                    break
            if flushed:
                LOGGER.debug("Discarded %d queued key event(s) before typing", flushed)
        except Exception:  # pragma: no cover - platform dependent
            LOGGER.debug("Could not flush the input queue", exc_info=True)
