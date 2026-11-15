"""Human typing behaviour models: word difficulty and plausible typos.

This module answers two questions that make synthesised typing look less
mechanical, without doing any timing of its own:

* **How hard is this word?** Typists slow down and pause before long, unusual
  or mixed-case words. :func:`word_difficulty` scores a word in ``0..1`` and
  :func:`pause_difficulties` maps every separator in a text to the difficulty
  of the word that follows it, so the timing engine can place *planning* pauses
  where a human actually places them.
* **What would I have mistyped?** :func:`keyboard_neighbours` returns the keys
  physically adjacent to a character on a US QWERTY layout, which is where real
  slips come from (``teh``, ``wrold``).

Everything here is pure and deterministic - no RNG, no clock, no I/O - so the
:class:`autotyper.core.timing.TimingEngine` remains the only place randomness
is injected and tests can pin behaviour exactly.

The interface deliberately **never touches the mouse**: AutoTyper is a keyboard
tool, and moving the pointer would be both detectable and destructive to
whatever the user is doing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: Keyboard rows, top to bottom, in QWERTY order (US layout). Only the keys
#: that appear unshifted are listed; shifted forms are derived by upper-casing.
_ROWS: tuple[str, ...] = (
    "`1234567890-=",
    "qwertyuiop[]",
    "asdfghjkl;'",
    "zxcvbnm,./",
)

#: Horizontal offset of each row, in key widths, following the physical
#: stagger of a real ANSI keyboard. Without it, a column compared across rows
#: lands on the wrong key: ``g`` would be treated as sitting under ``r``/``t``
#: instead of between ``t`` and ``y``, and ``a`` would be treated as directly
#: above ``q`` rather than offset under it.
_ROW_OFFSETS: tuple[float, ...] = (0.0, 0.5, 0.75, 1.25)

#: Characters that commonly replace one another when a finger slips sideways,
#: where the layout table above cannot help (shifted punctuation).
_SYMBOL_NEIGHBOURS: Mapping[str, tuple[str, ...]] = {
    "!": ("@", "1"),
    "@": ("!", "#"),
    "#": ("@", "$"),
    "$": ("#", "%"),
    "%": ("$", "^"),
    "^": ("%", "&"),
    "&": ("^", "*"),
    "*": ("&", "("),
    "(": ("*", ")"),
    ")": ("(", "_"),
    "_": ("-", "+"),
    "+": ("=", "_"),
    "{": ("[", "}"),
    "}": ("]", "{"),
    ":": (";", '"'),
    '"': (":", "'"),
    "<": (",", ">"),
    ">": (".", "<"),
    "?": (".", "/"),
    "~": ("`", "!"),
}

#: Character separators that get a word-planning pause.
_PAUSE_TRIGGERS = frozenset(" \t\n.!?,;:")

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _build_layout() -> dict[str, tuple[int, float]]:
    """Return ``{key: (row, horizontal position)}`` for the unshifted layout."""
    layout: dict[str, tuple[int, float]] = {}
    for row, keys in enumerate(_ROWS):
        for column, key in enumerate(keys):
            layout[key] = (row, column + _ROW_OFFSETS[row])
    return layout


_LAYOUT: dict[str, tuple[int, float]] = _build_layout()


def _neighbours_of_lower(key: str) -> tuple[str, ...]:
    """Return the unshifted keys adjacent to ``key``, nearest first."""
    entry = _LAYOUT.get(key)
    if entry is None:
        return ()
    row, position = entry
    ranked: list[tuple[int, float, str]] = []
    for candidate, (other_row, other_position) in _LAYOUT.items():
        if candidate == key:
            continue
        distance = abs(other_position - position)
        if other_row == row and distance <= 1.01:
            # Same row: a straight sideways slip, the most common error.
            ranked.append((0, distance, candidate))
        elif abs(other_row - row) == 1 and distance <= 0.85:
            # Diagonal slip. The leading rank keeps *every* same-row key ahead
            # of every diagonal one, which a single blended score cannot do.
            ranked.append((1, distance, candidate))
    ranked.sort()
    return tuple(candidate for _rank, _distance, candidate in ranked)


def _capitalize_like(candidate: str, original: str) -> str:
    """Mimic whether ``original`` needed Shift when substitution happened."""
    if original.isalpha() and original.isupper():
        return candidate.upper()
    return candidate


def _filter_plausible(original: str, candidates: tuple[str, ...]) -> tuple[str, ...]:
    """Drop substitutions that change *kind* (a letter does not slip to a digit).

    Keeping letters as letters is what makes ``teh`` read as a believable typo
    rather than as a different token typed on purpose.
    """
    if original.isalpha():
        return tuple(candidate for candidate in candidates if candidate.isalpha())
    return candidates


def keyboard_neighbours(char: str) -> tuple[str, ...]:
    """Return the characters a finger slip could produce instead of ``char``.

    Args:
        char: The intended character.

    Returns:
        Adjacent characters, nearest first. Empty for whitespace, control
        characters and anything outside the modelled layout.

    Example:
        >>> keyboard_neighbours("a")[:2]
        ('s', 'q')
        >>> keyboard_neighbours("A")[0]
        'S'
        >>> keyboard_neighbours("\\n")
        ()
    """
    if not char or char.isspace() or len(char) != 1:
        return ()
    lowered = char.lower()
    neighbours = _neighbours_of_lower(lowered)
    if neighbours:
        shifted = tuple(_capitalize_like(candidate, char) for candidate in neighbours)
        return _filter_plausible(char, shifted)
    return _SYMBOL_NEIGHBOURS.get(char, ())


def is_typo_candidate(char: str) -> bool:
    """Return whether ``char`` can be mistyped plausibly.

    Whitespace and control characters are excluded: mistyping a space would
    merge two words, and the correction would still be visible as a deleted
    character, so it is not worth modelling.
    """
    return bool(keyboard_neighbours(char))


def word_difficulty(word: str) -> float:
    """Score how hard ``word`` is to type, from ``0.0`` to ``1.0``.

    The score combines the effects documented in typing research: longer words
    are slower, digits and symbols cost more than letters, inner capitals break
    the rhythm (``getUserName``), and repeated characters invite errors
    (``committee``).

    Args:
        word: A single word; surrounding whitespace is ignored.

    Returns:
        A bounded difficulty score. Empty input scores ``0.0``.

    Example:
        >>> word_difficulty("cat") < word_difficulty("difficulty")
        True
        >>> word_difficulty("passw0rd!") > 0.5
        True
    """
    letters = [char for char in word if not char.isspace()]
    if not letters:
        return 0.0

    length = len(letters)
    score = 0.0
    if length >= 12:
        score += 0.55
    elif length >= 9:
        score += 0.42
    elif length >= 6:
        score += 0.25
    elif length >= 4:
        score += 0.10

    unusual = sum(1 for char in letters if char.isdigit() or not char.isalpha())
    score += min(0.30, unusual * 0.10)

    inner_capitals = sum(1 for char in letters[1:] if char.isupper())
    score += min(0.15, inner_capitals * 0.05)

    repeats = len(letters) - len({char.lower() for char in letters})
    score += min(0.10, repeats * 0.02)

    return round(min(1.0, score), 4)


def pause_difficulties(text: str) -> list[float | None]:
    """Map each character index to the difficulty of the word that follows it.

    Only separator characters (space, tab, newline and sentence/clause
    punctuation) receive a value; every other index gets ``None``. The timing
    engine uses this to place a *planning* pause immediately before a hard word
    rather than at an unrelated random offset.

    The scan is linear: word spans are found once and walked forward with a
    single cursor as the index advances.

    Args:
        text: The payload about to be typed.

    Returns:
        A list the same length as ``text``.

    Example:
        >>> pause_difficulties("go extraordinary")[2] > 0.5
        True
        >>> pause_difficulties("abc")[1] is None
        True
    """
    result: list[float | None] = [None] * len(text)
    if not text:
        return result

    spans = [(match.start(), match.end()) for match in _WORD_RE.finditer(text)]
    cursor = 0
    for index, char in enumerate(text):
        if char not in _PAUSE_TRIGGERS:
            continue
        # Advance to the first word that starts after this separator. A single
        # moving cursor keeps the whole pass O(len(text)).
        while cursor < len(spans) and spans[cursor][0] <= index:
            cursor += 1
        if cursor >= len(spans):
            break
        start, end = spans[cursor]
        result[index] = word_difficulty(text[start:end])
    return result


def describe_difficulty(score: float) -> str:
    """Turn a difficulty score into a short human label (used by tooltips)."""
    if score <= 0.05:
        return "easy"
    if score <= 0.30:
        return "ordinary"
    if score <= 0.55:
        return "long"
    return "hard"

