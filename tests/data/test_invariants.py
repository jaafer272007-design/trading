"""Post-conversion invariants on the real feed, and proof they can fail.

The real-data half asserts the pipeline's output. The mutation half converts
the same bars *wrongly*, in each of the three ways a timezone conversion
realistically goes wrong, and requires every mutation to be caught.

That second half is the point. An invariant that passes on correct data and
also passes on a series shifted by an hour is not an invariant, and the whole
reason this module exists is that a wrongly-converted series looks perfect:
every bar present, every price real, every session feature in the wrong
session.

The three mutations, and what each stands for:

===================  =====================================================
``shifted``          The offset is uniformly wrong — a sign error, or the
                     winter offset applied all year.
``fixed_offset``     DST is ignored entirely. The most plausible mistake,
                     because it is what "just subtract two hours" produces.
``us_rule``          The right idea, the wrong calendar: the server treated
                     as following New York's transition dates rather than
                     Europe's. Wrong for about four weeks a year, which is
                     exactly the window that distinguishes the rules.
===================  =====================================================
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from data.calendar import MarketCalendar, load_calendar
from data.convert import server_epoch_to_naive, to_utc
from data.invariants import (
    DAILY_BREAK_HOUR_NY,
    NEW_YORK,
    NFP_HOUR_NY,
    WEEKLY_CLOSE_HOUR_NY,
    InvariantError,
    assert_daily_break_is_at_new_york_seventeen,
    assert_payrolls_volume_peaks_at_the_release_hour,
    assert_release_hour_is_covered,
    assert_weekly_close_is_new_york_anchored,
    first_fridays,
    weekly_boundaries,
)
from data.raw import find
from data.snapshot import build_derived

Converted = tuple[
    pd.DatetimeIndex, pd.DatetimeIndex, MarketCalendar, "npt.NDArray[np.int64]"
]


@functools.cache
def _window_with_volume() -> Converted:
    """The real H1 export, converted, restricted to H-006's window.

    Returns:
        ``(utc, server, calendar, tick_volume)``.
    """
    calendar = load_calendar()
    raw = pd.read_csv(find("H1").path)
    derived, _ = build_derived(raw, calendar)
    inside = derived[derived["in_window"].to_numpy()].reset_index(drop=True)
    return (
        pd.DatetimeIndex(inside["timestamp_utc"]),
        pd.DatetimeIndex(inside["timestamp_server"]),
        calendar,
        inside["tick_volume"].to_numpy(dtype="int64"),
    )


def _window() -> tuple[pd.DatetimeIndex, pd.DatetimeIndex, MarketCalendar]:
    """The same, without the volumes.

    Returns:
        ``(utc, server, calendar)``.
    """
    utc, server, calendar, _ = _window_with_volume()
    return utc, server, calendar


# ---------------------------------------------------------------------------
# The real feed
# ---------------------------------------------------------------------------


def test_weekly_close_is_anchored_to_new_york() -> None:
    utc, server, calendar = _window()
    report = assert_weekly_close_is_new_york_anchored(utc, server, calendar)
    assert report.weeks > 500, report.weeks
    standard = report.close_hour_ny[WEEKLY_CLOSE_HOUR_NY]
    assert standard / report.weeks > 0.90, dict(report.close_hour_ny)


def test_every_off_hour_close_is_a_holiday_week() -> None:
    """The exceptions are explained, not tolerated."""
    utc, server, calendar = _window()
    report = weekly_boundaries(utc, server, calendar)
    assert report.off_hour_closes, "no early closes at all would itself be odd"
    assert report.off_hour_unexplained == ()


def test_the_same_close_is_not_constant_in_utc() -> None:
    """The correction, asserted rather than left in a comment.

    A test demanding UTC constancy would fail here — on data this module has
    just certified as correctly converted. Pinning the real behaviour stops
    anyone reinstating that check from a plausible-sounding first principle.

    Restricted to standard-hour weeks: holiday weeks contribute extra UTC
    hours and would make this pass for a reason that has nothing to do with
    daylight saving.
    """
    utc, _server, _calendar = _window()
    hours = {int(utc[position].hour) for position in _standard_close_positions(utc)}
    assert len(hours) == 2, sorted(hours)
    low, high = sorted(hours)
    assert high - low == 1, (low, high)


def _standard_close_positions(utc: pd.DatetimeIndex) -> list[int]:
    """Indexes of weekly closes that landed on the standard New York hour.

    Args:
        utc: Converted timestamps, sorted.

    Returns:
        Positions in ``utc``.
    """
    deltas = utc[1:] - utc[:-1]
    return [
        position
        for position in range(len(deltas))
        if deltas[position] >= pd.Timedelta(hours=24)
        and utc[position].tz_convert(NEW_YORK).hour == WEEKLY_CLOSE_HOUR_NY
    ]


def test_nfp_lands_in_the_eight_oclock_new_york_bar() -> None:
    utc, _server, calendar = _window()
    report = assert_release_hour_is_covered(utc, calendar)
    assert report.bar_present > 100, report.bar_present
    assert set(report.hour_ny) == {8}, dict(report.hour_ny)


def test_nfp_is_not_at_a_constant_utc_hour_either() -> None:
    """13:30 UTC is the release under EST only. Pinned for the same reason."""
    utc, _server, calendar = _window()
    report = assert_release_hour_is_covered(utc, calendar)
    assert set(report.hour_utc_when_est) == {13}, dict(report.hour_utc_when_est)
    assert set(report.hour_utc_when_edt) == {12}, dict(report.hour_utc_when_edt)
    assert report.hour_utc_when_edt.total() > 0
    assert report.hour_utc_when_est.total() > 0


def test_every_missing_nfp_bar_is_a_closure() -> None:
    utc, _server, calendar = _window()
    report = assert_release_hour_is_covered(utc, calendar)
    for day in report.absent_dates:
        assert calendar.holiday_near(date.fromisoformat(day)) is not None, day


def test_the_daily_break_never_moves_on_new_yorks_clock() -> None:
    """It moves twice a year in server time and never in New York."""
    _utc, server, calendar = _window()
    hours = assert_daily_break_is_at_new_york_seventeen(server, calendar)
    assert set(hours) == {DAILY_BREAK_HOUR_NY}, dict(hours)
    assert hours[DAILY_BREAK_HOUR_NY] > 1_000, hours[DAILY_BREAK_HOUR_NY]


# ---------------------------------------------------------------------------
# The invariants can fail
# ---------------------------------------------------------------------------


def _mutate(kind: str) -> Converted:
    """Convert the real bars wrongly, in a named way.

    Args:
        kind: ``"shifted"``, ``"fixed_offset"``, or ``"us_rule"``.

    Returns:
        ``(utc, server, calendar, tick_volume)`` with a broken ``utc``.
    """
    calendar = load_calendar()
    raw = pd.read_csv(find("H1").path)
    server_all = server_epoch_to_naive(raw["time"].to_numpy().astype("int64"))
    keep = [i for i, ts in enumerate(server_all) if ts.date() >= calendar.window_start]
    server = server_all[keep]
    volume = raw["tick_volume"].to_numpy(dtype="int64")[keep]

    if kind == "shifted":
        utc = to_utc(server, calendar) + pd.Timedelta(hours=1)
    elif kind == "fixed_offset":
        utc = to_utc(
            server,
            replace(calendar, clock_rule="fixed", offset_summer=calendar.offset_winter),
        )
    elif kind == "us_rule":
        utc = to_utc(server, replace(calendar, clock_rule="us"))
    else:  # pragma: no cover - guarded by the parametrize list
        raise AssertionError(kind)
    return utc, server, calendar, volume


@pytest.mark.parametrize("kind", ["shifted", "fixed_offset", "us_rule"])
def test_a_broken_conversion_fails_the_weekly_close_invariant(kind: str) -> None:
    """Each realistic conversion bug must be caught, not merely most of them."""
    utc, server, calendar, _volume = _mutate(kind)
    with pytest.raises(InvariantError):
        assert_weekly_close_is_new_york_anchored(utc, server, calendar)


@pytest.mark.parametrize("shift", [-1, 1])
def test_a_shifted_conversion_moves_the_payrolls_volume_peak(shift: int) -> None:
    """The check that reads the data rather than the labels.

    A one-hour shift is the single most likely conversion error and the
    hardest to see: every bar is present and every price is real. The spike
    in trading around the release is in the market, so it stays where it is
    while the labels move, and the peak lands on the wrong hour.
    """
    utc, _server, _calendar, volume = _window_with_volume()
    moved = utc + pd.Timedelta(hours=shift)
    with pytest.raises(InvariantError, match="peaks at"):
        assert_payrolls_volume_peaks_at_the_release_hour(moved, volume)


#: The measured coverage matrix, asserted rather than described.
#:
#: Every cell is a claim that can be checked by running the suite, and the
#: ``False`` cells are the important half: they pin blind spots so that a
#: check nobody has tested cannot be quietly assumed to work. If a future
#: change makes a ``False`` become ``True``, that is good news and this table
#: must be updated to say so — a stale table understating coverage is only
#: marginally better than one overstating it.
COVERAGE: tuple[tuple[str, bool, bool, bool], ...] = (
    # mutation,        weekly close, volume peak, release-hour coverage
    ("shifted_up", True, True, False),
    ("shifted_down", True, True, False),
    ("fixed_offset", True, False, False),
    ("us_rule", True, False, False),
)


@pytest.mark.parametrize(
    ("mutation", "close_catches", "peak_catches", "coverage_catches"),
    COVERAGE,
    ids=[row[0] for row in COVERAGE],
)
def test_the_measured_coverage_matrix_still_holds(
    mutation: str,
    close_catches: bool,
    peak_catches: bool,
    coverage_catches: bool,
) -> None:
    """Each check is required to catch what it catches and no more.

    Asserting the misses matters as much as asserting the hits. The
    release-hour check catches nothing here — not the shift its first
    docstring claimed, nothing at all — and it took running this matrix to
    find that out. Writing the misses down is what stops the next reader
    counting it as a fourth line of defence.
    """
    if mutation == "shifted_up":
        utc, server, calendar, volume = _window_with_volume()
        utc = utc + pd.Timedelta(hours=1)
    elif mutation == "shifted_down":
        utc, server, calendar, volume = _window_with_volume()
        utc = utc - pd.Timedelta(hours=1)
    else:
        utc, server, calendar, volume = _mutate(mutation)

    assert (
        _catches(assert_weekly_close_is_new_york_anchored, utc, server, calendar)
        is close_catches
    ), "weekly close"
    assert (
        _catches(assert_payrolls_volume_peaks_at_the_release_hour, utc, volume)
        is peak_catches
    ), "volume peak"
    assert (
        _catches(assert_release_hour_is_covered, utc, calendar) is coverage_catches
    ), "release-hour coverage"


def _catches(check: Callable[..., object], *args: Any) -> bool:  # noqa: ANN401
    """Whether a check rejects its input.

    Args:
        check: The assertion function.
        *args: Its arguments.

    Returns:
        True if it raised ``InvariantError``.
    """
    try:
        check(*args)
    except InvariantError:
        return True
    return False


def test_the_release_hour_check_is_not_vacuous_on_something() -> None:
    """It catches nothing in the matrix, so show what it IS for.

    Coverage, not alignment: a release-day bar that is simply absent, with no
    holiday to explain it. Kept because the check would otherwise be a green
    tick with no demonstrated failure mode at all.
    """
    utc, _server, calendar, _volume = _window_with_volume()
    keep = [
        i
        for i, ts in enumerate(utc)
        if not (
            ts.tz_convert(NEW_YORK).hour == NFP_HOUR_NY
            and ts.tz_convert(NEW_YORK).weekday() == 4
            and ts.tz_convert(NEW_YORK).day <= 7
        )
    ]
    with pytest.raises(InvariantError, match="no holiday explains it"):
        assert_release_hour_is_covered(utc[keep], calendar)


def test_the_payrolls_peak_is_where_it_should_be_on_the_real_feed() -> None:
    utc, _server, _calendar, volume = _window_with_volume()
    report = assert_payrolls_volume_peaks_at_the_release_hour(utc, volume)
    assert report.mode == NFP_HOUR_NY
    assert report.days > 100, report.days
    runner_up = report.peak_hour_ny.most_common(2)[1][1]
    assert report.peak_hour_ny[NFP_HOUR_NY] > 2 * runner_up, dict(report.peak_hour_ny)


def test_an_empty_series_is_an_error_not_a_pass() -> None:
    """A vacuous sweep must not report success."""
    _utc, _server, calendar = _window()
    empty = pd.DatetimeIndex([], tz="UTC")
    with pytest.raises(InvariantError):
        assert_weekly_close_is_new_york_anchored(empty, pd.DatetimeIndex([]), calendar)
    with pytest.raises(InvariantError):
        assert_release_hour_is_covered(empty, calendar)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_first_fridays_are_first_fridays() -> None:
    days = first_fridays(date(2026, 1, 1), date(2026, 12, 31))
    assert len(days) == 12
    for day in days:
        assert day.weekday() == 4
        assert day.day <= 7
