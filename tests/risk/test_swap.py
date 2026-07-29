"""Swap normalisation, and the measured-versus-registered finding.

The load-bearing test in this file is
``test_a_nightly_rate_below_the_registered_one_can_still_exceed_it_over_a_week``.
It is the reason the comparison is reported on a weekly basis at all: a broker
charging 15 points a night looks conservative against the registered 20 and is
not, because the registered model has no triple-swap concept and charges five
nights a week where the broker charges seven.
"""

import pytest

from backtest.costs import (
    SWAP_LONG_POINTS_PER_LOT_PER_NIGHT,
    SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT,
)
from risk.refusal import Refusal, RefusalCode
from risk.swap import (
    REGISTERED_LONG_POINTS,
    REGISTERED_SHORT_POINTS,
    REGISTERED_WEEKLY_LONG_POINTS,
    DeclaredSwap,
    SwapMode,
    SwapVerdict,
    declared_swap,
    swap_divergence,
)
from tests.risk import fixtures


def _declared(**overrides: float | int | str) -> DeclaredSwap:
    result = declared_swap(fixtures.gold(**overrides), "USD")
    assert isinstance(result, DeclaredSwap)
    return result


# --------------------------------------------------------------------------
# The registered constants are read, not restated
# --------------------------------------------------------------------------


def test_the_registered_figures_track_the_cost_model_rather_than_a_copy() -> None:
    assert REGISTERED_LONG_POINTS == SWAP_LONG_POINTS_PER_LOT_PER_NIGHT
    assert REGISTERED_SHORT_POINTS == SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT


def test_the_registered_weekly_figure_counts_five_rollovers() -> None:
    assert (
        pytest.approx(SWAP_LONG_POINTS_PER_LOT_PER_NIGHT * 5.0)
        == REGISTERED_WEEKLY_LONG_POINTS
    )


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


def test_the_brokers_sign_is_flipped_into_charge_terms() -> None:
    declared = _declared(swap_long=-10.0, swap_short=2.0)
    assert declared.charge_long_points == pytest.approx(10.0)
    assert declared.charge_short_points == pytest.approx(-2.0)
    assert declared.short_is_credited
    assert not declared.long_is_credited


def test_a_currency_quoted_swap_converts_through_the_point_value() -> None:
    # 1.00 of deposit currency per lot per night, at 1.00 per point, is 1 point.
    declared = _declared(swap_mode=4, swap_long=-1.0, swap_short=-0.5)
    assert declared.mode is SwapMode.CURRENCY_DEPOSIT
    assert declared.charge_long_points == pytest.approx(1.0)
    assert declared.charge_short_points == pytest.approx(0.5)


def test_a_disabled_swap_normalises_to_zero_on_both_sides() -> None:
    declared = _declared(swap_mode=0, swap_long=-99.0, swap_short=99.0)
    assert declared.charge_long_points == 0.0
    assert declared.charge_short_points == 0.0


def test_a_margin_currency_swap_is_accepted_when_it_is_the_deposit_currency() -> None:
    declared = _declared(swap_mode=3, currency_margin="USD", swap_long=-2.0)
    assert declared.charge_long_points == pytest.approx(2.0)


# --------------------------------------------------------------------------
# Refusals -- the adversarial half
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "fragment"),
    [
        (2, "base currency"),
        (5, "annual interest"),
        (6, "annual interest"),
        (7, "closing and reopening"),
        (8, "closing and reopening"),
    ],
)
def test_an_uninterpretable_swap_mode_refuses_and_names_the_missing_input(
    mode: int, fragment: str
) -> None:
    result = declared_swap(fixtures.gold(swap_mode=mode), "USD")
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.SWAP_MODE_UNSUPPORTED
    assert fragment in result.reason


def test_an_undocumented_swap_mode_refuses_rather_than_falling_back() -> None:
    result = declared_swap(fixtures.gold(swap_mode=99), "USD")
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.SWAP_MODE_UNSUPPORTED
    assert "99" in result.reason


def test_a_foreign_margin_currency_refuses_rather_than_assuming_parity() -> None:
    result = declared_swap(fixtures.gold(swap_mode=3, currency_margin="EUR"), "USD")
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.SWAP_CURRENCY_MISMATCH


def test_a_currency_swap_without_a_point_value_refuses() -> None:
    result = declared_swap(fixtures.gold(swap_mode=4, trade_tick_value=0.0), "USD")
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.NO_POINT_VALUE


# --------------------------------------------------------------------------
# The divergence finding
# --------------------------------------------------------------------------


def test_a_cheap_broker_leaves_the_registered_figure_conservative() -> None:
    finding = swap_divergence("XAUUSD", _declared(swap_long=-10.0), {}, 0.10)
    assert finding.verdict is SwapVerdict.REGISTERED_IS_CONSERVATIVE
    assert not finding.bears_on_the_registry
    assert all(not c.exceeds for c in finding.comparisons)


def test_an_expensive_broker_calls_the_registry_into_question() -> None:
    finding = swap_divergence("XAUUSD", _declared(swap_long=-30.0), {}, 0.10)
    assert finding.verdict is SwapVerdict.REGISTERED_IS_OPTIMISTIC
    assert finding.bears_on_the_registry
    assert "HYPOTHESES.md" in finding.notes[0]


def test_a_nightly_rate_below_the_registered_one_can_still_exceed_it_over_a_week() -> (
    None
):
    # 15 < 20 a night. But 7 x 15 = 105 > 5 x 20 = 100 over a week, because
    # the registered model charges five rollovers and has no triple swap.
    declared = _declared(swap_long=-15.0)
    assert declared.charge_long_points < REGISTERED_LONG_POINTS

    finding = swap_divergence("XAUUSD", declared, {}, 0.10)
    assert finding.verdict is SwapVerdict.REGISTERED_IS_OPTIMISTIC
    weekly_long = next(
        c for c in finding.comparisons if c.side == "long" and c.source == "declared"
    )
    assert weekly_long.broker_points == pytest.approx(105.0)
    assert weekly_long.registered_points == pytest.approx(100.0)
    assert weekly_long.exceeds


def test_the_declared_route_is_compared_exactly_with_no_tolerance() -> None:
    # One tenth of a point a night over the line. A tolerance would swallow it.
    over = REGISTERED_LONG_POINTS * 5.0 / 7.0 + 0.001
    finding = swap_divergence("XAUUSD", _declared(swap_long=-over), {}, 0.50)
    assert finding.verdict is SwapVerdict.REGISTERED_IS_OPTIMISTIC


def test_the_measured_route_gets_the_configured_tolerance() -> None:
    # Registered weekly long is 100 points; 15 a day is 105 a week, 5% over.
    inside = swap_divergence("XAUUSD", _declared(swap_long=-1.0), {"long": 15.0}, 0.10)
    measured = next(c for c in inside.comparisons if c.source == "measured")
    assert measured.broker_points == pytest.approx(105.0)
    assert not measured.exceeds

    outside = swap_divergence("XAUUSD", _declared(swap_long=-1.0), {"long": 15.0}, 0.01)
    assert any(c.exceeds for c in outside.comparisons if c.source == "measured")


def test_a_short_credit_is_reported_rather_than_netted_away() -> None:
    finding = swap_divergence("XAUUSD", _declared(swap_short=5.0), {}, 0.10)
    assert finding.short_is_credited
    assert any("CREDITS the short side" in n for n in finding.notes)


def test_nothing_measurable_is_unavailable_and_not_agreement() -> None:
    refusal = declared_swap(fixtures.gold(swap_mode=7), "USD")
    finding = swap_divergence("XAUUSD", refusal, {}, 0.10)
    assert finding.verdict is SwapVerdict.UNAVAILABLE
    assert not finding.bears_on_the_registry
    assert finding.comparisons == ()


def test_the_triple_swap_gap_is_always_stated_when_a_comparison_was_made() -> None:
    finding = swap_divergence("XAUUSD", _declared(), {}, 0.10)
    assert any("triple-swap concept" in n for n in finding.notes)


def test_the_finding_names_the_symbol_it_is_about() -> None:
    finding = swap_divergence("GOLD.spot", _declared(), {}, 0.10)
    assert finding.symbol == "GOLD.spot"
