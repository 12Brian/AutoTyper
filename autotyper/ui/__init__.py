"""Application UI layer built on PySide6.

Everything here imports Qt; the domain logic lives in :mod:`autotyper.core`,
:mod:`autotyper.config` and :mod:`autotyper.profiles`.
"""

from __future__ import annotations

from .theme import Theme, apply_theme, detect_system_theme

__all__ = ["Theme", "apply_theme", "detect_system_theme"]
