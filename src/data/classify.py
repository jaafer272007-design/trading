"""Why each bar is absent, and the ``valid`` column that follows from it.

``DATA_CONTRACT.md`` §6 forbids silent imputation and requires a missing bar to
be marked invalid rather than filled. That is only actionable if a missing bar
can be told apart from a closed market, which is what this module does.

Five reasons, and only one of them is a defect
----------------------------------------------

=================  ==========================================================
``weekend``        Saturday and the Sunday before the weekly open.
``daily_break``    The one-hour rollover, absent every trading day.
``early_close``    A session that ended early and resumed on schedule. Every
                   one observed on this feed landed on the CME/COMEX calendar.
``holiday``        A full-day closure.
``out_of_window``  Wholly before H-006's ``window_start``. The one-bar-a-day
                   era is nothing but gaps; calling them defects would bury
                   the real ones under sixty times their number.
``unknown``        Everything left. **The only category that marks data
                   invalid.**
=================  ==========================================================

The distinction matters because the two ends demand opposite handling. A
closure has no missing data — the market was shut, there was nothing to
record, and the decisions that would have spanned it are excluded as
closed-market. An unknown gap is a hole in a session that was open, the bars
around it are suspect, and §6 marks them invalid.

Collapsing the two is not a rounding error in either direction. Treat closures
as defects and 3,700 of 3,835 gaps poison the dataset; treat defects as
closures and real holes are silently absorbed. The probe's correction log
records both failures happening for real.

Label validity is separate from bar validity
--------------------------------------------

A label looks forward. A 24-bar label computed at bar ``T`` reads bars
``T+1 … T+24``, so it is only as valid as the worst bar in that window: **a
label whose forward window spans an invalid bar is itself invalid**, even
though the bar it is attached to is perfectly good. That is
:func:`label_validity`, and it is the reason ``valid`` is a first-class column
rather than something reconstructed at use time — a consumer that has to
remember to check it will eventually not.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from data.calendar import MarketCalendar

SATURDAY: Final = 5
SUNDAY: Final = 6


class GapCause(StrEnum):
    """Why a run of bars is absent."""

    WEEKEND = "weekend"
    DAILY_BREAK = "daily_break"
    EARLY_CLOSE = "early_close"
    HOLIDAY = "holiday"
    OUT_OF_WINDOW = "out_of_window"
    UNKNOWN = "unknown"


#: The only cause that invalidates surrounding data. Everything else is the
#: market being shut, which is not missing data.
INVALIDATING: Final = frozenset({GapCause.UNKNOWN})

#: A gap at least this long is a full-day closure rather than a short session.
HOLIDAY_MIN_MISSING_BARS: Final = 20


def classify_gap(
    before: pd.Timestamp, after: pd.Timestamp, missing: int, calendar: MarketCalendar
) -> GapCause:
    """Name the reason for one gap.

    Ordered most-specific first. ``unknown`` is the fallthrough, deliberately:
    a cause this function cannot name must not be quietly absorbed into the
    nearest plausible category.

    ``out_of_window`` is checked first and is not an explanation — it says the
    gap is outside the dataset H-006 declares, so whether it is a defect is
    not a question this project asks. Without it the sparse era contributes
    one 23-bar "unknown" per day and drowns the handful of real holes: on the
    ingest fixture, 61 against 1.

    Args:
        before: Last bar present before the gap, in **server** time.
        after: First bar present after it, in server time.
        missing: How many hourly bars are absent.
        calendar: The frozen calendar.

    Returns:
        The cause.
    """
    if before.date() < calendar.window_start:
        return GapCause.OUT_OF_WINDOW

    spans_saturday = any(
        (before.date() + timedelta(days=d)).weekday() == SATURDAY
        for d in range((after.date() - before.date()).days + 1)
    )
    if spans_saturday:
        return GapCause.WEEKEND

    if missing == 1 and before.hour == (calendar.break_hour(before.date()) - 1) % 24:
        return GapCause.DAILY_BREAK

    holiday = calendar.holiday_near(before.date()) or calendar.holiday_near(
        after.date()
    )
    if holiday is not None:
        if missing >= HOLIDAY_MIN_MISSING_BARS:
            return GapCause.HOLIDAY
        # The session ended early and picked up on schedule: the gap swallows
        # the rollover hour rather than sitting inside an open session.
        break_hour = calendar.break_hour(before.date())
        covers_break = any(
            ((before + pd.Timedelta(hours=k)).hour == break_hour)
            for k in range(1, missing + 1)
        )
        if covers_break:
            return GapCause.EARLY_CLOSE

    if missing >= HOLIDAY_MIN_MISSING_BARS:
        # Long, and no holiday explains it. Not a defect we can attribute, and
        # not something to call a holiday because of its size alone.
        return GapCause.UNKNOWN

    return GapCause.UNKNOWN


Gap = tuple[pd.Timestamp, pd.Timestamp, int, GapCause]


def bar_validity(
    server_index: pd.DatetimeIndex, calendar: MarketCalendar
) -> tuple[npt.NDArray[np.bool_], list[Gap]]:
    """Mark each bar valid or invalid, and return the gap census.

    A bar is invalid when it sits adjacent to a gap whose cause is
    ``unknown``: the hole is inside a session that was open, so the bars on
    either side of it are the ones whose neighbourhood is incomplete.

    Args:
        server_index: Bar timestamps in server time, sorted.
        calendar: The frozen calendar.

    Returns:
        ``(valid, gaps)`` where ``gaps`` is one tuple per gap.
    """
    valid = np.ones(len(server_index), dtype=np.bool_)
    gaps: list[Gap] = []
    if len(server_index) < 2:
        return valid, gaps

    # Timedeltas, not the index's integer view: that view is in the index's
    # own resolution (nanoseconds under pandas 2, microseconds under pandas 3),
    # so a hardcoded scale factor silently reports no gaps and marks every bar
    # valid — a failure that looks exactly like clean data.
    hour = pd.Timedelta(hours=1)
    deltas = server_index[1:] - server_index[:-1]
    for raw_position in np.flatnonzero(deltas > hour):
        position = int(raw_position)
        before = server_index[position]
        after = server_index[position + 1]
        missing = int(deltas[position] // hour) - 1
        cause = classify_gap(before, after, missing, calendar)
        gaps.append((before, after, missing, cause))
        if cause in INVALIDATING:
            valid[position] = False
            valid[position + 1] = False
    return valid, gaps


def label_validity(
    bar_valid: npt.NDArray[np.bool_], horizon_bars: int
) -> npt.NDArray[np.bool_]:
    """Propagate bar validity forward across a label's horizon.

    A label at ``i`` reads bars ``i+1 … i+horizon``. It is valid only if the
    bar it sits on and every bar it reads is valid, and invalid at the tail
    where the horizon runs past the end of the series — a label computed from
    a truncated window is not a shorter label, it is a wrong one.

    Args:
        bar_valid: Per-bar validity.
        horizon_bars: Forward window length.

    Returns:
        Per-label validity, same length as ``bar_valid``.

    Raises:
        ValueError: If ``horizon_bars`` is not positive.
    """
    if horizon_bars <= 0:
        raise ValueError(f"horizon_bars must be positive, got {horizon_bars}")

    n = len(bar_valid)
    out = np.zeros(n, dtype=np.bool_)
    if n == 0:
        return out

    # Suffix-window AND, computed as a difference of prefix sums so the cost
    # does not scale with the horizon.
    invalid_prefix = np.concatenate(([0], np.cumsum(~bar_valid)))
    last = n - horizon_bars
    for i in range(max(last, 0)):
        window_invalid = invalid_prefix[i + horizon_bars + 1] - invalid_prefix[i]
        out[i] = window_invalid == 0
    return out


def gap_census(gaps: list[Gap]) -> dict[str, int]:
    """Count gaps by cause, for the snapshot manifest.

    Recorded per snapshot so a shift in the ``unknown`` rate between snapshots
    is visible. A feed quietly degrading shows up here before it shows up in a
    result.

    Args:
        gaps: Output of :func:`bar_validity`.

    Returns:
        Cause name to count, every cause present even at zero.
    """
    counts = dict.fromkeys((c.value for c in GapCause), 0)
    for _, _, _, cause in gaps:
        counts[cause.value] += 1
    return counts
