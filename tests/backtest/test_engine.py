"""Tests for running an arm, and for the realised-cost comparison.

Two of these are load-bearing for H-003's claim rather than for the code:

``test_the_arms_differ_only_in_direction``
    "Identical risk management" is the phrase the claim turns on. This asserts
    it structurally — same entry bar, same size, same stop distance, same ATR —
    rather than trusting that both arms happen to call the same function.

``test_a_component_that_cannot_differ_voids_the_comparison``
    If commission ever differs between two arms trading the same grid at the
    same size, the grid or the sizing is broken. That is a louder failure than
    a cost difference and the verdict says so instead of reporting a number.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from backtest.costs import CostModel, spread_multipliers
from backtest.direction import DirectionSource, LogisticDirection, RandomDirection
from backtest.engine import (
    COST_COMPONENTS,
    ArmResult,
    ComponentComparison,
    CostInvariance,
    assess_cost_invariance,
    run_arm,
)
from backtest.execution import (
    BarArrays,
    Direction,
    ExitReason,
    RiskModel,
    build_bars,
)
from data.synthetic import generate_ohlcv
from features.atr import ATR

N_BARS = 900
HORIZON = 24
RISK = 100.0


@dataclass
class Setup:
    """Everything ``run_arm`` needs, built once per test."""

    model: CostModel
    frame: pd.DataFrame
    bars: BarArrays
    risk: RiskModel
    decisions: npt.NDArray[np.int64]
    atr_points: npt.NDArray[np.float64]

    @property
    def n(self) -> int:
        """Decision count."""
        return len(self.decisions)


def _setup(seed: int = 7) -> Setup:
    """A synthetic frame with a decision grid the engine can run end to end."""
    model = CostModel()
    frame = generate_ohlcv(N_BARS, seed)
    multipliers = spread_multipliers(pd.DatetimeIndex(frame.index), model)
    bars = build_bars(frame, multipliers, model, points_per_price_unit=100.0)
    risk = RiskModel(
        stop_atr_mult=1.5,
        target_atr_mult=1.5,
        max_hold_bars=HORIZON,
        risk_per_trade_currency=RISK,
    )

    atr_series = ATR(period=14).compute(frame).to_numpy(dtype=np.float64) * 100.0
    decisions = np.arange(24, N_BARS - HORIZON - 2, HORIZON, dtype=np.int64)
    atr_points = atr_series[decisions]
    keep = np.isfinite(atr_points) & (atr_points > 0)
    return Setup(
        model=model,
        frame=frame,
        bars=bars,
        risk=risk,
        decisions=decisions[keep],
        atr_points=atr_points[keep],
    )


def _run(source: DirectionSource, name: str, setup: Setup) -> ArmResult:
    """Run one source over a prepared setup."""
    return run_arm(
        name=name,
        source=source,
        frame=setup.frame,
        bars=setup.bars,
        decisions=setup.decisions,
        atr_points=setup.atr_points,
        risk=setup.risk,
        model=setup.model,
    )


def test_an_arm_produces_one_result_per_decision() -> None:
    setup = _setup()
    n = setup.n
    arm = _run(RandomDirection(seed=0), "control", setup)

    assert arm.n_decisions == n
    assert len(arm.trades) == n
    assert arm.n_flat == 0
    assert sum(arm.exit_reasons().values()) == n
    assert set(arm.exit_reasons()) == {r.value for r in ExitReason}


def test_the_arms_differ_only_in_direction() -> None:
    setup = _setup()
    n = setup.n
    longs = _run(LogisticDirection(tuple([0.9] * n)), "all_long", setup)
    shorts = _run(LogisticDirection(tuple([0.1] * n)), "all_short", setup)

    assert len(longs.trades) == len(shorts.trades)
    for a, b in zip(longs.trades, shorts.trades, strict=True):
        assert a.direction is Direction.LONG
        assert b.direction is Direction.SHORT
        assert a.decision_index == b.decision_index
        assert a.entry_index == b.entry_index
        assert a.entry_timestamp == b.entry_timestamp
        assert a.entry_mid_points == pytest.approx(b.entry_mid_points)
        assert a.atr_points == pytest.approx(b.atr_points)
        assert a.lots == pytest.approx(b.lots)
        assert a.commission_points == pytest.approx(b.commission_points)
        # Stop and target sit on opposite sides, at the same distance.
        assert a.stop_points is not None
        assert b.stop_points is not None
        assert abs(a.stop_points - a.entry_mid_points) == pytest.approx(
            abs(b.stop_points - b.entry_mid_points)
        )


def test_a_declined_decision_scores_zero_and_is_counted() -> None:
    setup = _setup()
    n = setup.n
    probabilities = [0.9] * n
    probabilities[0] = 0.5
    arm = _run(LogisticDirection(tuple(probabilities)), "with_a_tie", setup)

    assert arm.n_flat == 1
    assert len(arm.trades) == n - 1
    assert arm.r_by_decision[0] == 0.0
    assert arm.direction_counts()["flat"] == 1


def test_a_source_returning_the_wrong_count_is_refused() -> None:
    setup = _setup()
    with pytest.raises(ValueError, match="probabilities for"):
        _run(LogisticDirection((0.6, 0.6)), "too_short", setup)


def test_a_decision_that_cannot_complete_is_refused() -> None:
    setup = _setup()
    setup.decisions = np.array([N_BARS - 2], dtype=np.int64)
    setup.atr_points = np.array([1000.0], dtype=np.float64)
    with pytest.raises(ValueError, match="cannot complete inside the series"):
        _run(RandomDirection(seed=0), "past_the_end", setup)


def test_mismatched_atr_length_is_refused() -> None:
    setup = _setup()
    setup.atr_points = np.array([1000.0], dtype=np.float64)
    with pytest.raises(ValueError, match="ATR values for"):
        _run(RandomDirection(seed=0), "ragged", setup)


def test_the_random_control_is_reproducible_and_price_blind() -> None:
    setup_a = _setup(seed=7)
    setup_b = _setup(seed=11)

    first = RandomDirection(seed=3).directions(setup_a.frame, setup_a.decisions)
    again = RandomDirection(seed=3).directions(setup_a.frame, setup_a.decisions)
    assert first == again

    # Different prices, same decision count, same seed: the control must not
    # have acquired a view from the data.
    assert setup_b.n == setup_a.n
    other = RandomDirection(seed=3).directions(setup_b.frame, setup_b.decisions)
    assert first == other


def test_cost_components_are_reported_in_r_and_sum_to_the_total() -> None:
    setup = _setup()
    arm = _run(RandomDirection(seed=0), "control", setup)

    total = sum(arm.cost_r(c) for c in COST_COMPONENTS)
    assert arm.total_cost_r() == pytest.approx(total)
    assert all(arm.cost_r(c) >= 0 for c in COST_COMPONENTS)
    with pytest.raises(ValueError, match="unknown cost component"):
        arm.cost_r("not_a_component")


def test_commission_is_identical_across_arms_on_the_same_grid() -> None:
    setup = _setup()
    n = setup.n
    signal = _run(LogisticDirection(tuple([0.9] * n)), "signal", setup)
    controls = tuple(
        _run(RandomDirection(seed=s), f"random_s{s}", setup) for s in range(4)
    )

    verdict = assess_cost_invariance(signal, controls)
    assert verdict.construction_violations == ()
    commission = next(c for c in verdict.components if c.component == "commission")
    assert commission.divergence_r == pytest.approx(0.0, abs=1e-12)
    assert commission.identical_by_construction


def test_swap_and_exit_side_costs_are_allowed_to_diverge() -> None:
    setup = _setup()
    n = setup.n
    signal = _run(LogisticDirection(tuple([0.9] * n)), "signal", setup)
    controls = (_run(LogisticDirection(tuple([0.1] * n)), "all_short", setup),)

    verdict = assess_cost_invariance(signal, controls)
    swap = next(c for c in verdict.components if c.component == "swap")
    # A long book and a short book pay different financing. If this were ever
    # zero the invariance would look stronger than H-003 §E says it is.
    assert swap.divergence_r > 0
    assert not swap.identical_by_construction


def _arm(name: str, cost_scale: float, expectancy: float) -> ArmResult:
    """A stub result carrying a chosen expectancy, for verdict-logic tests."""
    del cost_scale
    return ArmResult(
        name=name,
        decision_method="stub",
        trades=(),
        r_by_decision=np.full(10, expectancy, dtype=np.float64),
        n_flat=0,
    )


def test_a_component_that_cannot_differ_voids_the_comparison() -> None:
    verdict = CostInvariance(
        components=(
            ComponentComparison("commission", 0.01, 0.02, True),
            ComponentComparison("swap", 0.01, 0.01, False),
        ),
        expectancy_difference_r=1.0,
        tolerance=0.10,
        construction_violations=("commission",),
    )
    assert not verdict.holds
    assert "VOID" in verdict.statement()
    assert "defect" in verdict.statement()


def test_divergence_above_tolerance_requires_the_difference_breakeven() -> None:
    verdict = CostInvariance(
        components=(ComponentComparison("swap", 0.05, 0.00, False),),
        expectancy_difference_r=0.10,
        tolerance=0.10,
        construction_violations=(),
    )
    assert verdict.divergence_share == pytest.approx(0.5)
    assert not verdict.holds
    assert "breakeven spread of the difference is required" in verdict.statement()


def test_divergence_inside_tolerance_permits_the_insensitivity_claim() -> None:
    verdict = CostInvariance(
        components=(ComponentComparison("swap", 0.005, 0.000, False),),
        expectancy_difference_r=0.10,
        tolerance=0.10,
        construction_violations=(),
    )
    assert verdict.holds
    assert "Cost invariance holds" in verdict.statement()


def test_a_zero_effect_can_never_clear_the_tolerance() -> None:
    verdict = CostInvariance(
        components=(ComponentComparison("swap", 0.001, 0.000, False),),
        expectancy_difference_r=0.0,
        tolerance=0.10,
        construction_violations=(),
    )
    assert verdict.divergence_share == float("inf")
    assert not verdict.holds


def test_the_comparison_needs_a_control() -> None:
    with pytest.raises(ValueError, match="at least one control"):
        assess_cost_invariance(_arm("signal", 1.0, 0.1), ())
