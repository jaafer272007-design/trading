"""The daily loss limit and the concurrent-position cap."""

from datetime import UTC, datetime, timedelta

import pytest

from risk.clock import RolloverClock
from risk.limits import DailyLossStatus, concurrency_status, daily_loss_status
from risk.refusal import Refusal, RefusalCode
from risk.state import (
    DealState,
    PositionDirection,
    PositionState,
)
from tests.risk import fixtures

CLOCK = RolloverClock(fixtures.SERVER_OFFSET_HOURS)


def _status(
    *,
    positions: tuple[PositionState, ...] = (),
    deals: tuple[DealState, ...] = (),
    limit_pct: float = 3.0,
    clock: RolloverClock | None = CLOCK,
) -> DailyLossStatus | Refusal:
    return daily_loss_status(
        fixtures.account(),
        positions,
        deals,
        limit_pct,
        fixtures.NOW,
        clock,
    )


def _ok(
    *,
    positions: tuple[PositionState, ...] = (),
    deals: tuple[DealState, ...] = (),
    limit_pct: float = 3.0,
) -> DailyLossStatus:
    result = _status(positions=positions, deals=deals, limit_pct=limit_pct)
    assert isinstance(result, DailyLossStatus)
    return result


# --------------------------------------------------------------------------
# The day boundary
# --------------------------------------------------------------------------


def test_the_day_is_the_servers_and_runs_twenty_four_hours() -> None:
    status = _ok()
    assert status.day_start == datetime(2026, 7, 28, 21, 0, tzinfo=UTC)
    assert status.day_end == datetime(2026, 7, 29, 21, 0, tzinfo=UTC)


def test_a_deal_outside_the_server_day_is_not_counted() -> None:
    inside = fixtures.deal(closed_at=datetime(2026, 7, 29, 9, 15, tzinfo=UTC))
    before = fixtures.deal(
        ticket=2, closed_at=datetime(2026, 7, 28, 20, 59, tzinfo=UTC)
    )
    status = _ok(deals=(inside, before))
    assert status.deals_counted == 1
    assert status.realised == pytest.approx(-88.60)


def test_a_deal_inside_the_utc_day_but_outside_the_server_day_is_excluded() -> None:
    # 22:00 UTC on the 29th is 01:00 on the 30th for the server.
    late = fixtures.deal(closed_at=datetime(2026, 7, 29, 22, 0, tzinfo=UTC))
    assert _ok(deals=(late,)).deals_counted == 0


def test_without_a_server_clock_the_limit_is_refused_not_measured_over_utc() -> None:
    result = _status(clock=None)
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.NO_SERVER_CLOCK
    assert "mix two sessions" in result.reason


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------


def test_realised_counts_every_cost_component_of_a_deal() -> None:
    status = _ok(deals=(fixtures.deal(),))
    assert status.realised == pytest.approx(-84.20 - 1.40 - 3.00)


def test_floating_counts_open_positions_including_their_financing() -> None:
    status = _ok(positions=(fixtures.position(profit=-125.50, swap=-2.0),))
    assert status.floating == pytest.approx(-127.50)


def test_the_denominator_is_the_opening_balance_and_does_not_move() -> None:
    # Equity 4,637.20 with -127.50 of the day's result already in it.
    status = _ok(positions=(fixtures.position(profit=-125.50, swap=-2.0),))
    assert status.opening_balance == pytest.approx(4_764.70)
    assert status.limit_currency == pytest.approx(4_764.70 * 0.03)


def test_a_limit_measured_against_current_equity_would_never_be_reached() -> None:
    # The regression this denominator exists to prevent: as the loss grows,
    # equity falls, so a limit taken as a share of equity falls with it.
    small = _ok(positions=(fixtures.position(profit=-50.0, swap=0.0),))
    large = _ok(positions=(fixtures.position(profit=-500.0, swap=0.0),))
    assert small.limit_currency < large.limit_currency
    assert large.opening_balance > small.opening_balance


def test_a_day_in_profit_shows_no_loss_rather_than_a_negative_one() -> None:
    status = _ok(positions=(fixtures.position(profit=200.0, swap=0.0),))
    assert status.total > 0
    assert status.loss == 0.0
    assert not status.breached


def test_the_limit_binds_when_the_drawdown_reaches_it() -> None:
    # 3% of roughly 4,780 is roughly 143.
    status = _ok(positions=(fixtures.position(profit=-200.0, swap=0.0),))
    assert status.breached
    assert status.remaining == 0.0
    assert status.used_fraction_of_limit is not None
    assert status.used_fraction_of_limit > 1.0


def test_remaining_is_what_is_left_before_the_limit_binds() -> None:
    status = _ok(positions=(fixtures.position(profit=-100.0, swap=0.0),))
    assert not status.breached
    assert status.remaining == pytest.approx(status.limit_currency - status.loss)


def test_a_position_carried_in_from_an_earlier_day_is_counted_and_flagged() -> None:
    status = _ok(positions=(fixtures.position(),))
    assert status.carried_in_positions == 1


def test_a_position_opened_inside_the_day_is_not_flagged_as_carried_in() -> None:
    today = fixtures.position(opened_at=fixtures.NOW - timedelta(hours=2), swap=0.0)
    assert _ok(positions=(today,)).carried_in_positions == 0


# --------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------


def test_the_cap_binds_at_the_configured_number_not_above_it() -> None:
    two = (fixtures.position(ticket=1), fixtures.position(ticket=2))
    assert concurrency_status(two, 2).breached
    assert not concurrency_status(two[:1], 2).breached


def test_headroom_says_how_many_more_may_be_opened() -> None:
    assert concurrency_status((fixtures.position(),), 2).headroom == 1
    assert concurrency_status((), 2).headroom == 2


def test_two_tickets_in_one_symbol_are_two_positions() -> None:
    two = (fixtures.position(ticket=1), fixtures.position(ticket=2))
    status = concurrency_status(two, 2)
    assert status.open_positions == 2
    assert status.by_symbol == (("XAUUSD", 2),)


def test_positions_are_broken_down_by_symbol_and_direction() -> None:
    mixed = (
        fixtures.position(ticket=1),
        fixtures.position(ticket=2, symbol="XAGUSD", direction=PositionDirection.SHORT),
    )
    status = concurrency_status(mixed, 5)
    assert status.by_symbol == (("XAGUSD", 1), ("XAUUSD", 1))
    assert status.by_direction == (("long", 1), ("short", 1))
