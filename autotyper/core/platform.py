"""Platform capability and permission detection.

Keyboard injection is privileged on macOS (Accessibility) and depends on a
working input backend on Linux (X11 vs. Wayland). Rather than failing with a
cryptic pynput traceback, the app calls :func:`check_keyboard_access` at startup
and shows the returned remediation steps in a banner.

The probes are cheap and non-destructive: importing pynput is the only side
effect, and no input events are generated.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass, field

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlatformReport:
    """Outcome of a platform capability probe.

    Attributes:
        platform: ``"Windows"``, ``"macOS"``, ``"Linux"`` or ``"Unknown"``.
        keyboard_available: True when a keyboard controller can be constructed.
        session_type: ``"x11"``, ``"wayland"``, ``"native"`` or ``"unknown"``.
        summary: One-line description shown in the banner/settings panel.
        steps: Ordered remediation instructions shown to the user.
        severity: ``"ok"``, ``"warning"`` or ``"error"`` for banner styling.
    """

    platform: str
    keyboard_available: bool
    session_type: str
    summary: str
    steps: tuple[str, ...] = field(default_factory=tuple)
    severity: str = "ok"

    @property
    def needs_attention(self) -> bool:
        """True when the banner should be visible."""
        return self.severity != "ok"

    def steps_text(self) -> str:
        """Render the remediation steps as a numbered, line-broken string."""
        if not self.steps:
            return ""
        return "\n".join(f"{index}. {step}" for index, step in enumerate(self.steps, start=1))


def platform_name() -> str:
    """Return a friendly name for the running platform."""
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("linux"):
        return "Linux"
    return "Unknown"


def detect_session_type() -> str:
    """Detect the Linux display server type.

    Returns:
        ``"native"`` on Windows/macOS, ``"wayland"`` or ``"x11"`` on Linux, and
        ``"unknown"`` when no session environment is present (headless CI).
    """
    if not sys.platform.startswith("linux"):
        return "native"
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session in {"wayland", "x11"}:
        return session
    return "unknown"


def _probe_pynput_keyboard() -> tuple[bool, str]:
    """Try to build a pynput keyboard controller.

    Returns:
        ``(available, message)`` where ``message`` explains a failure.
    """
    try:
        from pynput.keyboard import Controller  # noqa: PLC0415 - lazy import
    except Exception as exc:  # pragma: no cover - platform dependent
        return False, str(exc) or exc.__class__.__name__

    try:
        Controller()
    except Exception as exc:  # pragma: no cover - platform dependent
        return False, str(exc) or exc.__class__.__name__
    return True, ""


_MACOS_STEPS = (
    "Open System Settings → Privacy & Security → Accessibility.",
    "Enable the switch next to AutoTyper (add it with the + button if it is not listed).",
    "Also allow it under Privacy & Security → Input Monitoring.",
    "Quit and relaunch AutoTyper (macOS only applies the permission on restart).",
)

_MACOS_DEV_STEPS = _MACOS_STEPS + (
    "When running from source, grant the permission to your terminal app "
    "(Terminal, iTerm2, VS Code) instead of the Python binary.",
)

_LINUX_WAYLAND_STEPS = (
    "Global hotkeys and synthetic keystrokes need X11. Log out and pick an 'X11' "
    "(Xorg) session at the login screen.",
    "Alternatively launch with QT_QPA_PLATFORM=xcb so Qt uses XWayland.",
    "Some Wayland desktops additionally require the Remote Desktop portal permission.",
)

_LINUX_X11_STEPS = (
    "Install the X11 bindings: sudo apt install python3-xlib (Debian/Ubuntu) or "
    "sudo dnf install python3-xlib (Fedora).",
    "Make sure DISPLAY is set and you are running inside a graphical session.",
    "If AutoTyper was started as root, run it as your desktop user instead.",
)


def check_keyboard_access() -> PlatformReport:
    """Probe keyboard control availability and build remediation guidance.

    Returns:
        A :class:`PlatformReport` describing whether typing can work and, when
        it cannot, exactly what the user should do about it.

    Example:
        >>> isinstance(check_keyboard_access().keyboard_available, bool)
        True
    """
    platform = platform_name()
    available, detail = _probe_pynput_keyboard()
    session = detect_session_type()

    if platform == "macOS":
        if available:
            return PlatformReport(
                platform=platform,
                keyboard_available=True,
                session_type=session,
                summary="Accessibility access granted - typing and global hotkeys are ready.",
            )
        steps = _MACOS_STEPS if getattr(sys, "frozen", False) else _MACOS_DEV_STEPS
        return PlatformReport(
            platform=platform,
            keyboard_available=False,
            session_type=session,
            summary=(
                "macOS blocked keyboard control, so AutoTyper cannot type or listen "
                f"for hotkeys yet ({detail})."
            ),
            steps=steps,
            severity="error",
        )

    if platform == "Linux":
        if available and session in {"x11", "native"}:
            return PlatformReport(
                platform=platform,
                keyboard_available=True,
                session_type=session,
                summary="X11 keyboard backend ready.",
            )
        if session == "wayland":
            return PlatformReport(
                platform=platform,
                keyboard_available=False,
                session_type=session,
                summary=(
                    "A Wayland session was detected. Synthetic keystrokes and global "
                    "hotkeys are unreliable under native Wayland."
                ),
                steps=_LINUX_WAYLAND_STEPS,
                severity="warning",
            )
        return PlatformReport(
            platform=platform,
            keyboard_available=False,
            session_type=session,
            summary=f"Keyboard backend unavailable on Linux ({detail or 'no display'}).",
            steps=_LINUX_X11_STEPS,
            severity="error",
        )

    if platform == "Windows" and not available:
        return PlatformReport(
            platform=platform,
            keyboard_available=False,
            session_type=session,
            summary=f"Windows refused keyboard control ({detail}).",
            steps=(
                "Close applications that block input injection (some anti-cheat and "
                "remote-desktop tools do).",
                "Run AutoTyper at the same integrity level as the target window - "
                "elevated and non-elevated windows cannot send input to each other.",
                "Repair the Microsoft Visual C++ runtime if pynput fails to load.",
            ),
            severity="error",
        )

    return PlatformReport(
        platform=platform,
        keyboard_available=available,
        session_type=session,
        summary="Keyboard control is ready." if available else "Keyboard control unavailable.",
        severity="ok" if available else "error",
    )


def is_gui_available() -> bool:
    """Return whether a Qt GUI can probably be created in this environment.

    Used to show a clear error instead of a Qt abort when the app is launched
    from a headless SSH session.
    """
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def interpreter_hint() -> str:
    """Return a short interpreter path, used in macOS permission instructions."""
    return sys.executable or (shutil.which("python") or "python")

    return True, ""
