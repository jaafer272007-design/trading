"""Distance from the broker's own intervention levels."""

import pytest

from risk.margin import StopoutMode, margin_projection
from risk.refusal import RefusalCode
from tests.risk import fixtures

NOW = fixtures.NOW


def test_the_margin_level_is_equity_over_margin() -> None:
    account = fixtures.account(equity=4_637.20, margin=481.44)
    projection = margin_projection(account, 1.0, NOW)
    assert projection.margin_level_pct == pytest.approx(963.19, abs=0.01)


def test_the_thresholds_come_from_the_broker_not_from_a_convention() -> None:
    # 100% call, 50% stop-out, on 481.44 of margin.
    projection = margin_projection(fixtures.account(), 1.0, NOW)
    assert projection.mode is StopoutMode.PERCENT
    assert projection.call is not None
    assert projection.stop_out is not None
    assert projection.call.threshold_equity == pytest.approx(481.44)
    assert projection.stop_out.threshold_equity == pytest.approx(240.72)


def test_a_broker_quoting_money_levels_is_read_in_money() -> None:
    account = fixtures.account(
        margin_so_mode=1, margin_so_call=500.0, margin_so_so=250.0
    )
    projection = margin_projection(account, 1.0, NOW)
    assert projection.mode is StopoutMode.MONEY
    assert projection.call is not None
    assert projection.call.threshold_equity == pytest.approx(500.0)


def test_an_unrecognised_margin_mode_refuses_rather_than_assuming_percent() -> None:
    projection = margin_projection(fixtures.account(margin_so_mode=7), 1.0, NOW)
    assert projection.mode is None
    assert projection.call is None
    assert projection.stop_out is None
    codes = {r.code for r in projection.refusals}
    assert RefusalCode.MARGIN_MODE_UNSUPPORTED in codes
    reason = next(
        r.reason
        for r in projection.refusals
        if r.code is RefusalCode.MARGIN_MODE_UNSUPPORTED
    )
    assert "orders of magnitude" in reason


def test_days_to_a_level_is_headroom_divided_by_daily_financing() -> None:
    # Equity 4,637.20, stop-out at 240.72, headroom 4,396.48, at 100 a day.
    projection = margin_projection(fixtures.account(), 100.0, NOW)
    assert projection.stop_out is not None
    assert projection.stop_out.headroom == pytest.approx(4_396.48)
    assert projection.stop_out.days_to_reach == pytest.approx(43.9648)
    assert projection.stop_out.date_reached is not None
    assert projection.stop_out.date_reached > NOW


def test_the_stop_out_is_always_further_away_than_the_call() -> None:
    projection = margin_projection(fixtures.account(), 100.0, NOW)
    assert projection.call is not None
    assert projection.stop_out is not None
    assert projection.call.days_to_reach is not None
    assert projection.stop_out.days_to_reach is not None
    assert projection.stop_out.days_to_reach > projection.call.days_to_reach


def test_an_account_already_past_a_level_says_so_instead_of_projecting() -> None:
    projection = margin_projection(fixtures.account(equity=200.0), 100.0, NOW)
    assert projection.stop_out is not None
    assert projection.stop_out.already_breached
    assert projection.stop_out.days_to_reach is None


def test_with_no_financing_rate_the_levels_are_located_but_have_no_time_axis() -> None:
    projection = margin_projection(fixtures.account(), None, NOW)
    assert projection.stop_out is not None
    assert projection.stop_out.threshold_equity == pytest.approx(240.72)
    assert projection.stop_out.days_to_reach is None
    assert RefusalCode.NO_CARRY_RATE in {r.code for r in projection.refusals}


def test_a_net_credit_does_not_project_an_account_toward_a_stop_out() -> None:
    projection = margin_projection(fixtures.account(), -5.0, NOW)
    assert projection.stop_out is not None
    assert projection.stop_out.days_to_reach is None


def test_a_flat_account_has_no_margin_level_and_refuses_to_invent_one() -> None:
    projection = margin_projection(fixtures.account(margin=0.0), 1.0, NOW)
    assert projection.margin_level_pct is None
    assert projection.call is None
    assert RefusalCode.NO_MARGIN_IN_USE in {r.code for r in projection.refusals}


def test_the_constant_price_assumption_travels_with_the_number() -> None:
    assert margin_projection(fixtures.account(), 1.0, NOW).price_is_held_constant
