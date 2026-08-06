"""Financing cost on an open position: what has been paid, what will be.

This is the mechanism that emptied the account this layer exists for. A long
gold position held for two months is charged financing every night, the charge
does not appear in the platform's profit column in a way anyone looks at, and
it compounds against the position quietly until the margin is gone. Nothing
about it is a prediction problem. It is a number the terminal already knows and
nobody was adding up.

Backward and forward are different quantities, and are labelled as such
--------------------------------------------------------------------------

**What has been paid is measured.** ``position.swap`` is the broker's own
record of what it has charged. It is not modelled, not estimated, and not
subject to any convention this layer has to get right. It is reported as
:attr:`PositionCarry.carry_paid`.

**What will be paid is modelled**, and every model of it can be wrong. Two
routes exist and both are reported:

*declared* — the broker's published nightly rate, converted by
:func:`risk.swap.declared_swap`. This is the forward rate by definition.

*measured* — what this position has actually been charged, divided by the
calendar days it has been open. Backward-looking, and contaminated by where the
triple-swap weekday fell inside the hold, but it needs no convention at all.

When both exist and they disagree, the projection uses **the more expensive of
the two** and says so. That is the conservative direction, and in a layer whose
entire purpose is to stop an account being surprised by a cost, the
conservative direction is the correct default rather than a bias.

Why the *projection* rate is per calendar day rather than per charging event
---------------------------------------------------------------------------

See :mod:`risk.clock`. A broker charges five times a week, one of them tripled,
and nothing at the weekend. A per-calendar-day rate absorbs that schedule, plus
holidays and any rate change during the hold, without modelling any of them --
and it needs no knowledge of which weekday carries the triple charge.

Two measured bases, and why both are reported
---------------------------------------------

The projection wants a rate per calendar day. The *comparison against the
registry* wants a rate per night, because ``backtest.costs`` is quoted per night
and ``rollovers_crossed`` counts nights. Over a whole week the two are the same
number -- seven nights across seven days -- and over a **sub-week hold they are
not**, so both are computed and both are reported:

``rate_measured_per_day``
    ``carry_paid / days_open``. Exact over any whole number of weeks. On a
    shorter hold it is biased by ``nights / days``: a position opened on a
    Tuesday evening and read on a Thursday morning has crossed two midnights in
    1.87 days, and this figure comes out about 7% high.

``rate_measured_per_night``
    ``carry_paid / nights_held``. Exact whenever every midnight crossed carried
    exactly one ordinary charge -- a mid-week hold with no weekend and no
    triple-swap day inside it. Over a hold containing a weekend it is biased the
    other way, because two of the midnights it counts are charged nothing.

**Neither is unbiased for an arbitrary sub-week hold, and their disagreement is
the size of the schedule effect.** That is why the disagreement is reported
rather than resolved: when the two agree, the schedule did not bite and either
figure is the rate. `[MEASURED]` this distinction is not hypothetical -- it is
what made a 2026-08-01 reading of a 44.8-hour hold display a ratio of 3.64x
where the per-night ratio was 3.40x. See :mod:`risk.swap`.

When the rate is itself price-dependent
---------------------------------------

`[MEASURED]` FxPro's gold uses ``swap_mode = 2``, where the charge is
denominated in ounces and the dollar cost therefore moves with the gold price.
For such a symbol the constant-price assumption on every projection below does
double duty: it holds equity constant *and* it holds the financing rate
constant. A long held into a rising market pays more than the projection says,
and :attr:`PositionCarry.notes` says so on every position whose symbol is in one
of those modes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from risk.carry_log import StructuralStatus
from risk.clock import (
    SWAP_UNITS_PER_CALENDAR_DAY,
    RolloverClock,
    days_between,
    hours_between,
)
from risk.refusal import Refusal, RefusalCode
from risk.state import (
    PositionDirection,
    PositionState,
    SymbolTerms,
    value_per_point_per_lot,
)
from risk.swap import DeclaredSwap, SwapMode

#: How far apart the two measured rates may be before the disagreement is
#: named. Expressed as a **fraction of the rate** rather than as a difference
#: in days, because the rate is the thing a reader quotes: a 3.2-hour gap
#: between 1.87 days and 2 midnights is a small number of hours and a 7.2%
#: difference in the figure it produces. One percent, so the note fires on the
#: reading that motivated it rather than only on extreme ones. A reporting
#: threshold; it limits nothing.
BASIS_AGREEMENT_FRACTION: Final = 0.01


class CarrySource(StrEnum):
    """Which route supplied the forward financing rate."""

    #: The broker's published nightly rate.
    DECLARED = "declared"
    #: What this position has actually been charged, per calendar day.
    MEASURED = "measured"
    #: Both routes existed and disagreed; the more expensive one is in use.
    MORE_ADVERSE_OF_BOTH = "more adverse of both"
    #: Neither route was available. Nothing is projected.
    NONE = "none"


@dataclass(frozen=True, slots=True)
class CarryProjection:
    """Financing at one forward horizon, price held constant.

    Attributes:
        horizon_days: Calendar days ahead of the reading.
        additional: Financing that will accrue over the horizon, account
            currency, positive meaning paid.
        cumulative: ``carry_paid + additional``.
        cumulative_pct_of_equity: Cumulative financing as a percentage of
            current equity.
        breakeven_points: Price move, in points and in the position's
            favourable direction, needed at that horizon just to cover
            financing.
        breakeven_pct: The same move as a percentage of the open price.
    """

    horizon_days: float
    additional: float
    cumulative: float
    cumulative_pct_of_equity: float | None
    breakeven_points: float | None
    breakeven_pct: float | None


@dataclass(frozen=True, slots=True)
class PositionCarry:
    """Everything this layer knows about one position's financing.

    Attributes:
        ticket: Broker ticket.
        symbol: Symbol.
        direction: Long or short.
        volume: Lots.
        opened_at: When the position opened, UTC.
        hours_open: Elapsed hours.
        days_open: Elapsed calendar days.
        nights_held: Server midnights crossed, or ``None`` when the server
            clock could not be located. **Not** a count of financing charges;
            see :mod:`risk.clock`.
        has_stop: Whether a stop loss is attached.
        floating_pnl: The position's own floating result, account currency.
        carry_paid: Financing charged so far, positive meaning paid.
        carry_is_credit: True when the broker has paid the account instead.
        carry_pct_of_equity: ``carry_paid`` against current equity.
        carry_vs_floating_pnl: ``carry_paid`` as a share of the absolute
            floating result, or ``None`` when the position is exactly flat.
            The number that says "financing is now the position".
        breakeven_points: Favourable move needed to cover financing paid.
        breakeven_price: The price that move reaches.
        breakeven_pct: That move as a percentage of the open price.
        rate_declared_per_day: Forward rate from the published figure.
        rate_measured_per_day: Forward rate from what was actually charged,
            divided by calendar days.
        rate_measured_per_night: The same charge divided by **midnights
            crossed** instead. ``None`` when the server clock is unavailable or
            no midnight has been crossed. Not used for any projection; it exists
            because the registered constant is per night and comparing a
            per-day figure against it mismatches units on a sub-week hold.
        rate_per_day: The rate the projections use.
        rate_source: Which route it came from.
        projections: Financing at each configured horizon.
        refusals: Anything that could not be computed for this position.
        notes: Sentences worth reading about this position specifically.
    """

    ticket: int
    symbol: str
    direction: PositionDirection
    volume: float
    opened_at: datetime
    hours_open: float
    days_open: float
    nights_held: int | None
    has_stop: bool
    floating_pnl: float
    carry_paid: float
    carry_is_credit: bool
    carry_pct_of_equity: float | None
    carry_vs_floating_pnl: float | None
    breakeven_points: float | None
    breakeven_price: float | None
    breakeven_pct: float | None
    rate_declared_per_day: float | None
    rate_measured_per_day: float | None
    rate_measured_per_night: float | None
    rate_per_day: float | None
    rate_source: CarrySource
    projections: tuple[CarryProjection, ...]
    refusals: tuple[Refusal, ...]
    notes: tuple[str, ...]


def carry_paid(position: PositionState) -> float:
    """Financing charged on a position so far, in charge terms.

    Args:
        position: The open position.

    Returns:
        Positive when the account has paid, negative when it has been paid.
        This is the sign flip against MT5's convention, and it happens exactly
        here so that nothing downstream has to remember it.
    """
    return -position.swap


def _breakeven(carry: float, volume: float, per_point: float | None) -> float | None:
    """Points of favourable move needed to cover a financing charge.

    Args:
        carry: Financing paid, account currency, positive meaning paid.
        volume: Lots.
        per_point: Account currency per point per lot.

    Returns:
        Points, or ``None`` when the point value is unavailable.
    """
    if per_point is None or per_point <= 0 or volume <= 0:
        return None
    return carry / (volume * per_point)


def position_carry(
    position: PositionState,
    terms: SymbolTerms | None,
    declared: DeclaredSwap | Refusal,
    now: datetime,
    equity: float,
    clock: RolloverClock | None,
    horizons: tuple[float, ...],
    minimum_days_for_measured_rate: float,
    structural_status: StructuralStatus | None = None,
) -> PositionCarry:
    """Assemble the financing picture for one position.

    Args:
        position: The open position.
        terms: Symbol terms, or ``None`` when they were not supplied.
        declared: The broker's published swap, normalised, or a refusal.
        now: Reading time, timezone-aware UTC.
        equity: Account equity, for the percentage figures.
        clock: The server clock, or ``None`` when it could not be located.
        horizons: Forward horizons in calendar days.
        minimum_days_for_measured_rate: How long a position must have been
            open before its own charge history is used as a rate.
        structural_status: What the carry log currently establishes, so that
            the price-dependence note is dated by the log rather than by a
            literal.

    Returns:
        The position's financing report, including every refusal it hit.
    """
    refusals: list[Refusal] = []
    notes: list[str] = []

    hours = hours_between(position.opened_at, now)
    days = days_between(position.opened_at, now)
    nights = clock.nights_between(position.opened_at, now) if clock else None
    if clock is None:
        refusals.append(
            Refusal(
                RefusalCode.NO_SERVER_CLOCK,
                f"ticket {position.ticket}",
                "the server clock could not be located, so the number of "
                "nights held is unknown; the financing figures below do not "
                "depend on it",
            )
        )

    paid = carry_paid(position)

    per_point: float | None = None
    if terms is None:
        refusals.append(
            Refusal(
                RefusalCode.SYMBOL_TERMS_MISSING,
                f"ticket {position.ticket}",
                f"no symbol_info was supplied for {position.symbol!r}, so "
                f"points cannot be converted to money",
            )
        )
    else:
        per_point = value_per_point_per_lot(terms)
        if per_point is None:
            refusals.append(
                Refusal(
                    RefusalCode.NO_POINT_VALUE,
                    f"ticket {position.ticket}",
                    f"{position.symbol} reports point={terms.point}, "
                    f"trade_tick_size={terms.trade_tick_size}, "
                    f"trade_tick_value={terms.trade_tick_value}; no "
                    f"currency-per-point conversion exists",
                )
            )

    # ---- the forward rate ------------------------------------------------
    rate_declared: float | None = None
    if isinstance(declared, DeclaredSwap) and per_point is not None:
        points = (
            declared.charge_long_points
            if position.direction is PositionDirection.LONG
            else declared.charge_short_points
        )
        rate_declared = (
            points * per_point * position.volume * SWAP_UNITS_PER_CALENDAR_DAY
        )

    rate_measured: float | None = None
    if days >= minimum_days_for_measured_rate and paid != 0.0:
        rate_measured = paid / days
    elif days >= minimum_days_for_measured_rate:
        # Zero charged over a period long enough to have rolled. This is
        # ambiguous in a way that matters and is refused rather than read as
        # a measurement of zero: a swap-free account and a hold that has not
        # yet crossed a rollover -- a Friday-evening open read on a Sunday,
        # for instance -- are indistinguishable from this field alone.
        refusals.append(
            Refusal(
                RefusalCode.CARRY_TOO_YOUNG,
                f"ticket {position.ticket}",
                f"open {days:.2f} days with zero financing charged; a "
                f"swap-free account and a hold that has not yet crossed a "
                f"rollover cannot be told apart from this, so no rate is "
                f"measured from it",
            )
        )
    else:
        refusals.append(
            Refusal(
                RefusalCode.CARRY_TOO_YOUNG,
                f"ticket {position.ticket}",
                f"open {days:.2f} days, below the "
                f"{minimum_days_for_measured_rate:.2f}-day minimum for a "
                f"measured rate",
            )
        )

    # The per-night basis, for the registry comparison only. Gated on exactly
    # the same conditions as the per-day one so that the two appear and
    # disappear together and a reader is never shown one without the other.
    rate_measured_nightly: float | None = None
    if rate_measured is not None and nights is not None and nights > 0:
        rate_measured_nightly = paid / nights

    rate, source = _choose_rate(rate_declared, rate_measured, notes)
    if rate is None:
        refusals.append(
            Refusal(
                RefusalCode.NO_CARRY_RATE,
                f"ticket {position.ticket}",
                "neither a published nor a measured financing rate is "
                "available, so nothing is projected forward for this position",
            )
        )

    # ---- break-even on financing paid so far -----------------------------
    be_points = _breakeven(paid, position.volume, per_point)
    be_price: float | None = None
    be_pct: float | None = None
    if be_points is not None and terms is not None:
        move = be_points * terms.point
        sign = 1.0 if position.direction is PositionDirection.LONG else -1.0
        be_price = position.price_open + sign * move
        be_pct = 100.0 * move / position.price_open

    projections = tuple(
        _project(h, rate, paid, equity, position, terms, per_point) for h in horizons
    )

    if terms is not None:
        try:
            swap_mode: SwapMode | None = SwapMode(terms.swap_mode)
        except ValueError:
            swap_mode = None
        if swap_mode is not None and swap_mode.is_price_dependent:
            structural = (
                structural_status.as_sentence()
                if structural_status is not None
                else "UNDETERMINED - no carry log was supplied to this report"
            )
            notes.append(
                f"swap_mode is {swap_mode.name}, which declares the financing "
                f"rate to be itself a function of price -- if it holds, the "
                f"projections below hold price constant for the rate as well "
                f"as for equity, and a rising market raises the dollar carry "
                f"on a long above every figure shown. Whether it holds is "
                f"{structural}; the projection is the conservative reading "
                f"either way"
            )

    if (
        rate_measured is not None
        and rate_measured_nightly is not None
        and nights is not None
        and rate_measured_nightly != 0
        and abs(rate_measured / rate_measured_nightly - 1.0) > BASIS_AGREEMENT_FRACTION
    ):
        notes.append(
            f"the two measured bases disagree: {rate_measured:,.2f} a calendar "
            f"day over {days:.2f} days against {rate_measured_nightly:,.2f} a "
            f"night over {nights} midnights crossed, a factor of "
            f"{rate_measured / rate_measured_nightly:.3f}. That is the "
            f"schedule, not a rate change -- the hold is not a whole number of "
            f"weeks. The per-night figure is the one to compare against the "
            f"registered constant, which is quoted per night"
        )

    if paid > 0 and position.profit != 0:
        notes.append(
            f"financing paid is {abs(paid / position.profit):.1%} of the "
            f"position's floating result of {position.profit:,.2f}"
        )

    return PositionCarry(
        ticket=position.ticket,
        symbol=position.symbol,
        direction=position.direction,
        volume=position.volume,
        opened_at=position.opened_at,
        hours_open=hours,
        days_open=days,
        nights_held=nights,
        has_stop=position.has_stop,
        floating_pnl=position.profit,
        carry_paid=paid,
        carry_is_credit=paid < 0,
        carry_pct_of_equity=(100.0 * paid / equity if equity > 0 else None),
        carry_vs_floating_pnl=(
            paid / abs(position.profit) if position.profit != 0 else None
        ),
        breakeven_points=be_points,
        breakeven_price=be_price,
        breakeven_pct=be_pct,
        rate_declared_per_day=rate_declared,
        rate_measured_per_day=rate_measured,
        rate_measured_per_night=rate_measured_nightly,
        rate_per_day=rate,
        rate_source=source,
        projections=projections,
        refusals=tuple(refusals),
        notes=tuple(notes),
    )


def _choose_rate(
    declared: float | None, measured: float | None, notes: list[str]
) -> tuple[float | None, CarrySource]:
    """Pick the forward rate, preferring the more adverse when both exist.

    Args:
        declared: Rate from the broker's published figure.
        measured: Rate from what this position was charged.
        notes: Appended to when the two disagree.

    Returns:
        ``(rate, source)``.
    """
    if declared is None and measured is None:
        return None, CarrySource.NONE
    if measured is None:
        return declared, CarrySource.DECLARED
    if declared is None:
        return measured, CarrySource.MEASURED
    if measured > declared:
        notes.append(
            f"this position has been charged {measured:,.2f} a day against a "
            f"published rate of {declared:,.2f}; the projection uses the "
            f"measured figure because it is the more expensive of the two"
        )
        return measured, CarrySource.MORE_ADVERSE_OF_BOTH
    return declared, CarrySource.DECLARED


def _project(
    horizon_days: float,
    rate: float | None,
    paid: float,
    equity: float,
    position: PositionState,
    terms: SymbolTerms | None,
    per_point: float | None,
) -> CarryProjection:
    """Financing at one horizon.

    Args:
        horizon_days: Calendar days ahead.
        rate: Financing per calendar day, or ``None``.
        paid: Financing paid so far.
        equity: Account equity.
        position: The position.
        terms: Symbol terms, or ``None``.
        per_point: Currency per point per lot, or ``None``.

    Returns:
        The projection. Every derived field is ``None`` when the rate is.
    """
    if rate is None:
        return CarryProjection(horizon_days, 0.0, paid, None, None, None)
    additional = rate * horizon_days
    cumulative = paid + additional
    be_points = _breakeven(cumulative, position.volume, per_point)
    be_pct: float | None = None
    if be_points is not None and terms is not None:
        be_pct = 100.0 * (be_points * terms.point) / position.price_open
    return CarryProjection(
        horizon_days=horizon_days,
        additional=additional,
        cumulative=cumulative,
        cumulative_pct_of_equity=(100.0 * cumulative / equity if equity > 0 else None),
        breakeven_points=be_points,
        breakeven_pct=be_pct,
    )


@dataclass(frozen=True, slots=True)
class PortfolioCarry:
    """Financing across every open position.

    Attributes:
        paid_total: Financing charged so far across the book.
        rate_per_day: Financing per calendar day across the book, or ``None``
            when no position has a usable rate.
        rate_is_partial: True when at least one position contributed no rate,
            so the total understates the real cost.
        days_until_carry_consumes_equity: Equity divided by the daily rate.
            Arithmetic under a constant price and a constant book. It is the
            two-month hold stated as a number before it happens.
        date_carry_consumes_equity: That many days after the reading.
        per_lot_per_day_points: Charge in points per lot per calendar day,
            keyed by symbol and then by side, for
            :func:`risk.swap.swap_divergence`. Keyed by symbol because swap
            terms are a property of the instrument, and pooling two symbols'
            financing into one comparison against a gold constant would be
            comparing the constant against something it was never about.
        per_lot_per_night_points: The same charge on the **per-midnight**
            basis. Same keys, same units, different denominator; see the module
            docstring for which is exact when. Empty for any position whose
            server clock could not be located.
    """

    paid_total: float
    rate_per_day: float | None
    rate_is_partial: bool
    days_until_carry_consumes_equity: float | None
    date_carry_consumes_equity: datetime | None
    per_lot_per_day_points: dict[str, dict[str, float]]
    per_lot_per_night_points: dict[str, dict[str, float]]


def portfolio_carry(
    carries: tuple[PositionCarry, ...],
    positions: tuple[PositionState, ...],
    terms_by_symbol: dict[str, SymbolTerms],
    equity: float,
    now: datetime,
) -> PortfolioCarry:
    """Aggregate financing across the book.

    The per-side points figure is a volume-weighted mean over the positions
    that have a measured rate, because that is the quantity
    :func:`risk.swap.swap_divergence` compares against the registered
    substitute. Positions without one are excluded rather than counted as
    zero, which would drag the mean toward agreement.

    Args:
        carries: Per-position financing reports.
        positions: The positions those reports describe.
        terms_by_symbol: Symbol terms, keyed by symbol.
        equity: Account equity.
        now: Reading time, timezone-aware UTC.

    Returns:
        The book-level financing figures.
    """
    paid_total = sum(c.carry_paid for c in carries)
    rated = [c for c in carries if c.rate_per_day is not None]
    rate = sum(c.rate_per_day or 0.0 for c in rated) if rated else None
    partial = len(rated) != len(carries)

    days_to_zero: float | None = None
    date_to_zero: datetime | None = None
    if rate is not None and rate > 0 and equity > 0:
        days_to_zero = equity / rate
        date_to_zero = now + timedelta(days=days_to_zero)

    daily_samples: dict[tuple[str, str], list[tuple[float, float]]] = {}
    nightly_samples: dict[tuple[str, str], list[tuple[float, float]]] = {}
    by_ticket = {p.ticket: p for p in positions}
    for c in carries:
        if c.rate_measured_per_day is None:
            continue
        terms = terms_by_symbol.get(c.symbol)
        position = by_ticket.get(c.ticket)
        if terms is None or position is None:
            continue
        per_point = value_per_point_per_lot(terms)
        if per_point is None or per_point <= 0:
            continue
        key = (c.symbol, c.direction.value)
        daily_samples.setdefault(key, []).append(
            (c.volume, c.rate_measured_per_day / (per_point * c.volume))
        )
        if c.rate_measured_per_night is not None:
            nightly_samples.setdefault(key, []).append(
                (c.volume, c.rate_measured_per_night / (per_point * c.volume))
            )

    return PortfolioCarry(
        paid_total=paid_total,
        rate_per_day=rate,
        rate_is_partial=partial,
        days_until_carry_consumes_equity=days_to_zero,
        date_carry_consumes_equity=date_to_zero,
        per_lot_per_day_points=_volume_weighted(daily_samples),
        per_lot_per_night_points=_volume_weighted(nightly_samples),
    )


def _volume_weighted(
    samples_by_key: dict[tuple[str, str], list[tuple[float, float]]],
) -> dict[str, dict[str, float]]:
    """Collapse ``(volume, points)`` samples into a volume-weighted mean.

    Args:
        samples_by_key: Samples keyed by ``(symbol, side)``.

    Returns:
        ``{symbol: {side: points}}``, omitting any key whose weight is zero.
    """
    out: dict[str, dict[str, float]] = {}
    for (symbol, side), samples in samples_by_key.items():
        weight = sum(v for v, _ in samples)
        if weight > 0:
            out.setdefault(symbol, {})[side] = sum(v * p for v, p in samples) / weight
    return out
