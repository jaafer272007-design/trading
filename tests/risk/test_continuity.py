"""The invariant that caught instrument defect #10, and the bound that did not.

`[MEASURED]` 2026-08-02: a stale weekend tick produced a server offset of
``-23.0``, the adapter called it ``measured``, every ``opened_at`` moved 26
hours and the headline divergence ratio moved from ``3.64x`` to ``5.05x``.

Two guards answer it, and the point of this file is that they are **not
equally strong**:

- the plausibility bound catches this instance and a class of others, and is
  defeated by any staleness that happens to be a plausible offset;
- the continuity invariant catches every one of them, and needs to know
  nothing about clocks.

``test_a_plausible_but_wrong_offset_defeats_the_bound_and_not_the_invariant``
is the one that says so, and it is the reason both exist.
"""

from datetime import UTC, datetime, timedelta

import pytest

from risk.clock import (
    MAX_PLAUSIBLE_UTC_OFFSET_HOURS,
    MIN_PLAUSIBLE_UTC_OFFSET_HOURS,
    offset_is_plausible,
)
from risk.continuity import check_openings, merge_openings
from risk.refusal import RefusalCode
from tests.risk import fixtures

TICKET = fixtures.position().ticket
OPENED = fixtures.position().opened_at


# --------------------------------------------------------------------------
# Guard 1: the offset must be a possible clock
# --------------------------------------------------------------------------


def test_the_offset_that_was_reported_as_measured_is_refused() -> None:
    # The actual value, from the actual reading.
    assert not offset_is_plausible(-23.0)


@pytest.mark.parametrize("offset", [-12.0, -5.0, 0.0, 2.0, 3.0, 13.0, 14.0])
def test_every_real_utc_offset_is_accepted(offset: float) -> None:
    # The bound is a fact about time zones, not a guess about brokers. A
    # tighter one -- "MT5 servers are UTC+0 to UTC+3" -- would refuse a real
    # reading somewhere, and the refusal would be indistinguishable from a
    # real fault.
    assert offset_is_plausible(offset)


@pytest.mark.parametrize("offset", [-23.0, -13.0, 15.0, 24.0, -24.0])
def test_nothing_outside_the_range_of_real_offsets_is_accepted(
    offset: float,
) -> None:
    assert not offset_is_plausible(offset)


def test_the_bound_is_the_range_of_real_time_zones_and_not_a_preference() -> None:
    assert MIN_PLAUSIBLE_UTC_OFFSET_HOURS == -12.0
    assert MAX_PLAUSIBLE_UTC_OFFSET_HOURS == 14.0


# --------------------------------------------------------------------------
# Guard 2: an opening time cannot move
# --------------------------------------------------------------------------


def test_a_first_reading_has_nothing_to_contradict_and_is_trusted() -> None:
    check = check_openings({}, (fixtures.position(),))
    assert check.trustworthy
    assert check.checked == 0
    assert check.refusals == ()


def test_an_unchanged_opening_time_passes() -> None:
    check = check_openings({TICKET: OPENED}, (fixtures.position(),))
    assert check.trustworthy
    assert check.checked == 1


def test_the_twenty_six_hour_move_is_caught_and_the_reason_names_the_clock() -> None:
    moved = fixtures.position(opened_at=OPENED + timedelta(hours=26))
    check = check_openings({TICKET: OPENED}, (moved,))
    assert not check.trustworthy
    refusal = check.refusals[0]
    assert refusal.code is RefusalCode.POSITION_AGE_MOVED
    assert "+26.00 hours" in refusal.reason
    assert "SERVER CLOCK" in refusal.reason
    # And it must say which figures die with it, in both directions.
    assert "BOTH denominators" in refusal.reason
    assert "financing CHARGE itself is unaffected" in refusal.reason


def test_a_sub_second_difference_is_not_a_move() -> None:
    # opened_at is a whole-second epoch converted through a float offset. A
    # guard that fires on float noise is a guard that gets turned off.
    jitter = fixtures.position(opened_at=OPENED + timedelta(milliseconds=400))
    assert check_openings({TICKET: OPENED}, (jitter,)).trustworthy


def test_a_backwards_host_clock_is_caught_too() -> None:
    now = fixtures.NOW
    check = check_openings(
        {TICKET: OPENED},
        (fixtures.position(),),
        previous_reading_at=now + timedelta(hours=2),
        now=now,
    )
    assert not check.trustworthy
    assert "BEFORE the previous one" in check.refusals[0].reason


def test_a_plausible_but_wrong_offset_defeats_the_bound_and_not_the_invariant() -> None:
    # This is why both guards exist. A tick stale by exactly twelve hours moves
    # a UTC+3 server to UTC-9, which is Alaska. The bound accepts it.
    assert offset_is_plausible(-9.0)
    # The invariant does not care what the offset was, only that the value it
    # produced moved.
    slid = fixtures.position(opened_at=OPENED + timedelta(hours=12))
    assert not check_openings({TICKET: OPENED}, (slid,)).trustworthy


# --------------------------------------------------------------------------
# The baseline must not heal itself
# --------------------------------------------------------------------------


def test_the_baseline_keeps_the_first_value_and_never_the_latest() -> None:
    # If a bad reading could overwrite the baseline, the guard would fire once
    # and then go quiet -- agreeing with the corruption from the second reading
    # onward. That is worse than no guard, because it looks like a guard.
    baseline = {TICKET: OPENED}
    corrupt = fixtures.position(opened_at=OPENED + timedelta(hours=26))
    carried = merge_openings(baseline, (corrupt,))
    assert carried[TICKET] == OPENED
    assert not check_openings(carried, (corrupt,)).trustworthy


def test_a_new_ticket_is_adopted_at_its_first_seen_value() -> None:
    carried = merge_openings({}, (fixtures.position(ticket=99),))
    assert carried == {99: OPENED}


def test_a_closed_ticket_leaves_the_baseline() -> None:
    carried = merge_openings({TICKET: OPENED, 4242: OPENED}, (fixtures.position(),))
    assert set(carried) == {TICKET}


def test_several_positions_are_each_checked_and_only_the_moved_one_refused() -> None:
    baseline = {1: OPENED, 2: OPENED}
    check = check_openings(
        baseline,
        (
            fixtures.position(ticket=1),
            fixtures.position(ticket=2, opened_at=OPENED - timedelta(hours=26)),
        ),
    )
    assert check.checked == 2
    assert [t for t, _, _ in check.moved] == [2]
    assert "-26.00 hours" in check.refusals[0].reason


def test_the_moved_pair_carries_both_instants_for_a_human_to_judge() -> None:
    # If the FIRST reading was the corrupt one, every later reading is refused
    # against a wrong baseline. That is the correct direction, and it is only
    # usable if the refusal shows both values.
    later = OPENED + timedelta(hours=26)
    check = check_openings({TICKET: OPENED}, (fixtures.position(opened_at=later),))
    ticket, was, now = check.moved[0]
    assert ticket == TICKET
    assert was == OPENED
    assert now == later
    assert was.isoformat() in check.refusals[0].reason
    assert now.isoformat() in check.refusals[0].reason


def test_naive_datetimes_are_never_produced_by_the_guard() -> None:
    check = check_openings({TICKET: OPENED}, (fixtures.position(),))
    assert check.trustworthy
    assert OPENED.tzinfo is UTC
    assert datetime.now(UTC).tzinfo is UTC
