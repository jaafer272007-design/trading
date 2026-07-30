"""Assembling a reading, and deciding what is worth an alert."""

from datetime import timedelta

import pytest

from risk.config import RiskConfig
from risk.notify import AlertCode, NullNotifier, Severity
from risk.refusal import RefusalCode
from risk.report import RiskReport, build_report, deliver
from risk.state import (
    OFFSET_UNAVAILABLE,
    DealState,
    PositionState,
    SymbolTerms,
)
from risk.swap import SwapVerdict
from tests.risk import fixtures

CONFIG = RiskConfig()
TERMS = {"XAUUSD": fixtures.gold()}


def _report(
    *,
    positions: tuple[PositionState, ...] | None = None,
    deals: tuple[DealState, ...] = (),
    terms: dict[str, SymbolTerms] | None = None,
    config: RiskConfig = CONFIG,
    account_kwargs: dict[str, object] | None = None,
    terminal_kwargs: dict[str, object] | None = None,
) -> RiskReport:
    return build_report(
        now=fixtures.NOW,
        terminal=fixtures.terminal(**(terminal_kwargs or {})),
        account=fixtures.account(**(account_kwargs or {})),
        positions=(fixtures.position(),) if positions is None else positions,
        deals=deals,
        terms_by_symbol=TERMS if terms is None else terms,
        config=config,
    )


def _codes(report: RiskReport) -> set[AlertCode]:
    return {a.code for a in report.alerts}


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_a_flat_account_produces_a_report_with_nothing_alarming() -> None:
    report = _report(positions=(), account_kwargs={"margin": 0.0})
    assert report.carries == ()
    assert report.concurrency.open_positions == 0
    assert AlertCode.TIME_IN_TRADE not in _codes(report)


def test_every_position_gets_its_own_financing_report() -> None:
    report = _report(
        positions=(fixtures.position(ticket=1), fixtures.position(ticket=2))
    )
    assert [c.ticket for c in report.carries] == [1, 2]


def test_the_swap_finding_is_present_for_every_symbol_with_terms() -> None:
    report = _report()
    assert [d.symbol for d in report.swap] == ["XAUUSD"]


def test_alerts_come_back_most_severe_first() -> None:
    report = _report(
        positions=(fixtures.position(stop_loss=None),),
        terminal_kwargs={"connected": False},
    )
    severities = [a.severity for a in report.alerts]
    assert severities[0] is Severity.CRITICAL
    assert report.worst_severity is Severity.CRITICAL


def test_nothing_raised_means_no_worst_severity() -> None:
    quiet = RiskConfig(time_in_trade_alert_hours=1_000.0, margin_call_alert_days=0.001)
    report = _report(positions=(), account_kwargs={"margin": 0.0}, config=quiet)
    assert report.alerts == ()
    assert report.worst_severity is None


# --------------------------------------------------------------------------
# The alerts that matter for this account
# --------------------------------------------------------------------------


def test_a_position_past_the_time_threshold_raises_a_warning() -> None:
    # The default fixture is 48 hours old against a 48-hour threshold.
    report = _report()
    alert = next(a for a in report.alerts if a.code is AlertCode.TIME_IN_TRADE)
    assert alert.severity is Severity.WARN
    assert "48.0 hours" in alert.detail
    assert "point move just to cover it" in alert.detail


def test_a_hold_three_times_past_the_threshold_is_critical() -> None:
    old = fixtures.position(opened_at=fixtures.NOW - timedelta(days=7), swap=-7.0)
    report = _report(positions=(old,))
    alert = next(a for a in report.alerts if a.code is AlertCode.TIME_IN_TRADE)
    assert alert.severity is Severity.CRITICAL


def test_the_two_month_hold_that_emptied_the_account_raises_everything() -> None:
    two_months = fixtures.position(
        opened_at=fixtures.NOW - timedelta(days=60), swap=-60.0
    )
    report = _report(positions=(two_months,))
    codes = _codes(report)
    assert AlertCode.TIME_IN_TRADE in codes
    assert AlertCode.CARRY_HEAVY in codes
    critical = {a.code for a in report.alerts if a.severity is Severity.CRITICAL}
    assert AlertCode.TIME_IN_TRADE in critical


def test_a_position_with_no_stop_is_named() -> None:
    report = _report(positions=(fixtures.position(stop_loss=None),))
    alert = next(a for a in report.alerts if a.code is AlertCode.NO_STOP_LOSS)
    assert "no arithmetic bound" in alert.detail


def test_a_disconnected_terminal_is_critical_and_refuses_everything_below() -> None:
    report = _report(terminal_kwargs={"connected": False})
    assert AlertCode.TERMINAL_DISCONNECTED in _codes(report)
    assert RefusalCode.TERMINAL_DISCONNECTED in {r.code for r in report.refusals}


def test_the_daily_loss_limit_binds_and_is_critical() -> None:
    report = _report(positions=(fixtures.position(profit=-400.0, swap=0.0),))
    alert = next(a for a in report.alerts if a.code is AlertCode.DAILY_LOSS_LIMIT)
    assert alert.severity is Severity.CRITICAL


def test_approaching_the_daily_limit_warns_before_it_binds() -> None:
    # Roughly 110 against a limit of roughly 143 is about 77%.
    report = _report(positions=(fixtures.position(profit=-110.0, swap=0.0),))
    alert = next(a for a in report.alerts if a.code is AlertCode.DAILY_LOSS_LIMIT)
    assert alert.severity is Severity.WARN
    assert "remaining" in alert.detail


def test_the_position_cap_raises_when_it_binds() -> None:
    two = (fixtures.position(ticket=1), fixtures.position(ticket=2))
    assert AlertCode.MAX_POSITIONS in _codes(_report(positions=two))


def test_an_account_already_past_stop_out_is_critical() -> None:
    report = _report(account_kwargs={"equity": 100.0})
    alert = next(a for a in report.alerts if a.code is AlertCode.MARGIN_BREACHED)
    assert alert.severity is Severity.CRITICAL


def test_financing_reaching_stop_out_soon_is_critical() -> None:
    # Headroom of roughly 260 at 100 a day is under three days.
    heavy = fixtures.position(swap=-200.0)
    report = _report(positions=(heavy,), account_kwargs={"equity": 500.0})
    alert = next(a for a in report.alerts if a.code is AlertCode.MARGIN_STOPOUT_NEAR)
    assert alert.severity is Severity.CRITICAL
    assert "price held constant" in alert.detail


# --------------------------------------------------------------------------
# The swap divergence is promoted, not logged
# --------------------------------------------------------------------------


def test_an_expensive_broker_raises_a_critical_alert_of_its_own() -> None:
    report = _report(terms={"XAUUSD": fixtures.gold(swap_long=-30.0)})
    alert = next(a for a in report.alerts if a.code is AlertCode.SWAP_DIVERGENCE)
    assert alert.severity is Severity.CRITICAL
    assert "HYPOTHESES.md" in alert.detail
    assert report.swap[0].bears_on_the_registry


def test_a_conservative_registered_figure_raises_nothing() -> None:
    report = _report()
    assert AlertCode.SWAP_DIVERGENCE not in _codes(report)
    assert report.swap[0].verdict is SwapVerdict.REGISTERED_IS_CONSERVATIVE


# --------------------------------------------------------------------------
# A guard that stops running says so
# --------------------------------------------------------------------------


def test_an_unmeasurable_server_clock_announces_that_the_limit_is_off() -> None:
    report = _report(
        terminal_kwargs={
            "server_utc_offset_hours": None,
            "server_offset_source": OFFSET_UNAVAILABLE,
        }
    )
    alert = next(
        a
        for a in report.alerts
        if a.code is AlertCode.REFUSAL and a.subject == "daily loss limit"
    )
    assert "NOT BEING ENFORCED" in alert.detail


def test_an_unrecognised_margin_mode_announces_that_the_projection_is_off() -> None:
    report = _report(account_kwargs={"margin_so_mode": 9})
    alert = next(
        a
        for a in report.alerts
        if a.code is AlertCode.REFUSAL and a.subject == "stop-out projection"
    )
    assert "NOT BEING ENFORCED" in alert.detail
    assert "orders of magnitude" in alert.detail


def test_the_stop_out_refusal_alert_names_the_cause_it_actually_hit() -> None:
    # Implausible leverage and an unrecognised margin mode both leave the
    # projection empty. An alert that blames the mode when leverage was the
    # cause sends the reader to the wrong field.
    leverage = _report(account_kwargs={"leverage": 2_000_000_000})
    alert = next(
        a
        for a in leverage.alerts
        if a.code is AlertCode.REFUSAL and a.subject == "stop-out projection"
    )
    assert alert.key == RefusalCode.LEVERAGE_IMPLAUSIBLE.value
    assert "1/leverage" in alert.detail

    mode = _report(account_kwargs={"margin_so_mode": 9})
    alert = next(
        a
        for a in mode.alerts
        if a.code is AlertCode.REFUSAL and a.subject == "stop-out projection"
    )
    assert alert.key == RefusalCode.MARGIN_MODE_UNSUPPORTED.value


def test_a_price_dependent_swap_mode_raises_the_divergence_on_structure() -> None:
    # FxPro's gold. No declared comparison is possible, and it still bears on
    # the registry because a fixed points substitute is wrong in kind.
    report = _report(
        terms={"XAUUSD": fixtures.gold(swap_mode=2, swap_long=-67.9, swap_short=27.0)}
    )
    assert report.swap[0].mode_is_price_dependent
    assert report.swap[0].bears_on_the_registry
    note = next(n for n in report.carries[0].notes if "function of price" in n.lower())
    assert "rising market raises the dollar carry" in note


def test_every_position_refusal_reaches_the_reports_own_list() -> None:
    report = _report(positions=(fixtures.position(swap=0.0),))
    assert RefusalCode.CARRY_TOO_YOUNG in {r.code for r in report.refusals}


def test_a_position_in_a_symbol_with_no_terms_is_refused_not_skipped() -> None:
    report = _report(positions=(fixtures.position(symbol="XAGUSD"),))
    assert len(report.carries) == 1
    assert RefusalCode.SYMBOL_TERMS_MISSING in {r.code for r in report.refusals}


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------


def test_delivery_hands_every_alert_to_the_channel() -> None:
    report = _report()
    channel = NullNotifier()
    assert deliver(report, channel) == len(report.alerts)
    assert len(channel.emitted) == len(report.alerts)


def test_the_reading_time_is_the_only_clock_the_report_reads() -> None:
    later = build_report(
        now=fixtures.NOW + timedelta(days=1),
        terminal=fixtures.terminal(),
        account=fixtures.account(),
        positions=(fixtures.position(),),
        deals=(),
        terms_by_symbol=TERMS,
        config=CONFIG,
    )
    assert later.generated_at == fixtures.NOW + timedelta(days=1)
    assert later.carries[0].days_open == pytest.approx(3.0)
