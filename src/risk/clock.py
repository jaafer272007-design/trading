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
count, because the two differ:

- Saturday and Sunday midnights are crossed by any position held over a
  weekend, but no financing is charged on them.
- One weekday each week carries a **triple** charge, covering the weekend.
  Which weekday is ``SymbolTerms.swap_rollover_3days_weekday``.

The net of those two is that a full week costs seven nights' financing charged
across five rollovers. That is why :mod:`risk.carry` projects forward on a
**per calendar day** basis measured from what the broker actually charged,
rather than by counting rollovers and multiplying: the calendar-day rate
absorbs the triple-swap convention, weekends, holidays and mid-hold rate
changes without needing to model any of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

#: Financing charges in one calendar week. Five rollovers occur, one of them
#: at triple rate, so the week costs seven nights.
SWAP_UNITS_PER_WEEK: Final = 7.0

#: Rollovers in one calendar week, which is what ``backtest.costs`` counts
#: through ``rollovers_crossed``. The gap between this and the line above is
#: the triple-swap convention, and :mod:`risk.swap` reports it as a divergence
#: rather than leaving it implicit.
ROLLOVERS_PER_WEEK: Final = 5.0

DAYS_PER_WEEK: Final = 7.0
HOURS_PER_DAY: Final = 24.0
SECONDS_PER_HOUR: Final = 3600.0

#: Nights of financing per calendar day, averaged over a full week. It is 1.0,
#: and it is written as a ratio rather than as the literal because the two
#: sevens are different quantities that happen to be equal: seven nights are
#: charged, and a week has seven days. Holding a position over a weekend costs
#: financing for the weekend even though no rollover occurs on it, which is
#: what makes the average come out at one and what makes a
#: rollover-counting projection wrong.
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
