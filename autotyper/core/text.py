"""Text loading and normalisation helpers.

Typing text needs care: files may be UTF-8 with BOM, UTF-16 (common on Windows
when saved from Notepad) or legacy ANSI encodings, and every platform uses a
slightly different newline convention. Normalising up front means the timing
engine and the progress counter agree with what the target window receives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

#: Encodings attempted in order when loading a file.
_ENCODINGS: Final[tuple[str, ...]] = ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1")

#: Refuse absurdly large payloads, which would make progress pointless.
MAX_TEXT_BYTES: Final[int] = 5 * 1024 * 1024


class TextLoadError(RuntimeError):
    """Raised when a text file cannot be read or decoded."""


def normalize_newlines(text: str) -> str:
    """Convert CRLF/CR to LF and drop a leading BOM.

    Args:
        text: Raw input text.

    Returns:
        Text with only ``\\n`` line separators and no byte-order mark.

    Example:
        >>> normalize_newlines("a\\r\\nb\\rc")
        'a\\nb\\nc'
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def load_text_file(path: str | Path) -> str:
    """Read a text file, trying several encodings before giving up.

    Args:
        path: File to read.

    Returns:
        The normalised file contents.

    Raises:
        TextLoadError: If the file is missing, unreadable, empty, too large or
            cannot be decoded with any supported encoding.
    """
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise TextLoadError(f"'{file_path.name}' could not be opened: {exc.strerror or exc}") from exc

    if size == 0:
        raise TextLoadError(f"'{file_path.name}' is empty.")
    if size > MAX_TEXT_BYTES:
        raise TextLoadError(
            f"'{file_path.name}' is {size / 1_048_576:.1f} MB; the limit is "
            f"{MAX_TEXT_BYTES // 1_048_576} MB."
        )

    raw: bytes | None = None
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        raise TextLoadError(f"'{file_path.name}' could not be read: {exc.strerror or exc}") from exc

    for encoding in _ENCODINGS:
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        normalized = normalize_newlines(text)
        if normalized.strip() == "":
            raise TextLoadError(f"'{file_path.name}' contains no visible text.")
        return normalized

    raise TextLoadError(
        f"'{file_path.name}' uses an unsupported encoding. Re-save it as UTF-8 and try again."
    )


def prepare_payload(text: str) -> str:
    """Normalise user-entered text immediately before a run.

    Handles editors that paste Windows newlines and strips a stray BOM.
    """
    return normalize_newlines(text)


def preview_text(text: str, limit: int = 48) -> str:
    """Return a single-line, length-limited preview of ``text``.

    Args:
        text: Source text, possibly multi-line.
        limit: Maximum characters of the preview (ellipsis included).

    Returns:
        Something like ``"Hello world, this is…"`` safe for a list widget.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(0, limit - 1)].rstrip() + "…"


def character_breakdown_preview(text: str) -> tuple[int, int, int]:
    """Return ``(characters, words, lines)`` counts for the editor footer.

    Args:
        text: Editor contents.

    Returns:
        A tuple of character count (Unicode code points), whitespace-separated
        word count and line count (trailing newline does not add a line).
    """
    chars = len(text)
    words = len(text.split())
    lines = text.count("\n") + (1 if text else 0)
    return (chars, words, lines)
