"""Tests for the pessimistic cost model.

The first test in this file is the one that matters most: it is H-003 §I
requirement 3 — the H-005 spread floor, build-enforced. Everything else here
pins arithmetic so that a failure can be attributed.
"""

import numpy as np
import pandas as pd
import pytest

from backtest.costs import (
    SCHEDULED_NEWS_MULTIPLIER,
    SPREAD_FLOOR_POINTS,
    WEEKLY_OPEN_MULTIPLIER,
    CostModel,
    commission_points,
    half_spread_points,
    latency_points,
    multiplier_coverage,
    rollovers_crossed,
    slippage_points,
    spread_multipliers,
    swap_points,
)

#: H-005 condition (i), restated as a literal. Restated rather than imported so
#: that lowering the constant cannot also lower the assertion — an assertion
#: that reads the value it is guarding is not a guard.
H005_REGISTERED_FLOOR = 75.0


def test_the_spread_floor_has_not_been_lowered() -> None:
    assert SPREAD_FLOOR_POINTS >= H005_REGISTERED_FLOOR


def test_a_model_below_the_floor_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match=r"below the.*H-005 floor"):
        CostModel(spread_floor_points=H005_REGISTERED_FLOOR - 1)


def test_the_breakeven_solver_may_bypass_the_floor_and_says_so_in_its_name() -> None:
    model = CostModel().unsafe_with_spread_floor(0.0)
    assert model.spread_floor_points == 0.0
    with pytest.raises(ValueError, match="non-negative"):
        CostModel().unsafe_with_spread_floor(-1.0)


def test_doubling_doubles_every_cost_and_nothing_else() -> None:
    base = CostModel()
    doubled = base.doubled()

    for field in (
        "spread_floor_points",
        "slippage_atr_coeff",
        "commission_points_per_lot_per_side",
        "swap_long_points_per_lot_per_night",
        "swap_short_points_per_lot_per_night",
        "latency_seconds",
    ):
        assert getattr(doubled, field) == pytest.approx(2 * getattr(base, field))

    # Multipliers and shapes are not costs. Doubling them would change the
    # model's structure, not its price, and K-5 asks about price.
    for field in (
        "weekly_open_multiplier",
        "scheduled_news_multiplier",
        "weekly_open_bars",
        "reference_lots",
        "latency_atr_coeff_per_second",
    ):
        assert getattr(doubled, field) == getattr(base, field)


def test_the_version_hash_changes_with_any_constant() -> None:
    base = CostModel()
    assert base.version() == CostModel().version()
    assert base.version() != base.doubled().version()
    assert base.version() != CostModel(spread_floor_points=76.0).version()


def test_half_spread_is_half_the_quote() -> None:
    model = CostModel()
    assert half_spread_points(1.0, model) == pytest.approx(
        model.spread_floor_points / 2
    )
    assert half_spread_points(3.0, model) == pytest.approx(
        3 * model.spread_floor_points / 2
    )


def test_a_naive_index_is_refused() -> None:
    naive = pd.DatetimeIndex(pd.date_range("2021-01-04", periods=3, freq="h"))
    with pytest.raises(ValueError, match="timezone-aware"):
        spread_multipliers(naive, CostModel())


def test_the_weekly_open_carries_a_multiplier() -> None:
    # Friday evening, then a weekend gap, then Sunday evening.
    stamps = pd.DatetimeIndex(
        [
            "2021-06-04T20:00:00+00:00",
            "2021-06-04T21:00:00+00:00",
            "2021-06-06T21:00:00+00:00",
            "2021-06-06T22:00:00+00:00",
            "2021-06-06T23:00:00+00:00",
            "2021-06-07T00:00:00+00:00",
        ]
    )
    multipliers = spread_multipliers(stamps, CostModel())

    assert list(multipliers[:2]) == [1.0, 1.0]
    assert list(multipliers[2:5]) == [WEEKLY_OPEN_MULTIPLIER] * 3
    assert multipliers[5] == 1.0


def test_the_payrolls_hour_carries_the_news_multiplier() -> None:
    # 2021-06-04 is a first Friday. 08:00 New York is 12:00 UTC in EDT.
    stamps = pd.DatetimeIndex(
        [
            "2021-06-04T11:00:00+00:00",
            "2021-06-04T12:00:00+00:00",
            "2021-06-04T13:00:00+00:00",
        ]
    )
    multipliers = spread_multipliers(stamps, CostModel())
    assert list(multipliers) == [1.0, SCHEDULED_NEWS_MULTIPLIER, 1.0]


def test_a_second_friday_carries_nothing() -> None:
    stamps = pd.DatetimeIndex(["2021-06-11T12:00:00+00:00"])
    assert list(spread_multipliers(stamps, CostModel())) == [1.0]


def test_coverage_reports_the_share_the_event_model_reaches() -> None:
    multipliers = np.array([1.0, 3.0, 1.0, 10.0, 1.0], dtype=np.float64)
    coverage = multiplier_coverage(multipliers)
    assert coverage.n_bars == 5
    assert coverage.n_weekly_open == 1
    assert coverage.n_news == 1
    assert coverage.share_elevated == pytest.approx(0.4)


def test_slippage_grows_with_atr_and_with_the_square_root_of_size() -> None:
    model = CostModel()
    assert slippage_points(300.0, 1.0, model) == pytest.approx(15.0)
    assert slippage_points(600.0, 1.0, model) == pytest.approx(30.0)
    assert slippage_points(300.0, 4.0, model) == pytest.approx(30.0)
    assert slippage_points(300.0, 0.0, model) == 0.0


def test_latency_scales_with_the_configured_delay() -> None:
    model = CostModel()
    doubled = model.doubled()
    assert latency_points(300.0, doubled) == pytest.approx(
        2 * latency_points(300.0, model)
    )


def test_commission_is_charged_on_both_sides() -> None:
    model = CostModel()
    one = commission_points(2.0, sides=1, model=model)
    two = commission_points(2.0, sides=2, model=model)
    assert two == pytest.approx(2 * one)
    assert one == pytest.approx(model.commission_points_per_lot_per_side * 2.0)


def test_rollovers_are_counted_at_seventeen_new_york() -> None:
    # 2021-06-07 21:00 UTC is 17:00 New York (EDT).
    before = pd.Timestamp("2021-06-07T20:00:00+00:00")
    after = pd.Timestamp("2021-06-07T22:00:00+00:00")
    assert rollovers_crossed(before, after) == 1
    assert rollovers_crossed(before, pd.Timestamp("2021-06-07T20:30:00+00:00")) == 0
    assert rollovers_crossed(before, pd.Timestamp("2021-06-09T22:00:00+00:00")) == 3
    assert rollovers_crossed(after, before) == 0


def test_swap_is_asymmetric_and_charged_in_both_directions() -> None:
    model = CostModel()
    long_cost = swap_points(is_long=True, nights=1, lots=1.0, model=model)
    short_cost = swap_points(is_long=False, nights=1, lots=1.0, model=model)

    assert long_cost > 0
    assert short_cost > 0
    # The asymmetry is the whole reason the paired-arm cost invariance in
    # `engine` is only partial. If these ever became equal the invariance would
    # look stronger than it is, so the inequality is asserted rather than
    # assumed.
    assert long_cost != short_cost
    assert swap_points(is_long=True, nights=0, lots=1.0, model=model) == 0.0
