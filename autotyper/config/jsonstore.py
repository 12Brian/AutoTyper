"""Small, dependency-free helper for atomically persisted JSON documents.

Every write goes to a temporary file in the same directory followed by
``os.replace`` so a crash mid-write can never truncate the user's data. If an
existing document is unreadable (corrupt JSON, wrong shape) it is renamed to
``<name>.corrupt-<timestamp>.bak`` and defaults are returned, which keeps the
application usable instead of hard-failing at startup.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


class JsonStoreError(RuntimeError):
    """Raised when a JSON document cannot be written to disk."""


class JsonStore:
    """Read/write a single JSON document with atomic replacement.

    Args:
        path: Location of the JSON document.
        defaults: Mapping returned when the file does not exist or is corrupt.
        validate: Optional structural check applied to loaded data. Returning
            ``False`` treats the document as corrupt.
    """

    def __init__(
        self,
        path: Path,
        defaults: Mapping[str, Any] | None = None,
        validate: Callable[[Any], bool] | None = None,
    ) -> None:
        self.path = Path(path)
        self._defaults: dict[str, Any] = dict(defaults or {})
        self._validate = validate

    # ------------------------------------------------------------------ read
    def load(self) -> dict[str, Any]:
        """Return the parsed document, falling back to defaults when unusable."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return json.loads(json.dumps(self._defaults))
        except OSError as exc:  # pragma: no cover - permissions dependent
            LOGGER.warning("Cannot read %s: %s", self.path, exc)
            return json.loads(json.dumps(self._defaults))

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            LOGGER.warning("Corrupt JSON in %s (%s); using defaults", self.path, exc)
            self._quarantine()
            return json.loads(json.dumps(self._defaults))

        if not isinstance(data, dict) or (
            self._validate is not None and not self._validate(data)
        ):
            LOGGER.warning("Unexpected structure in %s; using defaults", self.path)
            self._quarantine()
            return json.loads(json.dumps(self._defaults))
        return data

    # ----------------------------------------------------------------- write
    def save(self, data: Mapping[str, Any]) -> None:
        """Atomically persist ``data`` as pretty-printed UTF-8 JSON.

        Raises:
            JsonStoreError: When the file cannot be written (disk full,
                read-only directory, permissions, ...).
        """
        payload = json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(payload)
        except OSError as exc:
            raise JsonStoreError(f"Could not save {self.path}: {exc}") from exc

    def _atomic_write(self, payload: str) -> None:
        directory = self.path.parent
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

    def _quarantine(self) -> None:
        """Rename an unusable document aside so it is never silently lost."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}{self.path.suffix}")
        try:
            os.replace(self.path, target)
            LOGGER.info("Moved unreadable %s to %s", self.path, target)
        except OSError as exc:  # pragma: no cover - permissions dependent
            LOGGER.warning("Could not quarantine %s: %s", self.path, exc)

    def exists(self) -> bool:
        """Return whether the backing file is present."""
        return self.path.exists()
