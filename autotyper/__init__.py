"""AutoTyper - a polished, cross-platform desktop auto-typing utility.

The package is split into four layers:

``autotyper.config``
    Portable settings models plus JSON persistence helpers (no Qt imports).
``autotyper.core``
    The typing engine, timing math, global hotkeys and platform checks. The
    timing and runner modules are deliberately free of Qt/pynput imports so
    they can be unit tested headlessly.
``autotyper.profiles``
    Stored snippets and their per-profile settings.
``autotyper.ui``
    PySide6 widgets, theming and the main window.
"""

from __future__ import annotations

__version__ = "1.0.0"

#: Shown in the header badge, the About tab and the Windows installer metadata.
#: Kept here so every surface reads the same string.
__author__ = "Otachi"

__all__ = ["__author__", "__version__"]
