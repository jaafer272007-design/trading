"""Tests for Brier score, BSS, and the bootstrap CI."""

import numpy as np
import pytest

from metrics.brier import bootstrap_ci, brier_score, brier_skill_score


def test_perfect_forecast_scores_zero() -> None:
    y = np.array([1.0, 0.0, 1.0, 0.0])

    assert brier_score(y, y) == 0.0


def test_worst_forecast_scores_one() -> None:
    y = np.array([1.0, 0.0])
    f = np.array([0.0, 1.0])

    assert brier_score(f, y) == 1.0


def test_matches_hand_computed_value() -> None:
    f = np.array([0.8, 0.3])
    y = np.array([1.0, 0.0])

    # ((0.8-1)^2 + (0.3-0)^2) / 2 = (0.04 + 0.09) / 2 = 0.065
    assert brier_score(f, y) == pytest.approx(0.065)


def test_bss_is_zero_for_the_base_rate_forecast() -> None:
    """Predicting climatology is the definition of no skill."""
    y = np.array([1.0, 1.0, 0.0, 0.0, 1.0, 0.0])
    f = np.full_like(y, float(np.mean(y)))

    assert brier_skill_score(f, y) == pytest.approx(0.0)


def test_bss_is_one_for_a_perfect_forecast() -> None:
    y = np.array([1.0, 0.0, 1.0, 0.0])

    assert brier_skill_score(y, y) == pytest.approx(1.0)


def test_bss_is_negative_when_worse_than_climatology() -> None:
    y = np.array([1.0, 1.0, 1.0, 0.0])
    f = np.array([0.1, 0.1, 0.1, 0.9])

    assert brier_skill_score(f, y) < 0.0


def test_bss_uses_the_in_window_base_rate_not_a_fixed_half() -> None:
    """EVALUATION §3.2: the reference is climatology over the same window.

    Scoring an unbalanced window against a fixed 0.5 would manufacture
    apparent skill out of the imbalance alone.
    """
    y = np.array([1.0] * 9 + [0.0])
    f = np.full_like(y, 0.9)

    assert brier_skill_score(f, y) == pytest.approx(0.0)


def test_degenerate_window_raises_rather_than_returning_a_number() -> None:
    """All-identical outcomes make the skill ratio undefined."""
    y = np.ones(10)

    with pytest.raises(ValueError, match="degenerate"):
        brier_skill_score(np.full_like(y, 0.5), y)


def test_rejects_misaligned_inputs() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        brier_score(np.zeros(3), np.zeros(4))


def test_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one"):
        brier_score(np.array([]), np.array([]))


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_ci_brackets_the_sample_mean() -> None:
    rng = np.random.default_rng(0)
    values = rng.normal(loc=0.3, scale=0.1, size=200)

    ci = bootstrap_ci(values)

    assert ci.lower < float(np.mean(values)) < ci.upper


def test_bootstrap_ci_is_deterministic_under_the_fixed_seed() -> None:
    """REPRODUCIBILITY §3: seed 1337, named and logged, not generated."""
    values = np.linspace(-0.01, 0.01, 30)

    first = bootstrap_ci(values)
    second = bootstrap_ci(values)

    assert (first.lower, first.upper) == (second.lower, second.upper)


def test_bootstrap_ci_narrows_as_the_sample_grows() -> None:
    rng = np.random.default_rng(1)
    small = bootstrap_ci(rng.normal(size=10), resamples=2000)
    large = bootstrap_ci(rng.normal(size=1000), resamples=2000)

    assert (large.upper - large.lower) < (small.upper - small.lower)


def test_bootstrap_ci_rejects_empty_sample() -> None:
    with pytest.raises(ValueError, match="at least one"):
        bootstrap_ci(np.array([]))
