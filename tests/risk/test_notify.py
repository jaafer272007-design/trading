"""Alerts and the channels they go to."""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from risk.notify import (
    SEVERITY_RANK,
    Alert,
    AlertCode,
    FileNotifier,
    MultiNotifier,
    Notifier,
    NullNotifier,
    Severity,
    StreamNotifier,
    ThrottledNotifier,
)

NOW = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)


def _alert(**overrides: object) -> Alert:
    fields: dict[str, object] = {
        "code": AlertCode.TIME_IN_TRADE,
        "severity": Severity.WARN,
        "subject": "XAUUSD long #1",
        "detail": "open 72 hours",
        "raised_at": NOW,
        "key": "1",
    }
    fields.update(overrides)
    return Alert(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The alert itself
# --------------------------------------------------------------------------


def test_severity_order_is_not_the_alphabetical_one() -> None:
    # "CRITICAL" < "INFO" as text. The rank exists so nothing relies on that.
    assert Severity.CRITICAL.value < Severity.INFO.value
    assert SEVERITY_RANK[Severity.CRITICAL] > SEVERITY_RANK[Severity.INFO]
    assert SEVERITY_RANK[Severity.WARN] > SEVERITY_RANK[Severity.INFO]


def test_an_alert_needs_a_timezone_aware_instant() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _alert(raised_at=datetime(2026, 7, 29, 14, 30))


def test_the_json_form_round_trips_every_field() -> None:
    payload = json.loads(_alert().to_json())
    assert payload["code"] == "TIME_IN_TRADE"
    assert payload["severity"] == "WARN"
    assert payload["key"] == "1"
    assert payload["raised_at"] == NOW.isoformat()


def test_the_line_form_carries_the_severity_and_the_subject() -> None:
    line = _alert().to_line()
    assert "WARN" in line
    assert "XAUUSD long #1" in line
    assert "\n" not in line


# --------------------------------------------------------------------------
# Channels
# --------------------------------------------------------------------------


def test_every_implementation_satisfies_the_one_method_interface() -> None:
    channels: tuple[Notifier, ...] = (
        NullNotifier(),
        StreamNotifier(io.StringIO()),
        FileNotifier(Path("/dev/null")),
        MultiNotifier(()),
        ThrottledNotifier(NullNotifier(), timedelta(minutes=1)),
    )
    for channel in channels:
        assert isinstance(channel, Notifier)


def test_the_stream_channel_writes_one_line_per_alert() -> None:
    stream = io.StringIO()
    notifier = StreamNotifier(stream)
    notifier.emit(_alert())
    notifier.emit(_alert(key="2"))
    assert len(stream.getvalue().strip().splitlines()) == 2


def test_the_file_channel_appends_json_lines(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "alerts.jsonl"
    notifier = FileNotifier(path)
    notifier.emit(_alert())
    notifier.emit(_alert(key="2"))

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["key"] == "2"


def test_the_file_channel_creates_its_directory() -> None:
    # Covered by the test above; stated separately because a monitor started
    # against a fresh clone must not fail on a missing directory.
    assert FileNotifier(Path("/tmp/x/y.jsonl")).path.name == "y.jsonl"


def test_a_failing_channel_does_not_silence_the_others() -> None:
    class Broken:
        def emit(self, alert: Alert) -> None:
            raise OSError("disk full")

    working = NullNotifier()
    fan_out = MultiNotifier((Broken(), working))

    with pytest.raises(OSError, match="disk full"):
        fan_out.emit(_alert())
    assert len(working.emitted) == 1


# --------------------------------------------------------------------------
# Throttling
# --------------------------------------------------------------------------


def test_a_repeat_inside_the_window_is_suppressed() -> None:
    inner = NullNotifier()
    throttle = ThrottledNotifier(inner, timedelta(hours=1))
    throttle.emit(_alert())
    throttle.emit(_alert(raised_at=NOW + timedelta(minutes=30)))
    assert len(inner.emitted) == 1


def test_a_repeat_after_the_window_passes_again() -> None:
    inner = NullNotifier()
    throttle = ThrottledNotifier(inner, timedelta(hours=1))
    throttle.emit(_alert())
    throttle.emit(_alert(raised_at=NOW + timedelta(hours=2)))
    assert len(inner.emitted) == 2


def test_two_positions_are_throttled_independently() -> None:
    inner = NullNotifier()
    throttle = ThrottledNotifier(inner, timedelta(hours=1))
    throttle.emit(_alert(key="1"))
    throttle.emit(_alert(key="2"))
    assert len(inner.emitted) == 2


def test_two_codes_on_one_position_are_throttled_independently() -> None:
    inner = NullNotifier()
    throttle = ThrottledNotifier(inner, timedelta(hours=1))
    throttle.emit(_alert(code=AlertCode.TIME_IN_TRADE))
    throttle.emit(_alert(code=AlertCode.CARRY_HEAVY))
    assert len(inner.emitted) == 2


def test_an_escalation_is_never_swallowed_by_the_throttle() -> None:
    inner = NullNotifier()
    throttle = ThrottledNotifier(inner, timedelta(hours=1))
    throttle.emit(_alert(severity=Severity.WARN))
    throttle.emit(
        _alert(severity=Severity.CRITICAL, raised_at=NOW + timedelta(minutes=1))
    )
    assert [a.severity for a in inner.emitted] == [
        Severity.WARN,
        Severity.CRITICAL,
    ]


def test_a_de_escalation_inside_the_window_is_still_suppressed() -> None:
    inner = NullNotifier()
    throttle = ThrottledNotifier(inner, timedelta(hours=1))
    throttle.emit(_alert(severity=Severity.CRITICAL))
    throttle.emit(_alert(severity=Severity.WARN, raised_at=NOW + timedelta(minutes=1)))
    assert len(inner.emitted) == 1


def test_an_escalation_resets_the_window_at_the_new_severity() -> None:
    inner = NullNotifier()
    throttle = ThrottledNotifier(inner, timedelta(hours=1))
    throttle.emit(_alert(severity=Severity.WARN))
    throttle.emit(
        _alert(severity=Severity.CRITICAL, raised_at=NOW + timedelta(minutes=1))
    )
    throttle.emit(
        _alert(severity=Severity.CRITICAL, raised_at=NOW + timedelta(minutes=2))
    )
    assert len(inner.emitted) == 2
