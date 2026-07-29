"""The parts of the MT5 adapter that do not need MetaTrader.

The adapter itself cannot be tested here: it is Windows-only, it needs a
logged-in terminal, and credentials never reach this machine. That is precisely
why every piece of judgement was pushed out of it and into ``src/risk``, which
these tests cover in full.

What is left in the adapter is still worth testing, because two of its
properties are safety properties rather than conveniences:

- **the server-epoch conversion**, which is where a one-hour error would put
  every position's age and every deal's day out by an hour and be invisible;
- **the status check**, which must refuse to report "all clear" from a monitor
  that is no longer running. Silence from a dead process and silence from a
  quiet account look identical, and only one of them is safe.
"""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from risk.config import RiskConfig
from risk.notify import Alert, AlertCode, MultiNotifier, Severity, ThrottledNotifier
from risk.report import RiskReport, build_report
from tests.risk import fixtures

REPO: Final = Path(__file__).resolve().parents[2]


def _load_adapter() -> ModuleType:
    """Import the adapter by path.

    ``scripts/`` is not a package -- nothing in the pipeline imports from it,
    and giving it an ``__init__.py`` to satisfy a test would make it one.

    Returns:
        The loaded module.
    """
    path = REPO / "scripts" / "risk_monitor.py"
    spec = importlib.util.spec_from_file_location("risk_monitor_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER: Final = _load_adapter()


# --------------------------------------------------------------------------
# It imports without MetaTrader
# --------------------------------------------------------------------------


def test_the_adapter_imports_on_a_machine_with_no_terminal() -> None:
    # The MetaTrader5 import is inside require_mt5, so everything else in the
    # file is reachable for testing and for reading.
    assert "MetaTrader5" not in sys.modules
    assert callable(ADAPTER.main)


def test_it_refuses_to_run_on_the_wrong_platform_with_a_useful_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        ADAPTER.require_mt5()
    assert exit_info.value.code == 2
    out = capsys.readouterr().out
    assert "must run on Windows" in out
    assert "src/risk" in out


# --------------------------------------------------------------------------
# The server-epoch conversion
# --------------------------------------------------------------------------


def test_a_server_epoch_becomes_the_instant_it_actually_was() -> None:
    # MT5 hands back the server's wall clock as an epoch. On a server three
    # hours ahead, a value that reads as 17:30 "UTC" was really 14:30 UTC.
    epoch = int(datetime(2026, 7, 29, 17, 30, tzinfo=UTC).timestamp())
    assert ADAPTER.server_epoch_to_utc(epoch, 3.0) == datetime(
        2026, 7, 29, 14, 30, tzinfo=UTC
    )


def test_without_a_measured_offset_the_reading_is_left_unshifted() -> None:
    # Not silently corrected toward UTC. The report says the offset is
    # unavailable and refuses every quantity that depends on the server day.
    epoch = int(datetime(2026, 7, 29, 17, 30, tzinfo=UTC).timestamp())
    assert ADAPTER.server_epoch_to_utc(epoch, None) == datetime(
        2026, 7, 29, 17, 30, tzinfo=UTC
    )


def test_the_conversion_always_returns_an_aware_instant() -> None:
    result = ADAPTER.server_epoch_to_utc(1_800_000_000, 2.0)
    assert result.tzinfo is not None


# --------------------------------------------------------------------------
# The heartbeat, and the refusal to report all-clear from a dead monitor
# --------------------------------------------------------------------------


def _report(**overrides: object) -> RiskReport:
    kwargs: dict[str, object] = {
        "now": fixtures.NOW,
        "terminal": fixtures.terminal(),
        "account": fixtures.account(),
        "positions": (fixtures.position(),),
        "deals": (),
        "terms_by_symbol": {"XAUUSD": fixtures.gold()},
        "config": RiskConfig(),
    }
    kwargs.update(overrides)
    return build_report(**kwargs)  # type: ignore[arg-type]


def test_the_heartbeat_records_enough_to_answer_the_status_question(
    tmp_path: Path,
) -> None:
    path = tmp_path / "beat.json"
    ADAPTER.write_heartbeat(path, _report())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["at"] == fixtures.NOW.isoformat()
    assert payload["worst_severity"] in {"INFO", "WARN", "CRITICAL"}
    assert payload["positions"] == 1
    assert "summary" in payload


def test_an_absent_heartbeat_is_not_an_all_clear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = ADAPTER.report_status(tmp_path / "missing.json", RiskConfig(), fixtures.NOW)
    assert code == 2
    assert "NOT an all-clear" in capsys.readouterr().out


def test_a_stale_heartbeat_is_not_an_all_clear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "beat.json"
    ADAPTER.write_heartbeat(path, _report())
    config = RiskConfig(heartbeat_stale_seconds=180.0)

    code = ADAPTER.report_status(path, config, fixtures.NOW + timedelta(hours=1))
    assert code == 2
    out = capsys.readouterr().out
    assert "STALE" in out
    assert "whatever the summary above says" in out


def test_a_corrupt_heartbeat_is_not_an_all_clear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "beat.json"
    path.write_text("{not json", encoding="utf-8")
    assert ADAPTER.report_status(path, RiskConfig(), fixtures.NOW) == 2
    assert "NOT an all-clear" in capsys.readouterr().out


def test_a_fresh_heartbeat_reports_the_severity_it_recorded(tmp_path: Path) -> None:
    path = tmp_path / "beat.json"
    quiet = RiskConfig(time_in_trade_alert_hours=1_000.0)
    ADAPTER.write_heartbeat(
        path,
        _report(positions=(), account=fixtures.account(margin=0.0), config=quiet),
    )
    assert ADAPTER.report_status(path, quiet, fixtures.NOW + timedelta(seconds=30)) == 0

    ADAPTER.write_heartbeat(path, _report())
    assert ADAPTER.report_status(
        path, RiskConfig(), fixtures.NOW + timedelta(seconds=30)
    ) in (1, 2)


# --------------------------------------------------------------------------
# The offset cache
# --------------------------------------------------------------------------


def test_a_measured_offset_survives_for_use_while_the_market_is_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "offset.json"
    ADAPTER.save_cached_offset(path, 3.0, fixtures.NOW)
    offset, reason = ADAPTER.load_cached_offset(path)
    assert offset == 3.0
    assert "cached from a measurement" in reason


def test_an_absent_cache_returns_nothing_and_says_so(tmp_path: Path) -> None:
    offset, reason = ADAPTER.load_cached_offset(tmp_path / "nope.json")
    assert offset is None
    assert "no cached measurement" in reason


def test_a_corrupt_cache_returns_nothing_rather_than_a_wrong_offset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "offset.json"
    path.write_text("{}", encoding="utf-8")
    offset, reason = ADAPTER.load_cached_offset(path)
    assert offset is None
    assert "could not be read" in reason


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


def test_the_channel_is_throttled_and_fans_out(tmp_path: Path) -> None:
    notifier = ADAPTER.build_notifier(tmp_path, quiet=False)
    assert isinstance(notifier, ThrottledNotifier)
    assert isinstance(notifier.inner, MultiNotifier)
    assert len(notifier.inner.notifiers) == 2


def test_quiet_mode_keeps_the_file_and_drops_the_terminal(tmp_path: Path) -> None:
    notifier = ADAPTER.build_notifier(tmp_path, quiet=True)
    assert isinstance(notifier, ThrottledNotifier)
    assert isinstance(notifier.inner, MultiNotifier)
    assert len(notifier.inner.notifiers) == 1


def test_an_alert_reaches_the_log_file_through_the_assembled_channel(
    tmp_path: Path,
) -> None:
    notifier = ADAPTER.build_notifier(tmp_path, quiet=True)
    notifier.emit(
        Alert(
            AlertCode.TIME_IN_TRADE,
            Severity.WARN,
            "XAUUSD long #1",
            "open too long",
            fixtures.NOW,
            "1",
        )
    )
    log = tmp_path / ADAPTER.ALERTS_NAME
    assert json.loads(log.read_text(encoding="utf-8").strip())["key"] == "1"


def test_the_carry_log_records_what_the_increments_can_be_derived_from(
    tmp_path: Path,
) -> None:
    path = tmp_path / "carry.jsonl"
    ADAPTER.append_carry_log(path, _report(), 2_398.80)
    row = json.loads(path.read_text(encoding="utf-8").strip())
    # Everything the swap measurement needs, and the price alongside it so the
    # price-dependence of a base-currency swap is testable from the file alone.
    assert row["ticket"] == fixtures.position().ticket
    assert row["carry_paid"] == pytest.approx(2.0)
    assert row["price"] == pytest.approx(2_398.80)
    assert row["days_open"] == pytest.approx(2.0)
    assert row["direction"] == "long"


def test_the_carry_log_appends_so_increments_survive(tmp_path: Path) -> None:
    path = tmp_path / "carry.jsonl"
    ADAPTER.append_carry_log(path, _report(), 2_398.80)
    ADAPTER.append_carry_log(
        path, _report(positions=(fixtures.position(swap=-3.0),)), 2_410.00
    )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    # The nightly increment is recoverable, which is the whole point.
    assert rows[1]["carry_paid"] - rows[0]["carry_paid"] == pytest.approx(1.0)


def test_a_flat_account_writes_no_carry_rows(tmp_path: Path) -> None:
    path = tmp_path / "carry.jsonl"
    ADAPTER.append_carry_log(
        path, _report(positions=(), account=fixtures.account(margin=0.0)), None
    )
    assert not path.exists()


def test_the_defaults_reach_the_configuration_unchanged() -> None:
    config = ADAPTER.config_from_args(ADAPTER.parse_args([]))
    assert config == RiskConfig()


def test_every_limit_can_be_overridden_from_the_command_line() -> None:
    config = ADAPTER.config_from_args(
        ADAPTER.parse_args(
            [
                "--risk-pct",
                "0.5",
                "--daily-loss-pct",
                "2",
                "--max-positions",
                "1",
                "--time-alert-hours",
                "24",
            ]
        )
    )
    assert config.risk_per_trade_pct == 0.5
    assert config.daily_loss_limit_pct == 2.0
    assert config.max_concurrent_positions == 1
    assert config.time_in_trade_alert_hours == 24.0


def test_the_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        ADAPTER.parse_args(["--probe", "--once"])


def test_status_needs_no_terminal_and_therefore_no_windows(tmp_path: Path) -> None:
    # The one mode that must work when MT5 is not running, because "is the
    # monitor alive" is exactly the question asked after something died.
    code = ADAPTER.main(["--status", "--state-dir", str(tmp_path)])
    assert code == 2
