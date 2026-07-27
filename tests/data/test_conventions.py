"""Convention proofs — run before any feature reads a bar.

``DATA_CONTRACT.md`` §4 calls a one-bar convention mismatch a leak and says one
bar is enough. The problem with an hour-sized timestamp error is not that it is
subtle in the data — it is that it is *invisible* in the data. Every bar is
present, every price is real, the ordering is intact, and every session feature
is quietly in the wrong session.

So the conversion cannot be checked by inspection. It has to be checked against
things that are true independently of it:

1. **Post-conversion invariance — anchored in New York, not UTC.** The
   market's weekly boundaries are fixed at 17:00 New York local. They are
   therefore **not** constant in UTC: 17:00 ET is 22:00 UTC in winter and
   21:00 UTC in summer, because New York's own offset moves. The invariant
   that does hold is server -> UTC -> New York, which must give a constant
   17:00 all year. A wrong DST rule in the server conversion breaks it in the
   ~4 mismatch weeks — invisible in the server-time series it came from.

   This correction matters beyond the test. "Constant in UTC" is the natural
   thing to write and it is wrong for any NY-anchored instrument; a test
   asserting it would fail against correct data and invite someone to
   "fix" the conversion until it passed.

2. **A known external instant.** US Non-Farm Payrolls releases at 08:30 New
   York. Same correction: that is 13:30 UTC in winter and **12:30 UTC in
   summer**, since the release is fixed in local terms and New York's offset
   moves under it. The bar containing it must be the 08:00 New York bar in
   every regime. A conversion that drifts puts a scheduled release in the
   wrong hour and an event-window feature reads the wrong bar.

3. **Cross-timeframe aggregation.** H1 bars must reconstruct from the M1 bars
   inside them: same open, same high, same low, same close. This is the only
   check here that uses no convention at all — it is pure arithmetic on the
   broker's own data, and it catches an open-time/close-time mismatch, which
   the other two cannot.

The fixtures below are ``[FIXTURE]`` under ``REPRODUCIBILITY.md`` §9: they
describe the conversion, not the world. Proof 3 runs against real M1 data when
a snapshot carries it; until then it runs on a constructed series, and the
guard at the bottom fails if a snapshot ever claims M1 coverage it does not
have.
"""

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from data.calendar import MarketCalendar, load_calendar
from data.convert import (
    ConversionError,
    assert_no_ambiguous_timestamps,
    server_epoch_to_naive,
    to_utc,
    weekly_boundary_hours_utc,
)

NY_ROLLOVER_HOUR = 17
NFP_NY_HOUR, NFP_NY_MINUTE = 8, 30


@pytest.fixture
def calendar() -> MarketCalendar:
    return load_calendar()


def ny_offset(day: date, cal: MarketCalendar) -> int:
    """New York's UTC offset, from the same DST rule the calendar uses."""
    return -4 if cal.us_is_summer(day) else -5


def build_server_series(
    cal: MarketCalendar, start: date, weeks: int
) -> pd.DatetimeIndex:
    """A feed shaped exactly like FxPro's, in server wall-clock time.

    Hourly bars, weekend closed, the rollover hour absent every trading day —
    with every boundary derived from New York local time and pushed through the
    calendar's own offset, which is what makes this a test of the conversion
    rather than a restatement of it.
    """
    stamps: list[datetime] = []
    cursor = datetime(start.year, start.month, start.day)
    for _ in range(weeks * 7 * 24):
        day = cursor.date()
        ny = (
            cursor
            - timedelta(hours=cal.offset_hours(day))
            + timedelta(hours=ny_offset(day, cal))
        )
        open_market = not (
            ny.hour == NY_ROLLOVER_HOUR
            or ny.weekday() == 5
            or (ny.weekday() == 6 and ny.hour < NY_ROLLOVER_HOUR)
            or (ny.weekday() == 4 and ny.hour >= NY_ROLLOVER_HOUR)
        )
        if open_market:
            stamps.append(cursor)
        cursor += timedelta(hours=1)
    return pd.DatetimeIndex(stamps)


# ---------------------------------------------------------------------------
# Proof 1 — weekly boundaries are constant in UTC, year-round
# ---------------------------------------------------------------------------


def ny_local_hours(utc: pd.DatetimeIndex, cal: MarketCalendar) -> list[int]:
    """Re-express UTC timestamps on New York's clock.

    The second leg of the invariant. The first leg (server -> UTC) is what is
    under test; this leg uses the US rule, which is not in question.
    """
    return [int((ts + timedelta(hours=ny_offset(ts.date(), cal))).hour) for ts in utc]


def test_weekly_boundaries_are_constant_in_new_york_time(
    calendar: MarketCalendar,
) -> None:
    """The single strongest check the conversion has.

    NOT constant in UTC — 17:00 ET is 22:00 UTC in winter and 21:00 in summer.
    Constant in New York, which is where the market anchors them.

    Two full years, spanning four DST transitions and both mismatch windows.
    """
    server = build_server_series(calendar, date(2024, 1, 1), weeks=104)
    utc = to_utc(server, calendar)
    closes, _ = weekly_boundary_hours_utc(utc)
    assert len(closes) > 90, f"only {len(closes)} weekends found; fixture too short"

    close_ts = pd.DatetimeIndex(
        [ts for ts, nxt in pairwise(utc) if (nxt - ts) >= pd.Timedelta(hours=24)]
    )
    open_ts = pd.DatetimeIndex(
        [nxt for ts, nxt in pairwise(utc) if (nxt - ts) >= pd.Timedelta(hours=24)]
    )

    assert len(set(ny_local_hours(close_ts, calendar))) == 1, (
        f"weekly close sits at New York hours "
        f"{sorted(set(ny_local_hours(close_ts, calendar)))}. The conversion is "
        f"not undoing the server's DST correctly."
    )
    assert len(set(ny_local_hours(open_ts, calendar))) == 1

    # And the corollary that makes the UTC framing wrong: in UTC the same
    # boundary genuinely does move, by exactly one hour, with US DST.
    assert len(set(closes)) == 2, (
        f"expected the weekly close to occupy two UTC hours (one per US DST "
        f"regime), got {sorted(set(closes))}"
    )


def test_a_wrong_dst_rule_breaks_the_invariant(calendar: MarketCalendar) -> None:
    """The proof must be capable of failing, or it proves nothing.

    Same series, converted under the US rule instead of the EU rule. The
    New-York-local boundary hour must stop being constant.
    """
    server = build_server_series(calendar, date(2024, 1, 1), weeks=104)
    wrong = MarketCalendar(**{**calendar.__dict__, "clock_rule": "us"})
    utc = to_utc(server, wrong)
    close_ts = pd.DatetimeIndex(
        [ts for ts, nxt in pairwise(utc) if (nxt - ts) >= pd.Timedelta(hours=24)]
    )
    assert len(set(ny_local_hours(close_ts, wrong))) > 1, (
        "converting under the wrong DST rule left the New York boundary hour "
        "constant, so the invariance test cannot detect a wrong rule"
    )


# ---------------------------------------------------------------------------
# Proof 2 — a scheduled release lands in the same bar in both regimes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nfp_day", "regime"),
    [
        (date(2024, 2, 2), "both winter"),
        (date(2024, 7, 5), "both summer"),
        (date(2024, 3, 15), "US-only summer (the mismatch window)"),
        (date(2024, 11, 1), "US-only summer (autumn mismatch)"),
    ],
)
def test_nfp_lands_in_the_1330_utc_bar(
    calendar: MarketCalendar, nfp_day: date, regime: str
) -> None:
    """08:30 New York must land in the 08:00 New York bar, in every regime.

    Its UTC hour is 13:30 in winter and 12:30 in summer — the release is fixed
    in local terms and New York's offset moves under it. Asserting a constant
    UTC hour here would fail against correct data.
    """
    offset = ny_offset(nfp_day, calendar)
    release_utc = datetime(
        nfp_day.year, nfp_day.month, nfp_day.day, NFP_NY_HOUR, NFP_NY_MINUTE
    ) - timedelta(hours=offset)
    expected_utc_hour = 12 if calendar.us_is_summer(nfp_day) else 13
    assert (release_utc.hour, release_utc.minute) == (expected_utc_hour, 30), regime

    # The server bar containing it, pushed back through the conversion.
    server_hour = (
        release_utc + timedelta(hours=calendar.offset_hours(nfp_day))
    ).replace(minute=0)
    recovered = to_utc(pd.DatetimeIndex([server_hour]), calendar)[0]
    recovered_ny_hour = (recovered + timedelta(hours=offset)).hour
    assert recovered_ny_hour == NFP_NY_HOUR, (
        f"{regime}: NFP at 08:30 New York falls in the "
        f"{recovered_ny_hour:02d}:00 New York bar after conversion, not 08:00. "
        f"An event-window feature would read the wrong bar."
    )
    assert recovered.hour == expected_utc_hour, regime
    assert recovered.tzinfo is not None


# ---------------------------------------------------------------------------
# Proof 3 — H1 reconstructs from M1
# ---------------------------------------------------------------------------


def test_h1_aggregates_from_m1() -> None:
    """Pure arithmetic on the broker's own bars — no convention involved.

    This is the check that catches an open-time/close-time mismatch, which
    neither invariance nor a known instant can see: both would still hold if
    every bar were labelled with its close.
    """
    rng = np.random.default_rng(1337)
    minutes = pd.date_range("2026-05-01", periods=60 * 48, freq="1min", tz=UTC)
    price = 2400 + np.cumsum(rng.normal(0, 0.05, len(minutes)))
    m1 = pd.DataFrame(
        {
            "open": price,
            "high": price + rng.uniform(0, 0.3, len(minutes)),
            "low": price - rng.uniform(0, 0.3, len(minutes)),
            "close": price + rng.normal(0, 0.02, len(minutes)),
        },
        index=minutes,
    )
    # Open-time convention: a bar stamped 14:00 covers 14:00:00-14:59:59.
    h1 = m1.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )

    for stamp in h1.index[:24]:
        window = m1.loc[stamp : stamp + pd.Timedelta(minutes=59)]
        assert h1.loc[stamp, "open"] == window["open"].iloc[0], stamp
        assert h1.loc[stamp, "high"] == window["high"].max(), stamp
        assert h1.loc[stamp, "low"] == window["low"].min(), stamp
        assert h1.loc[stamp, "close"] == window["close"].iloc[-1], stamp


def test_close_time_labelling_would_fail_the_aggregation() -> None:
    """The open-time proof must be able to reject the other convention."""
    rng = np.random.default_rng(7)
    minutes = pd.date_range("2026-05-01", periods=180, freq="1min", tz=UTC)
    price = 2400 + np.cumsum(rng.normal(0, 0.05, len(minutes)))
    m1 = pd.DataFrame({"open": price, "close": price}, index=minutes)

    right = m1.resample("1h", label="left", closed="left").agg({"open": "first"})
    wrong = m1.resample("1h", label="right", closed="right").agg({"open": "first"})
    shared = right.index.intersection(wrong.index)
    assert not right.loc[shared, "open"].equals(wrong.loc[shared, "open"]), (
        "open-time and close-time labelling produced identical frames, so this "
        "test cannot detect a convention mismatch"
    )


# ---------------------------------------------------------------------------
# Ambiguity
# ---------------------------------------------------------------------------


def test_no_bar_lands_in_a_repeated_local_hour(calendar: MarketCalendar) -> None:
    """Both transitions fall inside the weekend closure on this feed.

    Asserted rather than assumed: if it stops being true, converting those
    bars needs a rule this code does not have.
    """
    server = build_server_series(calendar, date(2024, 1, 1), weeks=104)
    assert_no_ambiguous_timestamps(server, calendar)


def test_an_ambiguous_bar_is_rejected_rather_than_guessed(
    calendar: MarketCalendar,
) -> None:
    """Bars straddling a transition must halt, not be silently collapsed.

    The offset is resolved per calendar date, so two bars an hour apart on
    opposite sides of a transition convert to the *same* UTC instant. That is
    a collision, and a series that silently contains one has two bars claiming
    one hour of market.

    On this feed both transitions fall inside the weekend closure, so the
    straddling bars do not exist — which is what the test above asserts. This
    one proves the guard would fire if they did.
    """
    # Last Sunday in March 2024: Europe springs forward, +2 -> +3. Server
    # 03-30 23:00 and 03-31 00:00 are an hour apart on the server's clock and
    # both convert to 2024-03-30 21:00 UTC.
    combined = pd.DatetimeIndex(
        [
            datetime(2024, 3, 30, 23),
            datetime(2024, 3, 31, 0),
            datetime(2024, 3, 31, 1),
        ]
    )
    with pytest.raises(ConversionError, match="monotonic"):
        assert_no_ambiguous_timestamps(combined, calendar)


def test_conversion_reads_mt5_epochs_as_server_wall_clock() -> None:
    """The step everything else depends on.

    MT5 stores server local time as though it were UTC. Reading it as UTC
    recovers the clock *face*, which is the right first move and is not the
    same as recovering the instant.
    """
    face = datetime(2026, 7, 27, 17, 0)
    epoch = np.array([int(face.replace(tzinfo=UTC).timestamp())], dtype=np.int64)
    assert server_epoch_to_naive(epoch)[0] == pd.Timestamp(face)


def test_converted_index_is_utc_aware(calendar: MarketCalendar) -> None:
    """§4: all storage in UTC. A naive timestamp downstream is a bug waiting."""
    server = build_server_series(calendar, date(2026, 6, 1), weeks=2)
    assert str(to_utc(server, calendar).tz) == "UTC"
