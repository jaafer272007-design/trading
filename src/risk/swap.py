"""Swap terms, normalised — and the measured-versus-registered divergence.

Two jobs, and the second is the reason this module is prominent rather than a
helper.

**Normalise.** ``symbol_info().swap_long`` and ``swap_short`` are quoted in
units chosen by ``swap_mode``, with the broker's sign convention. Everything
downstream wants a **charge in points per lot per night**, positive when money
leaves the account. :func:`declared_swap` produces that, or refuses.

**Compare.** ``backtest.costs`` charges 20 points long and 8 points short, and
those numbers were never this broker's rate. They are H-005's *pessimistic
substitute*, chosen when the feed could not be calibrated, and their whole
justification is that they overstate what a real account pays. That
justification is an empirical claim, and :class:`SwapDivergence` is a first-class
field of the risk report rather than a diagnostic, because if it fails then every
cost-dependent result in ``HYPOTHESES.md`` was computed against costs that were
too low — a finding about the registry, not about the account.

What was measured, 2026-07-29, FxPro `GOLD`
------------------------------------------

`[MEASURED]` ``swap_mode = 2`` (``CURRENCY_SYMBOL``), ``swap_long = -67.9``,
``swap_short = +27.0``. Three things follow, and they are different in kind from
each other:

**1. The refusal is the finding.** In ``CURRENCY_SYMBOL`` the rate is
denominated in the symbol's **base** currency — ounces of gold. The
account-currency cost is therefore **proportional to the gold price at the
moment of charging**, so a long held through a rising market pays a rising
dollar carry. The registered substitute is a fixed points rate. That is a
difference in *structure*, not in magnitude, and no constant can absorb it.
:func:`declared_swap` refuses the conversion rather than picking a price, and
that refusal is what surfaced the structure.

**2. The sign is asymmetric.** Long pays, short is **credited**. The registered
model charges *both* directions — ``swap_points`` says so in its own docstring,
on the ground that a credit is an optimistic assumption about an unobserved
rate. It is now observed, and it is a credit. Charging the short side is a
structural error in the cost model, independent of any magnitude.

**3. The magnitude is roughly 3.4x, on the reading below.** If the figures are
read as an effective charge in the deposit currency per lot per night — which
the *magnitude* strongly supports and the field alone cannot confirm — then

===================  ==================  ==============  ================
side                 registered          FxPro `GOLD`    annualised
===================  ==================  ==============  ================
long                 20.0 / night        67.9 / night    3.0% -> 10.3%
short                8.0 charged         27.0 credited   1.2% -> -4.1%
===================  ==================  ==============  ================

at 100 ounces a lot and gold near 2,400. **Both annualised figures are
plausible financing rates and the registered one is not** — 3% on a gold CFD
long is below any dollar funding rate that has existed in the evaluation
window. That is evidence for the reading, and evidence is not a measurement.
**One week of a real position settles it**; until then the declared route stays
refused and the measured route is what fills the comparison in.

A correction to what this module previously claimed
--------------------------------------------------

An earlier version asserted that ``backtest.costs.rollovers_crossed`` "counts
five rollovers a week and has no triple-swap concept", so that the registered
model understated a week's carry by two sevenths *on top of* the magnitude
error, and that a broker charging 15 a night would therefore already exceed the
registry. **All of that was wrong.** It was asserted from the function's name
without reading its body.

`[MEASURED]` ``rollovers_crossed`` counts **every** calendar day's 17:00 New
York boundary, weekends included — 7 over a Monday-to-Monday span, 14 over two
weeks, pinned in ``tests/risk/test_swap.py`` against the real function. The
registered night **count** per calendar week is right. What differs is *when*
the nights land: the registered model charges on Saturday and Sunday when
nothing is charged, and charges once on the triple-swap weekday when three are.
Those miss in opposite directions and cancel over whole weeks.

So the weekly basis below is a restatement of the per-night basis in units that
suit a multi-day hold. It is not an independent finding, and it must not be
presented as one.

Three bases, and which one to trust for this broker
--------------------------------------------------

**Per night.** The registered constant against the broker's rate. Exact when
the mode permits a conversion.

**Per calendar week.** The same ratio in the units a multi-day hold is felt in.
Both sides use seven nights, per the correction above.

**Annualised percent of notional.** ``charge x 365 / (contract size x price)``.
This is the only basis that is **invariant to the gold price**, so it is the one
that means anything for a base-currency-denominated swap — and it is what makes
a 20-point substitute and a 67.9-point charge comparable as *rates* rather than
as numbers.

Importing the constants rather than restating them
--------------------------------------------------

``tests/backtest/test_costs.py`` restates the H-005 spread floor as a literal,
so that lowering the constant cannot also lower the assertion. The opposite is
right here. This is not a guard on the constant; it is a comparison against
whatever the registry currently declares. If someone changes the registered
swap, this report must immediately compare against the new value — a stale
literal would keep reporting agreement with a number nothing uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Final

from backtest.costs import (
    SWAP_LONG_POINTS_PER_LOT_PER_NIGHT,
    SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT,
)
from risk.clock import DAYS_PER_WEEK, REGISTERED_NIGHTS_PER_WEEK, SWAP_UNITS_PER_WEEK
from risk.refusal import Refusal, RefusalCode
from risk.state import SymbolTerms, value_per_point_per_lot

#: The registered pessimistic substitute, read live from ``backtest.costs``.
REGISTERED_LONG_POINTS: Final = SWAP_LONG_POINTS_PER_LOT_PER_NIGHT
REGISTERED_SHORT_POINTS: Final = SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT

#: What a week of financing costs under the registered model. Seven nights, per
#: the correction in this module's docstring -- ``rollovers_crossed`` counts one
#: boundary per calendar day, weekends included.
REGISTERED_WEEKLY_LONG_POINTS: Final = (
    REGISTERED_LONG_POINTS * REGISTERED_NIGHTS_PER_WEEK
)
REGISTERED_WEEKLY_SHORT_POINTS: Final = (
    REGISTERED_SHORT_POINTS * REGISTERED_NIGHTS_PER_WEEK
)

#: Nights in a year, for the annualised basis. Calendar days rather than
#: trading days, because financing accrues over the weekend whether or not it
#: is charged on it.
NIGHTS_PER_YEAR: Final = 365.0


class SwapMode(IntEnum):
    """MT5's ``ENUM_SYMBOL_SWAP_MODE``.

    Named rather than compared as integers, because the value that means "no
    swap at all" is ``0`` and that is exactly what an unpopulated field reads
    as. :func:`declared_swap` therefore treats ``DISABLED`` as a claim to be
    checked against what the broker actually charged, not as a fact.
    """

    DISABLED = 0
    POINTS = 1
    CURRENCY_SYMBOL = 2
    CURRENCY_MARGIN = 3
    CURRENCY_DEPOSIT = 4
    INTEREST_CURRENT = 5
    INTEREST_OPEN = 6
    REOPEN_CURRENT = 7
    REOPEN_BID = 8

    @property
    def is_price_dependent(self) -> bool:
        """Whether the account-currency charge is a function of a price.

        This is the property that matters most about FxPro's gold, and it is
        the one a fixed points substitute cannot represent at all. Under
        ``CURRENCY_SYMBOL`` the rate is in ounces, so the dollar cost rises
        with the gold price; under the interest and reopen modes it is derived
        from a price directly.

        ``INTEREST_OPEN`` is included even though it uses the *entry* price and
        is therefore constant for the life of one position: it still varies
        between positions opened at different prices, so no single constant
        describes it either.

        Returns:
            True for the modes whose charge moves with a price.
        """
        return self in {
            SwapMode.CURRENCY_SYMBOL,
            SwapMode.INTEREST_CURRENT,
            SwapMode.INTEREST_OPEN,
            SwapMode.REOPEN_CURRENT,
            SwapMode.REOPEN_BID,
        }


#: Why each unsupported mode is refused rather than approximated. Written out so
#: that the refusal message names the missing input, which is the thing a person
#: needs in order to decide whether to go and find it.
_UNSUPPORTED_REASON: Final[dict[SwapMode, str]] = {
    SwapMode.CURRENCY_SYMBOL: (
        "the rate is quoted in the symbol's BASE currency -- ounces of gold "
        "here -- so the account-currency charge is proportional to the gold "
        "price at the moment of charging. A long held into a rising market "
        "pays a rising dollar carry. No fixed points rate can represent that, "
        "and picking a price to convert at would bury a structural difference "
        "inside a constant. Measure it from position.swap instead"
    ),
    SwapMode.INTEREST_CURRENT: (
        "the rate is an annual interest percentage on the current price, and "
        "turning it into a nightly charge needs the broker's day-count "
        "convention, which MT5 does not publish"
    ),
    SwapMode.INTEREST_OPEN: (
        "the rate is an annual interest percentage on the entry price, and "
        "turning it into a nightly charge needs the broker's day-count "
        "convention, which MT5 does not publish"
    ),
    SwapMode.REOPEN_CURRENT: (
        "financing is applied by closing and reopening the position at a new "
        "price, so it is not a nightly charge at all and has no points-per-lot "
        "equivalent"
    ),
    SwapMode.REOPEN_BID: (
        "financing is applied by closing and reopening the position at a new "
        "price, so it is not a nightly charge at all and has no points-per-lot "
        "equivalent"
    ),
}


@dataclass(frozen=True, slots=True)
class DeclaredSwap:
    """The broker's published financing rate, normalised.

    Attributes:
        mode: The mode the figures were read under.
        charge_long_points: Points per lot per night the account pays to hold
            a long. **Negative means the broker pays the account.**
        charge_short_points: The same for a short.
    """

    mode: SwapMode
    charge_long_points: float
    charge_short_points: float

    @property
    def long_is_credited(self) -> bool:
        """Whether holding a long earns rather than costs.

        Returns:
            True when the charge is negative.
        """
        return self.charge_long_points < 0

    @property
    def short_is_credited(self) -> bool:
        """Whether holding a short earns rather than costs.

        `[MEASURED]` FxPro credits the short side of gold. The registered model
        charges 8 points there regardless, so the credit is a real asymmetry the
        model cannot represent, and it is reported rather than netted away.

        Returns:
            True when the charge is negative.
        """
        return self.charge_short_points < 0


def declared_swap(terms: SymbolTerms, account_currency: str) -> DeclaredSwap | Refusal:
    """Normalise a symbol's published swap to points per lot per night.

    Args:
        terms: Symbol terms as read from the terminal.
        account_currency: The account's deposit currency.

    Returns:
        A :class:`DeclaredSwap`, or a :class:`Refusal` naming what the
        conversion would have had to assume.
    """
    try:
        mode = SwapMode(terms.swap_mode)
    except ValueError:
        return Refusal(
            RefusalCode.SWAP_MODE_UNSUPPORTED,
            terms.name,
            f"swap_mode={terms.swap_mode} is not a documented "
            f"ENUM_SYMBOL_SWAP_MODE value; the units of swap_long="
            f"{terms.swap_long} and swap_short={terms.swap_short} are "
            f"therefore unknown and cannot be converted",
        )

    if mode in _UNSUPPORTED_REASON:
        return Refusal(
            RefusalCode.SWAP_MODE_UNSUPPORTED,
            terms.name,
            f"swap_mode is {mode.name} (swap_long={terms.swap_long}, "
            f"swap_short={terms.swap_short}): {_UNSUPPORTED_REASON[mode]}",
        )

    if mode is SwapMode.DISABLED:
        return DeclaredSwap(mode, 0.0, 0.0)

    # MT5's sign convention on the published rate is the same as on a position:
    # negative is what the account pays. Everything below this line is in
    # charge terms, positive meaning money leaves.
    if mode is SwapMode.POINTS:
        return DeclaredSwap(mode, -terms.swap_long, -terms.swap_short)

    if mode is SwapMode.CURRENCY_MARGIN and terms.currency_margin != account_currency:
        return Refusal(
            RefusalCode.SWAP_CURRENCY_MISMATCH,
            terms.name,
            f"swap is quoted in the margin currency {terms.currency_margin!r} "
            f"but the account is denominated in {account_currency!r}; "
            f"converting needs a rate this layer does not read",
        )

    # CURRENCY_DEPOSIT, and CURRENCY_MARGIN once it has been shown to be the
    # same currency: the figure is money per lot per night, so it converts
    # through the point value.
    per_point = value_per_point_per_lot(terms)
    if per_point is None:
        return Refusal(
            RefusalCode.NO_POINT_VALUE,
            terms.name,
            f"swap_mode is {mode.name} so the rate is in currency, but "
            f"point={terms.point}, trade_tick_size={terms.trade_tick_size} "
            f"and trade_tick_value={terms.trade_tick_value} do not yield a "
            f"currency-per-point conversion",
        )
    return DeclaredSwap(
        mode,
        -terms.swap_long / per_point,
        -terms.swap_short / per_point,
    )


class SwapVerdict(StrEnum):
    """What the comparison against the registered substitute concluded."""

    #: The broker charges no more than the registered figure on either side.
    #: The substitute was pessimistic, as H-005 assumed, and no cost-dependent
    #: result in the registry is affected.
    REGISTERED_IS_CONSERVATIVE = "REGISTERED_IS_CONSERVATIVE"
    #: The broker charges **more** than the registered figure on at least one
    #: side. The substitute was not pessimistic, and every cost-dependent
    #: result in the registry was computed against financing that was too low.
    REGISTERED_IS_OPTIMISTIC = "REGISTERED_IS_OPTIMISTIC"
    #: Neither a published nor a measured rate could be obtained.
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class WeeklyComparison:
    """One side of the book, compared on the weekly and annualised bases.

    Attributes:
        side: ``"long"`` or ``"short"``.
        source: ``"declared"`` when read from the broker's published rate,
            ``"measured"`` when derived from what open positions were actually
            charged.
        registered_points: Registered weekly financing, points per lot.
        broker_points: The broker's weekly financing, points per lot.
        ratio: ``broker / registered``. ``None`` when the registered figure is
            zero, which it is not today but could become.
        exceeds: Whether the broker charges more than the registry assumes.
        registered_annual_pct: Registered charge annualised as a percentage of
            one lot's notional. ``None`` when no price was supplied.
        broker_annual_pct: The same for the broker. **This is the basis to
            trust for a price-dependent swap mode**, because it is the only one
            that does not move when the gold price does.
    """

    side: str
    source: str
    registered_points: float
    broker_points: float
    ratio: float | None
    exceeds: bool
    registered_annual_pct: float | None
    broker_annual_pct: float | None


@dataclass(frozen=True, slots=True)
class SwapDivergence:
    """Measured-versus-registered financing, as a reportable finding.

    Attributes:
        symbol: The instrument these figures belong to. Swap terms are a
            property of the instrument, so a divergence is always about one.
        verdict: The conclusion.
        mode: The swap mode the published figures were read under, if any.
        mode_is_price_dependent: Whether the charge moves with a price. When
            true, no fixed points constant can represent the broker's terms and
            the registered substitute is wrong in kind rather than in degree.
        declared_long_points: Published nightly charge, points per lot.
        declared_short_points: Published nightly charge, points per lot.
        measured_daily_points: Nightly-equivalent charge per lot derived from
            open positions, per calendar day. ``None`` when no position has
            been open long enough.
        comparisons: Every comparison that could be made.
        short_is_credited: Whether the broker pays the account to hold a
            short, which the registered model cannot represent.
        notes: Sentences a person should read, in the order they matter.
    """

    symbol: str
    verdict: SwapVerdict
    mode: SwapMode | None
    mode_is_price_dependent: bool
    declared_long_points: float | None
    declared_short_points: float | None
    measured_daily_points: dict[str, float]
    comparisons: tuple[WeeklyComparison, ...]
    short_is_credited: bool | None
    notes: tuple[str, ...]

    @property
    def bears_on_the_registry(self) -> bool:
        """Whether any cost-dependent registry result is called into question.

        True when the broker's financing exceeds the registered substitute, and
        **also** when the mode is price-dependent: a substitute that is wrong in
        structure bears on the registry whether or not its magnitude happens to
        come out high, because no value of the constant would have been right.

        Returns:
            True when a cost-dependent result should be re-read.
        """
        return (
            self.verdict is SwapVerdict.REGISTERED_IS_OPTIMISTIC
            or self.mode_is_price_dependent
        )


def _annual_pct(
    points_per_night: float,
    currency_per_point: float | None,
    notional_per_lot: float | None,
) -> float | None:
    """Annualise a nightly points charge as a percentage of notional.

    Args:
        points_per_night: Charge in points per lot per night.
        currency_per_point: Account currency per point per lot.
        notional_per_lot: Contract size times price, in account currency.

    Returns:
        Percent per year, or ``None`` when either input is missing.
    """
    if currency_per_point is None or notional_per_lot is None:
        return None
    if notional_per_lot <= 0:
        return None
    return (
        100.0
        * points_per_night
        * currency_per_point
        * NIGHTS_PER_YEAR
        / (notional_per_lot)
    )


def _compare(
    side: str,
    source: str,
    registered_weekly: float,
    broker_weekly: float,
    registered_nightly: float,
    broker_nightly: float,
    tolerance: float,
    currency_per_point: float | None,
    notional_per_lot: float | None,
) -> WeeklyComparison:
    """Build one comparison.

    Args:
        side: ``"long"`` or ``"short"``.
        source: ``"declared"`` or ``"measured"``.
        registered_weekly: Registered weekly points per lot.
        broker_weekly: The broker's weekly points per lot.
        registered_nightly: Registered nightly points per lot, for annualising.
        broker_nightly: The broker's nightly points per lot, for annualising.
        tolerance: Fractional allowance before an exceedance is called. Zero
            for the declared route, which is exact; non-zero for the measured
            route, which absorbs triple-swap timing, partial days and any rate
            change during the hold.
        currency_per_point: Account currency per point per lot.
        notional_per_lot: Contract size times price.

    Returns:
        The comparison.
    """
    ratio = broker_weekly / registered_weekly if registered_weekly != 0 else None
    return WeeklyComparison(
        side=side,
        source=source,
        registered_points=registered_weekly,
        broker_points=broker_weekly,
        ratio=ratio,
        exceeds=broker_weekly > registered_weekly * (1.0 + tolerance),
        registered_annual_pct=_annual_pct(
            registered_nightly, currency_per_point, notional_per_lot
        ),
        broker_annual_pct=_annual_pct(
            broker_nightly, currency_per_point, notional_per_lot
        ),
    )


def swap_divergence(
    symbol: str,
    declared: DeclaredSwap | Refusal,
    measured_daily_points: dict[str, float],
    measured_tolerance: float,
    mode: SwapMode | None = None,
    currency_per_point: float | None = None,
    notional_per_lot: float | None = None,
) -> SwapDivergence:
    """Compare the broker's financing against the registered substitute.

    Args:
        symbol: The instrument being compared.
        declared: Result of :func:`declared_swap`.
        measured_daily_points: Charge in points per lot per **calendar day**,
            keyed by ``"long"``/``"short"``, derived from open positions. The
            calendar-day basis is used rather than a per-charging-event one
            because it needs no schedule -- it absorbs the triple-swap weekday,
            the weekend and any holiday without modelling them.
        measured_tolerance: Fractional allowance on the measured route.
        mode: The swap mode, supplied when ``declared`` is a refusal so that a
            price-dependent structure is still reported. Ignored when
            ``declared`` carries its own mode.
        currency_per_point: Account currency per point per lot, for the
            annualised basis.
        notional_per_lot: Contract size times current price, for the annualised
            basis.

    Returns:
        The finding. ``verdict`` is ``UNAVAILABLE`` only when neither route
        produced anything.
    """
    notes: list[str] = []
    comparisons: list[WeeklyComparison] = []
    declared_long: float | None = None
    declared_short: float | None = None
    short_credited: bool | None = None
    effective_mode = mode

    if isinstance(declared, Refusal):
        notes.append(f"published rate unavailable - {declared.reason}")
    else:
        effective_mode = declared.mode
        declared_long = declared.charge_long_points
        declared_short = declared.charge_short_points
        short_credited = declared.short_is_credited
        # Exact comparison on the declared route: the broker's published figure
        # carries no measurement noise, so any exceedance at all is a real one
        # and a tolerance would only hide it.
        comparisons.append(
            _compare(
                "long",
                "declared",
                REGISTERED_WEEKLY_LONG_POINTS,
                declared_long * SWAP_UNITS_PER_WEEK,
                REGISTERED_LONG_POINTS,
                declared_long,
                0.0,
                currency_per_point,
                notional_per_lot,
            )
        )
        comparisons.append(
            _compare(
                "short",
                "declared",
                REGISTERED_WEEKLY_SHORT_POINTS,
                declared_short * SWAP_UNITS_PER_WEEK,
                REGISTERED_SHORT_POINTS,
                declared_short,
                0.0,
                currency_per_point,
                notional_per_lot,
            )
        )
        if declared.short_is_credited:
            notes.append(
                f"the broker CREDITS the short side at "
                f"{-declared_short:.2f} points per lot per night; the "
                f"registered model charges "
                f"{REGISTERED_SHORT_POINTS:.2f} in both directions and has no "
                f"way to represent a credit. That is a structural error in the "
                f"cost model, separate from any magnitude"
            )

    price_dependent = effective_mode is not None and effective_mode.is_price_dependent
    if price_dependent and effective_mode is not None:
        notes.insert(
            0,
            f"swap_mode is {effective_mode.name}, so the account-currency "
            f"charge is a FUNCTION OF PRICE, not a constant. The registered "
            f"substitute is a fixed points rate and is therefore wrong in kind "
            f"rather than in magnitude: no value of it would have been right. "
            f"Every cost-dependent result in HYPOTHESES.md priced financing "
            f"with a structure this broker does not use",
        )

    for side, per_day in sorted(measured_daily_points.items()):
        registered_weekly = (
            REGISTERED_WEEKLY_LONG_POINTS
            if side == "long"
            else REGISTERED_WEEKLY_SHORT_POINTS
        )
        registered_nightly = (
            REGISTERED_LONG_POINTS if side == "long" else REGISTERED_SHORT_POINTS
        )
        # DAYS_PER_WEEK, not SWAP_UNITS_PER_WEEK. The two are the same number
        # and they mean different things: the measured figure is already a
        # per-calendar-day rate, so it scales by calendar days.
        comparisons.append(
            _compare(
                side,
                "measured",
                registered_weekly,
                per_day * DAYS_PER_WEEK,
                registered_nightly,
                per_day,
                measured_tolerance,
                currency_per_point,
                notional_per_lot,
            )
        )

    if not comparisons:
        return SwapDivergence(
            symbol=symbol,
            verdict=SwapVerdict.UNAVAILABLE,
            mode=effective_mode,
            mode_is_price_dependent=price_dependent,
            declared_long_points=None,
            declared_short_points=None,
            measured_daily_points={},
            comparisons=(),
            short_is_credited=None,
            notes=(
                *notes,
                "no open position has been held long enough to measure a rate",
            ),
        )

    exceeding = [c for c in comparisons if c.exceeds]
    if exceeding:
        verdict = SwapVerdict.REGISTERED_IS_OPTIMISTIC
        for c in exceeding:
            ratio_text = f"{c.ratio:.2f}x" if c.ratio is not None else "n/a"
            annual = ""
            if c.registered_annual_pct is not None and c.broker_annual_pct is not None:
                annual = (
                    f", which annualises to {c.broker_annual_pct:.2f}% of "
                    f"notional against the registered "
                    f"{c.registered_annual_pct:.2f}%"
                )
            notes.insert(
                0,
                f"{c.source} {c.side} financing is {c.broker_points:.1f} points "
                f"per lot per week against the registered "
                f"{c.registered_points:.1f} ({ratio_text}){annual}; the "
                f"registered figure is NOT pessimistic on this side and every "
                f"cost-dependent result in HYPOTHESES.md was computed against "
                f"financing that is too low",
            )
    else:
        verdict = SwapVerdict.REGISTERED_IS_CONSERVATIVE
        notes.append(
            "the registered substitute charges at least as much as this broker "
            "on every side that could be compared, which is the direction "
            "H-005 assumed"
        )

    notes.append(
        f"both bases use {REGISTERED_NIGHTS_PER_WEEK:.0f} nights a week: "
        f"rollovers_crossed counts one boundary per calendar day including "
        f"Saturday and Sunday, so the registered night COUNT is right. What "
        f"differs is when they land -- nothing is charged at the weekend and "
        f"three nights are charged on one weekday -- and that cancels over "
        f"whole weeks"
    )

    return SwapDivergence(
        symbol=symbol,
        verdict=verdict,
        mode=effective_mode,
        mode_is_price_dependent=price_dependent,
        declared_long_points=declared_long,
        declared_short_points=declared_short,
        measured_daily_points=dict(measured_daily_points),
        comparisons=tuple(comparisons),
        short_is_credited=short_credited,
        notes=tuple(notes),
    )
