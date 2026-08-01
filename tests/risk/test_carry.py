"""Financing on an open position: what was paid, and what will be."""

from datetime import UTC, datetime, timedelta

import pytest

from risk.carry import (
    CarrySource,
    PositionCarry,
    carry_paid,
    portfolio_carry,
    position_carry,
)
from risk.clock import RolloverClock
from risk.refusal import Refusal, RefusalCode
from risk.state import PositionDirection, PositionState, SymbolTerms
from risk.swap import DeclaredSwap, declared_swap
from tests.risk import fixtures

CLOCK = RolloverClock(fixtures.SERVER_OFFSET_HOURS)
HORIZONS = (7.0, 30.0, 60.0, 90.0)
TERMS = fixtures.gold()
EQUITY = fixtures.account().equity


def _declared(**overrides: float | int | str) -> DeclaredSwap:
    result = declared_swap(fixtures.gold(**overrides), "USD")
    assert isinstance(result, DeclaredSwap)
    return result


def _carry(
    position: PositionState | None = None,
    *,
    terms: SymbolTerms | None = TERMS,
    declared: DeclaredSwap | Refusal | None = None,
    clock: RolloverClock | None = CLOCK,
    minimum_days: float = 1.0,
) -> PositionCarry:
    return position_carry(
        position=position or fixtures.position(),
        terms=terms,
        declared=_declared() if declared is None else declared,
        now=fixtures.NOW,
        equity=EQUITY,
        clock=clock,
        horizons=HORIZONS,
        minimum_days_for_measured_rate=minimum_days,
    )


# --------------------------------------------------------------------------
# The sign flip happens once
# --------------------------------------------------------------------------


def test_a_negative_broker_swap_is_a_positive_charge() -> None:
    assert carry_paid(fixtures.position(swap=-2.0)) == pytest.approx(2.0)


def test_a_positive_broker_swap_is_a_credit() -> None:
    assert carry_paid(fixtures.position(swap=7.5)) == pytest.approx(-7.5)


# --------------------------------------------------------------------------
# The measured half
# --------------------------------------------------------------------------


def test_the_age_of_a_position_is_measured_in_hours_and_days() -> None:
    carry = _carry()
    assert carry.hours_open == pytest.approx(48.0)
    assert carry.days_open == pytest.approx(2.0)


def test_nights_held_counts_server_midnights_not_utc_ones() -> None:
    assert _carry().nights_held == 2


def test_without_a_server_clock_the_night_count_is_refused_not_guessed() -> None:
    carry = _carry(clock=None)
    assert carry.nights_held is None
    assert any(r.code is RefusalCode.NO_SERVER_CLOCK for r in carry.refusals)
    # The financing figures do not depend on it and are still there.
    assert carry.carry_paid == pytest.approx(2.0)


def test_the_break_even_move_is_the_charge_divided_by_the_point_value() -> None:
    carry = _carry()
    # 2.00 paid on 0.10 lots at 1.00 a point is 20 points.
    assert carry.breakeven_points == pytest.approx(20.0)
    assert carry.breakeven_price == pytest.approx(2_411.55)
    assert carry.breakeven_pct == pytest.approx(0.008294, abs=1e-6)


def test_a_short_pays_off_its_financing_by_moving_down() -> None:
    carry = _carry(fixtures.position(direction=PositionDirection.SHORT, swap=-2.0))
    assert carry.breakeven_price == pytest.approx(2_411.15)


def test_financing_is_reported_against_equity() -> None:
    carry = _carry()
    assert carry.carry_pct_of_equity == pytest.approx(100.0 * 2.0 / EQUITY)


# --------------------------------------------------------------------------
# The forward rate, and how it is chosen
# --------------------------------------------------------------------------


def test_the_published_rate_is_used_when_the_two_agree() -> None:
    carry = _carry()
    assert carry.rate_declared_per_day == pytest.approx(1.0)
    assert carry.rate_measured_per_day == pytest.approx(1.0)
    assert carry.rate_source is CarrySource.DECLARED


def test_the_more_expensive_route_wins_when_they_disagree() -> None:
    # Charged 8.00 over two days against a published 1.00 a day.
    carry = _carry(fixtures.position(swap=-8.0))
    assert carry.rate_measured_per_day == pytest.approx(4.0)
    assert carry.rate_per_day == pytest.approx(4.0)
    assert carry.rate_source is CarrySource.MORE_ADVERSE_OF_BOTH
    assert any("more expensive" in n for n in carry.notes)


def test_a_cheaper_measured_rate_does_not_displace_the_published_one() -> None:
    carry = _carry(fixtures.position(swap=-0.5))
    assert carry.rate_per_day == pytest.approx(1.0)
    assert carry.rate_source is CarrySource.DECLARED


def test_a_position_too_young_to_have_rolled_gets_no_measured_rate() -> None:
    young = fixtures.position(opened_at=fixtures.NOW - timedelta(hours=4), swap=0.0)
    carry = _carry(young)
    assert carry.rate_measured_per_day is None
    assert any(r.code is RefusalCode.CARRY_TOO_YOUNG for r in carry.refusals)


def test_zero_charged_over_a_long_hold_is_ambiguous_and_is_refused() -> None:
    carry = _carry(fixtures.position(swap=0.0))
    assert carry.rate_measured_per_day is None
    refusal = next(r for r in carry.refusals if r.code is RefusalCode.CARRY_TOO_YOUNG)
    assert "swap-free" in refusal.reason
    assert "rollover" in refusal.reason


def test_with_no_published_rate_the_measured_one_carries_the_projection() -> None:
    refusal = declared_swap(fixtures.gold(swap_mode=7), "USD")
    carry = _carry(declared=refusal)
    assert carry.rate_declared_per_day is None
    assert carry.rate_source is CarrySource.MEASURED


def test_with_neither_route_nothing_is_projected_and_it_says_so() -> None:
    refusal = declared_swap(fixtures.gold(swap_mode=7), "USD")
    carry = _carry(fixtures.position(swap=0.0), declared=refusal)
    assert carry.rate_per_day is None
    assert carry.rate_source is CarrySource.NONE
    assert any(r.code is RefusalCode.NO_CARRY_RATE for r in carry.refusals)
    assert all(p.additional == 0.0 for p in carry.projections)


def test_missing_symbol_terms_refuse_rather_than_defaulting_a_point_value() -> None:
    carry = _carry(terms=None)
    assert any(r.code is RefusalCode.SYMBOL_TERMS_MISSING for r in carry.refusals)
    assert carry.breakeven_points is None


def test_an_unusable_tick_value_refuses_rather_than_defaulting() -> None:
    carry = _carry(terms=fixtures.gold(trade_tick_value=0.0))
    assert any(r.code is RefusalCode.NO_POINT_VALUE for r in carry.refusals)


# --------------------------------------------------------------------------
# Projections
# --------------------------------------------------------------------------


def test_a_projection_compounds_the_charge_already_paid() -> None:
    carry = _carry()
    week = next(p for p in carry.projections if p.horizon_days == 7.0)
    assert week.additional == pytest.approx(7.0)
    assert week.cumulative == pytest.approx(9.0)
    assert week.breakeven_points == pytest.approx(90.0)


def test_the_two_month_horizon_is_the_shape_that_emptied_the_account() -> None:
    carry = _carry()
    two_months = next(p for p in carry.projections if p.horizon_days == 60.0)
    assert two_months.cumulative == pytest.approx(62.0)
    assert two_months.breakeven_points == pytest.approx(620.0)


def test_every_configured_horizon_appears_exactly_once() -> None:
    carry = _carry()
    assert tuple(p.horizon_days for p in carry.projections) == HORIZONS


# --------------------------------------------------------------------------
# The book
# --------------------------------------------------------------------------


def test_the_book_rate_is_the_sum_of_the_positions_that_have_one() -> None:
    positions = (
        fixtures.position(ticket=1),
        fixtures.position(ticket=2, volume=0.20, swap=-4.0),
    )
    carries = tuple(_carry(p) for p in positions)
    book = portfolio_carry(
        carries,
        positions,
        {"XAUUSD": TERMS},
        EQUITY,
        fixtures.NOW,
    )
    assert book.paid_total == pytest.approx(6.0)
    assert book.rate_per_day == pytest.approx(3.0)
    assert not book.rate_is_partial


def test_a_position_without_a_rate_marks_the_book_figure_as_partial() -> None:
    positions = (fixtures.position(ticket=1), fixtures.position(ticket=2, swap=0.0))
    refusal = declared_swap(fixtures.gold(swap_mode=7), "USD")
    carries = (
        _carry(positions[0]),
        _carry(positions[1], declared=refusal),
    )
    book = portfolio_carry(
        carries,
        positions,
        {"XAUUSD": TERMS},
        EQUITY,
        fixtures.NOW,
    )
    assert book.rate_is_partial


def test_financing_alone_has_a_date_on_which_it_consumes_the_account() -> None:
    positions = (fixtures.position(),)
    carries = (_carry(),)
    book = portfolio_carry(
        carries,
        positions,
        {"XAUUSD": TERMS},
        EQUITY,
        fixtures.NOW,
    )
    assert book.days_until_carry_consumes_equity == pytest.approx(EQUITY / 1.0)
    assert book.date_carry_consumes_equity is not None
    assert book.date_carry_consumes_equity > fixtures.NOW


def test_the_measured_rate_is_reduced_to_points_per_lot_for_the_comparison() -> None:
    positions = (fixtures.position(),)
    book = portfolio_carry(
        (_carry(),),
        positions,
        {"XAUUSD": TERMS},
        EQUITY,
        fixtures.NOW,
    )
    # 1.00 a day on 0.10 lots at 1.00 a point is 10 points per lot per day.
    assert book.per_lot_per_day_points == {"XAUUSD": {"long": pytest.approx(10.0)}}


def test_two_symbols_are_kept_apart_rather_than_pooled() -> None:
    silver = fixtures.gold(name="XAGUSD")
    positions = (
        fixtures.position(ticket=1),
        fixtures.position(ticket=2, symbol="XAGUSD", swap=-4.0),
    )
    carries = (
        _carry(positions[0]),
        _carry(positions[1], terms=silver),
    )
    book = portfolio_carry(
        carries,
        positions,
        {"XAUUSD": TERMS, "XAGUSD": silver},
        EQUITY,
        fixtures.NOW,
    )
    assert set(book.per_lot_per_day_points) == {"XAUUSD", "XAGUSD"}
    assert book.per_lot_per_day_points["XAGUSD"]["long"] == pytest.approx(20.0)


def test_a_credited_position_is_labelled_as_a_credit() -> None:
    carry = _carry(fixtures.position(swap=4.0))
    assert carry.carry_is_credit
    assert carry.carry_paid == pytest.approx(-4.0)


def test_a_position_opened_in_the_future_is_not_silently_aged() -> None:
    # A terminal whose clock disagrees with this machine's produces this.
    ahead = fixtures.position(opened_at=fixtures.NOW + timedelta(hours=2))
    carry = _carry(ahead)
    assert carry.hours_open == pytest.approx(-2.0)
    assert carry.nights_held == 0


def test_a_naive_open_timestamp_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        fixtures.position(opened_at=datetime(2026, 7, 27, 14, 30))


def test_a_position_with_no_volume_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="volume must be positive"):
        fixtures.position(volume=0.0)


def test_the_utc_requirement_applies_to_deals_too() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        fixtures.deal(closed_at=datetime(2026, 7, 29, 9, 15))


def test_a_deal_sums_every_cost_component_not_just_profit() -> None:
    assert fixtures.deal().realised == pytest.approx(-88.60)


def test_the_reading_time_is_the_only_clock_anything_here_reads() -> None:
    # Same inputs, a different "now", a different age -- and nothing else in
    # the result depends on the machine's own clock.
    later = position_carry(
        position=fixtures.position(),
        terms=TERMS,
        declared=_declared(),
        now=fixtures.NOW + timedelta(days=1),
        equity=EQUITY,
        clock=CLOCK,
        horizons=HORIZONS,
        minimum_days_for_measured_rate=1.0,
    )
    assert later.days_open == pytest.approx(3.0)
    assert later.opened_at == datetime(2026, 7, 27, 14, 30, tzinfo=UTC)


# --------------------------------------------------------------------------
# Two measured denominators
# --------------------------------------------------------------------------


def test_the_measured_charge_is_reported_per_night_as_well_as_per_day() -> None:
    # The default fixture is exactly two days old and crosses two midnights, so
    # the two bases coincide and the arithmetic is checkable by hand.
    carry = _carry()
    assert carry.days_open == pytest.approx(2.0)
    assert carry.nights_held == 2
    assert carry.rate_measured_per_day == pytest.approx(1.0)
    assert carry.rate_measured_per_night == pytest.approx(1.0)


def test_a_sub_week_hold_separates_the_two_denominators() -> None:
    # `[MEASURED]` the 2026-08-01 reading: 13.58 charged on 0.10 lots over
    # 44.769 hours, two midnights crossed. Per calendar day it is 7.28; per
    # night it is 6.79. Neither number is wrong and they are not the same
    # quantity.
    position = fixtures.position(
        opened_at=fixtures.NOW - timedelta(hours=44.769), swap=-13.58
    )
    carry = _carry(position)
    assert carry.nights_held == 2
    assert carry.rate_measured_per_day == pytest.approx(7.2800, abs=1e-4)
    assert carry.rate_measured_per_night == pytest.approx(6.79)
    note = next(n for n in carry.notes if "two measured bases disagree" in n)
    assert "schedule, not a rate change" in note
    assert "per-night figure is the one to compare" in note


def test_agreeing_denominators_raise_no_note() -> None:
    assert not any("two measured bases disagree" in n for n in _carry().notes)


def test_without_a_server_clock_there_is_no_per_night_figure_to_guess_at() -> None:
    carry = _carry(clock=None)
    assert carry.nights_held is None
    assert carry.rate_measured_per_day is not None
    assert carry.rate_measured_per_night is None


def test_the_book_reports_both_bases_for_the_registry_comparison() -> None:
    position = fixtures.position(
        opened_at=fixtures.NOW - timedelta(hours=44.769), swap=-13.58
    )
    carry = _carry(position)
    book = portfolio_carry(
        (carry,), (position,), {"XAUUSD": TERMS}, EQUITY, fixtures.NOW
    )
    assert book.per_lot_per_day_points["XAUUSD"]["long"] == pytest.approx(
        72.800, abs=1e-3
    )
    assert book.per_lot_per_night_points["XAUUSD"]["long"] == pytest.approx(67.9)


def test_a_book_with_no_clock_reports_no_nightly_basis_rather_than_a_wrong_one() -> (
    None
):
    position = fixtures.position()
    carry = _carry(position, clock=None)
    book = portfolio_carry(
        (carry,), (position,), {"XAUUSD": TERMS}, EQUITY, fixtures.NOW
    )
    assert book.per_lot_per_day_points["XAUUSD"]["long"] == pytest.approx(10.0)
    assert book.per_lot_per_night_points == {}
