"""Saved snippets ("profiles") and their persistence.

A profile is a named payload plus the typing/hotkey configuration that should be
restored with it. Profiles live in ``profiles.json`` next to ``settings.json`` in
the user's app-data directory.
"""

from __future__ import annotations

from .collection import ProfileCollection
from .models import Profile, new_profile_id
from .repository import ProfileError, ProfileRepository

__all__ = [
    "Profile",
    "ProfileCollection",
    "ProfileError",
    "ProfileRepository",
    "new_profile_id",
]
