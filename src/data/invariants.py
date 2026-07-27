"""Post-conversion invariants: what must hold once server time becomes UTC.

Nothing downstream may read a bar until these pass. The conversion in
``src/data/convert.py`` is one subtraction, and getting it wrong by an hour
produces a series in which every bar is present, every price is real, and
every session feature sits in the wrong session. These are the checks that
can tell the difference.

A correction to how these were specified
----------------------------------------

The obvious form of the first invariant is *"the weekly session boundaries
are constant in UTC year-round"*, and it is wrong. It would fail on a
correct conversion.

The market's boundaries are anchored to New York — the week closes at 17:00
America/New_York — and New York's own UTC offset moves twice a year. So a
correctly converted series puts the weekly close in **two** UTC hours, 20:00
and 21:00, one per US daylight-saving regime. MEASURED over the H-006 window:
20:00 UTC on 364 weeks and 21:00 UTC on 184, with the split following New
York's DST calendar exactly.

Asserting UTC constancy would therefore fail on correct data and pass on data
that had been wrongly forced to a fixed offset — the test would actively
select for the bug. This module states the invariant in the frame where it is
actually constant, and states the UTC consequence in the form that is
genuinely true: exactly two hours, differing by exactly one, assigned by New
York's DST regime and not by anything else.

The same correction applies to the payrolls check. Non-farm payrolls are
released at 08:30 America/New_York, which is 13:30 UTC in winter and 12:30
UTC in summer. "NFP at 13:30 UTC" holds for 45 of the 125 releases in this
window and fails for the other 80.

A second correction: checking a label against itself
----------------------------------------------------

The natural way to write the payrolls check is to resolve 08:30 New York to a
UTC instant, find the bar there, and assert it is the 08:00 New York bar.
That is circular. The lookup key *is* the answer, so the assertion holds for
any conversion whatsoever — shift the whole series an hour and a different bar
moves into the slot and passes just as happily. It was written that way here
first, and it passed on data deliberately shifted by an hour.

The version that works reads the data instead of the labels:
:func:`assert_payrolls_volume_peaks_at_the_release_hour` asks the tick counts
which hour is unusually busy on payrolls Fridays, normalised against ordinary
Fridays so the daily volume profile cancels. MEASURED: the busiest hour is
08:00 New York on 47 of 125 releases; under a one-hour shift in either
direction the mode moves to the neighbouring hour with the same share. The
spike is in the market, so it does not move when the labelling does.

What each check actually catches
--------------------------------

MEASURED by converting the real H1 export four wrong ways and running every
check against each. This table is the output of that run, not a design intent:

=====================  =======  =======  =======  =======
mutation               weekly   volume   release  daily
                       close    peak     hour     break
=====================  =======  =======  =======  =======
shifted +1h            CAUGHT   CAUGHT   pass     CAUGHT
shifted -1h            CAUGHT   CAUGHT   pass     CAUGHT
fixed offset (no DST)  CAUGHT   pass     pass     CAUGHT
US transition dates    CAUGHT   pass     pass     CAUGHT
=====================  =======  =======  =======  =======

Three things follow, and the second was a surprise:

1. **The weekly close is the load-bearing check.** It catches every mutation,
   because it samples every week and is anchored to a clock the broker does
   not control.

2. **The release-hour check catches nothing.** Not just the shift its own
   docstring originally claimed — nothing at all. It is retained as a
   data-completeness check, which is a real thing to want, and its name and
   docstring now say so. Presenting it as a conversion invariant would have
   put a fourth green tick next to a check that cannot go red.

3. **The volume peak is the independent one.** It is the only check here that
   reads prices and volumes rather than timestamps, so it fails differently
   from the others. On ``fixed offset`` and ``US transition dates`` its mode
   stays correct — those errors are wrong only for part of the year, and the
   mode survives them — which is a limit, not a defect, and is why it is not
   the check anything relies on alone.

All of them are stated against ``zoneinfo``'s IANA database rather than
against a rule written here. Re-deriving New York's DST dates in this file,
and then checking the conversion against that derivation, would prove only
that two copies of the same mistake agree.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import numpy as np
import numpy.typing as npt
import pandas as pd

from data.calendar import MarketCalendar

NEW_YORK: Final = ZoneInfo("America/New_York")

#: The hour the last bar of the trading week opens, on New York's clock. The
#: week closes an hour later, at 17:00 — the standard rollover.
WEEKLY_CLOSE_HOUR_NY: Final = 16

#: The hour the daily break occupies, on New York's clock, in every era that
#: has one.
DAILY_BREAK_HOUR_NY: Final = 17

#: Non-farm payrolls, released 08:30 America/New_York. The bar that contains
#: it opens at 08:00 under the LEFT labelling proved in ``data/aggregate.py``.
NFP_HOUR_NY: Final = 8
NFP_MINUTE_NY: Final = 30

#: A gap at least this long marks a weekend rather than a break.
WEEKEND_MIN_HOURS: Final = 24

#: Friday, as ``datetime.weekday`` numbers it.
FRIDAY: Final = 4

#: Below this many release days the peak-hour mode is noise.
MIN_RELEASE_DAYS: Final = 60

#: Weekly closes that may sit off the standard hour, as a share. Holiday weeks
#: end early and legitimately do; the bound is on how many, not on whether.
MAX_OFF_HOUR_SHARE: Final = 0.10


class InvariantError(RuntimeError):
    """A converted series violates something that must hold."""


@dataclass
class BoundaryReport:
    """Where the weekly boundaries actually landed."""

    weeks: int
    close_hour_ny: Counter[int] = field(default_factory=Counter)
    close_hour_utc: Counter[int] = field(default_factory=Counter)
    open_hour_ny: Counter[int] = field(default_factory=Counter)
    open_hour_server: Counter[int] = field(default_factory=Counter)
    off_hour_closes: tuple[tuple[str, int], ...] = ()
    off_hour_unexplained: tuple[str, ...] = ()


def _weekend_positions(utc: pd.DatetimeIndex) -> list[int]:
    """Indexes of the last bar before each weekend.

    Args:
        utc: UTC timestamps, sorted.

    Returns:
        Positions in ``utc``.
    """
    if len(utc) < 2:
        return []
    deltas = utc[1:] - utc[:-1]
    threshold = pd.Timedelta(hours=WEEKEND_MIN_HOURS)
    return [int(i) for i in np.flatnonzero(deltas >= threshold)]


def weekly_boundaries(
    utc: pd.DatetimeIndex, server: pd.DatetimeIndex, calendar: MarketCalendar
) -> BoundaryReport:
    """Measure where each trading week starts and ends.

    Args:
        utc: Converted timestamps, sorted.
        server: The same bars' server wall-clock readings.
        calendar: The frozen calendar, for the holiday list.

    Returns:
        The measurement, in three frames.
    """
    positions = _weekend_positions(utc)
    report = BoundaryReport(weeks=len(positions))
    off: list[tuple[str, int]] = []
    unexplained: list[str] = []

    for i in positions:
        close_ny = utc[i].tz_convert(NEW_YORK)
        open_ny = utc[i + 1].tz_convert(NEW_YORK)
        report.close_hour_ny[close_ny.hour] += 1
        report.close_hour_utc[int(utc[i].hour)] += 1
        report.open_hour_ny[open_ny.hour] += 1
        report.open_hour_server[int(server[i + 1].hour)] += 1

        if close_ny.hour != WEEKLY_CLOSE_HOUR_NY:
            off.append((str(close_ny.date()), close_ny.hour))
            if calendar.holiday_near(close_ny.date(), tolerance_days=4) is None:
                unexplained.append(str(close_ny.date()))

    report.off_hour_closes = tuple(off)
    report.off_hour_unexplained = tuple(unexplained)
    return report


def assert_weekly_close_is_new_york_anchored(
    utc: pd.DatetimeIndex, server: pd.DatetimeIndex, calendar: MarketCalendar
) -> BoundaryReport:
    """The week must end at 17:00 New York, every week that is not shortened.

    Args:
        utc: Converted timestamps, sorted.
        server: The same bars' server wall-clock readings.
        calendar: The frozen calendar.

    Returns:
        The measurement, so a caller can report it.

    Raises:
        InvariantError: If too many weeks close off the standard hour, if an
            off-hour close has no holiday near it, or if the UTC hours are not
            exactly the two that New York's DST regime implies.
    """
    report = weekly_boundaries(utc, server, calendar)
    if report.weeks == 0:
        raise InvariantError(
            "no weekend gaps found. Either the series is under a week long or "
            "the weekend detector is broken; neither may pass silently."
        )

    off_share = len(report.off_hour_closes) / report.weeks
    if off_share > MAX_OFF_HOUR_SHARE:
        raise InvariantError(
            f"{len(report.off_hour_closes)} of {report.weeks} weeks close away "
            f"from {WEEKLY_CLOSE_HOUR_NY:02d}:00 New York "
            f"({off_share:.1%}). The rollover is the most stable landmark on "
            f"this feed; this many exceptions means the conversion, not the "
            f"schedule. Hours seen: {dict(report.close_hour_ny)}"
        )

    if report.off_hour_unexplained:
        raise InvariantError(
            f"weeks closing off the standard hour with no holiday within four "
            f"days: {list(report.off_hour_unexplained)}. An early close is "
            f"explained by the exchange calendar or it is not explained."
        )

    _assert_utc_hours_follow_new_york(utc, calendar)
    return report


def _assert_utc_hours_follow_new_york(
    utc: pd.DatetimeIndex, calendar: MarketCalendar
) -> None:
    """The UTC form of the same fact, stated so it is actually true.

    A correct conversion puts the weekly close in exactly two UTC hours, one
    per US daylight-saving regime, differing by exactly one — and which of the
    two is fixed by New York's own calendar, not by the broker's.

    This is the check that would be *weakened* by the intuitive version. A
    series wrongly held at a constant UTC hour would satisfy "constant in UTC"
    and fail here, which is the correct outcome.

    Args:
        utc: Converted timestamps, sorted.
        calendar: The frozen calendar.

    Raises:
        InvariantError: If a standard-hour close sits in the wrong UTC hour
            for its regime, or if the two regimes do not differ by one hour.
    """
    summer: set[int] = set()
    winter: set[int] = set()
    for i in _weekend_positions(utc):
        local = utc[i].tz_convert(NEW_YORK)
        if local.hour != WEEKLY_CLOSE_HOUR_NY:
            continue  # holiday-shortened; the standard hour is what is claimed
        (summer if local.dst() else winter).add(int(utc[i].hour))

    for name, hours in (("US summer", summer), ("US winter", winter)):
        if len(hours) > 1:
            raise InvariantError(
                f"the weekly close occupies more than one UTC hour within {name}: "
                f"{sorted(hours)}. Inside a single DST regime New York's offset "
                f"is fixed, so a correct conversion cannot spread across hours."
            )

    if summer and winter:
        gap = (winter.copy().pop() - summer.copy().pop()) % 24
        if gap != 1:
            raise InvariantError(
                f"the weekly close sits at {sorted(summer)} UTC in US summer and "
                f"{sorted(winter)} UTC in US winter. Those must differ by exactly "
                f"one hour — that difference IS New York's daylight saving. A "
                f"difference of {gap} means the offset is being applied on the "
                f"wrong dates."
            )
    # Neither regime present is not an error here: a short series can sit
    # entirely inside one. It is reported rather than asserted, because
    # demanding both would make this fail on a legitimately short snapshot.
    _ = calendar


@dataclass
class NfpReport:
    """Where the payrolls release landed, release by release."""

    releases: int
    bar_present: int
    absent_dates: tuple[str, ...]
    hour_ny: Counter[int] = field(default_factory=Counter)
    hour_utc_when_edt: Counter[int] = field(default_factory=Counter)
    hour_utc_when_est: Counter[int] = field(default_factory=Counter)


def first_fridays(start: date, end: date) -> list[date]:
    """Every first-Friday-of-the-month in a range.

    The usual payrolls release day. Not every one carries a release — the BLS
    shifts a few, and this makes no attempt to model that. It does not need
    to: the invariant is about which *bar* contains a given New York instant,
    and that is true of any instant, released or not.

    Args:
        start: First date to consider.
        end: Last date to consider.

    Returns:
        The dates, ascending.
    """
    out: list[date] = []
    year, month = start.year, start.month
    while True:
        first = date(year, month, 1)
        friday = first + timedelta(days=(4 - first.weekday()) % 7)
        if friday > end:
            break
        if friday >= start:
            out.append(friday)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def assert_release_hour_is_covered(
    utc: pd.DatetimeIndex, calendar: MarketCalendar
) -> NfpReport:
    """The market must be covered at 08:30 New York on every open release day.

    .. warning::

       **This is a coverage check, not a conversion check.** An earlier
       version of it was named and documented as the latter, and it caught
       none of the four conversion mutations the test suite throws at it.

       The reason is circularity. It resolves 08:30 New York to a UTC instant,
       looks that instant up, and reports the bar's New York hour — which is
       08:00 by construction, whatever the conversion did. Shift the series an
       hour and a different bar moves into the slot and passes just as
       happily. There is no arrangement of the timestamps this can reject.

       What it does establish is worth having on its own terms: the feed has a
       bar at the release hour on every open payrolls Friday, and every
       absence is a closure on the exchange calendar rather than a hole.

       For alignment, see :func:`assert_payrolls_volume_peaks_at_the_release_hour`,
       which reads the tick counts instead of the labels, and
       :func:`assert_weekly_close_is_new_york_anchored`, which catches
       everything.

    Under the LEFT labelling proved in ``data/aggregate.py``, a bar stamped
    ``t`` covers ``[t, t+3600)``. So the bar containing 08:30 is the one whose
    own label is 08:00 — in **New York**, which is 13:00 UTC in winter and
    12:00 UTC in summer.

    Args:
        utc: Converted timestamps, sorted.
        calendar: The frozen calendar, for explaining absences.

    Returns:
        The measurement.

    Raises:
        InvariantError: If a bar is missing on a day with no holiday to
            explain it, or if the release sits in more than one UTC hour
            within a single US daylight-saving regime.
    """
    if len(utc) == 0:
        raise InvariantError("empty series")

    present = {ts: i for i, ts in enumerate(utc)}
    fridays = first_fridays(utc[0].tz_convert(NEW_YORK).date(), utc[-1].date())
    report = NfpReport(releases=len(fridays), bar_present=0, absent_dates=())
    absent: list[str] = []

    for day in fridays:
        release = pd.Timestamp(
            f"{day} {NFP_HOUR_NY:02d}:{NFP_MINUTE_NY:02d}", tz=NEW_YORK
        )
        wanted = release.floor("h").tz_convert("UTC")
        index = present.get(wanted)
        if index is None:
            absent.append(str(day))
            continue

        report.bar_present += 1
        local = utc[index].tz_convert(NEW_YORK)
        report.hour_ny[local.hour] += 1
        if local.dst():
            report.hour_utc_when_edt[int(utc[index].hour)] += 1
        else:
            report.hour_utc_when_est[int(utc[index].hour)] += 1

        if local.hour != NFP_HOUR_NY:
            raise InvariantError(
                f"{day}: 08:30 New York resolves to a bar opening "
                f"{local.hour:02d}:00 New York, not {NFP_HOUR_NY:02d}:00. The "
                f"conversion has moved the release out of its own hour."
            )

    unexplained = [
        d for d in absent if calendar.holiday_near(date.fromisoformat(d)) is None
    ]
    if unexplained:
        raise InvariantError(
            f"no bar covers 08:30 New York on {unexplained}, and no holiday "
            f"explains it. A missing release-hour bar on an open market is a "
            f"hole, not a closure."
        )

    for regime, counter in (
        ("EDT", report.hour_utc_when_edt),
        ("EST", report.hour_utc_when_est),
    ):
        if len(counter) > 1:
            raise InvariantError(
                f"the release bar occupies more than one UTC hour within "
                f"{regime}: {dict(counter)}. Within one regime it cannot."
            )

    edt = set(report.hour_utc_when_edt)
    est = set(report.hour_utc_when_est)
    if edt and est and (est.copy().pop() - edt.copy().pop()) % 24 != 1:
        raise InvariantError(
            f"the release bar sits at {sorted(edt)} UTC under EDT and "
            f"{sorted(est)} UTC under EST. Those must differ by exactly one "
            f"hour. This is the check that 'NFP is at 13:30 UTC' gets wrong: "
            f"13:30 UTC is the release only under EST."
        )

    report.absent_dates = tuple(absent)
    return report


#: How far either side of the release hour to look for the volume peak. Wide
#: enough that a one-hour error has somewhere to go, narrow enough to exclude
#: the London and New York equity opens.
PEAK_SEARCH_HOURS: Final = range(5, 13)

#: The release hour must be the most active hour on at least this share of
#: release days, measured against a same-hour baseline from ordinary Fridays.
#:
#: This floor is NOT what detects a misalignment — the *mode* is. It exists so
#: a mode computed from a signal too weak to mean anything cannot be read as
#: agreement. MEASURED at 0.376 on the H-006 window.
#:
#: Set at 0.25 rather than the 0.30 first tried. At 0.30 the US-transition-
#: dates mutation happened to score 0.280 and tripped it, which was tempting
#: to keep and wrong to: that mutation puts the peak in the RIGHT hour, so
#: catching it would have been the threshold firing by luck rather than the
#: check working. A gate that passes for a reason nobody can state is a gate
#: nobody can rely on. That mutation is caught decisively by the weekly close,
#: at 66 of 576 weeks.
MIN_PEAK_SHARE: Final = 0.25


@dataclass
class PeakReport:
    """Where the payrolls activity spike actually landed."""

    days: int
    peak_hour_ny: Counter[int] = field(default_factory=Counter)

    @property
    def mode(self) -> int | None:
        """The most common peak hour.

        Returns:
            The hour, or ``None`` if nothing was measured.
        """
        return self.peak_hour_ny.most_common(1)[0][0] if self.peak_hour_ny else None

    @property
    def mode_share(self) -> float:
        """How dominant that hour is.

        Returns:
            A share in ``[0, 1]``.
        """
        total = self.peak_hour_ny.total()
        return self.peak_hour_ny.most_common(1)[0][1] / total if total else 0.0


def payrolls_volume_peak(
    utc: pd.DatetimeIndex, tick_volume: npt.NDArray[np.int64]
) -> PeakReport:
    """Find which New York hour is unusually busy on payrolls Fridays.

    Normalised against the same hour on **other** Fridays, so the ordinary
    intraday volume profile — which peaks around the New York equity open on
    every day of the week — cancels out and what is left is the release.

    Args:
        utc: Converted timestamps, sorted.
        tick_volume: Per-bar tick counts, aligned to ``utc``.

    Returns:
        The distribution of per-day peak hours.
    """
    local = utc.tz_convert(NEW_YORK)
    hour = np.array([ts.hour for ts in local])
    weekday = np.array([ts.weekday() for ts in local])
    day = np.array([ts.date() for ts in local])
    volume = tick_volume.astype("float64")

    releases = set(first_fridays(local[0].date(), local[-1].date()))
    on_release = np.array([d in releases for d in day])
    friday = weekday == FRIDAY

    baseline = {
        h: float(np.median(volume[friday & ~on_release & (hour == h)]))
        for h in PEAK_SEARCH_HOURS
        if (friday & ~on_release & (hour == h)).any()
    }

    report = PeakReport(days=0)
    for release_day in sorted(releases):
        same_day = day == release_day
        scored = {
            h: float(volume[same_day & (hour == h)][0]) / baseline[h]
            for h in PEAK_SEARCH_HOURS
            if h in baseline and baseline[h] > 0 and (same_day & (hour == h)).any()
        }
        if not scored:
            continue
        report.days += 1
        report.peak_hour_ny[max(scored, key=lambda h: scored[h])] += 1
    return report


def assert_payrolls_volume_peaks_at_the_release_hour(
    utc: pd.DatetimeIndex, tick_volume: npt.NDArray[np.int64]
) -> PeakReport:
    """The activity spike must land in the bar the release is labelled into.

    The check that is actually sensitive to a shifted conversion. It uses no
    label to find the answer: it asks the tick counts which hour is busy on
    payrolls Fridays, and requires that hour to be the one 08:30 New York
    falls in. Move the conversion by an hour and the spike moves with it,
    because the spike is in the data and the labelling is not.

    Statistical rather than arithmetic, and stated as such. The threshold is
    on the *mode*, not on any single day: individual releases are sometimes
    dull and other news sometimes lands elsewhere in the morning.

    Args:
        utc: Converted timestamps, sorted.
        tick_volume: Per-bar tick counts, aligned to ``utc``.

    Returns:
        The measurement.

    Raises:
        InvariantError: If the busiest hour is not the release hour, or if it
            is not dominant enough for that to mean anything.
    """
    report = payrolls_volume_peak(utc, tick_volume)
    if report.days < MIN_RELEASE_DAYS:
        raise InvariantError(
            f"only {report.days} payrolls days available; this check needs at "
            f"least {MIN_RELEASE_DAYS} for a mode to be worth reading."
        )
    if report.mode != NFP_HOUR_NY:
        raise InvariantError(
            f"payrolls activity peaks at {report.mode:02d}:00 New York, not "
            f"{NFP_HOUR_NY:02d}:00. The release is at "
            f"{NFP_HOUR_NY:02d}:{NFP_MINUTE_NY}, so the busiest hour of a "
            f"payrolls Friday is the one containing it — unless the conversion "
            f"has moved the bars relative to the clock. "
            f"Distribution: {dict(sorted(report.peak_hour_ny.items()))}"
        )
    if report.mode_share < MIN_PEAK_SHARE:
        raise InvariantError(
            f"the release hour is the busiest on only {report.mode_share:.1%} "
            f"of payrolls days (floor {MIN_PEAK_SHARE:.0%}). The peak is in the "
            f"right place but too weak to certify the alignment. "
            f"Distribution: {dict(sorted(report.peak_hour_ny.items()))}"
        )
    return report


def assert_daily_break_is_at_new_york_seventeen(
    server: pd.DatetimeIndex, calendar: MarketCalendar
) -> Counter[int]:
    """Every daily-break gap must map to 17:00 New York.

    The break moves twice a year in server time — 00:00 when the US and EU
    calendars agree, 23:00 when only the US has changed — and both readings
    are 17:00 in New York. That invariance is the conversion working; a break
    that lands anywhere else means the offset was applied on the wrong dates.

    Args:
        server: Server wall-clock timestamps, sorted.
        calendar: The frozen calendar.

    Returns:
        Count of New York hours the break was found at.

    Raises:
        InvariantError: If any break falls outside 17:00 New York.
    """
    from data.classify import GapCause, bar_validity

    _, gaps = bar_validity(server, calendar)
    hours: Counter[int] = Counter()
    for before, _after, _missing, cause in gaps:
        if cause is not GapCause.DAILY_BREAK:
            continue
        break_at = before + pd.Timedelta(hours=1)
        offset = calendar.offset_hours(break_at.date())
        as_utc = (break_at - pd.Timedelta(hours=offset)).tz_localize("UTC")
        hours[as_utc.tz_convert(NEW_YORK).hour] += 1

    stray = {h: n for h, n in hours.items() if h != DAILY_BREAK_HOUR_NY}
    if stray:
        raise InvariantError(
            f"daily breaks found at New York hours {stray}, expected only "
            f"{DAILY_BREAK_HOUR_NY:02d}:00. The break is the market's rollover "
            f"and does not move on New York's clock; if it appears to, the "
            f"server-to-UTC offset is being resolved on the wrong dates."
        )
    return hours
