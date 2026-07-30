"""Swap normalisation, and the measured-versus-registered finding.

Two groups of tests matter most here.

**The FxPro measurement**, 2026-07-29: ``swap_mode = 2``, long -67.9, short
+27.0. The refusal is the finding, and
``test_a_base_currency_swap_is_refused_and_the_refusal_names_the_structure``
pins it -- a base-currency rate makes the account-currency charge a function of
the gold price, which no fixed points constant can represent.

**The correction.** An earlier version of this file asserted that a broker
charging 15 points a night would already exceed the registry, because the
registered model was said to charge five nights a week against a broker's seven.
It charges seven. ``test_the_two_bases_agree_because_the_night_counts_agree``
replaces that claim, and ``tests/risk/test_clock.py`` measures the night count
against the real function rather than believing a name.
"""

from typing import Final

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


def test_the_registered_weekly_figure_counts_seven_nights() -> None:
    assert (
        pytest.approx(SWAP_LONG_POINTS_PER_LOT_PER_NIGHT * 7.0)
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
        (2, "BASE currency"),
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


def test_the_two_bases_agree_because_the_night_counts_agree() -> None:
    # The correction. A rate below the registered one is below it on BOTH the
    # nightly and the weekly basis, because both count seven nights a week.
    # The earlier version of this test asserted the opposite.
    declared = _declared(swap_long=-15.0)
    assert declared.charge_long_points < REGISTERED_LONG_POINTS

    finding = swap_divergence("XAUUSD", declared, {}, 0.10)
    weekly_long = next(
        c for c in finding.comparisons if c.side == "long" and c.source == "declared"
    )
    assert weekly_long.broker_points == pytest.approx(105.0)
    assert weekly_long.registered_points == pytest.approx(140.0)
    assert not weekly_long.exceeds
    # And the weekly ratio equals the nightly ratio exactly -- the weekly basis
    # is a restatement in readable units, not an independent finding.
    assert weekly_long.ratio == pytest.approx(15.0 / REGISTERED_LONG_POINTS)


def test_the_notes_state_that_the_night_counts_agree() -> None:
    finding = swap_divergence("XAUUSD", _declared(), {}, 0.10)
    assert any("registered night COUNT is right" in n for n in finding.notes)


def test_the_declared_route_is_compared_exactly_with_no_tolerance() -> None:
    # One thousandth of a point a night over the line. A tolerance would
    # swallow it; the declared figure carries no noise, so nothing should.
    finding = swap_divergence(
        "XAUUSD", _declared(swap_long=-(REGISTERED_LONG_POINTS + 0.001)), {}, 0.50
    )
    assert finding.verdict is SwapVerdict.REGISTERED_IS_OPTIMISTIC


def test_the_measured_route_gets_the_configured_tolerance() -> None:
    # Registered weekly long is 140 points; 21 a day is 147 a week, 5% over.
    inside = swap_divergence("XAUUSD", _declared(swap_long=-1.0), {"long": 21.0}, 0.10)
    measured = next(c for c in inside.comparisons if c.source == "measured")
    assert measured.broker_points == pytest.approx(147.0)
    assert not measured.exceeds

    outside = swap_divergence("XAUUSD", _declared(swap_long=-1.0), {"long": 21.0}, 0.01)
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


def test_the_timing_mismatch_is_stated_without_being_called_an_undercount() -> None:
    finding = swap_divergence("XAUUSD", _declared(), {}, 0.10)
    timing = next(n for n in finding.notes if "when they land" in n)
    assert "cancels over" in timing
    assert "night COUNT is right" in timing


def test_the_finding_names_the_symbol_it_is_about() -> None:
    finding = swap_divergence("GOLD.spot", _declared(), {}, 0.10)
    assert finding.symbol == "GOLD.spot"


# --------------------------------------------------------------------------
# What the probe measured on FxPro GOLD, 2026-07-29
# --------------------------------------------------------------------------

#: Exactly what `scripts/risk_monitor.py --probe` read off the terminal.
FXPRO_GOLD: Final = {"swap_mode": 2, "swap_long": -67.9, "swap_short": 27.0}


def test_a_base_currency_swap_is_refused_and_the_refusal_names_the_structure() -> None:
    result = declared_swap(fixtures.gold(**FXPRO_GOLD), "USD")
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.SWAP_MODE_UNSUPPORTED
    # Not merely "cannot convert" -- the reason has to say what the structure
    # is, because the structure is the finding.
    assert "BASE currency" in result.reason
    assert "proportional to the gold price" in result.reason
    assert "-67.9" in result.reason


def test_a_price_dependent_mode_bears_on_the_registry_on_structure_alone() -> None:
    # No magnitude comparison is possible -- the declared route is refused and
    # no position has been held. It still bears on the registry, because a
    # fixed points substitute is wrong in kind: no value of it would be right.
    refusal = declared_swap(fixtures.gold(**FXPRO_GOLD), "USD")
    finding = swap_divergence("GOLD", refusal, {}, 0.10, mode=SwapMode.CURRENCY_SYMBOL)
    assert finding.verdict is SwapVerdict.UNAVAILABLE
    assert finding.mode_is_price_dependent
    assert finding.bears_on_the_registry
    assert any("FUNCTION OF PRICE" in n for n in finding.notes)
    assert any("wrong in kind" in n for n in finding.notes)


def test_a_fixed_currency_mode_is_not_price_dependent() -> None:
    for mode in (SwapMode.POINTS, SwapMode.CURRENCY_DEPOSIT, SwapMode.CURRENCY_MARGIN):
        assert not mode.is_price_dependent
    for mode in (
        SwapMode.CURRENCY_SYMBOL,
        SwapMode.INTEREST_CURRENT,
        SwapMode.INTEREST_OPEN,
        SwapMode.REOPEN_CURRENT,
        SwapMode.REOPEN_BID,
    ):
        assert mode.is_price_dependent


def test_a_conservative_broker_on_a_fixed_mode_does_not_bear_on_the_registry() -> None:
    finding = swap_divergence("XAUUSD", _declared(swap_long=-10.0), {}, 0.10)
    assert not finding.mode_is_price_dependent
    assert not finding.bears_on_the_registry


# --------------------------------------------------------------------------
# The annualised basis -- the only one a price-dependent swap leaves invariant
# --------------------------------------------------------------------------


def test_the_annualised_basis_turns_points_into_a_rate() -> None:
    # 20 points a night at 1.00 a point is 20/night; over 365 nights that is
    # 7,300 against a notional of 100 oz x 2,400 = 240,000, or 3.04%.
    finding = swap_divergence(
        "XAUUSD",
        _declared(swap_long=-20.0),
        {},
        0.10,
        currency_per_point=1.0,
        notional_per_lot=240_000.0,
    )
    long_side = next(c for c in finding.comparisons if c.side == "long")
    assert long_side.registered_annual_pct == pytest.approx(3.0417, abs=1e-3)
    assert long_side.broker_annual_pct == pytest.approx(3.0417, abs=1e-3)


def test_the_measured_fxpro_magnitude_annualises_to_a_plausible_rate() -> None:
    # 67.9 a night on a 240,000 notional is 10.33% a year. The registered 20 is
    # 3.04%, which is below any dollar funding rate in the evaluation window --
    # that gap is the evidence for how the mode-2 figures should be read.
    finding = swap_divergence(
        "XAUUSD",
        _declared(swap_long=-67.9),
        {},
        0.10,
        currency_per_point=1.0,
        notional_per_lot=240_000.0,
    )
    long_side = next(c for c in finding.comparisons if c.side == "long")
    assert long_side.broker_annual_pct == pytest.approx(10.325, abs=1e-2)
    assert long_side.exceeds
    assert long_side.ratio == pytest.approx(67.9 / 20.0)


def test_without_a_price_the_annualised_basis_is_omitted_not_guessed() -> None:
    finding = swap_divergence("XAUUSD", _declared(), {}, 0.10)
    assert all(c.registered_annual_pct is None for c in finding.comparisons)
    assert all(c.broker_annual_pct is None for c in finding.comparisons)
