"""Core business logic: timing, typing backends, the run loop and platform checks.

Modules here avoid importing Qt. ``runner`` and ``timing`` additionally avoid
pynput so they can be exercised in unit tests without a display or event loop.
"""

from __future__ import annotations

__all__ = ["timing"]
