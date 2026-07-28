"""Tests for the bootstrap and the breakeven-spread solver.

The block-length tests are the ones with content. A stationary bootstrap that
ignored its block parameter would still pass a "returns a number" test, and
would silently restore exactly the understated variance the choice of bootstrap
was meant to avoid.
"""

import numpy as np
import pytest

from backtest.metrics import (
    bootstrap_mean,
    paired_difference,
    solve_breakeven_spread,
    stationary_bootstrap_indices,
)

N = 400


def _ar1(n: int, rho: float, seed: int) -> np.ndarray:
    """An autocorrelated series, which is what the block length exists for."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    out = np.empty(n, dtype=np.float64)
    out[0] = noise[0]
    for i in range(1, n):
        out[i] = rho * out[i - 1] + noise[i]
    return out


def test_block_length_one_almost_never_continues_a_block() -> None:
    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(N, 1.0, rng)
    continued = np.mean(idx[1:] == (idx[:-1] + 1) % N)
    assert continued < 0.05


def test_a_long_block_mostly_continues() -> None:
    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(N, 25.0, rng)
    continued = np.mean(idx[1:] == (idx[:-1] + 1) % N)
    assert continued > 0.85


def test_every_resampled_index_is_in_range() -> None:
    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(N, 10.0, rng)
    assert idx.shape == (N,)
    assert idx.min() >= 0
    assert idx.max() < N


def test_a_block_below_one_is_refused() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="at least 1"):
        stationary_bootstrap_indices(N, 0.5, rng)
    with pytest.raises(ValueError, match="n must be positive"):
        stationary_bootstrap_indices(0, 10.0, rng)


def test_a_longer_block_widens_the_interval_on_dependent_data() -> None:
    values = _ar1(N, rho=0.9, seed=1)
    narrow = bootstrap_mean(values, expected_block=1, n_resamples=400, seed=1337)
    wide = bootstrap_mean(values, expected_block=25, n_resamples=400, seed=1337)

    assert (wide.ci_high - wide.ci_low) > (narrow.ci_high - narrow.ci_low)
    assert narrow.observed == pytest.approx(wide.observed)


def test_the_p_value_is_never_exactly_zero() -> None:
    values = np.full(200, 5.0)
    result = bootstrap_mean(values, expected_block=10, n_resamples=200, seed=1337)
    assert result.p_value_one_sided > 0
    assert result.p_value_one_sided == pytest.approx(1 / 201)
    assert result.significant_at_5pct


def test_a_real_positive_mean_is_detected() -> None:
    rng = np.random.default_rng(4)
    values = 0.5 + 0.1 * rng.standard_normal(N)
    result = bootstrap_mean(values, expected_block=10, n_resamples=1000, seed=1337)
    assert result.significant_at_5pct
    assert result.ci_low > 0


def test_pure_noise_is_not_detected() -> None:
    rng = np.random.default_rng(9)
    values = rng.standard_normal(N)
    result = bootstrap_mean(values, expected_block=10, n_resamples=1000, seed=1337)
    assert not result.significant_at_5pct


def test_an_empty_series_cannot_be_bootstrapped() -> None:
    with pytest.raises(ValueError, match="empty series"):
        bootstrap_mean(np.zeros(0), expected_block=10, n_resamples=10, seed=1337)


def test_the_paired_difference_averages_the_controls_before_differencing() -> None:
    signal = np.array([1.0, 2.0, 3.0])
    controls = (
        np.array([0.0, 0.0, 0.0]),
        np.array([2.0, 2.0, 2.0]),
    )
    assert paired_difference(signal, controls) == pytest.approx([0.0, 1.0, 2.0])


def test_the_paired_difference_refuses_ragged_arms() -> None:
    with pytest.raises(ValueError, match="disagree in decision count"):
        paired_difference(np.zeros(3), (np.zeros(2),))
    with pytest.raises(ValueError, match="at least one control"):
        paired_difference(np.zeros(3), ())


def test_the_breakeven_spread_is_found_where_expectancy_crosses_zero() -> None:
    result = solve_breakeven_spread(lambda spread: 0.5 - spread / 200.0)
    assert result.points is not None
    assert result.points == pytest.approx(100.0, abs=1.0)
    assert "crosses zero" in result.note


def test_no_edge_at_zero_spread_reports_no_breakeven() -> None:
    result = solve_breakeven_spread(lambda spread: -0.1 - spread)
    assert result.points is None
    assert "no breakeven" in result.note
    assert result.expectancy_at_low == pytest.approx(-0.1)


def test_an_edge_surviving_the_bracket_is_reported_as_such() -> None:
    result = solve_breakeven_spread(lambda spread: 1.0, high=500.0)
    assert result.points is None
    assert "above the bracket" in result.note


def test_an_empty_bracket_is_refused() -> None:
    with pytest.raises(ValueError, match="empty bracket"):
        solve_breakeven_spread(lambda spread: 1.0, low=100.0, high=100.0)
    with pytest.raises(ValueError, match="probe_points must be at least 2"):
        solve_breakeven_spread(lambda spread: 1.0, probe_points=1)


def test_a_curve_that_changes_sign_repeatedly_has_no_breakeven() -> None:
    """The H-007 case. Bisection on this returns a real crossing that means nothing.

    A difference that is indistinguishable from zero oscillates as the spread
    moves exit bars around. Reporting one of its crossings as "the breakeven,
    bracketed to within 3.9 points" states a precision the quantity does not
    have.
    """
    result = solve_breakeven_spread(
        lambda spread: np.sin(spread / 100.0), low=0.0, high=2000.0
    )

    assert result.points is None
    assert "no breakeven" in result.note
    assert "changes sign" in result.note
    # The samples are in the note, so a reader can see the oscillation rather
    # than take the refusal on trust.
    assert "0:" in result.note


def test_the_probe_does_not_reject_a_single_clean_crossing() -> None:
    result = solve_breakeven_spread(lambda spread: 0.5 - spread / 200.0)
    assert result.points == pytest.approx(100.0, abs=1.0)
