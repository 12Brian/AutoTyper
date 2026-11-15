"""Load and save the profile collection on disk.

The repository wraps :class:`autotyper.config.jsonstore.JsonStore` and takes
care of the "profiles.json" document shape. All failures surface as
:class:`ProfileError` with a message that can be shown to the user directly.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.jsonstore import JsonStore, JsonStoreError
from ..config.paths import profiles_file
from .collection import ProfileCollection
from .models import Profile

LOGGER = logging.getLogger(__name__)


class ProfileError(RuntimeError):
    """Raised when profiles cannot be read from or written to disk."""


def _is_profile_document(data: object) -> bool:
    """Structural validation used by :class:`JsonStore`."""
    return isinstance(data, dict) and isinstance(data.get("profiles", []), list)


class ProfileRepository:
    """CRUD operations for the persisted profile collection.

    Args:
        path: Override the ``profiles.json`` location (used by tests).

    Example:
        >>> repo = ProfileRepository(Path(temp_dir) / "profiles.json")
        >>> repo.save(ProfileCollection().upsert(Profile(name="Hi", text="Hello")))
        >>> len(repo.load())
        1
    """

    def __init__(self, path: Path | None = None) -> None:
        self._store = JsonStore(
            path or profiles_file(),
            defaults={"version": 1, "profiles": []},
            validate=_is_profile_document,
        )
        self._cache: ProfileCollection | None = None

    @property
    def path(self) -> Path:
        """Location of the backing JSON document."""
        return self._store.path

    def load(self, force: bool = False) -> ProfileCollection:
        """Read the collection from disk.

        Args:
            force: Re-read even when a cached copy exists.

        Returns:
            The persisted collection (empty when the file is missing/corrupt).
        """
        if self._cache is not None and not force:
            return self._cache
        try:
            collection = ProfileCollection.from_dict(self._store.load())
        except JsonStoreError as exc:  # pragma: no cover - defensive
            raise ProfileError(str(exc)) from exc
        self._cache = collection
        LOGGER.debug("Loaded %d profile(s) from %s", len(collection), self.path)
        return collection

    def save(self, collection: ProfileCollection) -> None:
        """Persist ``collection`` atomically.

        Raises:
            ProfileError: If the document cannot be written.
        """
        try:
            self._store.save(collection.to_dict())
        except JsonStoreError as exc:
            raise ProfileError(
                f"Profiles could not be saved to {self.path}. {exc}"
            ) from exc
        self._cache = collection
        LOGGER.debug("Saved %d profile(s) to %s", len(collection), self.path)

    def upsert(self, profile: Profile) -> ProfileCollection:
        """Insert or update one profile and persist the result."""
        collection = self.load().upsert(profile)
        self.save(collection)
        return collection

    def delete(self, profile_id: str) -> ProfileCollection:
        """Remove a profile and persist the result."""
        collection = self.load().remove(profile_id)
        self.save(collection)
        return collection

    def reset_cache(self) -> None:
        """Drop the in-memory copy so the next :meth:`load` hits the disk."""
        self._cache = None
