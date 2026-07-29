"""The server clock: the boundary the trading day and the rollover sit on."""

from datetime import UTC, datetime, timedelta

import pytest

from risk.clock import (
    DAYS_PER_WEEK,
    ROLLOVERS_PER_WEEK,
    SWAP_UNITS_PER_CALENDAR_DAY,
    SWAP_UNITS_PER_WEEK,
    RolloverClock,
    days_between,
    hours_between,
)

CLOCK = RolloverClock(utc_offset_hours=3.0)


def test_the_server_reading_is_offset_from_utc() -> None:
    moment = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
    assert CLOCK.to_server(moment) == datetime(2026, 7, 29, 17, 30)


def test_a_naive_instant_is_refused_rather_than_assumed_to_be_utc() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        CLOCK.to_server(datetime(2026, 7, 29, 14, 30))


def test_no_midnight_is_crossed_inside_one_server_day() -> None:
    start = datetime(2026, 7, 29, 6, 0, tzinfo=UTC)
    end = datetime(2026, 7, 29, 17, 0, tzinfo=UTC)
    assert CLOCK.nights_between(start, end) == 0


def test_one_midnight_is_crossed_over_the_server_day_boundary() -> None:
    # 21:00 UTC is midnight on a server three hours ahead.
    start = datetime(2026, 7, 28, 20, 59, tzinfo=UTC)
    end = datetime(2026, 7, 28, 21, 1, tzinfo=UTC)
    assert CLOCK.nights_between(start, end) == 1


def test_the_boundary_is_the_servers_and_not_utcs() -> None:
    # Straddles UTC midnight without straddling the server's.
    start = datetime(2026, 7, 28, 23, 0, tzinfo=UTC)
    end = datetime(2026, 7, 29, 1, 0, tzinfo=UTC)
    assert CLOCK.nights_between(start, end) == 0
    assert RolloverClock(0.0).nights_between(start, end) == 1


def test_two_days_of_holding_crosses_two_midnights() -> None:
    start = datetime(2026, 7, 27, 14, 30, tzinfo=UTC)
    end = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
    assert CLOCK.nights_between(start, end) == 2


def test_an_end_before_the_start_counts_nothing_rather_than_going_negative() -> None:
    start = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
    assert CLOCK.nights_between(start, start - timedelta(days=3)) == 0


def test_the_server_day_is_twenty_four_hours_offset_from_utc_midnight() -> None:
    start, end = CLOCK.server_day_bounds(datetime(2026, 7, 29, 14, 30, tzinfo=UTC))
    assert start == datetime(2026, 7, 28, 21, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 29, 21, 0, tzinfo=UTC)
    assert end - start == timedelta(days=1)


def test_an_instant_lies_inside_its_own_server_day() -> None:
    moment = datetime(2026, 7, 29, 22, 15, tzinfo=UTC)
    start, end = CLOCK.server_day_bounds(moment)
    assert start <= moment < end
    # 22:15 UTC is 01:15 on the server, so it belongs to the NEXT server day.
    assert start == datetime(2026, 7, 29, 21, 0, tzinfo=UTC)


def test_elapsed_hours_and_days_agree() -> None:
    start = datetime(2026, 7, 27, 14, 30, tzinfo=UTC)
    end = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
    assert hours_between(start, end) == pytest.approx(48.0)
    assert days_between(start, end) == pytest.approx(2.0)


def test_a_backwards_interval_stays_signed_rather_than_being_clamped() -> None:
    start = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
    end = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
    assert hours_between(start, end) == pytest.approx(-2.0)


def test_a_week_costs_seven_nights_across_five_rollovers() -> None:
    assert SWAP_UNITS_PER_WEEK == 7.0
    assert ROLLOVERS_PER_WEEK == 5.0
    assert SWAP_UNITS_PER_WEEK > ROLLOVERS_PER_WEEK


def test_the_per_calendar_day_unit_is_one_because_the_week_closes() -> None:
    assert pytest.approx(1.0) == SWAP_UNITS_PER_CALENDAR_DAY
    assert SWAP_UNITS_PER_CALENDAR_DAY == SWAP_UNITS_PER_WEEK / DAYS_PER_WEEK
