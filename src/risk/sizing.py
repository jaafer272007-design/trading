"""Position size from a risk budget and a volatility-scaled stop.

The arithmetic is one division. What makes it worth its own module is
everything that surrounds the division, all of which is a place to lose money
quietly:

**The stop is scaled to volatility, not to a fixed distance.** A fixed
point-distance stop is a different risk on a quiet day than on a violent one,
which is the same as having no risk policy. ``k x ATR`` keeps the risk
constant and lets the distance move.

**The spread is inside the risk, not outside it.** A stop is filled at the
market's other side, so the adverse excursion that costs the budgeted amount is
``k x ATR + spread``, not ``k x ATR``. Sizing on the stop distance alone
overspends the risk budget by the spread's share of it, every time, in the same
direction. The spread used is the broker's **live quoted** figure, read at the
same moment as everything else. It is not
``backtest.costs.SPREAD_FLOOR_POINTS``: that constant is H-005's pessimistic
research substitute, and importing a research substitute into live accounting
is exactly the mistake this layer was built after.

The consequence of using the live quote is stated rather than hidden: a fill
during a wider spread than the one quoted at sizing time overspends the budget
by ``(actual - quoted) x lots x value_per_point``, and that excess is reported
as :attr:`SizingResult.risk_per_extra_spread_point` so the exposure to it is a
number rather than a caveat.

**Rounding is down, and below the minimum is a refusal.** Rounding a size up to
reach the broker's minimum volume silently raises the risk above the budget.
When the budget does not buy the minimum tradeable size, the honest answer is
that the trade does not fit the account.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from risk.refusal import Refusal, RefusalCode
from risk.state import SymbolTerms, value_per_point_per_lot

#: Guard against binary representation turning an exact multiple of the volume
#: step into one ulp below it, which would floor to the step beneath and
#: silently size one increment small. Far below any real volume step.
_STEP_EPSILON: Final = 1e-9

#: Volume steps are 0.01 lots at the smallest anywhere in retail, so eight
#: decimal places is more than enough and keeps the printed size clean.
_VOLUME_DECIMALS: Final = 8


@dataclass(frozen=True, slots=True)
class SizingResult:
    """A size, and every input that produced it.

    Attributes:
        lots: The size to trade, rounded down to the broker's volume step.
        lots_unrounded: Before rounding, for comparison.
        capped_at_maximum: Whether the broker's ``volume_max`` bound it.
        risk_budget: Currency the trade is allowed to lose.
        risk_at_this_size: Currency actually at risk after rounding down.
            Always at or below the budget.
        atr_points: The volatility input.
        stop_multiple: ``k``.
        stop_distance_points: ``k x ATR``.
        spread_points: Live quoted spread added to the adverse excursion.
        adverse_points: ``stop_distance_points + spread_points``.
        value_per_point_per_lot: The currency conversion used.
        risk_per_lot: Currency lost per lot if the stop is hit.
        risk_per_extra_spread_point: Currency of overspend per point by which
            the fill spread exceeds the quoted one.
        stop_price_long: Where the stop sits for a long entered at
            ``reference_price``.
        stop_price_short: The same for a short.
        notes: Anything a reader should know about this size.
    """

    lots: float
    lots_unrounded: float
    capped_at_maximum: bool
    risk_budget: float
    risk_at_this_size: float
    atr_points: float
    stop_multiple: float
    stop_distance_points: float
    spread_points: float
    adverse_points: float
    value_per_point_per_lot: float
    risk_per_lot: float
    risk_per_extra_spread_point: float
    stop_price_long: float | None
    stop_price_short: float | None
    notes: tuple[str, ...]


def round_down_to_step(volume: float, step: float) -> float:
    """Round a volume down to a whole multiple of the broker's step.

    Down, never to nearest. Rounding to nearest raises the risk above the
    budget half the time, and a risk policy that is exceeded half the time is
    not one.

    Args:
        volume: Unrounded lots.
        step: The broker's ``volume_step``.

    Returns:
        The largest multiple of ``step`` at or below ``volume``.

    Raises:
        ValueError: If ``step`` is not positive.
    """
    if step <= 0:
        raise ValueError(f"volume_step must be positive, got {step}")
    steps = math.floor(volume / step + _STEP_EPSILON)
    return round(steps * step, _VOLUME_DECIMALS)


def size_position(
    equity: float,
    risk_pct: float,
    atr_points: float,
    terms: SymbolTerms,
    stop_multiple: float,
    spread_points: float | None = None,
    reference_price: float | None = None,
) -> SizingResult | Refusal:
    """Size a position against a risk budget.

    Args:
        equity: Account equity, account currency.
        risk_pct: Percentage of equity the trade may lose.
        atr_points: Average true range, in points.
        terms: Symbol terms as read from the terminal.
        stop_multiple: ``k`` in ``k x ATR``.
        spread_points: Spread to add to the adverse excursion. Defaults to the
            live quoted spread on ``terms``.
        reference_price: Entry price, used only to place the stop prices in
            the result. Omitting it omits those two fields and nothing else.

    Returns:
        A :class:`SizingResult`, or a :class:`Refusal` naming what stopped it.

    Raises:
        ValueError: If ``equity``, ``risk_pct`` or ``stop_multiple`` is not
            positive. These are caller errors rather than broker conditions,
            so they raise instead of producing a refusal.
    """
    if equity <= 0:
        raise ValueError(f"equity must be positive, got {equity}")
    if risk_pct <= 0:
        raise ValueError(f"risk_pct must be positive, got {risk_pct}")
    if stop_multiple <= 0:
        raise ValueError(f"stop_multiple must be positive, got {stop_multiple}")

    if atr_points <= 0:
        return Refusal(
            RefusalCode.NO_VOLATILITY,
            terms.name,
            f"atr_points={atr_points} is not positive, so there is no stop "
            f"distance to size against; a zero-volatility reading means the "
            f"ATR window is empty or flat, not that risk is zero",
        )

    per_point = value_per_point_per_lot(terms)
    if per_point is None:
        return Refusal(
            RefusalCode.NO_POINT_VALUE,
            terms.name,
            f"point={terms.point}, trade_tick_size={terms.trade_tick_size} "
            f"and trade_tick_value={terms.trade_tick_value} do not yield a "
            f"currency-per-point conversion, so a risk budget in currency "
            f"cannot be turned into a size",
        )

    if terms.volume_step <= 0:
        return Refusal(
            RefusalCode.NO_VOLUME_STEP,
            terms.name,
            f"volume_step={terms.volume_step} is not positive, so no size can "
            f"be rounded to a tradeable increment",
        )

    notes: list[str] = []
    spread = terms.spread_points if spread_points is None else spread_points
    if spread < 0:
        return Refusal(
            RefusalCode.NO_POINT_VALUE,
            terms.name,
            f"spread_points={spread} is negative, which is not a quote this "
            f"layer knows how to reason about",
        )

    stop_distance = stop_multiple * atr_points
    adverse = stop_distance + spread
    risk_budget = equity * risk_pct / 100.0
    risk_per_lot = adverse * per_point
    unrounded = risk_budget / risk_per_lot

    capped = False
    if terms.volume_max > 0 and unrounded > terms.volume_max:
        unrounded = terms.volume_max
        capped = True
        notes.append(
            f"the risk budget buys more than the broker's maximum volume of "
            f"{terms.volume_max}; the size is capped there, which risks less "
            f"than the budget rather than more"
        )

    lots = round_down_to_step(unrounded, terms.volume_step)

    if lots < terms.volume_min:
        return Refusal(
            RefusalCode.SIZE_BELOW_MINIMUM,
            terms.name,
            f"a {risk_pct:.2f}% risk on {equity:,.2f} buys {unrounded:.4f} "
            f"lots at a {adverse:.0f}-point adverse excursion, below the "
            f"broker's minimum of {terms.volume_min}; taking the minimum "
            f"instead would risk "
            f"{terms.volume_min * risk_per_lot / equity * 100.0:.2f}% of "
            f"equity, so this trade does not fit this account",
        )

    stop_long: float | None = None
    stop_short: float | None = None
    if reference_price is not None and reference_price > 0:
        move = stop_distance * terms.point
        stop_long = reference_price - move
        stop_short = reference_price + move

    if spread > 0:
        notes.append(
            f"{spread:.0f} of the {adverse:.0f} adverse points is spread "
            f"({spread / adverse:.0%} of the risk budget); it is the live "
            f"quote at the moment of sizing, not a worst case"
        )

    return SizingResult(
        lots=lots,
        lots_unrounded=unrounded,
        capped_at_maximum=capped,
        risk_budget=risk_budget,
        risk_at_this_size=lots * risk_per_lot,
        atr_points=atr_points,
        stop_multiple=stop_multiple,
        stop_distance_points=stop_distance,
        spread_points=spread,
        adverse_points=adverse,
        value_per_point_per_lot=per_point,
        risk_per_lot=risk_per_lot,
        risk_per_extra_spread_point=lots * per_point,
        stop_price_long=stop_long,
        stop_price_short=stop_short,
        notes=tuple(notes),
    )
