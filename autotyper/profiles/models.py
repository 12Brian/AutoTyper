"""Profile data models.

Profiles are immutable-ish dataclasses: the repository replaces entries rather
than mutating them, which keeps the JSON file the single source of truth and
makes undo/redo style features trivial to add later.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ..config.models import HotkeySettings, TypingSettings

#: Maximum characters stored in a profile name.
MAX_NAME_LENGTH = 80

#: Maximum characters in one profile payload (5 MB of text is plenty).
MAX_TEXT_LENGTH = 5_000_000

_WHITESPACE_RE = re.compile(r"\s+")


def new_profile_id() -> str:
    """Return a fresh, sortable-enough unique profile identifier."""
    return uuid.uuid4().hex[:12]


def utc_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clean_name(name: str, fallback: str = "Untitled snippet") -> str:
    """Normalise a user-supplied profile name.

    Args:
        name: Raw name typed by the user.
        fallback: Used when the cleaned name is empty.

    Returns:
        A single-line name no longer than :data:`MAX_NAME_LENGTH`.

    Example:
        >>> clean_name("  My   snippet\\n ")
        'My snippet'
    """
    collapsed = _WHITESPACE_RE.sub(" ", (name or "").strip())
    if not collapsed:
        return fallback
    return collapsed[:MAX_NAME_LENGTH]


@dataclass(frozen=True, slots=True)
class Profile:
    """A named snippet together with the settings used to type it.

    Attributes:
        id: Stable identifier used as the dictionary key.
        name: Display name (unique, case-insensitively, within a collection).
        text: The payload, newline-normalised.
        typing: Typing settings restored when the profile is loaded.
        hotkeys: Optional per-profile hotkey overrides. ``None`` means "use the
            application hotkeys"; a value replaces them for this profile.
        created_at: ISO-8601 UTC creation timestamp.
        updated_at: ISO-8601 UTC modification timestamp.
    """

    id: str = field(default_factory=new_profile_id)
    name: str = "New snippet"
    text: str = ""
    typing: TypingSettings = field(default_factory=TypingSettings)
    hotkeys: HotkeySettings | None = None
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def normalized(self) -> Profile:
        """Return a copy with cleaned name/text and clamped settings."""
        return replace(
            self,
            name=clean_name(self.name),
            text=(self.text or "")[:MAX_TEXT_LENGTH],
            typing=self.typing.normalized(),
            hotkeys=self.hotkeys.normalized() if self.hotkeys is not None else None,
            created_at=self.created_at or utc_timestamp(),
            updated_at=self.updated_at or utc_timestamp(),
        )

    def touch(self) -> Profile:
        """Return a copy with an updated ``updated_at`` timestamp."""
        return replace(self, updated_at=utc_timestamp())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible mapping."""
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "text": self.text,
            "typing": self.typing.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.hotkeys is not None:
            payload["hotkeys"] = self.hotkeys.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Profile:
        """Build a normalized profile from untyped JSON data."""
        hotkeys_data = data.get("hotkeys")
        return cls(
            id=str(data.get("id") or new_profile_id()),
            name=str(data.get("name") or "Untitled snippet"),
            text=str(data.get("text") or ""),
            typing=TypingSettings.from_dict(data.get("typing")),
            hotkeys=HotkeySettings.from_dict(hotkeys_data) if isinstance(hotkeys_data, dict) else None,
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        ).normalized()
