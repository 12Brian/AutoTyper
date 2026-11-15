"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the package importable when the suite is run from a source checkout.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point AutoTyper's data directory at a temporary folder.

    Args:
        tmp_path: Pytest's per-test temporary directory.
        monkeypatch: Used to set ``AUTOTYPER_DATA_DIR``.

    Returns:
        The temporary directory that now acts as the app-data folder.
    """
    target = tmp_path / "data"
    target.mkdir()
    monkeypatch.setenv("AUTOTYPER_DATA_DIR", str(target))
    return target


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any inherited override so default paths can be asserted."""
    monkeypatch.delenv("AUTOTYPER_DATA_DIR", raising=False)
