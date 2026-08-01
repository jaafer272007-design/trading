"""The invariant that catches a clock error without knowing anything about clocks.

Why this exists
---------------

`[MEASURED]` 2026-08-02, instrument defect #10. A tick left over from Friday's
close was differenced against Sunday's wall clock and produced a server offset
of **-23.0 hours**, which the adapter labelled ``measured``. Every position's
``opened_at`` moved 26 hours later, every hold shortened by the same amount,
and the headline divergence ratio moved from ``3.64x`` to ``5.05x``. Nothing
was refused. The swap figure itself never changed; **only the denominator
did**, which is the same failure shape as defect #9 one layer down.

Two guards answer it and they are not equally strong.

**A plausibility bound on the offset** — :func:`risk.clock.offset_is_plausible`
— catches this instance, because no place on earth is at UTC-23. It does not
catch the general case. A tick stale by exactly twelve hours moves a UTC+3
server to UTC-9, which is Alaska, and passes.

**This module** catches all of them. A broker does not reopen a position:
``opened_at`` is a constant for the life of the ticket. So if the value derived
from it moves between two readings, the conversion changed, and no knowledge of
clocks, brokers, ticks or time zones is needed to know that something is wrong.
It is a property of the **derived value** rather than of the input, which is
what makes it independent of every assumption the derivation makes.

Why the baseline is first-seen and never updated
------------------------------------------------

The stored value is the **first** ``opened_at`` observed for a ticket, and it
is never overwritten while the ticket is open. Storing the latest would let a
bad reading rewrite the baseline, so the reading after it would agree with the
bad one and the guard would go quiet exactly one reading after it fired. A
guard that heals itself after a single bad sample is not a guard.

The cost is stated rather than hidden: if the **first** reading is the corrupt
one, every later reading is refused instead. That is the correct direction --
it fails loudly against a wrong baseline rather than quietly against a wrong
clock -- and the refusal prints both instants so a person can tell which is
which. ``--clear-offset-cache`` resets the baseline along with the cache.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from risk.refusal import Refusal, RefusalCode
from risk.state import PositionState

#: How far ``opened_at`` may move between readings before it is called a move.
#: One second: the field is a whole-second epoch, so any real change is at
#: least this large, and float conversion cannot manufacture it.
OPENED_AT_TOLERANCE: Final = timedelta(seconds=1)


@dataclass(frozen=True, slots=True)
class ContinuityCheck:
    """What comparing this reading against the last one established.

    Attributes:
        checked: Tickets that had a stored baseline to compare against.
        moved: Tickets whose ``opened_at`` moved, with both instants.
        refusals: One per moved ticket, plus one for a backwards host clock.
        trustworthy: False when anything moved. **Every age-derived figure in
            the report is void when this is false** -- see
            :attr:`risk.report.RiskReport.timing_refusal`.
    """

    checked: int
    moved: tuple[tuple[int, datetime, datetime], ...]
    refusals: tuple[Refusal, ...]
    trustworthy: bool


def check_openings(
    baseline: Mapping[int, datetime],
    positions: tuple[PositionState, ...],
    previous_reading_at: datetime | None = None,
    now: datetime | None = None,
) -> ContinuityCheck:
    """Compare this reading's opening times against the stored baseline.

    Args:
        baseline: First-seen ``opened_at`` per ticket, from previous readings.
        positions: Positions in this reading.
        previous_reading_at: When the last reading was taken, if known.
        now: This reading's time, if ``previous_reading_at`` is supplied.

    Returns:
        The check. ``trustworthy`` is True when nothing moved, including when
        there was no baseline to compare against -- a first reading cannot
        contradict itself, and saying otherwise would make the guard fire on
        every fresh install.
    """
    moved: list[tuple[int, datetime, datetime]] = []
    refusals: list[Refusal] = []
    checked = 0

    for position in positions:
        was = baseline.get(position.ticket)
        if was is None:
            continue
        checked += 1
        if abs(position.opened_at - was) <= OPENED_AT_TOLERANCE:
            continue
        moved.append((position.ticket, was, position.opened_at))
        drift = (position.opened_at - was).total_seconds() / 3600.0
        refusals.append(
            Refusal(
                RefusalCode.POSITION_AGE_MOVED,
                f"ticket {position.ticket}",
                f"opened_at was first read as {was.isoformat()} and is now "
                f"{position.opened_at.isoformat()}, a move of {drift:+.2f} "
                f"hours. A broker does not reopen a position, so the SERVER "
                f"CLOCK this timestamp was converted through has changed -- "
                f"most likely a stale tick measured while the market was "
                f"closed. Every figure derived from an age is void: hold "
                f"duration, nights held, the measured financing rate on BOTH "
                f"denominators, the divergence ratio built from it, and the "
                f"days-to-stop-out projection. The financing CHARGE itself is "
                f"unaffected -- it is read, not derived",
            )
        )

    if (
        previous_reading_at is not None
        and now is not None
        and now < previous_reading_at
    ):
        drift = (previous_reading_at - now).total_seconds() / 3600.0
        refusals.append(
            Refusal(
                RefusalCode.POSITION_AGE_MOVED,
                "reading clock",
                f"this reading is timestamped {drift:.2f} hours BEFORE the "
                f"previous one. Ages are measured against this machine's "
                f"clock, so an age can appear to shrink without any position "
                f"or server clock changing",
            )
        )

    return ContinuityCheck(
        checked=checked,
        moved=tuple(moved),
        refusals=tuple(refusals),
        trustworthy=not refusals,
    )


def merge_openings(
    baseline: Mapping[int, datetime], positions: tuple[PositionState, ...]
) -> dict[int, datetime]:
    """Carry the baseline forward, keeping the first value seen per ticket.

    Closed tickets are dropped: a ticket number is not reused by a broker
    within any horizon this matters over, and keeping them would grow the file
    without bound.

    Args:
        baseline: The stored baseline.
        positions: Positions in this reading.

    Returns:
        The baseline to store. Existing entries are **never overwritten** --
        see the module docstring on why healing is the failure mode this
        guards against.
    """
    out: dict[int, datetime] = {}
    for position in positions:
        out[position.ticket] = baseline.get(position.ticket, position.opened_at)
    return out
