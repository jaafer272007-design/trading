"""Reading a week of carry-log rows: what they can settle, and what they cannot.

**Written before the data exists.** The thresholds below are fixed here so that
they cannot be chosen after seeing the log, which is the same discipline
``mt5_probe.py`` applies to its DST anchors and for the same reason: an
instrument that can return an answer from every possible input is not measuring
anything.

The question this exists to answer
----------------------------------

`[MEASURED]` FxPro `GOLD` reports ``swap_mode = 2`` (``CURRENCY_SYMBOL``), which
means the nightly charge is denominated in ounces and the **account-currency
cost should therefore be proportional to the gold price**. That is the
structural claim in ``HYPOTHESES.md`` H-005, 2026-07-29, and it is the one thing
the field alone cannot confirm.

Two hypotheses, both consistent with a single reading:

``PRICE_DEPENDENT``
    The unit charge is ``k x P``. The dollar cost moves with gold, night by
    night, in both directions.

``FIXED_RATE``
    The unit charge is a constant in the deposit currency, which may **step**
    if the broker revises its rate. A rate that changed once during the week
    also produces "the charge went up", which is why a level comparison cannot
    separate the two and a **shape** comparison can.

Why the shape separates them and the level does not
---------------------------------------------------

Let ``u_n`` be the unit charge on night ``n`` with the triple-swap multiplier
divided out, and ``P_n`` the price at that charge.

- Under ``PRICE_DEPENDENT``: ``u_n / P_n`` is constant, ``u_n`` is not.
- Under ``FIXED_RATE``: ``u_n`` is constant, ``u_n / P_n`` is not.

So the discriminator is which of the two series is flatter, and
:data:`SEPARATION_FACTOR` fixes how much flatter one must be before the reading
is called.

**A step function does not retrace.** A single rate change can imitate a
proportional response over a week whose price moved one way. It cannot imitate
one over a week whose price went up, down, and up again — that would need three
rate changes, each coinciding in sign and rough magnitude with a price move.
Hence :data:`MIN_REVERSALS`: the test requires the price path to change
direction at least twice, and reports ``UNDETERMINED`` when it did not.

Power, and why it is checked before the verdict
-----------------------------------------------

The signal this test looks for is a variation in ``u`` of about ``s x mean(u)``,
where ``s`` is the week's fractional price range. It must clear the resolution
of the charge field, which is one cent. So the condition is

    ``s x mean(u) > POWER_MARGIN x CHARGE_RESOLUTION``

`[MEASURED]` against this project's own snapshot, 566 complete weeks of gold
from 2015-09-11:

============  ======================  =========================  ==============
size          mean nightly charge     range needed for power     weeks clearing
============  ======================  =========================  ==============
0.10 lots     about 6.79              **0.44%**                  **99.1%**
0.01 lots     about 0.68              **4.4%**                   **6.0%**
============  ======================  =========================  ==============

The median weekly high-low range is 1.71% and the 5th percentile is 0.65%, so at
**0.10 lots even a quiet week clears the bar** and at 0.01 lots almost no week
does. Adding the reversal requirement: **71.6% of weeks give a fully powered
test at 0.10 lots, against 2.8% at 0.01 lots.** That is the whole argument for
the size, and it is a measurement rather than a preference.

What one week settles regardless of power
------------------------------------------

None of these need the price to move at all:

1. **The magnitude** — the effective charge per lot per night, to well under a
   percent. This is what turns H-005 finding 3 from a reading into a
   measurement.
2. **The triple-swap weekday**, inferred from which increment triples rather
   than read off ``swap_rollover3days``.
3. **Whether the account is charged swaps at all.** A demo that does not charge
   produces all-zero increments, and that is an answer.

What one week cannot settle, ever
----------------------------------

**The historically correct constant.** This is the limitation most likely to be
over-read, so it is first. A measurement taken in 2026 is a measurement of 2026
funding. Gold financing tracks the dollar rate, and the H-006 evaluation window
opens in 2015 when that rate was near zero. **No week of 2026 data licenses a
retro-fit of the registry's cost model**, and nobody may use this to compute
what H-003 or H-007 "should have" charged. What the week bounds for all time is
the **structure** — a base-currency denomination is a property of the contract,
not of the rate cycle.

Also out of reach: whether the rate is stable over months, and whether the
weekday schedule holds across holidays. A week measures a week.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from typing import Final

#: Resolution of one nightly increment. Brokers post to the cent, so two charges
#: differing by less than this are indistinguishable however many readings are
#: taken. Conservative: the field is a double, but the posting is not.
CHARGE_RESOLUTION: Final = 0.01

#: How many times the price-driven signal must exceed the resolution before the
#: week is treated as having power. Three: enough that a one-cent posting
#: artefact cannot masquerade as a price response.
POWER_MARGIN: Final = 3.0

#: Direction changes the price path must make. Two, because a fixed rate that
#: stepped once can imitate a proportional response over a monotone week but
#: would need three coincidental steps to imitate one over a week that
#: reversed twice.
MIN_REVERSALS: Final = 2

#: Charging events needed before any of this is attempted.
MIN_RESOLVED_NIGHTS: Final = 5

#: How much flatter one series must be than the other before the verdict is
#: called. Below this the two explanations are not separated and the answer is
#: UNDETERMINED rather than the closer of the two.
SEPARATION_FACTOR: Final = 3.0

#: Multipliers a charging event may carry. Anything else means the inference
#: about the triple-swap weekday has failed and is reported rather than forced.
PERMITTED_MULTIPLIERS: Final = (1, 2, 3)


class StructureVerdict(StrEnum):
    """What the week concluded about the shape of the charge."""

    #: The unit charge tracks the price. Consistent with ``CURRENCY_SYMBOL``.
    PRICE_DEPENDENT = "PRICE_DEPENDENT"
    #: The unit charge is constant in the deposit currency.
    FIXED_RATE = "FIXED_RATE"
    #: The week could not separate them. **Not a negative result.**
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True, slots=True)
class CarryRow:
    """One reading of one position, as ``--carry-log`` wrote it.

    Attributes:
        at: Reading time, UTC.
        ticket: Broker ticket.
        carry_paid: Cumulative financing in charge terms, positive meaning paid.
        price: Symbol price at the reading, or ``None``.
        volume: Lots.
        server_offset_hours: Server clock offset, for the server weekday.
    """

    at: datetime
    ticket: int
    carry_paid: float
    price: float | None
    volume: float
    server_offset_hours: float | None


@dataclass(frozen=True, slots=True)
class NightlyCharge:
    """One charging event, reconstructed from consecutive readings.

    Attributes:
        observed_at: The first reading at which the increment appeared.
        server_weekday: Weekday on the broker's clock, ``0`` = Monday, or
            ``None`` when the offset was not recorded.
        increment: The change in cumulative financing.
        price: Price at that reading.
        multiplier: Inferred charging multiplier, 1 for an ordinary night and 3
            for the triple-swap weekday.
        unit_charge: ``increment / multiplier`` — one night's charge.
    """

    observed_at: datetime
    server_weekday: int | None
    increment: float
    price: float | None
    multiplier: int
    unit_charge: float


@dataclass(frozen=True, slots=True)
class PowerAssessment:
    """Whether the week could have detected a price response at all.

    Attributes:
        resolved_nights: Charging events found.
        mean_unit_charge: Mean single-night charge.
        price_range_fraction: ``(max - min) / mean`` over the observed prices.
        required_range_fraction: What that had to exceed.
        reversals: Direction changes in the price path.
        has_power: Whether every condition held.
        reasons: One line per condition that failed.
    """

    resolved_nights: int
    mean_unit_charge: float
    price_range_fraction: float | None
    required_range_fraction: float | None
    reversals: int
    has_power: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CarryLogAnalysis:
    """Everything a week of rows supports.

    Attributes:
        ticket: The position analysed.
        nights: The reconstructed charging events.
        power: Whether the structural test could fire.
        verdict: The structural conclusion.
        cv_unit_charge: Coefficient of variation of the unit charge.
        cv_charge_over_price: The same for ``unit charge / price``.
        charge_per_lot_per_night: The magnitude — settled with or without power.
        triple_swap_weekday: Inferred, ``0`` = Monday, or ``None``.
        charges_swaps: False when every increment was zero.
        notes: What to read, in the order it matters.
    """

    ticket: int
    nights: tuple[NightlyCharge, ...]
    power: PowerAssessment
    verdict: StructureVerdict
    cv_unit_charge: float | None
    cv_charge_over_price: float | None
    charge_per_lot_per_night: float | None
    triple_swap_weekday: int | None
    charges_swaps: bool
    notes: tuple[str, ...]


def parse_rows(lines: Iterable[str]) -> tuple[CarryRow, ...]:
    """Parse carry-log JSON lines.

    Args:
        lines: Raw lines; blanks are skipped.

    Returns:
        Rows in file order.

    Raises:
        ValueError: If a line is not a carry-log record.
    """
    out: list[CarryRow] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        try:
            out.append(
                CarryRow(
                    at=datetime.fromisoformat(payload["at"]),
                    ticket=int(payload["ticket"]),
                    carry_paid=float(payload["carry_paid"]),
                    price=(
                        float(payload["price"])
                        if payload.get("price") is not None
                        else None
                    ),
                    volume=float(payload["volume"]),
                    server_offset_hours=(
                        float(payload["server_offset_hours"])
                        if payload.get("server_offset_hours") is not None
                        else None
                    ),
                )
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"not a carry-log record: {line[:120]}") from exc
    return tuple(out)


def _coefficient_of_variation(values: Sequence[float]) -> float | None:
    """Standard deviation over the absolute mean.

    Args:
        values: Samples.

    Returns:
        ``None`` when there are fewer than two samples or the mean is zero.
    """
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    return statistics.stdev(values) / abs(mean)


def _reversals(values: Sequence[float]) -> int:
    """Count direction changes in a path.

    Args:
        values: The path.

    Returns:
        How many times the sign of the step changed. Zero steps are dropped
        first, so a flat night between two rises is not counted as two turns.
    """
    steps = [b - a for a, b in pairwise(values)]
    signs = [math.copysign(1.0, s) for s in steps if s != 0.0]
    return sum(1 for a, b in pairwise(signs) if a != b)


def nightly_charges(rows: Sequence[CarryRow]) -> tuple[NightlyCharge, ...]:
    """Reconstruct charging events from a stream of readings.

    The multiplier is **inferred from the data** rather than read off
    ``swap_rollover3days``: the median increment is taken as one night, and each
    increment is divided by it and rounded. That makes the triple-swap weekday a
    measurement, and it fails loudly — via a multiplier outside
    :data:`PERMITTED_MULTIPLIERS` — rather than silently mis-scaling.

    Args:
        rows: Readings for a single ticket, any order.

    Returns:
        One entry per charging event, in time order.
    """
    ordered = sorted(rows, key=lambda r: r.at)
    raw: list[tuple[datetime, float, float | None, float | None]] = []
    for previous, current in pairwise(ordered):
        delta = current.carry_paid - previous.carry_paid
        if delta == 0.0:
            continue
        raw.append((current.at, delta, current.price, current.server_offset_hours))
    if not raw:
        return ()

    unit = statistics.median(abs(d) for _, d, _, _ in raw)
    out: list[NightlyCharge] = []
    for at, delta, price, offset in raw:
        multiplier = max(1, round(abs(delta) / unit)) if unit > 0 else 1
        weekday: int | None = None
        if offset is not None:
            weekday = (at + timedelta(hours=offset)).weekday()
        out.append(
            NightlyCharge(
                observed_at=at,
                server_weekday=weekday,
                increment=delta,
                price=price,
                multiplier=multiplier,
                unit_charge=delta / multiplier,
            )
        )
    return tuple(out)


def _assess_power(nights: Sequence[NightlyCharge]) -> PowerAssessment:
    """Decide whether the week could have detected a price response.

    Args:
        nights: Reconstructed charging events.

    Returns:
        The assessment, with a reason per failed condition.
    """
    reasons: list[str] = []
    units = [n.unit_charge for n in nights]
    mean_unit = statistics.fmean(units) if units else 0.0

    if len(nights) < MIN_RESOLVED_NIGHTS:
        reasons.append(
            f"only {len(nights)} charging events resolved, below the "
            f"{MIN_RESOLVED_NIGHTS} this test needs"
        )

    priced = [n.price for n in nights if n.price is not None and n.price > 0]
    range_fraction: float | None = None
    required: float | None = None
    reversals = 0
    if len(priced) < 2:
        reasons.append("fewer than two readings carried a price")
    else:
        mean_price = statistics.fmean(priced)
        range_fraction = (max(priced) - min(priced)) / mean_price
        reversals = _reversals(priced)
        if mean_unit != 0:
            required = POWER_MARGIN * CHARGE_RESOLUTION / abs(mean_unit)
            if range_fraction < required:
                reasons.append(
                    f"the price moved {range_fraction:.4%} over the week against "
                    f"the {required:.4%} this charge size needs; a price "
                    f"response of that size would be smaller than the "
                    f"{CHARGE_RESOLUTION:.2f} posting resolution and could not "
                    f"have been seen"
                )
        if reversals < MIN_REVERSALS:
            reasons.append(
                f"the price path changed direction {reversals} times, below the "
                f"{MIN_REVERSALS} needed to rule out a fixed rate that stepped "
                f"once; a monotone week cannot tell a proportional response "
                f"from a single rate change"
            )

    if mean_unit == 0:
        reasons.append("every increment was zero, so there is no charge to explain")

    return PowerAssessment(
        resolved_nights=len(nights),
        mean_unit_charge=mean_unit,
        price_range_fraction=range_fraction,
        required_range_fraction=required,
        reversals=reversals,
        has_power=not reasons,
        reasons=tuple(reasons),
    )


def analyse(rows: Sequence[CarryRow]) -> CarryLogAnalysis:
    """Read one position's week.

    Args:
        rows: Readings for a single ticket.

    Returns:
        The analysis. ``verdict`` is ``UNDETERMINED`` whenever the week lacked
        power, whatever the two series happen to look like.

    Raises:
        ValueError: If ``rows`` is empty or spans more than one ticket.
    """
    if not rows:
        raise ValueError("no rows to analyse")
    tickets = {r.ticket for r in rows}
    if len(tickets) != 1:
        raise ValueError(f"expected one ticket, got {sorted(tickets)}")
    ticket = tickets.pop()
    volume = rows[0].volume

    nights = nightly_charges(rows)
    power = _assess_power(nights)
    notes: list[str] = []

    charges = bool(nights) and any(n.increment != 0.0 for n in nights)
    if not charges:
        notes.append(
            "no financing was charged over these readings. A swap-free account "
            "and a hold that never crossed a charging event look identical from "
            "here; if the position was open for more than two days, the account "
            "is not charged swaps and the measurement has to move to a live one"
        )

    per_lot: float | None = None
    if nights and volume > 0:
        per_lot = statistics.fmean(n.unit_charge for n in nights) / volume
        notes.append(
            f"magnitude, settled with or without power: "
            f"{per_lot:,.4f} per lot per night over {len(nights)} charging "
            f"events"
        )

    triple = next((n.server_weekday for n in nights if n.multiplier == 3), None)
    if triple is not None:
        notes.append(
            f"the triple-swap charge lands on server weekday {triple} "
            f"(0 = Monday), measured from the increment rather than read off "
            f"swap_rollover3days"
        )
    odd = sorted({n.multiplier for n in nights} - set(PERMITTED_MULTIPLIERS))
    if odd:
        notes.append(
            f"multipliers {odd} were inferred, which are not 1, 2 or 3; the "
            f"unit charge is not trustworthy and the verdict below should be "
            f"read as UNDETERMINED whatever it says"
        )

    units = [n.unit_charge for n in nights if n.price is not None and n.price > 0]
    ratios = [
        n.unit_charge / n.price for n in nights if n.price is not None and n.price > 0
    ]
    cv_unit = _coefficient_of_variation(units)
    cv_ratio = _coefficient_of_variation(ratios)

    verdict = StructureVerdict.UNDETERMINED
    if not power.has_power:
        notes.append(
            "the structural test did not fire. This is not evidence for either "
            "explanation and must not be reported as agreement with the "
            "registered fixed-rate model"
        )
    elif cv_unit is None or cv_ratio is None:
        notes.append("one of the two series could not be summarised")
    elif cv_ratio * SEPARATION_FACTOR < cv_unit:
        verdict = StructureVerdict.PRICE_DEPENDENT
        notes.insert(
            0,
            f"the charge divided by the price is {cv_unit / cv_ratio:.1f}x "
            f"flatter than the charge itself: the cost moves WITH the gold "
            f"price, as swap_mode 2 implies. The registered fixed-points "
            f"substitute is wrong in structure, and H-005's finding 1 is now "
            f"measured rather than inferred",
        )
    elif cv_unit * SEPARATION_FACTOR < cv_ratio:
        verdict = StructureVerdict.FIXED_RATE
        notes.insert(
            0,
            f"the charge is {cv_ratio / cv_unit:.1f}x flatter than the charge "
            f"divided by the price: it does NOT move with gold over this week, "
            f"despite swap_mode 2. H-005's finding 1 is contradicted and the "
            f"reason the mode says otherwise needs explaining before anything "
            f"is concluded",
        )
    else:
        notes.append(
            f"neither series is {SEPARATION_FACTOR:.0f}x flatter than the "
            f"other, so the week does not separate the two explanations"
        )

    return CarryLogAnalysis(
        ticket=ticket,
        nights=nights,
        power=power,
        verdict=verdict,
        cv_unit_charge=cv_unit,
        cv_charge_over_price=cv_ratio,
        charge_per_lot_per_night=per_lot,
        triple_swap_weekday=triple,
        charges_swaps=charges,
        notes=tuple(notes),
    )
