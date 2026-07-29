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
justification is an empirical claim, and until a live terminal is read it is
an untested one.

So this module measures it. If the broker's real financing cost exceeds the
registered figure, the substitute was not pessimistic, and every cost-dependent
result in ``HYPOTHESES.md`` was computed against costs that were too low. That
is not a diagnostic — it is a finding about the registry, and
:class:`SwapDivergence` is a first-class field of the risk report so that it
surfaces where someone will see it rather than in a log.

Two bases, because they can disagree
------------------------------------

The comparison is reported on two bases and both are needed:

**Per night.** The registered constant against the broker's published rate.
Direct, exact, and the number a reader expects.

**Per calendar week.** ``backtest.costs.rollovers_crossed`` counts rollovers,
and a trading week has five. A broker charges *seven* nights across those five
rollovers, because one weekday carries a triple charge covering the weekend.
So the registered model's weekly financing is ``5 x rate`` where the account's
is ``7 x rate`` — the registered model has no triple-swap concept at all, and
at identical per-night rates it would still understate a week's carry by two
sevenths.

The weekly basis is the one that bears on a multi-day hold, which is what the
registry's cost-dependent results are made of, and it is the basis the verdict
is taken on.

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
from risk.clock import DAYS_PER_WEEK, ROLLOVERS_PER_WEEK, SWAP_UNITS_PER_WEEK
from risk.refusal import Refusal, RefusalCode
from risk.state import SymbolTerms, value_per_point_per_lot

#: The registered pessimistic substitute, read live from ``backtest.costs``.
REGISTERED_LONG_POINTS: Final = SWAP_LONG_POINTS_PER_LOT_PER_NIGHT
REGISTERED_SHORT_POINTS: Final = SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT

#: What a week of financing costs under the registered model: five rollovers,
#: no triple-swap concept.
REGISTERED_WEEKLY_LONG_POINTS: Final = REGISTERED_LONG_POINTS * ROLLOVERS_PER_WEEK
REGISTERED_WEEKLY_SHORT_POINTS: Final = REGISTERED_SHORT_POINTS * ROLLOVERS_PER_WEEK


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


#: Why each unsupported mode is refused rather than approximated. Written out
#: so that the refusal message names the missing input, which is the thing a
#: person needs in order to decide whether to go and find it.
_UNSUPPORTED_REASON: Final[dict[SwapMode, str]] = {
    SwapMode.CURRENCY_SYMBOL: (
        "the rate is quoted in the symbol's base currency (ounces of gold "
        "here), and converting it to money needs a price, which makes the "
        "figure a function of when it is read"
    ),
    SwapMode.INTEREST_CURRENT: (
        "the rate is an annual interest percentage, and turning it into a "
        "nightly charge needs the broker's day-count convention, which MT5 "
        "does not publish"
    ),
    SwapMode.INTEREST_OPEN: (
        "the rate is an annual interest percentage, and turning it into a "
        "nightly charge needs the broker's day-count convention, which MT5 "
        "does not publish"
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

        Gold financed against a dollar rate frequently credits the short side.
        The registered model charges 8 points there regardless, so a credit is
        a real asymmetry the model deliberately ignores, and it is reported
        rather than netted away.

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
            f"swap_mode is {mode.name}: {_UNSUPPORTED_REASON[mode]}",
        )

    if mode is SwapMode.DISABLED:
        return DeclaredSwap(mode, 0.0, 0.0)

    # MT5's sign convention on the published rate is the same as on a
    # position: negative is what the account pays. Everything below this line
    # is in charge terms, positive meaning money leaves.
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
    """One side of the book, compared on the weekly basis.

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
    """

    side: str
    source: str
    registered_points: float
    broker_points: float
    ratio: float | None
    exceeds: bool


@dataclass(frozen=True, slots=True)
class SwapDivergence:
    """Measured-versus-registered financing, as a reportable finding.

    Attributes:
        symbol: The instrument these figures belong to. Swap terms are a
            property of the instrument, so a divergence is always about one.
        verdict: The conclusion.
        mode: The swap mode the published figures were read under, if any.
        declared_long_points: Published nightly charge, points per lot.
        declared_short_points: Published nightly charge, points per lot.
        measured_daily_points: Nightly-equivalent charge per lot derived from
            open positions, per calendar day. ``None`` when no position has
            been open long enough.
        comparisons: Every weekly comparison that could be made.
        short_is_credited: Whether the broker pays the account to hold a
            short, which the registered model does not represent.
        notes: Sentences a person should read, in the order they matter.
    """

    symbol: str
    verdict: SwapVerdict
    mode: SwapMode | None
    declared_long_points: float | None
    declared_short_points: float | None
    measured_daily_points: dict[str, float]
    comparisons: tuple[WeeklyComparison, ...]
    short_is_credited: bool | None
    notes: tuple[str, ...]

    @property
    def bears_on_the_registry(self) -> bool:
        """Whether any cost-dependent registry result is called into question.

        Returns:
            True only when the broker's financing exceeds the registered
            substitute. An unavailable comparison is not evidence either way
            and does not set this.
        """
        return self.verdict is SwapVerdict.REGISTERED_IS_OPTIMISTIC


def _compare(
    side: str, source: str, registered: float, broker: float, tolerance: float
) -> WeeklyComparison:
    """Build one weekly comparison.

    Args:
        side: ``"long"`` or ``"short"``.
        source: ``"declared"`` or ``"measured"``.
        registered: Registered weekly points per lot.
        broker: The broker's weekly points per lot.
        tolerance: Fractional allowance before an exceedance is called. Zero
            for the declared route, which is exact; non-zero for the measured
            route, which absorbs triple-swap timing, partial days and any rate
            change during the hold.

    Returns:
        The comparison.
    """
    ratio = broker / registered if registered != 0 else None
    return WeeklyComparison(
        side=side,
        source=source,
        registered_points=registered,
        broker_points=broker,
        ratio=ratio,
        exceeds=broker > registered * (1.0 + tolerance),
    )


def swap_divergence(
    symbol: str,
    declared: DeclaredSwap | Refusal,
    measured_daily_points: dict[str, float],
    measured_tolerance: float,
) -> SwapDivergence:
    """Compare the broker's financing against the registered substitute.

    Args:
        symbol: The instrument being compared.
        declared: Result of :func:`declared_swap`.
        measured_daily_points: Charge in points per lot per **calendar day**,
            keyed by ``"long"``/``"short"``, derived from open positions. The
            calendar-day basis is used rather than a per-rollover one because
            it absorbs the triple-swap convention instead of having to model
            it.
        measured_tolerance: Fractional allowance on the measured route.

    Returns:
        The finding. ``verdict`` is ``UNAVAILABLE`` only when neither route
        produced anything.
    """
    notes: list[str] = []
    comparisons: list[WeeklyComparison] = []
    mode: SwapMode | None = None
    declared_long: float | None = None
    declared_short: float | None = None
    short_credited: bool | None = None

    if isinstance(declared, Refusal):
        notes.append(f"published rate unavailable - {declared.reason}")
    else:
        mode = declared.mode
        declared_long = declared.charge_long_points
        declared_short = declared.charge_short_points
        short_credited = declared.short_is_credited
        # Exact comparison on the declared route: the broker's published
        # figure carries no measurement noise, so any exceedance at all is a
        # real one and a tolerance would only hide it.
        comparisons.append(
            _compare(
                "long",
                "declared",
                REGISTERED_WEEKLY_LONG_POINTS,
                declared_long * SWAP_UNITS_PER_WEEK,
                0.0,
            )
        )
        comparisons.append(
            _compare(
                "short",
                "declared",
                REGISTERED_WEEKLY_SHORT_POINTS,
                declared_short * SWAP_UNITS_PER_WEEK,
                0.0,
            )
        )
        if declared.short_is_credited:
            notes.append(
                f"the broker CREDITS the short side at "
                f"{-declared_short:.2f} points per lot per night; the "
                f"registered model charges "
                f"{REGISTERED_SHORT_POINTS:.2f} in both directions and has no "
                f"way to represent a credit"
            )

    for side, per_day in sorted(measured_daily_points.items()):
        registered_weekly = (
            REGISTERED_WEEKLY_LONG_POINTS
            if side == "long"
            else REGISTERED_WEEKLY_SHORT_POINTS
        )
        # DAYS_PER_WEEK, not SWAP_UNITS_PER_WEEK. The two are the same number
        # and they mean different things: the measured figure is already a
        # per-calendar-day rate, so it scales by calendar days, and the fact
        # that a week also carries seven swap units is what makes the two
        # routes comparable rather than what makes this line correct.
        comparisons.append(
            _compare(
                side,
                "measured",
                registered_weekly,
                per_day * DAYS_PER_WEEK,
                measured_tolerance,
            )
        )

    if not comparisons:
        return SwapDivergence(
            symbol=symbol,
            verdict=SwapVerdict.UNAVAILABLE,
            mode=mode,
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
            notes.insert(
                0,
                f"{c.source} {c.side} financing is {c.broker_points:.1f} points "
                f"per lot per week against the registered "
                f"{c.registered_points:.1f} ({ratio_text}); the registered "
                f"figure is NOT pessimistic on this side and every "
                f"cost-dependent result in HYPOTHESES.md was computed against "
                f"financing that is too low",
            )
    else:
        verdict = SwapVerdict.REGISTERED_IS_CONSERVATIVE
        notes.append(
            "the registered substitute overstates this broker's financing on "
            "every side that could be compared, which is the direction H-005 "
            "assumed; no cost-dependent result is called into question by it"
        )

    notes.append(
        f"the registered model charges {ROLLOVERS_PER_WEEK:.0f} rollovers a "
        f"week and has no triple-swap concept, while a broker charges "
        f"{SWAP_UNITS_PER_WEEK:.0f} nights across those rollovers; the weekly "
        f"basis above already accounts for that, and it is why the per-night "
        f"figures alone would understate the gap"
    )

    return SwapDivergence(
        symbol=symbol,
        verdict=verdict,
        mode=mode,
        declared_long_points=declared_long,
        declared_short_points=declared_short,
        measured_daily_points=dict(measured_daily_points),
        comparisons=tuple(comparisons),
        short_is_credited=short_credited,
        notes=tuple(notes),
    )
