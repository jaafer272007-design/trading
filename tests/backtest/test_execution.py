"""Tests for the position lifecycle.

Every pessimistic rule H-003 §D registers has a test here, and each one is
written so that inverting the rule fails it. A rule that would still pass with
its sign flipped is not being tested.

Prices are in points throughout. 200,000 points is $2,000 an ounce.
"""

import numpy as np
import pytest

from backtest.costs import POINT_VALUE_PER_LOT, CostModel
from backtest.execution import (
    BarArrays,
    Direction,
    ExitReason,
    RiskModel,
    Trade,
    build_bars,
    required_bars_after,
    simulate_position,
)
from tests.backtest.bars import bars_from, flat_bars, frame_from

ENTRY = 200_100.0
ATR = 1_000.0
RISK = 100.0

#: 1.5 x ATR either side of the entry, per H-003 §D.
STOP_LONG = ENTRY - 1_500.0
TARGET_LONG = ENTRY + 1_500.0

FLAT = (200_000.0, 200_000.0, 200_000.0)
ENTRY_BAR = (ENTRY, ENTRY, ENTRY)


@pytest.fixture
def risk() -> RiskModel:
    """The H-003 §D geometry, with a short hold so fixtures stay readable."""
    return RiskModel(
        stop_atr_mult=1.5,
        target_atr_mult=1.5,
        max_hold_bars=3,
        risk_per_trade_currency=RISK,
    )


def _simulate(
    bars: BarArrays, risk: RiskModel, direction: Direction = Direction.LONG
) -> Trade | None:
    """Run one decision at bar 0 against a default cost model."""
    return simulate_position(
        bars=bars,
        decision_index=0,
        direction=direction,
        atr_points=ATR,
        risk=risk,
        model=CostModel(),
    )


def test_entry_is_the_next_bars_open_not_this_bars_close(risk: RiskModel) -> None:
    bars = bars_from([FLAT, ENTRY_BAR, FLAT, FLAT, FLAT])
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.entry_index == 1
    assert trade.entry_mid_points == pytest.approx(ENTRY)
    assert trade.entry_timestamp == bars.index[1]


def test_the_stop_wins_when_one_bar_contains_both_levels(risk: RiskModel) -> None:
    # Bar 1 spans both. There is no intrabar path at H1, so the unfavourable
    # ordering is taken. Inverting the rule makes this a TARGET and fails.
    both = (ENTRY, TARGET_LONG, STOP_LONG)
    bars = bars_from([FLAT, both, FLAT, FLAT, FLAT])
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.exit_reason is ExitReason.STOP
    assert trade.exit_index == 1
    assert trade.exit_mid_points == pytest.approx(STOP_LONG)


def test_a_stop_gaps_through_and_does_not_fill_at_the_stop_price(
    risk: RiskModel,
) -> None:
    below = 198_000.0
    gapped = (below, below, below)
    bars = bars_from([FLAT, ENTRY_BAR, gapped, FLAT, FLAT])
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.exit_reason is ExitReason.STOP
    assert trade.exit_mid_points == pytest.approx(below)
    assert trade.gap_through_points == pytest.approx(STOP_LONG - below)


def test_a_target_fills_at_the_level_never_at_a_favourable_gap(
    risk: RiskModel,
) -> None:
    above = 202_000.0
    gapped = (above, above, above)
    bars = bars_from([FLAT, ENTRY_BAR, gapped, FLAT, FLAT])
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.exit_reason is ExitReason.TARGET
    assert trade.exit_mid_points == pytest.approx(TARGET_LONG)
    assert trade.gap_through_points == 0.0


def test_a_position_that_touches_neither_level_times_out(risk: RiskModel) -> None:
    bars = bars_from([FLAT, ENTRY_BAR, ENTRY_BAR, ENTRY_BAR, FLAT])
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.exit_reason is ExitReason.TIME
    assert trade.exit_index == 1 + risk.max_hold_bars


def test_the_trigger_uses_the_exit_side_quote_not_the_mid(risk: RiskModel) -> None:
    # A long exits on the bid. With a 50-point half-spread the bid touches the
    # stop while the mid is still 50 points above it, so this must stop out.
    # A mid-based implementation leaves the position open and times out.
    just_above = (ENTRY, ENTRY, STOP_LONG + 50.0)
    bars = bars_from([FLAT, ENTRY_BAR, just_above, FLAT, FLAT], half_spread=50.0)
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.exit_reason is ExitReason.STOP


def test_a_short_mirrors_a_long(risk: RiskModel) -> None:
    stop_short = ENTRY + 1_500.0
    above = stop_short + 400.0
    gapped = (above, above, above)
    bars = bars_from([FLAT, ENTRY_BAR, gapped, FLAT, FLAT])
    trade = _simulate(bars, risk, Direction.SHORT)

    assert trade is not None
    assert trade.exit_reason is ExitReason.STOP
    assert trade.stop_points == pytest.approx(stop_short)
    assert trade.gap_through_points == pytest.approx(above - stop_short)


def test_the_decomposition_reconciles_with_the_itemised_costs(
    risk: RiskModel,
) -> None:
    bars = bars_from([FLAT, ENTRY_BAR, ENTRY_BAR, ENTRY_BAR, FLAT], half_spread=40.0)
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.net_points == pytest.approx(trade.mid_gross_points - trade.cost_points)
    assert trade.cost_points == pytest.approx(
        trade.spread_points
        + trade.slippage_points
        + trade.latency_points
        + trade.commission_points
        + trade.swap_points
    )
    # The gap-through diagnostic must stay outside the cost total: the fill it
    # describes is already inside the gross result, and counting it twice would
    # inflate every stopped trade's cost.
    gapped = bars_from([FLAT, ENTRY_BAR, (197_000.0, 197_000.0, 197_000.0), FLAT, FLAT])
    stopped = _simulate(gapped, risk)
    assert stopped is not None
    assert stopped.gap_through_points > 0
    assert stopped.net_points == pytest.approx(
        stopped.mid_gross_points - stopped.cost_points
    )


def test_a_stop_costs_more_than_one_r(risk: RiskModel) -> None:
    bars = bars_from([FLAT, ENTRY_BAR, (STOP_LONG, STOP_LONG, STOP_LONG), FLAT, FLAT])
    trade = _simulate(bars, risk)

    assert trade is not None
    assert trade.exit_reason is ExitReason.STOP
    # Sizing budgets exactly 1R to the stop distance; costs are on top of it.
    assert trade.r_multiple < -1.0


def test_size_puts_exactly_one_r_at_the_stop_distance(risk: RiskModel) -> None:
    bars = bars_from([FLAT, ENTRY_BAR, FLAT, FLAT, FLAT])
    trade = _simulate(bars, risk)

    assert trade is not None
    stop_distance = 1.5 * ATR
    assert trade.lots * stop_distance * POINT_VALUE_PER_LOT == pytest.approx(RISK)


def test_without_a_stop_size_is_risk_parity_on_atr() -> None:
    # EVALUATION.md §2 rung 3. The float | None on the multipliers exists for
    # exactly this configuration, and without it the rung needs a second engine.
    rung3 = RiskModel(
        stop_atr_mult=None,
        target_atr_mult=None,
        max_hold_bars=3,
        risk_per_trade_currency=RISK,
    )
    bars = bars_from([FLAT, ENTRY_BAR, FLAT, FLAT, FLAT])
    trade = _simulate(bars, rung3)

    assert trade is not None
    assert trade.stop_points is None
    assert trade.target_points is None
    assert trade.exit_reason is ExitReason.TIME
    assert trade.lots * ATR * POINT_VALUE_PER_LOT == pytest.approx(RISK)


def test_flat_takes_no_position(risk: RiskModel) -> None:
    bars = bars_from([FLAT, ENTRY_BAR, FLAT, FLAT, FLAT])
    assert _simulate(bars, risk, Direction.FLAT) is None


def test_a_window_running_past_the_series_is_refused(risk: RiskModel) -> None:
    bars = flat_bars(4)
    assert required_bars_after(0, risk) == 4
    with pytest.raises(ValueError, match="needs bars through"):
        _simulate(bars, risk)


def test_a_missing_atr_is_refused_rather_than_substituted(risk: RiskModel) -> None:
    bars = flat_bars(6)
    for bad in (float("nan"), 0.0, -1.0):
        with pytest.raises(ValueError, match="atr_points must be positive"):
            simulate_position(
                bars=bars,
                decision_index=0,
                direction=Direction.LONG,
                atr_points=bad,
                risk=risk,
                model=CostModel(),
            )


def test_build_bars_scales_prices_and_matches_the_scalar_half_spread() -> None:
    bars = flat_bars(5)
    frame = frame_from(bars)
    multipliers = np.array([1.0, 3.0, 1.0, 10.0, 1.0], dtype=np.float64)
    model = CostModel()

    built = build_bars(frame, multipliers, model, points_per_price_unit=100.0)

    assert built.open == pytest.approx(bars.open)
    assert built.half_spread == pytest.approx(
        0.5 * model.spread_floor_points * multipliers
    )


def test_build_bars_refuses_a_frame_without_prices() -> None:
    bars = flat_bars(3)
    frame = frame_from(bars).drop(columns=["high"])
    with pytest.raises(ValueError, match="missing columns"):
        build_bars(frame, np.ones(3), CostModel(), points_per_price_unit=100.0)
