"""The pessimistic cost model — ``EVALUATION.md`` §10 under H-005's substitute.

§10 forbids optimistic assumptions and forbids a constant spread. H-005 registers
a deviation from the second half of that: this broker's demo feed carries a flat
15-point quote that is not a payable spread, so no session-dependent curve can be
fitted from it. The registered substitute is a **constant floor five times the
observed demo quote**, with §10's event multiplier kept on top of it.

The floor without the multiplier would be the deviation §10 actually warns
about. H-005 settles this with a measurement: the broker's own recorded spread
peaked at 700 points in March 2020, and the floor alone is 11% of that. The
multiplier is what makes the model's worst case the right order of magnitude.

What this model knows about events, and what it does not
--------------------------------------------------------

§10 says the spread "widens 3-10x around scheduled news and at the weekly open".
This project has no economic calendar. It has a frozen market calendar that knows
holidays, session structure, and — through ``data/invariants`` — where the weekly
boundary and the payrolls release land. So the event set implemented here is
exactly two members:

=====================  ==========  =========================================
weekly open            **x3**      §10 names it. Derived from the weekend gap
                                   in the index, not from a declared hour.
payrolls release hour  **x10**     The one scheduled release the calendar can
                                   locate. First Friday, 08:00 New York.
=====================  ==========  =========================================

**Every other scheduled release is priced at the floor**, and that error has a
known direction: it is *optimistic*, because a CPI print at 75 points is cheaper
than a CPI print at 225. Three things bound it rather than excuse it:

1. The floor is already 5x the observed quote and 2.5-3.6x the broker's own
   recorded median, so an unflagged event bar is not being priced at a
   realistic calm-market spread — it is being priced well above one.
2. :func:`multiplier_coverage` reports how many bars carry a multiplier above 1,
   so the gap is a number in the run output rather than an omission.
3. K-5 doubles every cost, and H-005 (ii) requires the breakeven spread. Between
   them the reader is told how much the assumption can be wrong before the
   result changes sign.

None of that is a substitute for an economic calendar. When one exists, the event
set widens and this module's constants change through a registered hypothesis.

Units
-----

Everything price-shaped is in **points** — hundredths of a dollar per ounce, the
scale ``data/aggregate`` fixes with ``PRICE_DECIMALS = 2``. One lot is 100 ounces,
so one point is one dollar per lot and :data:`POINT_VALUE_PER_LOT` is 1.0. That
coincidence is convenient and is *not* assumed anywhere: commission and swap are
declared in points-per-lot and converted through the constant, so a different
contract size changes one number here rather than the arithmetic everywhere.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from data.invariants import NEW_YORK, first_fridays

#: Ounces per lot, and therefore dollars per point per lot.
OUNCES_PER_LOT: Final = 100.0
POINT_VALUE_PER_LOT: Final = OUNCES_PER_LOT * 0.01

#: H-005 condition (i). **Never lowered.** ``tests/backtest/test_costs.py``
#: asserts this constant has not been reduced; raising it is always permitted
#: and cannot manufacture an edge, lowering it requires a new hypothesis ID.
SPREAD_FLOOR_POINTS: Final = 75.0

#: §10's "3-10x", at both ends of the stated range.
WEEKLY_OPEN_MULTIPLIER: Final = 3.0
SCHEDULED_NEWS_MULTIPLIER: Final = 10.0

#: Bars after the weekly open that carry the widened quote.
WEEKLY_OPEN_BARS: Final = 3

#: A weekend is any gap of at least this many hours. Matches
#: ``data.invariants.WEEKEND_MIN_HOURS``; restated rather than imported so the
#: two can diverge if one of them ever needs to.
WEEKEND_MIN_HOURS: Final = 24

#: New York hour containing the 08:30 payrolls release.
NFP_HOUR_NY: Final = 8

#: Slippage is a function of ATR and order size (§10), with square-root size
#: scaling — the standard market-impact form. At one lot and a 300-point ATR
#: this is 15 points per side.
SLIPPAGE_ATR_COEFF: Final = 0.05
REFERENCE_LOTS: Final = 1.0

#: Per lot, per side, in points. $3.50 a side is at the expensive end of retail
#: gold commission and is chosen for that reason.
COMMISSION_POINTS_PER_LOT_PER_SIDE: Final = 3.5

#: Charged, both directions, per lot per night held past the 17:00 New York
#: rollover. Long gold is the more expensive side to carry and the asymmetry is
#: real: it is the reason the paired-arm cost invariance in ``engine`` is only
#: partial, and it is deliberately not averaged away.
#:
#: .. warning::
#:
#:    **MEASURED WRONG, 2026-07-29. Do not use these for a new run without
#:    reading HYPOTHESES.md H-005 first.** A live FxPro terminal reports
#:    ``swap_mode = 2`` (``CURRENCY_SYMBOL``) on gold, ``swap_long = -67.9``,
#:    ``swap_short = +27.0``. Three things are wrong with the pair below, and
#:    only the third is a matter of degree:
#:
#:    1. **Structure.** A base-currency rate makes the charge proportional to
#:       the gold price. These constants are a fixed points rate with no
#:       price term, so no value of them would have been right.
#:    2. **Sign.** The broker CREDITS the short side. :func:`swap_points`
#:       charges it, on the stated ground that a credit is an optimistic
#:       assumption about an unobserved rate. It is now observed.
#:    3. **Magnitude.** `[MEASURED]` 2026-08-01, **3.395x too low on the long
#:       side**: a live 0.10-lot long was charged 13.58 across two charging
#:       events, which is 67.9 points per lot per night. The short side is
#:       still unmeasured.
#:
#: .. note::
#:
#:    **A fourth objection, which needs no broker at all.** The three above rest
#:    on readings of one account. This one is a property of the *functional
#:    form* below and would hold if no terminal had ever been opened.
#:
#:    A charge fixed in **points per lot per night** implies an annualised
#:    financing rate, as a percentage of notional, of
#:
#:    .. math::
#:
#:       r(P) = \\frac{\\text{points} \\times \\text{point value} \\times 365}
#:                    {\\text{contract size} \\times P}
#:
#:    which is **inversely proportional to price**. `[MEASURED]` against this
#:    project's own snapshot over the H-006 window, 2015-09-11 to 2026-07-27,
#:    at 20 points, 1.00 a point and 100 ounces a lot:
#:
#:    ==============================  ==========  ====================
#:    point in the window             gold        implied rate
#:    ==============================  ==========  ====================
#:    opens, 2015-09-11               1,111.72    **6.57% a year**
#:    window low                      1,050.02    **6.95% a year**
#:    window high                     5,562.51    **1.31% a year**
#:    closes, 2026-07-24              4,052.85    **1.80% a year**
#:    ==============================  ==========  ====================
#:
#:    So this constant does not represent one financing rate over the window. It
#:    represents a rate that **falls by a factor of 5.30 as the price rises**,
#:    monotonically, with no reference to any interest rate. Over the same span
#:    the dollar policy rate went from near zero to several percent — the
#:    *opposite* direction. And the argument is symmetric, which is what makes
#:    it decisive rather than merely awkward: **no single points constant can be
#:    right at both ends.** Calibrate it to 2015 and it is 5.3x too small by
#:    2026; calibrate it to 2026 — 67.9 points — and it implies **22.3% a year**
#:    at the window's opening price.
#:
#:    This bears on the **whole 2015-2026 window** rather than on one week, and
#:    it is **reasoning, not a result**: it says the registered structure cannot
#:    be right, not what the right structure is or what any run should have
#:    charged. Nothing here licenses a retro-fit. ``HYPOTHESES.md`` H-005,
#:    2026-08-01. The arithmetic is pinned in ``tests/backtest/test_costs.py``.
#:
#: .. warning::
#:
#:    They are **not changed here.** Changing a registered constant after the
#:    runs that used it is hypothesis laundering, and ``RESEARCH.md`` §5.2
#:    forbids it. H-003 and H-007 carry dated notes quantifying what the error
#:    did to them: 0.45% of H-003's effect, and a sign flip on H-007's point
#:    estimate that stays inside 2.4% of its own confidence interval.
#:
#:    ``src/risk/swap.py`` measures the divergence against a live account and
#:    reports it as a first-class output. This notice is asserted present by
#:    ``tests/backtest/test_costs.py`` so that it cannot be quietly deleted.
SWAP_LONG_POINTS_PER_LOT_PER_NIGHT: Final = 20.0
SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT: Final = 8.0

#: §10 default and stress value.
LATENCY_DEFAULT_SECONDS: Final = 0.25
LATENCY_STRESS_SECONDS: Final = 0.50

#: Latency cost as a fraction of ATR per second of delay. Deliberately small,
#: and the reason is worth stating rather than hiding in a constant: at H1
#: resolution a 250 ms delay is not separately observable, and the *material*
#: latency assumption in this engine is not this term at all — it is the
#: registered rule that a signal computed on bar ``T``'s close fills at bar
#: ``T+1``'s open, which is a delay 14,400x longer. A large coefficient here
#: would be double-counting dressed up as conservatism.
LATENCY_ATR_COEFF_PER_SECOND: Final = 0.02

#: New York rollover hour, when swap is charged.
ROLLOVER_HOUR_NY: Final = 17


@dataclass(frozen=True, slots=True)
class CostModel:
    """Every cost constant in one hashable object.

    Held as a value rather than read from module scope so that a run pins what
    it used (``REPRODUCIBILITY.md`` §5 ``cost_model_version``) and so that K-5's
    doubling is a transformation of data rather than a monkeypatch.
    """

    spread_floor_points: float = SPREAD_FLOOR_POINTS
    weekly_open_multiplier: float = WEEKLY_OPEN_MULTIPLIER
    scheduled_news_multiplier: float = SCHEDULED_NEWS_MULTIPLIER
    weekly_open_bars: int = WEEKLY_OPEN_BARS
    slippage_atr_coeff: float = SLIPPAGE_ATR_COEFF
    reference_lots: float = REFERENCE_LOTS
    commission_points_per_lot_per_side: float = COMMISSION_POINTS_PER_LOT_PER_SIDE
    swap_long_points_per_lot_per_night: float = SWAP_LONG_POINTS_PER_LOT_PER_NIGHT
    swap_short_points_per_lot_per_night: float = SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT
    latency_seconds: float = LATENCY_DEFAULT_SECONDS
    latency_atr_coeff_per_second: float = LATENCY_ATR_COEFF_PER_SECOND

    def __post_init__(self) -> None:
        """Refuse a model that violates H-005 (i).

        Raises:
            ValueError: If the spread floor is below the registered minimum.
        """
        if self.spread_floor_points < SPREAD_FLOOR_POINTS:
            raise ValueError(
                f"spread_floor_points={self.spread_floor_points} is below the "
                f"H-005 floor of {SPREAD_FLOOR_POINTS}. A run using less is "
                f"VOID. The floor may be raised freely; lowering it requires a "
                f"new hypothesis ID (H-005 guardrail)."
            )

    def version(self) -> str:
        """Content hash of every constant, for the run manifest.

        Returns:
            Hex sha256 over the sorted field values.
        """
        payload = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def doubled(self) -> CostModel:
        """Every cost doubled — the K-5 stress model.

        ``EVALUATION.md`` §10: "double every cost above and re-run. Edge
        disappearing trips K-5." Latency doubles to 500 ms, which is also §10's
        stated stress value; the two coincide and neither is derived from the
        other.

        Returns:
            A new model with every cost component multiplied by two.
        """
        return replace(
            self,
            spread_floor_points=self.spread_floor_points * 2.0,
            slippage_atr_coeff=self.slippage_atr_coeff * 2.0,
            commission_points_per_lot_per_side=(
                self.commission_points_per_lot_per_side * 2.0
            ),
            swap_long_points_per_lot_per_night=(
                self.swap_long_points_per_lot_per_night * 2.0
            ),
            swap_short_points_per_lot_per_night=(
                self.swap_short_points_per_lot_per_night * 2.0
            ),
            latency_seconds=self.latency_seconds * 2.0,
        )

    def with_spread_floor(self, points: float) -> CostModel:
        """A copy at a different spread floor, for the breakeven solver.

        Args:
            points: The floor to use. May be below :data:`SPREAD_FLOOR_POINTS`
                only via :meth:`unsafe_with_spread_floor`; this method refuses.

        Returns:
            A new model.
        """
        return replace(self, spread_floor_points=points)

    def unsafe_with_spread_floor(self, points: float) -> CostModel:
        """A copy at an arbitrary floor, bypassing the H-005 guard.

        The breakeven-spread solver required by H-005 (ii) must evaluate floors
        *below* the registered minimum — that is the entire question it answers:
        at what spread does the edge reach zero, and is that number above or
        below what a live account would have paid. Refusing to construct such a
        model would make the condition unimplementable.

        The escape is named to be conspicuous and is used in exactly one place.
        A model built this way must never reach a reported result: it is an
        input to a solver, not a configuration for a run.

        Args:
            points: Spread floor, may be any non-negative value.

        Returns:
            A model with the guard bypassed.

        Raises:
            ValueError: If ``points`` is negative.
        """
        if points < 0:
            raise ValueError(f"spread floor must be non-negative, got {points}")
        model = object.__new__(CostModel)
        for field_name, value in asdict(self).items():
            object.__setattr__(model, field_name, value)
        object.__setattr__(model, "spread_floor_points", points)
        return model


def _weekly_open_positions(index: pd.DatetimeIndex) -> npt.NDArray[np.int64]:
    """First bar of each trading week.

    Derived from gaps in the index rather than from a declared hour: the feed's
    weekly open moves with New York DST and with holidays, and a constant hour
    would mislabel both.

    Args:
        index: UTC bar timestamps, sorted.

    Returns:
        Positions of the first bar after each weekend gap.
    """
    if len(index) < 2:
        return np.zeros(0, dtype=np.int64)
    deltas = index[1:] - index[:-1]
    threshold = pd.Timedelta(hours=WEEKEND_MIN_HOURS)
    return (np.flatnonzero(deltas >= threshold) + 1).astype(np.int64)


def spread_multipliers(
    index: pd.DatetimeIndex, model: CostModel
) -> npt.NDArray[np.float64]:
    """Per-bar event multiplier applied on top of the spread floor.

    Args:
        index: UTC bar timestamps, sorted, timezone-aware.
        model: Cost model supplying the multiplier values.

    Returns:
        One multiplier per bar, at least 1.0.

    Raises:
        ValueError: If ``index`` is not timezone-aware.
    """
    if index.tz is None:
        raise ValueError(
            "spread_multipliers needs timezone-aware UTC timestamps; a naive "
            "index cannot be converted to New York and the payrolls hour would "
            "silently land on the wrong bar"
        )

    out = np.ones(len(index), dtype=np.float64)
    if len(index) == 0:
        return out

    for start in _weekly_open_positions(index):
        stop = min(int(start) + model.weekly_open_bars, len(index))
        out[int(start) : stop] = np.maximum(
            out[int(start) : stop], model.weekly_open_multiplier
        )

    ny = index.tz_convert(NEW_YORK)
    ny_dates: list[date] = [stamp.date() for stamp in ny]
    ny_hours = np.array([stamp.hour for stamp in ny], dtype=np.int64)
    releases: set[date] = set(first_fridays(min(ny_dates), max(ny_dates)))
    is_release_bar = np.array([d in releases for d in ny_dates], dtype=np.bool_) & (
        ny_hours == NFP_HOUR_NY
    )
    out[is_release_bar] = np.maximum(
        out[is_release_bar], model.scheduled_news_multiplier
    )
    return out


@dataclass(frozen=True, slots=True)
class MultiplierCoverage:
    """How much of the series the event model actually touches."""

    n_bars: int
    n_weekly_open: int
    n_news: int

    @property
    def share_elevated(self) -> float:
        """Fraction of bars priced above the flat floor."""
        if self.n_bars == 0:
            return float("nan")
        return (self.n_weekly_open + self.n_news) / self.n_bars


def multiplier_coverage(multipliers: npt.NDArray[np.float64]) -> MultiplierCoverage:
    """Count the bars the event model reaches.

    Reported so that the model's known blind spot — every scheduled release
    other than payrolls — is a number in the output rather than a silence.

    Args:
        multipliers: Output of :func:`spread_multipliers`.

    Returns:
        The counts.
    """
    return MultiplierCoverage(
        n_bars=len(multipliers),
        n_weekly_open=int(
            ((multipliers > 1.0) & (multipliers < SCHEDULED_NEWS_MULTIPLIER)).sum()
        ),
        n_news=int((multipliers >= SCHEDULED_NEWS_MULTIPLIER).sum()),
    )


def half_spread_points(multiplier: float, model: CostModel) -> float:
    """Half the quoted spread at one bar, in points.

    Crossing the spread costs half on the way in and half on the way out, so a
    round turn pays the full quote exactly once.

    Args:
        multiplier: That bar's event multiplier.
        model: The cost model.

    Returns:
        Points of adverse price movement, one side.
    """
    return 0.5 * model.spread_floor_points * multiplier


def slippage_points(atr_points: float, lots: float, model: CostModel) -> float:
    """Slippage for one side of one order.

    §10: "a function of ATR and order size, not a fixed pip value." Size enters
    under a square root — the standard market-impact form — so doubling size
    costs 1.41x rather than 2x.

    Args:
        atr_points: ATR at the decision bar, in points.
        lots: Order size.
        model: The cost model.

    Returns:
        Points of adverse price movement.
    """
    if lots <= 0 or atr_points <= 0:
        return 0.0
    scale = float((lots / model.reference_lots) ** 0.5)
    return float(model.slippage_atr_coeff * atr_points * scale)


def latency_points(atr_points: float, model: CostModel) -> float:
    """Adverse movement during the signal-to-fill delay.

    Applied to market orders only — entries, stop exits and time exits. A limit
    order at the target either fills at its price or does not fill, so latency
    cannot make it worse; modelling it as if it could would be pessimism applied
    where the mechanism does not exist.

    Args:
        atr_points: ATR at the decision bar, in points.
        model: The cost model.

    Returns:
        Points of adverse price movement.
    """
    return model.latency_atr_coeff_per_second * atr_points * model.latency_seconds


def commission_points(lots: float, sides: int, model: CostModel) -> float:
    """Commission, expressed as an equivalent adverse price move.

    Args:
        lots: Order size.
        sides: 1 or 2. §10 charges both sides.
        model: The cost model.

    Returns:
        Points, already scaled by size.
    """
    return model.commission_points_per_lot_per_side * sides * lots


def rollovers_crossed(entry: pd.Timestamp, exit_at: pd.Timestamp) -> int:
    """Count 17:00 New York rollovers strictly inside a holding period.

    Args:
        entry: Entry timestamp, timezone-aware.
        exit_at: Exit timestamp, timezone-aware.

    Returns:
        Number of rollovers crossed, zero if the position closes same-session.
    """
    if exit_at <= entry:
        return 0
    entry_ny = entry.tz_convert(NEW_YORK)
    exit_ny = exit_at.tz_convert(NEW_YORK)

    count = 0
    cursor = entry_ny.normalize() + pd.Timedelta(hours=ROLLOVER_HOUR_NY)
    if cursor <= entry_ny:
        cursor += pd.Timedelta(days=1)
    while cursor <= exit_ny:
        count += 1
        cursor += pd.Timedelta(days=1)
    return count


def swap_points(is_long: bool, nights: int, lots: float, model: CostModel) -> float:
    """Financing charged over the holding period.

    Both directions are charged rather than one being credited: a credit is an
    optimistic assumption about a rate this project has never observed, and §10
    does not permit one.

    Args:
        is_long: Direction of the position.
        nights: Rollovers crossed.
        lots: Order size.
        model: The cost model.

    Returns:
        Points, always non-negative, already scaled by size.
    """
    rate = (
        model.swap_long_points_per_lot_per_night
        if is_long
        else model.swap_short_points_per_lot_per_night
    )
    return rate * nights * lots
