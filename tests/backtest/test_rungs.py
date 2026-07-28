"""The engine must run `EVALUATION.md` §2 rungs 2-4 without new engine work.

This file exists because that is a **testable property, not an intention**, and
because the cheapest moment to find out it is false is now — before the rungs
are registered, while changing the engine still costs nothing.

The three rung sources below are implemented *here*, in the test module, and
deliberately not in ``src``. Two reasons, and the second is the load-bearing one:

1. Rung 4 needs a fast/slow pair and rung 3 needs a sizing rule. Nobody has
   registered those constants. Putting them in ``src`` would move unregistered
   choices into the evaluation path, which is the thing this project spends most
   of its machinery preventing.
2. **Implementing them outside ``src`` is what proves the claim.** If a rung
   could only be built by editing the engine, it could not be built from a test
   module, and this file would not import.

``test_no_rung_has_been_smuggled_into_the_evaluation_path`` closes the loop from
the other side: it fails if someone later adds one of these to ``src`` without
registering it, which is the failure mode this arrangement is exposed to.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

import backtest.direction as direction_module
from backtest.costs import POINT_VALUE_PER_LOT, CostModel, spread_multipliers
from backtest.direction import AlwaysLong, DirectionSource
from backtest.engine import ArmResult, run_arm
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

#: The geometry H-003 §D registers. Rungs 1, 2 and 4 must share it exactly — a
#: ladder whose rungs use different stops is not comparing what it claims to.
H003_RISK = RiskModel(
    stop_atr_mult=1.5,
    target_atr_mult=1.5,
    max_hold_bars=HORIZON,
    risk_per_trade_currency=RISK,
)

#: Rung 3 is the one that needed the engine to admit a position with no
#: protective orders. It differs from H003_RISK in exactly that, and in nothing
#: else.
RUNG3_RISK = RiskModel(
    stop_atr_mult=None,
    target_atr_mult=None,
    max_hold_bars=HORIZON,
    risk_per_trade_currency=RISK,
)


@dataclass(frozen=True, slots=True)
class BuyAndHold:
    """§2 rung 3. Risk-parity sized, and chained across the grid.

    Paired with :data:`RUNG3_RISK` — no stop, no target, held to the next
    decision — a long at every grid point reconstructs a continuously held
    position that is re-sized as volatility changes. That is what "buy-and-hold,
    risk-parity sized" means, and it is a configuration of this engine rather
    than a second one.
    """

    name: str = "rung3_buy_and_hold"
    decision_method: str = "buy_and_hold"

    def directions(
        self, frame: pd.DataFrame, decisions: npt.NDArray[np.int64]
    ) -> tuple[Direction, ...]:
        """Long, every time.

        Args:
            frame: Unused.
            decisions: Decision positions.

        Returns:
            One direction per decision.
        """
        del frame
        return tuple([Direction.LONG] * len(decisions))


@dataclass(frozen=True, slots=True)
class MovingAverageCrossover:
    """§2 rung 4. Can three lines of code match the whole platform?

    Reads closes at and before the decision bar and nothing after it. The
    causality test below is not decoration: a direction source is the one place
    in this design where a rung author could reach forward, because the protocol
    hands it the whole frame.
    """

    fast: int
    slow: int
    name: str = "rung4_ma_crossover"
    decision_method: str = "ma_crossover"

    def directions(
        self, frame: pd.DataFrame, decisions: npt.NDArray[np.int64]
    ) -> tuple[Direction, ...]:
        """Long when the fast average is above the slow one.

        Args:
            frame: Bar series with a ``close`` column.
            decisions: Decision positions.

        Returns:
            One direction per decision.
        """
        close = frame["close"].to_numpy(dtype=np.float64)
        out: list[Direction] = []
        for position in decisions:
            end = int(position) + 1
            fast = float(np.mean(close[max(0, end - self.fast) : end]))
            slow = float(np.mean(close[max(0, end - self.slow) : end]))
            out.append(Direction.LONG if fast > slow else Direction.SHORT)
        return tuple(out)


@dataclass
class Setup:
    """Everything ``run_arm`` needs."""

    model: CostModel
    frame: pd.DataFrame
    bars: BarArrays
    decisions: npt.NDArray[np.int64]
    atr_points: npt.NDArray[np.float64]


@pytest.fixture
def setup() -> Setup:
    """A synthetic frame with a decision grid."""
    model = CostModel()
    frame = generate_ohlcv(N_BARS, seed=7)
    multipliers = spread_multipliers(pd.DatetimeIndex(frame.index), model)
    bars = build_bars(frame, multipliers, model, points_per_price_unit=100.0)
    atr = ATR(period=14).compute(frame).to_numpy(dtype=np.float64) * 100.0
    decisions = np.arange(60, N_BARS - HORIZON - 2, HORIZON, dtype=np.int64)
    atr_points = atr[decisions]
    keep = np.isfinite(atr_points) & (atr_points > 0)
    return Setup(model, frame, bars, decisions[keep], atr_points[keep])


def _run(source: DirectionSource, risk: RiskModel, setup: Setup) -> ArmResult:
    """Run a rung through the unmodified engine."""
    return run_arm(
        name=source.name,
        source=source,
        frame=setup.frame,
        bars=setup.bars,
        decisions=setup.decisions,
        atr_points=setup.atr_points,
        risk=risk,
        model=setup.model,
    )


def test_every_rung_satisfies_the_direction_source_protocol() -> None:
    for source in (AlwaysLong(), BuyAndHold(), MovingAverageCrossover(20, 50)):
        assert isinstance(source, DirectionSource)


def test_rung_2_runs_through_the_unmodified_engine(setup: Setup) -> None:
    arm = _run(AlwaysLong(), H003_RISK, setup)
    assert len(arm.trades) == len(setup.decisions)
    assert arm.direction_counts()["short"] == 0


def test_rung_4_runs_through_the_unmodified_engine(setup: Setup) -> None:
    arm = _run(MovingAverageCrossover(20, 50), H003_RISK, setup)
    counts = arm.direction_counts()
    assert counts["long"] + counts["short"] == len(setup.decisions)
    # A crossover rule that never changes its mind is not a crossover rule, and
    # would make this a second always-long arm without saying so.
    assert counts["long"] > 0
    assert counts["short"] > 0


def test_rung_3_runs_and_is_risk_parity_sized(setup: Setup) -> None:
    arm = _run(BuyAndHold(), RUNG3_RISK, setup)
    trades = arm.trades

    assert len(trades) == len(setup.decisions)
    for trade in trades:
        assert trade.stop_points is None
        assert trade.target_points is None
        # Every position closes at the next decision, so chaining them
        # reconstructs a continuously held long.
        assert trade.exit_reason is ExitReason.TIME
        # Risk parity: size x volatility is the same on every trade.
        assert trade.lots * trade.atr_points * POINT_VALUE_PER_LOT == pytest.approx(
            RISK
        )


def test_rungs_1_2_and_4_share_one_risk_geometry(setup: Setup) -> None:
    # The comparison is only meaningful if the rungs differ in the direction and
    # in nothing else. Asserted on the object, not on a code reading.
    rung2 = _run(AlwaysLong(), H003_RISK, setup)
    rung4 = _run(MovingAverageCrossover(20, 50), H003_RISK, setup)

    by_decision = {t.decision_index: t for t in rung4.trades}
    for trade in rung2.trades:
        other = by_decision[trade.decision_index]
        assert trade.entry_index == other.entry_index
        assert trade.lots == pytest.approx(other.lots)
        assert trade.atr_points == pytest.approx(other.atr_points)


def test_the_crossover_rung_cannot_see_the_future(setup: Setup) -> None:
    # DATA_CONTRACT.md §1, applied to a direction source. Truncating the frame
    # immediately after a decision must not change that decision.
    source = MovingAverageCrossover(20, 50)
    decisions = setup.decisions[:5]
    full = source.directions(setup.frame, decisions)

    for i, position in enumerate(decisions):
        truncated = setup.frame.iloc[: int(position) + 1]
        one = source.directions(truncated, np.array([position], dtype=np.int64))
        assert one[0] is full[i]


def test_no_rung_has_been_smuggled_into_the_evaluation_path() -> None:
    # ``src/backtest/direction.py`` holds the two sources H-003 registers and
    # nothing else. A rung appearing here would be an unregistered constant in
    # the evaluation path; the failure message is the registration conversation.
    defined = {
        name
        for name, obj in vars(direction_module).items()
        if isinstance(obj, type)
        and getattr(obj, "__module__", "") == direction_module.__name__
    }
    assert defined == {
        "DirectionSource",
        "LogisticDirection",
        "RandomDirection",
        # Rung 2, admitted 2026-07-28 when H-007 registered it. This test
        # refused it before that, which is the whole point of the test: the
        # failure message was the registration conversation, and the
        # registration happened. Rungs 3 and 4 are still unregistered and are
        # still built from this module.
        "AlwaysLong",
    }
