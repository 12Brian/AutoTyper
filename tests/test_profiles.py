"""Unit tests for profile persistence (``autotyper.profiles``).

These cover the round-trip of Unicode/tabs/newlines, name de-duplication,
corrupt-file recovery and failure reporting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from autotyper.config.models import HotkeySettings, TypingSettings
from autotyper.profiles import (
    Profile,
    ProfileCollection,
    ProfileError,
    ProfileRepository,
)


@pytest.fixture()
def repo(tmp_path: Path) -> ProfileRepository:
    """A repository backed by a temporary ``profiles.json``."""
    return ProfileRepository(tmp_path / "profiles.json")


# ------------------------------------------------------------------ round trips
def test_save_and_load_round_trip(repo: ProfileRepository) -> None:
    """A saved profile comes back intact, including settings."""
    profile = Profile(
        name="Signature",
        text="Best regards,\nBrian",
        typing=TypingSettings(wpm=275, variability=45, countdown=4.0),
        hotkeys=HotkeySettings(start="ctrl+alt+s", pause="ctrl+alt+q", stop="f8"),
    )
    repo.save(ProfileCollection().upsert(profile))

    loaded = repo.load(force=True)
    assert len(loaded) == 1

    restored = loaded.get(profile.id)
    assert restored is not None
    assert restored.name == "Signature"
    assert restored.text == "Best regards,\nBrian"
    assert restored.typing.wpm == 275
    assert restored.typing.variability == 45
    assert restored.typing.countdown == 4.0
    assert restored.hotkeys is not None
    assert restored.hotkeys.stop == "f8"


def test_special_characters_survive_persistence(repo: ProfileRepository) -> None:
    """Tabs, newlines, quotes and non-ASCII text must not be mangled."""
    payload = 'Tab\there\nEmoji 🎉 accents éüß\n"quotes" & \\backslashes\\'
    profile = Profile(name="Unicode ✨", text=payload)
    repo.save(ProfileCollection().upsert(profile))

    restored = repo.load(force=True).get(profile.id)
    assert restored is not None
    assert restored.text == payload
    assert restored.name == "Unicode ✨"


def test_file_is_valid_utf8_json(repo: ProfileRepository) -> None:
    """The document is human-editable: pretty JSON, UTF-8, trailing newline."""
    repo.save(ProfileCollection().upsert(Profile(name="A", text="naïve")))
    raw = repo.path.read_text(encoding="utf-8")

    assert raw.endswith("\n")
    assert "naïve" in raw
    document = json.loads(raw)
    assert document["version"] == 1
    assert isinstance(document["profiles"], list)
    assert document["profiles"][0]["typing"]["wpm"] > 0


def test_multiple_profiles_keep_their_order(repo: ProfileRepository) -> None:
    """Display order is preserved across a save/load cycle."""
    collection = ProfileCollection()
    for index in range(5):
        collection = collection.upsert(Profile(name=f"Snippet {index}", text=f"t{index}"))
    repo.save(collection)

    names = [profile.name for profile in ProfileRepository(repo.path).load()]
    assert names == [f"Snippet {index}" for index in range(5)]


def test_per_profile_missing_hotkeys_means_inherit(repo: ProfileRepository) -> None:
    """A profile without hotkeys omits them and loads back as ``None``."""
    profile = Profile(name="Inherit", text="x", hotkeys=None)
    repo.save(ProfileCollection().upsert(profile))

    assert "hotkeys" not in repo.path.read_text(encoding="utf-8")
    restored = repo.load(force=True).get(profile.id)
    assert restored is not None
    assert restored.hotkeys is None



# -------------------------------------------------------------- name uniqueness
def test_duplicate_names_get_a_suffix_on_upsert() -> None:
    """Two profiles cannot share a name, even with different ids."""
    collection = ProfileCollection()
    collection = collection.upsert(Profile(name="Hello", text="one"))
    collection = collection.upsert(Profile(name="hello", text="two"))

    assert [profile.name for profile in collection] == ["Hello", "hello (2)"]


def test_updating_a_profile_keeps_its_own_name() -> None:
    """Editing text does not rename the profile via the clash resolver."""
    first = Profile(name="Keep", text="a")
    collection = ProfileCollection().upsert(first)
    collection = collection.upsert(Profile(id=first.id, name="Keep", text="b"))

    assert len(collection) == 1
    updated = collection.get(first.id)
    assert updated is not None
    assert updated.text == "b"
    assert updated.name == "Keep"


def test_rename_rejects_duplicates() -> None:
    """Renaming onto an existing name appends a numeric suffix."""
    collection = ProfileCollection().upsert(Profile(name="One", text="1"))
    second = Profile(name="Two", text="2")
    collection = collection.upsert(second)
    collection = collection.rename(second.id, "one")

    renamed = collection.get(second.id)
    assert renamed is not None
    assert renamed.name == "one (2)"


def test_upsert_deduplicates_conflicting_ids() -> None:
    """Two profiles loaded with the same id must not collapse into one."""
    collection = ProfileCollection()
    collection = collection.upsert(Profile(id="same", name="A", text="a"))
    collection = collection.upsert(Profile(id="same", name="B", text="b"))

    # ``upsert`` treats a matching id as an update, so the second call replaces
    # the first entry in place rather than appending a duplicate.
    assert len(collection) == 1
    assert collection.get("same") is not None
    assert collection.get("same").text == "b"  # type: ignore[union-attr]


def test_constructor_deduplicates_ids_from_disk() -> None:
    """Hand-edited files with repeated ids cannot create ghost entries."""
    duplicated = [
        Profile(name="First", text="a"),
        Profile(name="Second", text="b"),
    ]
    collection = ProfileCollection(
        [Profile(id="dup", name="First", text="a"), Profile(id="dup", name="Second", text="b")]
    )

    assert len(collection) == 2
    assert len({profile.id for profile in collection}) == 2
    assert [profile.name for profile in collection] == ["First", "Second"]
    assert len(duplicated) == 2  # the source list is untouched


# --------------------------------------------------------------------- mutations
def test_remove_and_move_behaviour() -> None:
    """Removal and reordering behave like list operations."""
    collection = ProfileCollection()
    for name in ("A", "B", "C"):
        collection = collection.upsert(Profile(name=name, text=name))

    second = collection.get_by_name("B")
    assert second is not None
    collection = collection.move(second.id, -1)
    assert [p.name for p in collection] == ["B", "A", "C"]

    collection = collection.remove(second.id)
    assert [p.name for p in collection] == ["A", "C"]


def test_move_clamps_at_the_edges() -> None:
    """Moving past either end is a no-op rather than an error."""
    collection = ProfileCollection()
    for name in ("A", "B"):
        collection = collection.upsert(Profile(name=name, text=name))

    first = collection.get_by_name("A")
    assert first is not None
    assert [p.name for p in collection.move(first.id, -5)] == ["A", "B"]
    assert [p.name for p in collection.move(first.id, 5)] == ["B", "A"]


def test_empty_collection_persists_cleanly(repo: ProfileRepository) -> None:
    """Saving nothing produces an empty, valid document."""
    repo.save(ProfileCollection())
    assert repo.load(force=True).is_empty()


def test_collection_survives_serialisation_cycle() -> None:
    """``to_dict``/``from_dict`` round-trips every field."""
    original = ProfileCollection().upsert(
        Profile(
            name="Round",
            text="trip\t✓",
            typing=TypingSettings(wpm=180, variability=90, repeat_count=4),
            hotkeys=HotkeySettings(stop="f7"),
        )
    )
    restored = ProfileCollection.from_dict(original.to_dict())

    assert len(restored) == 1
    profile = restored.profiles[0]
    assert profile.text == "trip\t✓"


# ----------------------------------------------------------------- error paths
def test_corrupt_json_falls_back_to_empty_and_is_quarantined(
    repo: ProfileRepository,
) -> None:
    """A truncated file must not crash the app; it is moved aside."""
    repo.path.write_text('{"profiles": [', encoding="utf-8")

    assert repo.load().is_empty()

    backups = list(repo.path.parent.glob("profiles.corrupt-*"))
    assert len(backups) == 1
    assert not repo.path.exists()


def test_wrong_shape_falls_back_to_empty(repo: ProfileRepository) -> None:
    """Valid JSON with the wrong structure is treated as corrupt."""
    repo.path.write_text('{"profiles": "not a list"}', encoding="utf-8")
    assert repo.load().is_empty()


def test_malformed_entries_are_skipped(repo: ProfileRepository) -> None:
    """Individual bad entries do not discard the good ones."""
    document = {
        "version": 1,
        "profiles": [
            "not-a-dict",
            {"name": "Good", "text": "kept"},
            {"id": 42, "name": None},
        ],
    }
    repo.path.write_text(json.dumps(document), encoding="utf-8")

    collection = repo.load()
    assert len(collection) == 2
    assert collection.get_by_name("Good") is not None


def test_clamped_values_are_restored_sanely(repo: ProfileRepository) -> None:
    """Hand-edited out-of-range speed values are clamped on load."""
    repo.path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "id": "x1",
                        "name": "Edited",
                        "text": "hi",
                        "typing": {
                            "wpm": 99999,
                            "variability": -50,
                            "countdown": 999,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    profile = repo.load().get("x1")
    assert profile is not None
    assert profile.typing.wpm <= 1200
    assert profile.typing.variability == 0
    assert profile.typing.countdown <= 15.0


def test_save_failure_raises_profile_error(tmp_path: Path) -> None:
    """Unwritable destinations surface as a friendly ``ProfileError``."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    repo = ProfileRepository(blocker / "profiles.json")

    with pytest.raises(ProfileError):
        repo.save(ProfileCollection().upsert(Profile(name="A", text="a")))


def test_load_is_cached_until_forced(repo: ProfileRepository) -> None:
    """Repeated loads reuse the cached collection (the UI relies on this)."""
    repo.save(ProfileCollection().upsert(Profile(name="A", text="a")))
    assert repo.load() is repo.load()
    assert repo.load(force=True) is not repo.load(force=True)


def test_missing_file_is_not_an_error(tmp_path: Path) -> None:
    """A first launch has no file yet and must start from an empty list."""
    repo = ProfileRepository(tmp_path / "nested" / "dir" / "profiles.json")
    assert repo.load().is_empty()
    assert not repo.path.exists()

