"""The server clock — where the trading day starts and where financing lands.

Two quantities in this layer depend on a boundary that is not UTC midnight and
not New York midnight:

- **the trading day**, which the daily loss limit is measured over;
- **the rollover**, which is when financing is charged.

On MT5 both are the **broker server's** midnight. That is not a constant to be
looked up: it moves with the server's own daylight-saving rule, which is a
property of the broker rather than of any published calendar. It is measurable,
because MT5 reports timestamps as the server's wall clock expressed as a Unix
epoch — so a fresh tick compared against true UTC gives the offset directly.
``scripts/mt5_probe.py`` makes that measurement for the data layer; the adapter
makes it again here.

When it cannot be measured, this module is not constructed and every quantity
that needs it is refused. There is no fallback to UTC midnight. A daily loss
limit measured over the wrong day is not approximately right — it silently
mixes two sessions, and on a day either side of a large move it reports a
number that never existed.

What ``nights_held`` is, and is not
-----------------------------------

:meth:`RolloverClock.nights_between` counts **server midnights crossed**. That
is a clean, checkable definition, and it is deliberately *not* called a swap
count, because the timing differs from what the broker charges:

- Saturday and Sunday midnights are crossed by any position held over a
  weekend, but **no financing is charged on them** — the market is closed.
- One weekday each week carries a **triple** charge covering the weekend. Which
  weekday is ``SymbolTerms.swap_rollover_3days_weekday``.

Those two cancel over a whole week: five charging events, one of them tripled,
is seven nights across seven calendar days. They do **not** cancel inside a
week, and they miss in both directions — a hold spanning only Saturday and
Sunday is charged nothing, while a hold spanning only the triple-swap weekday
is charged three nights for one crossing.

A correction to what this module previously said
------------------------------------------------

An earlier version of this docstring asserted that a week costs "seven nights
charged across **five** rollovers", and that ``backtest.costs.rollovers_crossed``
therefore understated a week's carry by two sevenths. **That was wrong, and it
was asserted without reading the function.**

`[MEASURED]` ``rollovers_crossed`` walks calendar days and counts **every**
17:00 New York boundary, weekends included: **7 over a Monday-to-Monday span,
14 over two weeks.** ``tests/risk/test_swap.py`` pins those two numbers against
the real function, so the premise this layer compares on is a measurement
rather than a belief about someone else's code.

So the registered model and a broker agree on the **count** of nights per
calendar week. They disagree on **when** those nights land, and that mismatch
averages out over whole weeks. It is a real difference for sub-week holds and
it is not a systematic understatement of anything.

The magnitude error found against this broker is a separate and much larger
thing, and it survives this correction untouched — see :mod:`risk.swap`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

#: Financing charges a broker levies in one calendar week: five charging
#: events, one of them at triple rate.
SWAP_UNITS_PER_WEEK: Final = 7.0

#: Nights the registered model charges in one calendar week.
#: `[MEASURED]` against ``backtest.costs.rollovers_crossed``, which counts one
#: boundary per calendar day including Saturday and Sunday. Equal to
#: :data:`SWAP_UNITS_PER_WEEK` by arithmetic rather than by coincidence, and the
#: equality is the finding: the registered night count is right.
REGISTERED_NIGHTS_PER_WEEK: Final = 7.0

DAYS_PER_WEEK: Final = 7.0
HOURS_PER_DAY: Final = 24.0
SECONDS_PER_HOUR: Final = 3600.0

#: The range of real UTC offsets, from Baker Island to Kiritimati. A server
#: clock outside it is not a clock.
#:
#: These are **facts about time zones, not judgements about brokers.** A
#: tighter bound -- "MT5 servers are UTC+0 to UTC+3" -- would be a preference,
#: and a wrong preference refuses a legitimate reading. This one cannot be
#: wrong.
#:
#: `[MEASURED]` 2026-08-02, instrument defect #10: a closed-market tick
#: produced ``-23.0`` and was reported as a measurement. It is 11 hours outside
#: the widest offset any place on earth uses.
MIN_PLAUSIBLE_UTC_OFFSET_HOURS: Final = -12.0
MAX_PLAUSIBLE_UTC_OFFSET_HOURS: Final = 14.0


def offset_is_plausible(offset_hours: float) -> bool:
    """Whether a measured server offset could be a clock at all.

    Args:
        offset_hours: Server wall clock minus UTC, in hours.

    Returns:
        True when it lies inside the range of real UTC offsets.
    """
    return (
        MIN_PLAUSIBLE_UTC_OFFSET_HOURS <= offset_hours <= MAX_PLAUSIBLE_UTC_OFFSET_HOURS
    )


#: Nights of financing per calendar day, averaged over a full week. It is 1.0,
#: and it is written as a ratio rather than as the literal because the two
#: sevens are different quantities that happen to be equal: seven nights are
#: charged, and a week has seven days. Holding a position over a weekend costs
#: financing for the weekend even though no charging event occurs on it, which
#: is what makes the average come out at one and what makes a rate measured per
#: calendar day the one that needs no schedule.
SWAP_UNITS_PER_CALENDAR_DAY: Final = SWAP_UNITS_PER_WEEK / DAYS_PER_WEEK


@dataclass(frozen=True, slots=True)
class RolloverClock:
    """The broker server's clock, as an offset from UTC.

    Attributes:
        utc_offset_hours: Server wall clock minus UTC, in hours. Whole hours
            for every broker seen in practice, but held as a float because
            nothing requires it to be.
    """

    utc_offset_hours: float

    def to_server(self, moment: datetime) -> datetime:
        """Convert a UTC instant to the server's wall-clock reading.

        Args:
            moment: A timezone-aware UTC instant.

        Returns:
            A naive datetime carrying the server's wall clock. Naive
            deliberately: it is a clock reading, not an instant, and giving it
            a timezone would invite it to be converted a second time.

        Raises:
            ValueError: If ``moment`` is naive.
        """
        if moment.tzinfo is None:
            raise ValueError("to_server needs a timezone-aware instant")
        return (moment + timedelta(hours=self.utc_offset_hours)).replace(tzinfo=None)

    def nights_between(self, start: datetime, end: datetime) -> int:
        """Count server midnights strictly after ``start`` and at or before ``end``.

        See the module docstring: this is a count of midnights crossed, not a
        count of financing charges.

        Args:
            start: Opening instant, timezone-aware UTC.
            end: Closing or current instant, timezone-aware UTC.

        Returns:
            Zero when the position opened and was measured on the same server
            day, or when ``end`` precedes ``start``.
        """
        if end <= start:
            return 0
        return (self.to_server(end).date() - self.to_server(start).date()).days

    def server_day_bounds(self, moment: datetime) -> tuple[datetime, datetime]:
        """The UTC interval covering the server day that contains ``moment``.

        Args:
            moment: A timezone-aware UTC instant.

        Returns:
            ``(start, end)`` in UTC, half-open: ``start <= t < end``.
        """
        server = self.to_server(moment)
        day_start_server = server.replace(hour=0, minute=0, second=0, microsecond=0)
        shift = timedelta(hours=self.utc_offset_hours)
        start = (day_start_server - shift).replace(tzinfo=moment.tzinfo)
        return start, start + timedelta(days=1)


def hours_between(start: datetime, end: datetime) -> float:
    """Elapsed hours, as a float.

    Args:
        start: Earlier instant, timezone-aware.
        end: Later instant, timezone-aware.

    Returns:
        Hours elapsed. Negative if ``end`` precedes ``start``, which is left
        signed rather than clamped so that a clock disagreement between the
        terminal and the machine shows up as a negative age instead of a zero.

    Raises:
        ValueError: If either instant is naive.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("hours_between needs timezone-aware instants")
    return (end - start).total_seconds() / SECONDS_PER_HOUR


def days_between(start: datetime, end: datetime) -> float:
    """Elapsed calendar days, as a float.

    Args:
        start: Earlier instant, timezone-aware.
        end: Later instant, timezone-aware.

    Returns:
        Days elapsed, signed.
    """
    return hours_between(start, end) / HOURS_PER_DAY
