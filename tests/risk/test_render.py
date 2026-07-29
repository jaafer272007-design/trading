"""Rendering: what a person actually sees, and in what order."""

from datetime import timedelta

from risk.config import RiskConfig
from risk.render import render, render_one_line, severity_exit_code
from risk.report import RiskReport, build_report
from risk.state import OFFSET_UNAVAILABLE
from tests.risk import fixtures

CONFIG = RiskConfig()
TERMS = {"XAUUSD": fixtures.gold()}


def _report(**overrides: object) -> RiskReport:
    kwargs: dict[str, object] = {
        "now": fixtures.NOW,
        "terminal": fixtures.terminal(),
        "account": fixtures.account(),
        # A smaller floating loss than the default fixture's, so that the
        # day sits under its limit and the worst severity in a plain reading
        # is WARN. The breached case has its own test.
        "positions": (fixtures.position(profit=-20.0),),
        "deals": (fixtures.deal(),),
        "terms_by_symbol": TERMS,
        "config": CONFIG,
    }
    kwargs.update(overrides)
    return build_report(**kwargs)  # type: ignore[arg-type]


def _index(text: str, needle: str) -> int:
    position = text.find(needle)
    assert position >= 0, f"{needle!r} is not in the rendered report"
    return position


# --------------------------------------------------------------------------
# Order is a decision
# --------------------------------------------------------------------------


def test_alerts_come_first_then_refusals_then_the_swap_finding() -> None:
    text = render(_report())
    assert _index(text, "ALERTS") < _index(text, "REFUSED")
    assert _index(text, "REFUSED") < _index(text, "SWAP")
    assert _index(text, "SWAP") < _index(text, "ACCOUNT")


def test_the_swap_finding_sits_above_the_accounts_own_numbers() -> None:
    # It is a finding about the registry, not a diagnostic about the account.
    text = render(_report())
    assert _index(text, "SWAP") < _index(text, "POSITIONS")


# --------------------------------------------------------------------------
# What must appear
# --------------------------------------------------------------------------


def test_the_report_says_what_it_is_not() -> None:
    text = render(_report())
    assert "predicts nothing and places nothing" in text


def test_a_registry_bearing_divergence_is_marked_in_the_section_heading() -> None:
    text = render(_report(terms_by_symbol={"XAUUSD": fixtures.gold(swap_long=-30.0)}))
    assert "*** BEARS ON THE REGISTRY ***" in text


def test_a_conservative_broker_does_not_get_the_marker() -> None:
    assert "BEARS ON THE REGISTRY" not in render(_report())


def test_an_unavailable_comparison_is_not_reported_as_agreement() -> None:
    # No published rate and no position to measure one from.
    text = render(
        _report(
            positions=(),
            account=fixtures.account(margin=0.0),
            terms_by_symbol={"XAUUSD": fixtures.gold(swap_mode=7)},
        )
    )
    assert "UNAVAILABLE verdict is not agreement" in text


def test_the_constant_price_assumption_is_printed_beside_the_projection() -> None:
    text = render(_report())
    assert text.count("price held constant") >= 1
    assert "This is a bound, not a forecast." in text


def test_a_position_shows_the_move_needed_to_cover_its_financing() -> None:
    text = render(_report())
    assert "move needed to cover financing" in text
    assert "20.0 points" in text


def test_a_breached_daily_limit_is_rendered_and_summarised_as_critical() -> None:
    breached = _report(positions=(fixtures.position(profit=-400.0),))
    assert "breached" in render(breached)
    assert "YES" in render(breached)
    assert "CRITICAL" in render_one_line(breached)
    assert severity_exit_code(breached) == 2


def test_a_missing_stop_is_spelled_out_rather_than_left_blank() -> None:
    text = render(_report(positions=(fixtures.position(stop_loss=None),)))
    assert "stop loss attached" in text
    assert "NO" in text


def test_a_disabled_guard_is_printed_where_its_number_would_have_been() -> None:
    text = render(
        _report(
            terminal=fixtures.terminal(
                server_utc_offset_hours=None,
                server_offset_source=OFFSET_UNAVAILABLE,
            )
        )
    )
    assert "daily loss limit: NOT BEING ENFORCED" in text
    assert "server clock" in text
    assert "UNAVAILABLE" in text


def test_a_clean_reading_says_nothing_was_defaulted() -> None:
    quiet = RiskConfig(time_in_trade_alert_hours=1_000.0)
    text = render(
        _report(positions=(), account=fixtures.account(margin=0.0), config=quiet)
    )
    assert "none open" in text


def test_the_carried_in_caveat_appears_only_when_it_applies() -> None:
    carried = render(_report())
    assert "inherited from" in carried

    same_day = render(
        _report(
            positions=(
                fixtures.position(
                    opened_at=fixtures.NOW - timedelta(hours=2), swap=0.0
                ),
            )
        )
    )
    assert "inherited from" not in same_day


def test_the_book_projection_names_the_date_financing_empties_the_account() -> None:
    text = render(_report())
    assert "days for financing alone to take equity" in text


# --------------------------------------------------------------------------
# The one-line forms
# --------------------------------------------------------------------------


def test_the_one_line_summary_carries_the_worst_severity() -> None:
    line = render_one_line(_report())
    assert "WARN" in line
    assert "\n" not in line


def test_a_quiet_reading_summarises_as_ok() -> None:
    quiet = RiskConfig(time_in_trade_alert_hours=1_000.0)
    line = render_one_line(
        _report(positions=(), account=fixtures.account(margin=0.0), config=quiet)
    )
    assert "OK" in line


def test_the_exit_code_escalates_with_the_worst_severity() -> None:
    quiet = RiskConfig(time_in_trade_alert_hours=1_000.0)
    assert (
        severity_exit_code(
            _report(positions=(), account=fixtures.account(margin=0.0), config=quiet)
        )
        == 0
    )
    assert severity_exit_code(_report()) == 1
    assert (
        severity_exit_code(_report(positions=(fixtures.position(profit=-400.0),))) == 2
    )


def test_the_rendered_report_is_plain_text_within_a_terminal_width() -> None:
    text = render(_report())
    assert all(len(line) <= 100 for line in text.splitlines())
