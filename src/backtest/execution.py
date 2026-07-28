"""The position lifecycle — one function, every arm, every rung.

H-003 §I requirement 1. There is exactly one place in this project where a
decision becomes a filled, managed, closed position, and every direction source
routes through it. That is not tidiness: "identical risk management" is the
phrase H-003's claim turns on, and the only way to make it a fact rather than an
assertion is to give the arms no way to differ. They pass a direction. Nothing
else about them reaches this module.

Executable prices, not mids
---------------------------

Levels are tested against the quote you would actually exit on — the bid for a
long, the ask for a short — rather than against the mid. The difference is half
a spread and its sign is not neutral: a long's stop triggers when the *bid*
touches it, which happens before the mid does. Testing on mids would make stops
fire later than they really do, which is an optimistic error, and
``EVALUATION.md`` §10 does not permit one.

Stops and targets are anchored on the entry **mid** and tested on the exit-side
quote. That is a deliberate half-spread of pessimism in the trigger, and it is
stated here rather than buried: a position is slightly more likely to be stopped
than a mid-to-mid model would suggest, and slightly less likely to reach target.

Where the pessimism is, in one list
-----------------------------------

===============================  ==========================================
ambiguous bar                    If one bar's range contains both the stop
                                 and the target, **the stop is taken.** H1
                                 bars carry no intrabar path, and the
                                 favourable reading would be an assumption
                                 about an ordering nobody observed.
stop fills                       Gap-through: the worse of the level and the
                                 bar's open. §10 — stops do not fill at the
                                 stop price.
target fills                     At the level exactly, never at a favourable
                                 gap. A limit order fills at its limit.
latency                          Charged on market orders — entry, stop, time
                                 exit — and not on a limit target, where the
                                 mechanism does not exist.
trigger quote                    The exit-side quote, half a spread earlier
                                 than the mid.
===============================  ==========================================

Everything is in **points**. The caller converts once, at the boundary, in
``engine``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from backtest.costs import (
    POINT_VALUE_PER_LOT,
    CostModel,
    commission_points,
    latency_points,
    rollovers_crossed,
    slippage_points,
    swap_points,
)


class Direction(StrEnum):
    """Which way a decision goes."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"

    @property
    def sign(self) -> int:
        """+1 long, -1 short, 0 flat."""
        return {Direction.LONG: 1, Direction.SHORT: -1, Direction.FLAT: 0}[self]


class ExitReason(StrEnum):
    """Why a position closed."""

    STOP = "stop"
    TARGET = "target"
    TIME = "time"


#: Reasons whose order reaches the market as a market order, and therefore pays
#: the latency cost. A limit at the target does not.
MARKET_EXITS: Final = frozenset({ExitReason.STOP, ExitReason.TIME})


@dataclass(frozen=True, slots=True)
class RiskModel:
    """The risk geometry both arms share.

    ``stop_atr_mult`` and ``target_atr_mult`` are optional so that a rung which
    holds a position without protective orders — ``EVALUATION.md`` §2 rung 3,
    buy-and-hold risk-parity sized — is expressible as a configuration of this
    engine rather than as a second engine. That is H-003 §I requirement 6, and
    it is the reason the field is ``float | None`` rather than a large number
    standing in for "off".
    """

    stop_atr_mult: float | None
    target_atr_mult: float | None
    max_hold_bars: int
    risk_per_trade_currency: float

    def __post_init__(self) -> None:
        """Reject an incoherent geometry.

        Raises:
            ValueError: If the holding period or risk is not positive, or a
                multiplier is present but not positive.
        """
        if self.max_hold_bars <= 0:
            raise ValueError(
                f"max_hold_bars must be positive, got {self.max_hold_bars}"
            )
        if self.risk_per_trade_currency <= 0:
            raise ValueError(
                f"risk_per_trade_currency must be positive, got "
                f"{self.risk_per_trade_currency}"
            )
        for label, mult in (
            ("stop_atr_mult", self.stop_atr_mult),
            ("target_atr_mult", self.target_atr_mult),
        ):
            if mult is not None and mult <= 0:
                raise ValueError(f"{label} must be positive or None, got {mult}")

    def sizing_reference_points(self, atr_points: float) -> float:
        """The distance risk is normalised against.

        The stop distance when there is a stop; the raw ATR when there is not.
        The second case is what makes rung 3 "risk-parity sized" rather than
        "one lot regardless of volatility".

        Args:
            atr_points: ATR at the decision bar.

        Returns:
            Points.
        """
        if self.stop_atr_mult is None:
            return atr_points
        return self.stop_atr_mult * atr_points


@dataclass(frozen=True, slots=True)
class Trade:
    """One decision, filled, managed and closed.

    Cost fields are **positive points already deducted** from
    :attr:`net_points`. ``gap_through_points`` is the exception and is a
    diagnostic: the fill it describes is already inside ``mid_gross_points``, so
    adding it to the cost total would count it twice.
    """

    decision_index: int
    entry_index: int
    exit_index: int
    direction: Direction
    exit_reason: ExitReason
    entry_timestamp: pd.Timestamp
    exit_timestamp: pd.Timestamp
    lots: float
    atr_points: float
    entry_mid_points: float
    exit_mid_points: float
    stop_points: float | None
    target_points: float | None
    mid_gross_points: float
    spread_points: float
    slippage_points: float
    latency_points: float
    commission_points: float
    swap_points: float
    gap_through_points: float
    nights: int
    net_points: float
    #: Carried so :attr:`r_multiple` does not need the risk model passed back in.
    risk_currency: float

    @property
    def cost_points(self) -> float:
        """Total deducted cost, excluding the gap-through diagnostic."""
        return (
            self.spread_points
            + self.slippage_points
            + self.latency_points
            + self.commission_points
            + self.swap_points
        )

    @property
    def net_currency(self) -> float:
        """Net result in account currency."""
        return self.net_points * self.lots * POINT_VALUE_PER_LOT

    @property
    def r_multiple(self) -> float:
        """Net result as a multiple of the risk budgeted at entry.

        A stop that fills at its level costs slightly more than ``-1R``: costs
        are on top, and a gap-through fill is below the level. That the number
        can exceed ``-1`` in magnitude is the model working, not a defect.
        """
        return self.net_currency / self.risk_currency


@dataclass(frozen=True, slots=True)
class BarArrays:
    """Price series in points, plus the timestamps and per-bar half-spreads.

    Built once per run by ``engine`` so the lifecycle never touches a DataFrame
    and never re-derives a cost.
    """

    index: pd.DatetimeIndex
    open: npt.NDArray[np.float64]
    high: npt.NDArray[np.float64]
    low: npt.NDArray[np.float64]
    half_spread: npt.NDArray[np.float64]

    def __post_init__(self) -> None:
        """Reject ragged input.

        Raises:
            ValueError: If the arrays disagree in length.
        """
        lengths = {
            len(self.index),
            len(self.open),
            len(self.high),
            len(self.low),
            len(self.half_spread),
        }
        if len(lengths) != 1:
            raise ValueError(f"BarArrays fields disagree in length: {sorted(lengths)}")

    def __len__(self) -> int:
        """Number of bars."""
        return len(self.index)


def build_bars(
    frame: pd.DataFrame,
    multipliers: npt.NDArray[np.float64],
    model: CostModel,
    points_per_price_unit: float,
) -> BarArrays:
    """Convert a snapshot frame into the arrays the lifecycle reads.

    Args:
        frame: Derived snapshot, UTC-indexed, with ``open``/``high``/``low``.
        multipliers: Per-bar event multiplier from
            :func:`backtest.costs.spread_multipliers`.
        model: The cost model.
        points_per_price_unit: Scale factor, ``10 ** PRICE_DECIMALS``.

    Returns:
        The arrays.

    Raises:
        ValueError: If a required column is absent or the index is not
            timezone-aware.
    """
    missing = [c for c in ("open", "high", "low") if c not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing columns {missing}")
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("frame must carry a timezone-aware DatetimeIndex")

    # Vectorised form of :func:`backtest.costs.half_spread_points`. The scalar
    # function stays the reference definition and a test asserts the two agree,
    # so the fast path here cannot drift away from it unnoticed.
    half = 0.5 * model.spread_floor_points * np.asarray(multipliers, dtype=np.float64)
    return BarArrays(
        index=index,
        open=frame["open"].to_numpy(dtype=np.float64) * points_per_price_unit,
        high=frame["high"].to_numpy(dtype=np.float64) * points_per_price_unit,
        low=frame["low"].to_numpy(dtype=np.float64) * points_per_price_unit,
        half_spread=half,
    )


def required_bars_after(decision_index: int, risk: RiskModel) -> int:
    """Last bar index a decision at ``decision_index`` can read.

    Entry is the open of ``decision_index + 1``; the time exit is the open of
    ``decision_index + 1 + max_hold_bars``. A decision whose window runs past
    the series is not a shorter trade, it is an unfinished one, and the engine
    excludes it rather than truncating it.

    Args:
        decision_index: Bar the signal was computed on.
        risk: The risk geometry.

    Returns:
        The highest bar index the simulation will touch.
    """
    return decision_index + 1 + risk.max_hold_bars


def simulate_position(
    *,
    bars: BarArrays,
    decision_index: int,
    direction: Direction,
    atr_points: float,
    risk: RiskModel,
    model: CostModel,
) -> Trade | None:
    """Fill, manage and close one decision.

    Args:
        bars: Price arrays in points.
        decision_index: Bar the signal was computed on. Entry is the next bar.
        direction: Which way to trade. ``FLAT`` returns ``None``.
        atr_points: ATR at ``decision_index``, in points.
        risk: The risk geometry.
        model: The cost model.

    Returns:
        The closed trade, or ``None`` if ``direction`` is ``FLAT``.

    Raises:
        ValueError: If the trade window runs past the series, or ``atr_points``
            is not positive and finite.
    """
    if direction is Direction.FLAT:
        return None

    last_needed = required_bars_after(decision_index, risk)
    if decision_index < 0 or last_needed >= len(bars):
        raise ValueError(
            f"decision at {decision_index} needs bars through {last_needed} but "
            f"the series has {len(bars)}. The engine must exclude such "
            f"decisions; truncating the holding period would silently change "
            f"the registered geometry."
        )
    if not np.isfinite(atr_points) or atr_points <= 0:
        raise ValueError(
            f"atr_points must be positive and finite, got {atr_points}. A "
            f"missing ATR is a missing stop distance and a missing size; "
            f"DATA_CONTRACT.md §6 forbids substituting a value for it."
        )

    sign = direction.sign
    entry_index = decision_index + 1
    entry_mid = float(bars.open[entry_index])

    reference = risk.sizing_reference_points(atr_points)
    lots = risk.risk_per_trade_currency / (reference * POINT_VALUE_PER_LOT)

    stop = (
        None
        if risk.stop_atr_mult is None
        else entry_mid - sign * risk.stop_atr_mult * atr_points
    )
    target = (
        None
        if risk.target_atr_mult is None
        else entry_mid + sign * risk.target_atr_mult * atr_points
    )

    entry_half = float(bars.half_spread[entry_index])
    entry_slip = slippage_points(atr_points, lots, model)
    entry_latency = latency_points(atr_points, model)

    exit_index, exit_reason, exit_level, gap = _resolve_exit(
        bars=bars,
        entry_index=entry_index,
        sign=sign,
        stop=stop,
        target=target,
        max_hold_bars=risk.max_hold_bars,
    )

    exit_half = float(bars.half_spread[exit_index])
    exit_slip = slippage_points(atr_points, lots, model)
    exit_latency = (
        latency_points(atr_points, model) if exit_reason in MARKET_EXITS else 0.0
    )

    # The exit level is an executable price on the far-side quote. Its mid
    # equivalent is what makes the decomposition below reconcile with a
    # mid-to-mid gross minus itemised costs.
    exit_mid = exit_level + sign * exit_half

    mid_gross = sign * (exit_mid - entry_mid)
    spread = entry_half + exit_half
    slippage = entry_slip + exit_slip
    latency = entry_latency + exit_latency
    commission = commission_points(lots, sides=2, model=model)
    nights = rollovers_crossed(bars.index[entry_index], bars.index[exit_index])
    swap = swap_points(direction is Direction.LONG, nights, lots, model)

    net = mid_gross - spread - slippage - latency - commission - swap

    return Trade(
        decision_index=decision_index,
        entry_index=entry_index,
        exit_index=exit_index,
        direction=direction,
        exit_reason=exit_reason,
        entry_timestamp=bars.index[entry_index],
        exit_timestamp=bars.index[exit_index],
        lots=lots,
        atr_points=atr_points,
        entry_mid_points=entry_mid,
        exit_mid_points=exit_mid,
        stop_points=stop,
        target_points=target,
        mid_gross_points=mid_gross,
        spread_points=spread,
        slippage_points=slippage,
        latency_points=latency,
        commission_points=commission,
        swap_points=swap,
        gap_through_points=gap,
        nights=nights,
        net_points=net,
        risk_currency=risk.risk_per_trade_currency,
    )


def _resolve_exit(
    *,
    bars: BarArrays,
    entry_index: int,
    sign: int,
    stop: float | None,
    target: float | None,
    max_hold_bars: int,
) -> tuple[int, ExitReason, float, float]:
    """Find where and why the position closes.

    Scans from the entry bar inclusive — the entry is the open of that bar, so
    its range is live — through ``max_hold_bars`` bars, then times out at the
    open of the next one.

    Args:
        bars: Price arrays.
        entry_index: Bar the position opened on.
        sign: +1 long, -1 short.
        stop: Stop level in points, or ``None``.
        target: Target level in points, or ``None``.
        max_hold_bars: Bars the position may remain open.

    Returns:
        ``(exit_index, reason, executable_exit_level, gap_through_points)``.
    """
    for i in range(entry_index, entry_index + max_hold_bars):
        half = float(bars.half_spread[i])
        # The quote a position exits on: bid for a long, ask for a short.
        far_high = float(bars.high[i]) - sign * half
        far_low = float(bars.low[i]) - sign * half
        far_open = float(bars.open[i]) - sign * half

        # Stop is tested first and returns first. That ordering *is* the
        # ambiguous-bar rule: when one bar contains both levels there is no
        # intrabar path to appeal to, so the unfavourable one is taken.
        if stop is not None and (far_low <= stop if sign > 0 else far_high >= stop):
            fill = min(far_open, stop) if sign > 0 else max(far_open, stop)
            return i, ExitReason.STOP, fill, sign * (stop - fill)
        if target is not None and (
            far_high >= target if sign > 0 else far_low <= target
        ):
            return i, ExitReason.TARGET, target, 0.0

    exit_index = entry_index + max_hold_bars
    half = float(bars.half_spread[exit_index])
    return exit_index, ExitReason.TIME, float(bars.open[exit_index]) - sign * half, 0.0
