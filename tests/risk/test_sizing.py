"""Position sizing: a risk budget, a volatility-scaled stop, and the spread."""

import pytest

from backtest.costs import SPREAD_FLOOR_POINTS
from risk.refusal import Refusal, RefusalCode
from risk.sizing import SizingResult, round_down_to_step, size_position
from risk.state import SymbolTerms
from tests.risk import fixtures

EQUITY = 4_637.20
ATR_POINTS = 500.0
K = 1.5


def _size(
    *,
    equity: float = EQUITY,
    risk_pct: float = 1.0,
    atr_points: float = ATR_POINTS,
    terms: SymbolTerms | None = None,
    stop_multiple: float = K,
    spread_points: float | None = None,
    reference_price: float | None = None,
) -> SizingResult | Refusal:
    return size_position(
        equity=equity,
        risk_pct=risk_pct,
        atr_points=atr_points,
        terms=terms if terms is not None else fixtures.gold(),
        stop_multiple=stop_multiple,
        spread_points=spread_points,
        reference_price=reference_price,
    )


def _ok(**overrides: float | SymbolTerms | None) -> SizingResult:
    result = _size(**overrides)  # type: ignore[arg-type]
    assert isinstance(result, SizingResult)
    return result


# --------------------------------------------------------------------------
# The arithmetic, checkable by hand
# --------------------------------------------------------------------------


def test_the_size_spends_the_budget_over_the_full_adverse_excursion() -> None:
    result = _ok()
    assert result.risk_budget == pytest.approx(46.372)
    assert result.stop_distance_points == pytest.approx(750.0)
    assert result.spread_points == pytest.approx(32.0)
    assert result.adverse_points == pytest.approx(782.0)
    assert result.risk_per_lot == pytest.approx(782.0)
    assert result.lots_unrounded == pytest.approx(46.372 / 782.0)
    assert result.lots == pytest.approx(0.05)


def test_rounding_is_down_so_the_budget_is_never_exceeded() -> None:
    result = _ok()
    assert result.lots <= result.lots_unrounded
    assert result.risk_at_this_size <= result.risk_budget


def test_the_spread_is_inside_the_risk_and_not_outside_it() -> None:
    with_spread = _ok()
    without = _ok(spread_points=0.0)
    assert without.adverse_points < with_spread.adverse_points
    assert without.lots_unrounded > with_spread.lots_unrounded


def test_the_live_quote_is_used_and_not_the_registered_research_floor() -> None:
    result = _ok()
    assert result.spread_points == fixtures.gold().spread_points
    assert result.spread_points != SPREAD_FLOOR_POINTS


def test_the_exposure_to_a_wider_fill_spread_is_a_number_not_a_caveat() -> None:
    result = _ok()
    # Each extra point of spread at fill costs lots x value-per-point.
    assert result.risk_per_extra_spread_point == pytest.approx(
        result.lots * result.value_per_point_per_lot
    )


def test_a_larger_stop_multiple_buys_a_smaller_position() -> None:
    assert _ok(stop_multiple=3.0).lots < _ok(stop_multiple=1.5).lots


def test_a_quieter_market_buys_a_larger_position_at_the_same_risk() -> None:
    assert _ok(atr_points=250.0).lots > _ok(atr_points=500.0).lots


def test_the_stop_prices_sit_the_stop_distance_either_side_of_the_entry() -> None:
    result = _ok(reference_price=2_400.00)
    assert result.stop_price_long == pytest.approx(2_392.50)
    assert result.stop_price_short == pytest.approx(2_407.50)


def test_omitting_the_entry_price_omits_only_the_stop_prices() -> None:
    result = _ok()
    assert result.stop_price_long is None
    assert result.lots > 0


# --------------------------------------------------------------------------
# Rounding
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("volume", "step", "expected"),
    [
        (0.0593, 0.01, 0.05),
        (0.10, 0.01, 0.10),
        (0.999, 0.1, 0.9),
        (1.0, 0.1, 1.0),
        (0.009, 0.01, 0.0),
    ],
)
def test_rounding_down_lands_on_a_tradeable_increment(
    volume: float, step: float, expected: float
) -> None:
    assert round_down_to_step(volume, step) == pytest.approx(expected)


def test_an_exact_multiple_is_not_dropped_by_a_representation_error() -> None:
    # 0.07 / 0.01 is 6.999999999999999 in binary floating point.
    assert round_down_to_step(0.07, 0.01) == pytest.approx(0.07)
    assert round_down_to_step(0.29, 0.01) == pytest.approx(0.29)


def test_a_zero_step_is_refused_rather_than_dividing_by_it() -> None:
    with pytest.raises(ValueError, match="volume_step must be positive"):
        round_down_to_step(1.0, 0.0)


# --------------------------------------------------------------------------
# Refusals -- the adversarial half
# --------------------------------------------------------------------------


def test_a_trade_that_does_not_fit_the_account_is_refused_not_rounded_up() -> None:
    result = _size(equity=50.0)
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.SIZE_BELOW_MINIMUM
    # The refusal states what taking the minimum anyway would have risked.
    assert "% of equity" in result.reason


def test_zero_volatility_is_refused_rather_than_read_as_zero_risk() -> None:
    result = _size(atr_points=0.0)
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.NO_VOLATILITY
    assert "not that risk is zero" in result.reason


def test_an_unusable_tick_value_refuses_rather_than_defaulting() -> None:
    result = _size(terms=fixtures.gold(trade_tick_value=0.0))
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.NO_POINT_VALUE


def test_a_broker_with_no_volume_step_is_refused() -> None:
    result = _size(terms=fixtures.gold(volume_step=0.0))
    assert isinstance(result, Refusal)
    assert result.code is RefusalCode.NO_VOLUME_STEP


def test_a_negative_spread_quote_is_refused() -> None:
    result = _size(spread_points=-1.0)
    assert isinstance(result, Refusal)


def test_the_brokers_maximum_volume_caps_the_size_and_says_so() -> None:
    result = _ok(equity=50_000_000.0, terms=fixtures.gold(volume_max=5.0))
    assert result.lots == pytest.approx(5.0)
    assert result.capped_at_maximum
    assert any("capped" in n for n in result.notes)
    assert result.risk_at_this_size < result.risk_budget


@pytest.mark.parametrize(
    ("field", "value"),
    [("equity", 0.0), ("risk_pct", 0.0), ("stop_multiple", 0.0)],
)
def test_a_caller_error_raises_rather_than_producing_a_refusal(
    field: str, value: float
) -> None:
    # A refusal describes a broker condition. A negative risk percentage is
    # not a broker condition, and returning one would let it be logged and
    # ignored instead of fixed.
    with pytest.raises(ValueError, match="must be positive"):
        _size(**{field: value})  # type: ignore[arg-type]
