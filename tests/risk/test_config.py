"""The configured limits, and what the layer refuses to be configured with.

The first four assertions pin the defaults the user set. They are **not** kill
criteria and nothing procedural governs them: they are operating limits on a
live account, meant to be tuned after the probe reports. The tests exist so
that a change to one is a visible, deliberate edit rather than a drift.
"""

import pytest

from risk.config import MAX_SANE_RISK_PCT, RiskConfig


def test_the_defaults_are_the_ones_that_were_agreed() -> None:
    config = RiskConfig()
    assert config.risk_per_trade_pct == 1.0
    assert config.daily_loss_limit_pct == 3.0
    assert config.max_concurrent_positions == 2
    assert config.time_in_trade_alert_hours == 48.0


def test_the_daily_limit_is_three_trades_at_the_per_trade_risk() -> None:
    config = RiskConfig()
    assert config.daily_loss_limit_pct == pytest.approx(3.0 * config.risk_per_trade_pct)


def test_the_time_alert_fires_long_before_a_two_month_hold_can_form() -> None:
    # The account died on a hold of roughly 1,440 hours.
    assert RiskConfig().time_in_trade_alert_hours < 24 * 60 / 10


def test_the_projection_horizons_reach_the_shape_that_emptied_the_account() -> None:
    assert 60.0 in RiskConfig().carry_projection_days


def test_a_misplaced_decimal_point_in_the_risk_is_refused() -> None:
    with pytest.raises(ValueError, match="misplaced decimal point"):
        RiskConfig(risk_per_trade_pct=MAX_SANE_RISK_PCT + 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk_per_trade_pct", 0.0),
        ("risk_per_trade_pct", -1.0),
        ("daily_loss_limit_pct", 0.0),
        ("daily_loss_limit_pct", 101.0),
        ("max_concurrent_positions", 0),
        ("time_in_trade_alert_hours", 0.0),
        ("stop_atr_multiple", 0.0),
        ("carry_alert_pct_of_equity", 0.0),
        ("margin_call_alert_days", 0.0),
        ("swap_divergence_tolerance", -0.1),
        ("minimum_days_for_measured_carry", 0.0),
        ("heartbeat_stale_seconds", 0.0),
    ],
)
def test_an_impossible_limit_is_refused_at_construction(
    field: str, value: float
) -> None:
    with pytest.raises(ValueError, match=field):
        RiskConfig(**{field: value})  # type: ignore[arg-type]


def test_a_zero_position_cap_would_make_every_reading_a_breach() -> None:
    with pytest.raises(ValueError, match="every reading a breach"):
        RiskConfig(max_concurrent_positions=0)


def test_an_empty_horizon_list_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        RiskConfig(carry_projection_days=())


def test_a_negative_horizon_is_refused() -> None:
    with pytest.raises(ValueError, match="horizon must be positive"):
        RiskConfig(carry_projection_days=(7.0, -1.0))


def test_the_config_is_frozen_so_a_limit_cannot_be_relaxed_mid_run() -> None:
    config = RiskConfig()
    with pytest.raises(AttributeError):
        config.risk_per_trade_pct = 5.0  # type: ignore[misc]
