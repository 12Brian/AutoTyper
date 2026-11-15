"""Tests for the human behaviour models (``autotyper.core.behaviour``).

Every helper here is pure, so the assertions can be exact.
"""

from __future__ import annotations

import pytest
from autotyper.core.behaviour import (
    describe_difficulty,
    is_typo_candidate,
    keyboard_neighbours,
    pause_difficulties,
    word_difficulty,
)


# ------------------------------------------------------------------- neighbours
def test_neighbours_come_from_the_same_row_first() -> None:
    """Horizontal slips dominate, so left/right keys rank above diagonals."""
    neighbours = keyboard_neighbours("g")
    assert set(neighbours) == {"f", "h", "t", "y", "v", "b"}
    assert set(neighbours[:2]) == {"f", "h"}, "same-row keys must be nearest"


def test_neighbours_preserve_shift_state() -> None:
    """A capital letter slips to a capital neighbour, not a lower-case one."""
    assert set(keyboard_neighbours("Q")[:2]) == {"W", "A"}
    assert all(candidate.isupper() for candidate in keyboard_neighbours("Q"))


def test_neighbours_of_punctuation_are_available() -> None:
    """Shifted punctuation is not in the layout table, so it has its own list."""
    assert "1" in keyboard_neighbours("!")
    assert keyboard_neighbours("?")[0] == "."


@pytest.mark.parametrize("char", [" ", "\n", "\t", "", "ab"])
def test_whitespace_and_non_single_characters_have_no_neighbours(char: str) -> None:
    """Whitespace cannot be "mistyped" and multi-char input is not a key."""
    assert keyboard_neighbours(char) == ()


def test_neighbour_lists_are_deterministic_and_unique() -> None:
    """The same key always yields the same ordering with no duplicates."""
    first = keyboard_neighbours("e")
    assert first == keyboard_neighbours("e")
    assert len(set(first)) == len(first)


def test_typo_candidacy_follows_neighbours() -> None:
    """Only keys with neighbours are plausible typo targets."""
    assert is_typo_candidate("a") is True
    assert is_typo_candidate(" ") is False
    assert is_typo_candidate("\n") is False


# ------------------------------------------------------------------- difficulty
def test_longer_words_are_harder() -> None:
    """Difficulty grows with length, monotonically across the bands."""
    short = word_difficulty("cat")
    medium = word_difficulty("planning")
    long = word_difficulty("uncharacteristically")
    assert short < medium < long


def test_digits_and_symbols_increase_difficulty() -> None:
    """Unusual characters cost more than plain letters."""
    assert word_difficulty("password") < word_difficulty("passw0rd")
    assert word_difficulty("password") < word_difficulty("pass-word")


def test_inner_capitals_increase_difficulty() -> None:
    """CamelCase words break the rhythm, so they score higher."""
    assert word_difficulty("username") < word_difficulty("userName")


def test_difficulty_is_bounded() -> None:
    """The score never escapes 0..1, whatever goes in."""
    assert word_difficulty("") == 0.0
    assert word_difficulty("   ") == 0.0
    assert 0.0 <= word_difficulty("a" * 200) <= 1.0
    assert 0.0 <= word_difficulty("MixedCase12345!!") <= 1.0


def test_repeated_letters_add_a_little_difficulty() -> None:
    """Repeats invite slips, but never dominate the score."""
    assert word_difficulty("committee") > word_difficulty("commitee")


# ----------------------------------------------------------------- pause map
def test_pause_map_is_the_same_length_as_the_text() -> None:
    """The timing engine zips this list against the payload."""
    text = "Hello, world!\n\tDone"
    assert len(pause_difficulties(text)) == len(text)


def test_pause_map_only_scores_separators() -> None:
    """Letters never carry a difficulty value; separators do."""
    text = "go extraordinary"
    values = pause_difficulties(text)
    assert all(value is None for value in values[:2]), "letters must be None"
    assert values[2] is not None
    assert values[2] > 0.5, "the following word is long"


def test_pause_map_tracks_the_word_that_follows() -> None:
    """Each separator scores the *next* word, so hard words pause longer."""
    text = "a extraordinarily longish b"
    values = pause_difficulties(text)
    separators = [value for value in values if value is not None]
    assert len(separators) == text.count(" ")
    assert separators[0] > 0.5, "extraordinarily is hard"
    assert separators[-1] < separators[0], "b is easy"


def test_pause_map_handles_trailing_separators() -> None:
    """A separator with no following word is skipped, not indexed out of range."""
    values = pause_difficulties("hello ")
    assert values[-1] is None


def test_empty_text_has_an_empty_pause_map() -> None:
    """No payload, no works: must not raise."""
    assert pause_difficulties("") == []


@pytest.mark.parametrize(
    ("score", "label"),
    [(0.0, "easy"), (0.2, "ordinary"), (0.4, "long"), (0.9, "hard")],
)
def test_describe_difficulty_labels(score: float, label: str) -> None:
    """Difficulty labels are stable for tooltips."""
    assert describe_difficulty(score) == label
