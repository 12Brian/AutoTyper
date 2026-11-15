"""Configuration primitives: data locations, JSON persistence and settings models.

This layer is intentionally free of Qt and pynput imports so that configuration
can be loaded and validated in headless environments (tests, CLI tooling).
"""

from __future__ import annotations

from .jsonstore import JsonStore, JsonStoreError
from .models import (
    DEFAULT_HOTKEYS,
    AppSettings,
    HotkeySettings,
    TypingSettings,
)
from .paths import app_data_dir, log_file, profiles_file, settings_file

__all__ = [
    "AppSettings",
    "DEFAULT_HOTKEYS",
    "HotkeySettings",
    "JsonStore",
    "JsonStoreError",
    "TypingSettings",
    "app_data_dir",
    "log_file",
    "profiles_file",
    "settings_file",
]
