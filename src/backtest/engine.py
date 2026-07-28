"""Running an arm, and comparing what two arms actually paid.

H-003 §I requirements 1 and 6 meet here: an arm is *a direction source plus the
shared risk geometry*, and running one is a loop over the decision grid calling
the single position lifecycle. Nothing an arm supplies can reach the fills.

The realised-cost comparison is not a footnote
----------------------------------------------

H-003 §E claims a partial invariance: the two arms trade the same timestamps at
the same size, so some cost components are identical across them and drop out of
the paired difference, which would make the primary metric largely insensitive
to H-005's spread floor. **That claim is weaker than it first looks, and this
module measures it rather than repeating it.**

Which components are actually identical by construction:

======================  ===========================================
entry half-spread       identical — same bar, same multiplier
entry slippage          identical — same ATR, same lots
entry latency           identical — same ATR
commission              identical — same lots, two sides always
======================  ===========================================

Which are not, and why:

======================  ===========================================
exit half-spread        the arms exit on **different bars**, and the
                        multiplier is a property of the bar
exit latency            a limit target pays none, a stop or a time
                        exit does; the arms hit different ones
swap                    direction-asymmetric rates *and* different
                        holding lengths
gap-through             a long and a short gap through different
                        levels on different bars
======================  ===========================================

So the honest question is not "are the costs equal" — four components provably
are not — but "is the residual cost divergence small next to the effect being
measured". :func:`assess_cost_invariance` answers that, and when the answer is
no it does not add a caveat: it changes what the run must report, because a
floor-sensitive difference needs its own breakeven spread.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from backtest.costs import POINT_VALUE_PER_LOT, CostModel
from backtest.direction import DirectionSource
from backtest.execution import (
    BarArrays,
    Direction,
    ExitReason,
    RiskModel,
    Trade,
    required_bars_after,
    simulate_position,
)

#: Cost components, in the order reported. ``gap_through`` is a diagnostic and
#: is excluded from the total — the fill it describes is already inside the
#: gross result, so adding it would count it twice.
COST_COMPONENTS: Final = (
    "spread",
    "slippage",
    "latency",
    "commission",
    "swap",
)

#: A registered researcher degree of freedom. The paired difference's
#: insensitivity to the spread floor is void when the arms' realised cost
#: differs by more than this fraction of the measured expectancy difference.
#: Ten percent is a judgement, not a measurement, and it is written down before
#: the run for the reason every other constant in this project is.
COST_DIVERGENCE_TOLERANCE: Final = 0.10


@dataclass(frozen=True, slots=True)
class ArmResult:
    """Everything one arm produced.

    ``r_by_decision`` is aligned to the decision grid, not to the trades, so two
    arms can be differenced element-wise. A decision the source declined carries
    ``0.0`` — no position, no cost — and is counted in ``n_flat`` so a source
    that declines often cannot look like one that trades badly.
    """

    name: str
    decision_method: str
    trades: tuple[Trade, ...]
    r_by_decision: npt.NDArray[np.float64]
    n_flat: int

    @property
    def n_decisions(self) -> int:
        """Decisions offered to the source."""
        return len(self.r_by_decision)

    @property
    def expectancy_r(self) -> float:
        """Mean result per decision, in units of the risk budgeted at entry."""
        if self.n_decisions == 0:
            return float("nan")
        return float(np.mean(self.r_by_decision))

    def exit_reasons(self) -> dict[str, int]:
        """How the positions closed.

        Returns:
            Reason name to count, every reason present even at zero.
        """
        counts = dict.fromkeys((r.value for r in ExitReason), 0)
        for trade in self.trades:
            counts[trade.exit_reason.value] += 1
        return counts

    def direction_counts(self) -> dict[str, int]:
        """How often the source went each way.

        Returns:
            Direction name to count, every direction present even at zero.
        """
        counts = dict.fromkeys((d.value for d in Direction), 0)
        counts[Direction.FLAT.value] = self.n_flat
        for trade in self.trades:
            counts[trade.direction.value] += 1
        return counts

    def cost_r(self, component: str) -> float:
        """Mean realised cost of one component, per decision, in R.

        Points are not comparable across trades because size varies with ATR.
        Dividing by the risk budgeted at entry puts every trade in the same unit
        as the expectancy, which is the only unit in which "is this cost big
        next to the effect" is a coherent question.

        Args:
            component: One of :data:`COST_COMPONENTS`, or ``"gap_through"``.

        Returns:
            Mean R per decision. Zero-trade arms return ``nan``.

        Raises:
            ValueError: If the component is unknown.
        """
        if component not in {*COST_COMPONENTS, "gap_through"}:
            raise ValueError(f"unknown cost component {component!r}")
        if self.n_decisions == 0:
            return float("nan")
        total = 0.0
        for trade in self.trades:
            points = float(getattr(trade, f"{component}_points"))
            total += points * trade.lots * POINT_VALUE_PER_LOT / trade.risk_currency
        return total / self.n_decisions

    def total_cost_r(self) -> float:
        """Mean realised cost per decision, in R, excluding the diagnostic."""
        return sum(self.cost_r(c) for c in COST_COMPONENTS)


def run_arm(
    *,
    name: str,
    source: DirectionSource,
    frame: pd.DataFrame,
    bars: BarArrays,
    decisions: npt.NDArray[np.int64],
    atr_points: npt.NDArray[np.float64],
    risk: RiskModel,
    model: CostModel,
) -> ArmResult:
    """Run one direction source over the decision grid.

    Args:
        name: Arm identifier for reports.
        source: The direction source.
        frame: Bar series, passed to the source.
        bars: Price arrays in points.
        decisions: Decision bar positions.
        atr_points: ATR at each decision, same length as ``decisions``.
        risk: The shared risk geometry.
        model: The cost model.

    Returns:
        The arm's result.

    Raises:
        ValueError: If the inputs disagree in length, or a decision's trade
            window runs past the series.
    """
    if len(atr_points) != len(decisions):
        raise ValueError(f"{len(atr_points)} ATR values for {len(decisions)} decisions")
    for position in decisions:
        if required_bars_after(int(position), risk) >= len(bars):
            raise ValueError(
                f"decision at bar {int(position)} cannot complete inside the "
                f"series under max_hold_bars={risk.max_hold_bars}. Eligibility "
                f"must exclude it upstream — silently shortening the hold would "
                f"change the registered geometry for a subset of decisions."
            )

    directions = source.directions(frame, decisions)
    if len(directions) != len(decisions):
        raise ValueError(
            f"{source.name} returned {len(directions)} directions for "
            f"{len(decisions)} decisions"
        )

    trades: list[Trade] = []
    results = np.zeros(len(decisions), dtype=np.float64)
    n_flat = 0

    for slot, (position, direction) in enumerate(
        zip(decisions, directions, strict=True)
    ):
        trade = simulate_position(
            bars=bars,
            decision_index=int(position),
            direction=direction,
            atr_points=float(atr_points[slot]),
            risk=risk,
            model=model,
        )
        if trade is None:
            n_flat += 1
            continue
        trades.append(trade)
        results[slot] = trade.r_multiple

    return ArmResult(
        name=name,
        decision_method=source.decision_method,
        trades=tuple(trades),
        r_by_decision=results,
        n_flat=n_flat,
    )


@dataclass(frozen=True, slots=True)
class ComponentComparison:
    """One cost component, as both arms actually paid it."""

    component: str
    signal_r: float
    control_r: float
    identical_by_construction: bool

    @property
    def divergence_r(self) -> float:
        """Absolute difference in mean cost per decision, in R."""
        return abs(self.signal_r - self.control_r)


#: Components that cannot differ between two arms trading the same timestamps at
#: the same size. Asserted rather than assumed: if one of these ever diverges,
#: something in the sizing or the grid has broken, and that is a louder failure
#: than a cost difference.
IDENTICAL_BY_CONSTRUCTION: Final = frozenset({"commission"})


@dataclass(frozen=True, slots=True)
class CostInvariance:
    """Whether H-003 §E's floor-insensitivity argument survives contact.

    ``holds`` is not "the costs matched". It is "the cost divergence is small
    enough, next to the measured effect, that the effect is not an artefact of
    the arms paying different prices".
    """

    components: tuple[ComponentComparison, ...]
    expectancy_difference_r: float
    tolerance: float
    construction_violations: tuple[str, ...]

    @property
    def total_divergence_r(self) -> float:
        """Absolute difference in total realised cost per decision, in R."""
        signal = sum(c.signal_r for c in self.components)
        control = sum(c.control_r for c in self.components)
        return abs(signal - control)

    @property
    def divergence_share(self) -> float:
        """Cost divergence as a fraction of the measured effect."""
        effect = abs(self.expectancy_difference_r)
        if effect == 0.0:
            return float("inf")
        return self.total_divergence_r / effect

    @property
    def holds(self) -> bool:
        """Whether the floor-insensitivity claim may be made."""
        return (
            not self.construction_violations and self.divergence_share <= self.tolerance
        )

    def statement(self) -> str:
        """The sentence the run must print, in either case.

        Returns:
            A finding, not a caveat.
        """
        if self.construction_violations:
            return (
                f"COST INVARIANCE VOID — components that cannot differ did: "
                f"{', '.join(self.construction_violations)}. This is not a cost "
                f"finding, it is a defect in the grid or the sizing. The "
                f"comparison is not interpretable until it is fixed."
            )
        if self.holds:
            return (
                f"Cost invariance holds. Realised cost differs between the arms "
                f"by {self.total_divergence_r:.6f} R per decision, "
                f"{self.divergence_share:.1%} of the measured expectancy "
                f"difference — within the registered {self.tolerance:.0%} "
                f"tolerance. The paired difference is not materially a function "
                f"of the spread floor."
            )
        return (
            f"COST INVARIANCE DOES NOT HOLD. Realised cost differs between the "
            f"arms by {self.total_divergence_r:.6f} R per decision, "
            f"{self.divergence_share:.1%} of the measured expectancy difference, "
            f"above the registered {self.tolerance:.0%} tolerance. H-003 §E's "
            f"floor-insensitivity argument is void for this run: the primary "
            f"metric IS a function of H-005's spread floor, and the breakeven "
            f"spread of the difference is required alongside the signal arm's."
        )


def assess_cost_invariance(
    signal: ArmResult,
    controls: tuple[ArmResult, ...],
    tolerance: float = COST_DIVERGENCE_TOLERANCE,
) -> CostInvariance:
    """Measure what each side actually paid, component by component.

    The control is the *mean over the control arms*, matching the paired
    statistic in H-003 §F: the thing the signal is differenced against is the
    average random arm, so the average random arm is the thing whose costs
    matter.

    Args:
        signal: The signal arm's result.
        controls: The control arms' results.
        tolerance: Divergence share above which the invariance claim is void.

    Returns:
        The assessment.

    Raises:
        ValueError: If there are no control arms.
    """
    if not controls:
        raise ValueError("cost invariance needs at least one control arm")

    comparisons: list[ComponentComparison] = []
    violations: list[str] = []
    for component in COST_COMPONENTS:
        signal_r = signal.cost_r(component)
        control_r = float(np.mean([c.cost_r(component) for c in controls]))
        by_construction = component in IDENTICAL_BY_CONSTRUCTION
        if by_construction and not np.isclose(signal_r, control_r, rtol=0, atol=1e-12):
            violations.append(component)
        comparisons.append(
            ComponentComparison(
                component=component,
                signal_r=signal_r,
                control_r=control_r,
                identical_by_construction=by_construction,
            )
        )

    control_expectancy = float(np.mean([c.expectancy_r for c in controls]))
    return CostInvariance(
        components=tuple(comparisons),
        expectancy_difference_r=signal.expectancy_r - control_expectancy,
        tolerance=tolerance,
        construction_violations=tuple(violations),
    )
