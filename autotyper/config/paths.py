"""Platform-correct locations for AutoTyper's persistent data.

The location can be overridden with the ``AUTOTYPER_DATA_DIR`` environment
variable, which is handy for portable installs, testing and CI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "AutoTyper"
_ENV_OVERRIDE = "AUTOTYPER_DATA_DIR"


def _user_config_root() -> Path:
    """Return the platform's per-user configuration root."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base)
    return Path.home() / ".config"


def app_data_dir() -> Path:
    """Return (without creating) the directory holding AutoTyper's data files."""
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    return _user_config_root() / APP_DIR_NAME


def ensure_app_data_dir() -> Path:
    """Create the application data directory if needed and return it.

    Raises:
        OSError: If the directory cannot be created (e.g. read-only profile).
    """
    directory = app_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def settings_file() -> Path:
    """Path of the global ``settings.json`` file."""
    return app_data_dir() / "settings.json"


def profiles_file() -> Path:
    """Path of the ``profiles.json`` file holding saved snippets."""
    return app_data_dir() / "profiles.json"


def log_file() -> Path:
    """Path of the rotating activity log file."""
    return app_data_dir() / "activity.log"
