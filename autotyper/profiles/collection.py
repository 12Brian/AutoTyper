"""Collection of saved profiles with unique names.

The collection is a value type: every mutation returns a new instance, which
keeps the repository (and the JSON file) the single source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from .models import Profile, clean_name, new_profile_id


class ProfileCollection:
    """An ordered set of profiles with unique, case-insensitive names.

    The collection is the in-memory mirror of ``profiles.json``. Mutation
    methods return a new :class:`ProfileCollection` so callers can treat it as a
    value and persist it when convenient.

    Args:
        profiles: Initial profiles, in display order.

    Example:
        >>> collection = ProfileCollection().upsert(Profile(name="Signature", text="Regards"))
        >>> collection.get_by_name("signature").text
        'Regards'
    """

    def __init__(self, profiles: Iterable[Profile] = ()) -> None:
        self._profiles: list[Profile] = []
        for profile in profiles:
            self._append_unchecked(profile.normalized())

    # ------------------------------------------------------------- accessors
    def __len__(self) -> int:
        return len(self._profiles)

    def __iter__(self) -> Any:
        return iter(self._profiles)

    def __contains__(self, profile_id: object) -> bool:
        return any(profile.id == profile_id for profile in self._profiles)

    @property
    def profiles(self) -> tuple[Profile, ...]:
        """All profiles in display order."""
        return tuple(self._profiles)

    def is_empty(self) -> bool:
        """True when no profile is stored."""
        return not self._profiles

    def get(self, profile_id: str) -> Profile | None:
        """Return the profile with ``profile_id`` or ``None``."""
        for profile in self._profiles:
            if profile.id == profile_id:
                return profile
        return None

    def get_by_name(self, name: str) -> Profile | None:
        """Return the profile whose name matches case-insensitively."""
        target = clean_name(name).casefold()
        for profile in self._profiles:
            if profile.name.casefold() == target:
                return profile
        return None

    def index_of(self, profile_id: str) -> int:
        """Return the display index of ``profile_id`` (``-1`` when absent)."""
        for index, profile in enumerate(self._profiles):
            if profile.id == profile_id:
                return index
        return -1

    def unique_name(self, base: str) -> str:
        """Return ``base`` with a numeric suffix that is not yet taken.

        Args:
            base: Desired name.

        Returns:
            A unique name such as ``"Signature (2)"``.
        """
        candidate = clean_name(base)
        if self.get_by_name(candidate) is None:
            return candidate
        for counter in range(2, 1000):
            suffixed = clean_name(f"{candidate} ({counter})")
            if self.get_by_name(suffixed) is None:
                return suffixed
        return clean_name(f"{candidate} {new_profile_id()[:4]}")

    # -------------------------------------------------------------- mutations
    def _append_unchecked(self, profile: Profile) -> None:
        """Append a profile, replacing a duplicate id with a fresh one."""
        if self.get(profile.id) is not None:
            profile = replace(profile, id=new_profile_id())
        self._profiles.append(profile)

    def upsert(self, profile: Profile) -> ProfileCollection:
        """Insert a profile or update the entry with the same id.

        A name clash with a *different* profile is resolved by appending a
        numeric suffix, so names stay unique and predictable.
        """
        normalized = profile.normalized()
        clash = self.get_by_name(normalized.name)
        if clash is not None and clash.id != normalized.id:
            normalized = replace(normalized, name=self.unique_name(normalized.name))
        index = self.index_of(normalized.id)
        if index < 0:
            return ProfileCollection([*self._profiles, normalized])
        return self._replace_at(index, normalized)

    def remove(self, profile_id: str) -> ProfileCollection:
        """Return a collection without ``profile_id`` (no-op when absent)."""
        if self.get(profile_id) is None:
            return ProfileCollection(self._profiles)
        return ProfileCollection(p for p in self._profiles if p.id != profile_id)

    def rename(self, profile_id: str, new_name: str) -> ProfileCollection:
        """Return a collection with a renamed, de-duplicated profile."""
        profile = self.get(profile_id)
        if profile is None:
            return ProfileCollection(self._profiles)
        cleaned = clean_name(new_name)
        clash = self.get_by_name(cleaned)
        if clash is not None and clash.id != profile_id:
            cleaned = self.unique_name(cleaned)
        return self._replace_at(self.index_of(profile_id), replace(profile, name=cleaned))

    def move(self, profile_id: str, delta: int) -> ProfileCollection:
        """Return a collection with the profile moved by ``delta`` positions."""
        index = self.index_of(profile_id)
        if index < 0:
            return ProfileCollection(self._profiles)
        target = max(0, min(len(self._profiles) - 1, index + delta))
        if target == index:
            return ProfileCollection(self._profiles)
        profiles = list(self._profiles)
        profiles.insert(target, profiles.pop(index))
        return ProfileCollection(profiles)

    def _replace_at(self, index: int, profile: Profile) -> ProfileCollection:
        """Return a collection with the entry at ``index`` replaced."""
        profiles = list(self._profiles)
        profiles[index] = profile
        return ProfileCollection(profiles)

    # --------------------------------------------------------- (de)serialise
    def to_dict(self) -> dict[str, Any]:
        """Serialize to the ``profiles.json`` document shape."""
        return {
            "version": 1,
            "profiles": [profile.to_dict() for profile in self._profiles],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ProfileCollection:
        """Build a collection from untyped JSON, skipping malformed entries."""
        source = data or {}
        raw_profiles = source.get("profiles")
        if not isinstance(raw_profiles, list):
            return cls()
        profiles: list[Profile] = []
        for entry in raw_profiles:
            if not isinstance(entry, dict):
                continue
            try:
                profiles.append(Profile.from_dict(entry))
            except Exception:  # pragma: no cover - defensive against bad JSON
                continue
        return cls(profiles)

