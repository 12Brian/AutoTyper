"""Reusable widgets shared by the main window and dialogs.

Each widget is self-contained and exposes plain Qt signals/properties so the
main window stays a thin coordinator rather than a bag of painting code.
"""

from __future__ import annotations

from .banner import Banner
from .cards import Card, Divider, SectionLabel, Slider, ValueReadout
from .hotkey_edit import HotkeyEdit
from .status_pill import StatusPill

__all__ = [
    "Banner",
    "Card",
    "Divider",
    "HotkeyEdit",
    "SectionLabel",
    "Slider",
    "StatusPill",
    "ValueReadout",
]
