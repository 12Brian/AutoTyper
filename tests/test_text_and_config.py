"""Tests for text loading/normalisation and JSON persistence primitives."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from autotyper.config.jsonstore import JsonStore, JsonStoreError
from autotyper.config.models import AppSettings, TypingSettings
from autotyper.config.paths import app_data_dir, log_file, profiles_file, settings_file
from autotyper.core.text import (
    MAX_TEXT_BYTES,
    TextLoadError,
    load_text_file,
    normalize_newlines,
    prepare_payload,
    preview_text,
)


# --------------------------------------------------------------------- newlines
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("a\nb", "a\nb"),
        ("\ufeffa\nb", "a\nb"),
        ("mixed\r\nline\rbreaks\n", "mixed\nline\nbreaks\n"),
    ],
)
def test_normalize_newlines(raw: str, expected: str) -> None:
    """CRLF, CR and a stray BOM are normalised to plain LF."""
    assert normalize_newlines(raw) == expected


def test_prepare_payload_is_idempotent() -> None:
    """Running the normaliser twice changes nothing (used before every run)."""
    once = prepare_payload("x\r\ny")
    assert prepare_payload(once) == once


# ---------------------------------------------------------------- file loading
@pytest.mark.parametrize(
    "encoding", ["utf-8", "utf-8-sig", "utf-16", "cp1252"]
)
def test_load_text_file_handles_common_encodings(tmp_path: Path, encoding: str) -> None:
    """Files saved as UTF-8/UTF-16/ANSI all load with the same text.

    cp1252 cannot represent "✓", so the payload is limited to characters every
    listed encoding supports.
    """
    text = "Hello\r\nWorld — café"
    path = tmp_path / "payload.txt"
    path.write_bytes(text.encode(encoding))

    assert load_text_file(path) == "Hello\nWorld — café"


def test_load_text_file_preserves_unicode(tmp_path: Path) -> None:
    """Astral-plane characters and symbols survive a UTF-8 round trip."""
    text = "Emoji 🎉 accents ünïcödé ✓ math ∑\n"
    path = tmp_path / "unicode.txt"
    path.write_text(text, encoding="utf-8", newline="")

    assert load_text_file(path) == text


def test_load_text_file_preserves_tabs(tmp_path: Path) -> None:
    """Tabs must survive loading (they are typed as Tab presses)."""
    path = tmp_path / "tabs.txt"
    path.write_text("a\tb\t\tc\n", encoding="utf-8")
    assert load_text_file(path) == "a\tb\t\tc\n"


def test_load_text_file_rejects_missing_file(tmp_path: Path) -> None:
    """A missing file produces a friendly, specific message."""
    with pytest.raises(TextLoadError) as excinfo:
        load_text_file(tmp_path / "nope.txt")
    assert "could not be opened" in str(excinfo.value)


def test_load_text_file_rejects_empty_file(tmp_path: Path) -> None:
    """An empty file is a user error worth reporting up front."""
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(TextLoadError) as excinfo:
        load_text_file(path)
    assert "empty" in str(excinfo.value)


def test_load_text_file_rejects_whitespace_only_file(tmp_path: Path) -> None:
    """A file with only newlines has nothing to type."""
    path = tmp_path / "blank.txt"
    path.write_text("\n\n   \n", encoding="utf-8")
    with pytest.raises(TextLoadError) as excinfo:
        load_text_file(path)
    assert "no visible text" in str(excinfo.value)


def test_load_text_file_rejects_oversized_file(tmp_path: Path) -> None:
    """Absurdly large files are refused with the limit in the message."""
    path = tmp_path / "big.txt"
    path.write_bytes(b"x" * (MAX_TEXT_BYTES + 1))
    with pytest.raises(TextLoadError) as excinfo:
        load_text_file(path)
    assert "MB" in str(excinfo.value)


# -------------------------------------------------------------------- previews
def test_preview_text_collapses_and_truncates() -> None:
    """List widgets get a single-line, length-limited preview."""
    assert preview_text("a\n b\tc") == "a b c"
    assert preview_text("") == ""
    assert preview_text("   \n ") == ""
    long = preview_text("word " * 40, limit=20)
    assert len(long) <= 20


# -------------------------------------------------------------------- json store
def test_json_store_creates_and_reads(tmp_path: Path) -> None:
    """Saving then loading returns the same mapping."""
    path = tmp_path / "doc.json"
    store = JsonStore(path, defaults={"a": 1})
    store.save({"a": 2, "b": "ü"})

    assert store.load() == {"a": 2, "b": "ü"}
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_json_store_returns_defaults_when_missing(tmp_path: Path) -> None:
    """Defaults are returned (not shared) when the file does not exist."""
    store = JsonStore(tmp_path / "absent.json", defaults={"a": 1})
    first = store.load()
    first["a"] = 99
    assert store.load() == {"a": 1}


def test_json_store_quarantines_corrupt_files(tmp_path: Path) -> None:
    """Corrupt documents are renamed aside rather than overwritten."""
    path = tmp_path / "doc.json"
    path.write_text("{oops", encoding="utf-8")
    store = JsonStore(path, defaults={"ok": True})

    assert store.load() == {"ok": True}
    assert list(tmp_path.glob("doc.corrupt-*.json"))
    assert not path.exists()


def test_json_store_validation_rejects_wrong_shapes(tmp_path: Path) -> None:
    """A custom validator can reject structurally wrong documents."""
    path = tmp_path / "doc.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    store = JsonStore(path, defaults={"ok": True}, validate=lambda d: "items" in d)

    assert store.load() == {"ok": True}


def test_json_store_write_is_atomic(tmp_path: Path) -> None:
    """No temporary files are left behind after a successful save."""
    path = tmp_path / "doc.json"
    JsonStore(path).save({"x": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["doc.json"]


def test_json_store_raises_on_unwritable_target(tmp_path: Path) -> None:
    """Write failures surface as ``JsonStoreError`` with context."""
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(JsonStoreError):
        JsonStore(blocker / "nested" / "doc.json").save({"x": 1})


# --------------------------------------------------------------- paths & models
def test_paths_follow_the_override(data_dir: Path) -> None:
    """``AUTOTYPER_DATA_DIR`` redirects every data file (portable installs)."""
    assert app_data_dir() == data_dir
    assert settings_file().parent == data_dir
    assert profiles_file().parent == data_dir
    assert log_file().parent == data_dir
    assert settings_file().name == "settings.json"
    assert profiles_file().name == "profiles.json"


def test_settings_round_trip() -> None:
    """``AppSettings`` survives a JSON cycle with nested models intact."""
    original = AppSettings(
        theme="dark",
        typing=TypingSettings(
            wpm=333, variability=66, repeat_count=3, loop_forever=True
        ),
        active_profile_id="abc123",
    )
    restored = AppSettings.from_dict(json.loads(json.dumps(original.to_dict())))

    assert restored.theme == "dark"
    assert restored.typing.wpm == 333
    assert restored.typing.variability == 66
    assert restored.typing.repeat_count == 3
    assert restored.typing.loop_forever is True
    assert restored.active_profile_id == "abc123"


def test_behaviour_settings_round_trip() -> None:
    """Dwell, typo and rhythm settings survive a JSON save/load cycle.

    Users configure these on the main window and expect them back next launch,
    so a silent reset would be a visible regression.
    """
    original = TypingSettings(
        dwell_min_ms=45,
        dwell_max_ms=115,
        typo_rate=1.5,
        burstiness=62,
        difficulty_weight=38,
    )
    restored = TypingSettings.from_dict(json.loads(json.dumps(original.to_dict())))

    assert restored.dwell_min_ms == 45
    assert restored.dwell_max_ms == 115
    assert restored.typo_rate == pytest.approx(1.5)
    assert restored.burstiness == 62
    assert restored.difficulty_weight == 38


def test_behaviour_defaults_are_all_off() -> None:
    """A fresh install (or an old settings file) behaves exactly as before.

    Every behaviour model must default to zero so upgrading cannot silently
    change how existing users' runs look or how long they take.
    """
    defaults = TypingSettings()
    assert defaults.dwell_min_ms == 0
    assert defaults.dwell_max_ms == 0
    assert defaults.typo_rate == 0.0
    assert defaults.burstiness == 0
    assert defaults.difficulty_weight == 0

    # An old settings document without the new keys must normalise to the same.
    legacy = TypingSettings.from_dict({"wpm": 250, "variability": 40})
    assert (legacy.dwell_min_ms, legacy.dwell_max_ms) == (0, 0)
    assert legacy.typo_rate == 0.0


def test_behaviour_settings_are_clamped() -> None:
    """Hostile JSON values are clamped into the supported ranges."""
    settings = TypingSettings.from_dict(
        {
            "dwell_min_ms": -50,
            "dwell_max_ms": 99_999,
            "typo_rate": 900,
            "burstiness": -20,
            "difficulty_weight": 400,
        }
    )
    assert settings.dwell_min_ms == 0
    assert settings.dwell_max_ms == 200
    assert settings.typo_rate == 5.0
    assert settings.burstiness == 0
    assert settings.difficulty_weight == 100


def test_dwell_seconds_property_matches_the_millisecond_fields() -> None:
    """Timing code works in seconds; the conversion must be exact."""
    settings = TypingSettings(dwell_min_ms=40, dwell_max_ms=95)
    assert settings.dwell_seconds == (0.04, 0.095)


def test_invalid_theme_falls_back_to_system() -> None:
    """A hand-edited theme value cannot break startup."""
    assert AppSettings.from_dict({"theme": "neon"}).theme == "system"


def test_garbage_settings_produce_valid_defaults() -> None:
    """Wildly wrong types are coerced into a usable configuration."""
    settings = AppSettings.from_dict(
        {
            "theme": None,
            "typing": {"wpm": "fast", "variability": None, "countdown": "soon"},
            "hotkeys": {"start": None},
            "active_profile_id": "",
        }
    )

    assert settings.theme == "system"
    assert 10 <= settings.typing.wpm <= 1200
    assert settings.typing.countdown >= 0.0
    assert settings.active_profile_id is None


def test_settings_clamp_extremes() -> None:
    """Numeric bounds keep a run from being infinitely fast or long."""
    settings = TypingSettings.from_dict(
        {"wpm": 10**9, "variability": 500, "countdown": 500, "repeat_count": 10**6}
    )

    assert settings.wpm <= 1200
    assert settings.variability <= 100
    assert settings.countdown <= 15.0
    assert settings.repeat_count <= 999
