"""Server wall-clock to UTC, and the proofs that the conversion is right.

``DATA_CONTRACT.md`` §4: **all storage in UTC, no exceptions, no local time
anywhere in the data layer.** MT5 hands over server wall-clock time expressed
as a Unix epoch — a number that *looks* like UTC and is not. This module is the
single place that difference is resolved, and nothing downstream may re-derive
an offset.

The conversion is one subtraction. What makes it dangerous is that getting it
wrong by an hour produces a series that is entirely plausible: every bar is
present, every price is real, the ordering is intact, and every session feature
is shifted into the wrong session. §4 calls a one-bar convention mismatch a
leak and says one bar is enough. So the arithmetic here is trivial and the
tests around it are not.

Why the offset is per-bar and not per-series
--------------------------------------------

The server clock moves twice a year. A single offset applied across a snapshot
is correct for at most half of it. The offset is therefore resolved for each
bar's own date, from the frozen calendar, which is also what makes the
conversion checkable.

The check is **not** that the weekly boundaries are constant in UTC. They are
not, and asserting that would fail against correct data: the market's rollover
is fixed at 17:00 New York, which is 22:00 UTC in winter and 21:00 UTC in
summer because New York's own offset moves. The invariant that holds is
server -> UTC -> New York, constant at 17:00 all year. Getting this backwards
is easy and expensive — a test asserting UTC constancy would fail on a correct
conversion and invite someone to "fix" it until it passed.
``tests/data/test_conventions.py`` asserts the New York form.

The ambiguous hour
------------------

A clock transition repeats or skips a local hour. Because the offset here is
resolved per calendar date, bars straddling a transition collide: two bars an
hour apart on the server clock convert to one UTC instant. On this feed both
transitions fall on a Sunday inside the weekend closure, so those bars do not
exist — but "no bar lands there" is a property of the market's schedule, not of
the arithmetic, and it is asserted rather than assumed.
:func:`assert_no_ambiguous_timestamps` fails loudly if a snapshot ever contains
one. Silently keeping both is exactly the plausible wrong answer this module
exists to prevent.
"""

from __future__ import annotations

from datetime import UTC

import numpy as np
import numpy.typing as npt
import pandas as pd

from data.calendar import MarketCalendar


class ConversionError(RuntimeError):
    """A timestamp cannot be converted unambiguously."""


def server_epoch_to_naive(epoch: npt.NDArray[np.int64]) -> pd.DatetimeIndex:
    """Read MT5 epochs as the server wall-clock readings they are.

    MT5 stores server local time as though it were UTC. Interpreting the value
    as UTC therefore recovers the server's clock face — which is the correct
    first step, and is emphatically not the same as recovering the instant.

    Args:
        epoch: MT5 ``time`` values, seconds.

    Returns:
        Naive datetimes carrying the server's wall-clock reading.
    """
    return pd.to_datetime(epoch, unit="s", utc=True).tz_localize(None)


def offsets_for(
    index: pd.DatetimeIndex, calendar: MarketCalendar
) -> npt.NDArray[np.int64]:
    """Resolve each timestamp's server-to-UTC offset from the calendar.

    Args:
        index: Naive server wall-clock timestamps.
        calendar: The frozen calendar.

    Returns:
        Whole-hour offsets, one per timestamp.
    """
    return np.array([calendar.offset_hours(ts.date()) for ts in index], dtype=np.int64)


def to_utc(index: pd.DatetimeIndex, calendar: MarketCalendar) -> pd.DatetimeIndex:
    """Convert server wall-clock timestamps to true UTC.

    Args:
        index: Naive server wall-clock timestamps.
        calendar: The frozen calendar.

    Returns:
        Timezone-aware UTC timestamps.
    """
    offsets = offsets_for(index, calendar)
    shifted = index - pd.to_timedelta(offsets, unit="h")
    return pd.DatetimeIndex(shifted).tz_localize(UTC)


def assert_no_ambiguous_timestamps(
    index: pd.DatetimeIndex, calendar: MarketCalendar
) -> None:
    """Fail if two bars convert to the same instant, or go backwards.

    The offset is resolved per calendar date, so two bars an hour apart on
    opposite sides of a transition can land on the *same* UTC instant — a
    collision in which two bars claim one hour of market.

    On this feed both transitions fall inside the weekend closure, so the
    straddling bars do not exist. That is a fact about the broker's schedule,
    not about the arithmetic, and it is checked rather than trusted: if it
    stops being true, converting those bars needs a sub-daily offset rule this
    module does not have, and inventing one silently is the failure mode.

    Args:
        index: Naive server wall-clock timestamps.
        calendar: The frozen calendar.

    Raises:
        ConversionError: If the converted series is not strictly increasing.
    """
    if len(index) == 0:
        return

    utc = to_utc(index, calendar)
    # A correct conversion is strictly monotonic wherever the input is. A
    # repeated hour shows up as a UTC timestamp that goes backwards.
    #
    # Compared as Timedeltas, never as raw int64. A DatetimeIndex's integer
    # view is in its own resolution — nanoseconds under pandas 2, microseconds
    # under pandas 3 — so a hardcoded 1e9 silently finds no gaps at all.
    deltas = utc[1:] - utc[:-1]
    if len(deltas) and deltas.min() <= pd.Timedelta(0):
        bad = int(np.argmin(deltas))
        raise ConversionError(
            f"conversion is not monotonic at server {index[bad]} -> {index[bad + 1]} "
            f"(UTC {utc[bad]} -> {utc[bad + 1]}). A bar sits in a repeated local "
            f"hour; this module has no rule for choosing between the two "
            f"occurrences and will not guess."
        )


def weekly_boundary_hours_utc(
    index: pd.DatetimeIndex, min_gap_hours: int = 24
) -> tuple[list[int], list[int]]:
    """Return the UTC hours of each weekly close and open.

    Raw material for the conversion proof, not the proof itself. Because the
    boundaries are anchored to New York and New York's offset moves, a correct
    conversion puts them in exactly **two** UTC hours — one per US DST regime.
    Re-express these on New York's clock and a correct conversion collapses
    them to one; a wrong DST rule does not.

    Args:
        index: UTC timestamps, sorted.
        min_gap_hours: Gap that marks a weekend.

    Returns:
        ``(close_hours, open_hours)``.
    """
    if len(index) < 2:
        return [], []
    deltas = index[1:] - index[:-1]
    positions = np.flatnonzero(deltas >= pd.Timedelta(hours=min_gap_hours))
    closes = [int(index[int(i)].hour) for i in positions]
    opens = [int(index[int(i) + 1].hour) for i in positions]
    return closes, opens
