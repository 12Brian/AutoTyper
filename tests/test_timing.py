"""Unit tests for the timing engine (``autotyper.core.timing``).

The engine is deterministic when a seeded ``random.Random`` is injected, so
every assertion here is exact or bounded by the documented jitter window.
"""

from __future__ import annotations

import random

import pytest
from autotyper.config.models import MAX_WPM, MIN_WPM, TypingSettings
from autotyper.core.timing import (
    MAX_JITTER,
    TimingEngine,
    character_breakdown,
    describe_speed,
    format_duration,
)


def engine(
    wpm: int = 300, variability: int = 0, humanize: bool = False, seed: int = 7
) -> TimingEngine:
    """Build a deterministic engine for tests."""
    settings = TypingSettings(wpm=wpm, variability=variability, humanize_pauses=humanize)
    return TimingEngine(settings, random.Random(seed))


# -------------------------------------------------------------------- speed math
@pytest.mark.parametrize(
    ("wpm", "expected"),
    [(60, 0.2), (120, 0.1), (300, 0.04), (600, 0.02), (1200, 0.01)],
)
def test_base_delay_matches_wpm_definition(wpm: int, expected: float) -> None:
    """One "word" is five characters: delay == 60 / (wpm * 5)."""
    assert engine(wpm=wpm).profile.base_delay == pytest.approx(expected)


def test_settings_are_clamped_into_supported_range() -> None:
    """Out-of-range speeds are clamped rather than producing a zero delay."""
    low = TimingEngine(TypingSettings(wpm=1, variability=500)).profile
    high = TimingEngine(TypingSettings(wpm=10_000)).profile

    assert low.base_delay > 0.0
    assert high.base_delay > 0.0
    assert low.jitter == pytest.approx(MAX_JITTER)
    assert MIN_WPM <= TypingSettings(wpm=1).normalized().wpm <= MAX_WPM


def test_zero_variability_is_perfectly_regular() -> None:
    """Variability 0 must produce identical, metronomic delays."""
    text = "hello world, again."
    delays = list(engine(wpm=300, variability=0).delays(text))
    assert len(delays) == len(text)
    assert len(set(delays)) == 1
    assert delays[0] == pytest.approx(0.04)


def test_delays_are_bounded_by_the_jitter_window() -> None:
    """No delay may escape the documented +/- jitter envelope."""
    eng = engine(wpm=300, variability=100, humanize=False)
    profile = eng.profile
    delays = list(eng.delays("abcdefghij" * 50))

    assert all(delay >= profile.min_delay for delay in delays)
    assert all(delay <= profile.max_delay for delay in delays)
    # With 100% variability the delays must actually vary.
    assert len({round(delay, 6) for delay in delays}) > 10


def test_variability_zero_disables_think_pauses() -> None:
    """The extra "thinking" pauses scale with variability and vanish at 0."""
    assert engine(variability=0).profile.extra_probability == 0.0
    assert engine(variability=100).profile.extra_probability > 0.0



# ------------------------------------------------------------------------- pauses
def test_punctuation_pauses_are_longer_than_letters() -> None:
    """Spaces, sentence ends, tabs and newlines pause longer than letters."""
    eng = engine(wpm=300, variability=0, humanize=True)
    letter = eng.delay_for("a")
    space = eng.delay_for(" ")
    sentence = eng.delay_for(".")
    tab = eng.delay_for("\t")
    newline = eng.delay_for("\n")

    assert letter < space < sentence
    assert space < tab < newline


def test_humanize_off_ignores_character_class() -> None:
    """With humanising disabled every character gets the base delay."""
    eng = engine(wpm=300, variability=0, humanize=False)
    assert eng.delay_for("a") == pytest.approx(eng.profile.base_delay)
    assert eng.delay_for(" ") == pytest.approx(eng.profile.base_delay)
    assert eng.delay_for("\n") == pytest.approx(eng.profile.base_delay)


def test_delays_never_reach_zero() -> None:
    """A pathological RNG still cannot produce a busy loop."""

    class AlwaysNegative(random.Random):
        """RNG that always returns the low end of a uniform range."""

        def uniform(self, a: float, b: float) -> float:  # noqa: D102
            return -abs(b)

        def random(self) -> float:  # noqa: D102
            return 0.0

    eng = TimingEngine(TypingSettings(wpm=1200, variability=100), AlwaysNegative())
    assert all(delay > 0.0 for delay in eng.delays("abc"))


# ---------------------------------------------------------------------- estimates
def test_estimate_counts_every_character() -> None:
    """A one-pass estimate equals the sum of per-character expectations."""
    eng = engine(wpm=300, variability=0, humanize=False)
    assert eng.estimate_passes_duration("abcde") == pytest.approx(5 * 0.04)


def test_estimate_includes_between_loop_delays() -> None:
    """Repeats add the between-run delay exactly ``repeats - 1`` times."""
    eng = engine(wpm=300, variability=0, humanize=False)
    single = eng.estimate_passes_duration("abc")
    total = eng.estimate_duration("abc", repeats=3, loop_delay=2.0)
    assert total == pytest.approx(single * 3 + 2.0 * 2)


def test_estimate_of_empty_text_is_zero() -> None:
    """Empty payloads take no time (and must not divide by zero)."""
    assert engine().estimate_duration("") == 0.0
    assert engine().estimate_duration("", repeats=5, loop_delay=3) == 0.0


def test_estimate_is_stable_across_calls() -> None:
    """The UI re-renders the estimate constantly; it must not jitter."""
    eng = engine(wpm=420, variability=70, humanize=True)
    text = "The quick brown fox. Jumps over 13 lazy dogs!"
    assert eng.estimate_duration(text, 2, 1.5) == pytest.approx(
        eng.estimate_duration(text, 2, 1.5)
    )


def test_higher_wpm_yields_shorter_estimate() -> None:
    """Speed changes must move the estimate in the right direction."""
    text = "some sample text to type out"
    fast = engine(wpm=800).estimate_passes_duration(text)
    slow = engine(wpm=100).estimate_passes_duration(text)
    assert fast < slow


def test_delays_yields_one_value_per_character() -> None:
    """Progress reporting relies on a 1:1 mapping of characters to delays."""
    text = "tabs\tand\nnewlines — and ünïcödé"
    assert len(list(engine().delays(text))) == len(text)


# --------------------------------------------------------------------- formatting
@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "0 ms"),
        (0.25, "250 ms"),
        (0.999, "999 ms"),
        (1.0, "1.0s"),
        (59.4, "59.4s"),
        (60.0, "1m 00s"),
        (65.0, "1m 05s"),
        (3599.0, "59m 59s"),
        (3600.0, "1h 00m"),
        (7322.0, "2h 02m"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    """``format_duration`` renders compact, human-readable labels."""
    assert format_duration(seconds) == expected


def test_format_duration_clamps_negatives() -> None:
    """Negative durations (clock skew) render as zero, never as junk."""
    assert format_duration(-5) == "0 ms"


def test_describe_speed_shows_wpm_and_cpm() -> None:
    """The label pairs WPM with the equivalent characters-per-minute value."""
    assert describe_speed(TypingSettings(wpm=250)) == "250 WPM · 1250 CPM"


def test_character_breakdown() -> None:
    """Counters match the editor footer's expectations."""
    assert character_breakdown("") == (0, 0, 0)
    assert character_breakdown("hello") == (5, 1, 1)
    assert character_breakdown("a b\nc d") == (7, 4, 2)
    assert character_breakdown("line\n") == (5, 1, 2)
