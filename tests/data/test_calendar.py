"""The calendar freeze guard, and what it refuses.

``test_calendar_has_not_changed_without_review`` is the load-bearing test. Same
filesystem-versus-declaration pattern as the feature registry and the K-1
sensitivity record: the build fails when the file moves and the recorded hash
does not move with it.
"""

import textwrap
from datetime import date
from pathlib import Path

import pytest

from data.calendar import (
    CALENDAR_PATH,
    RECORDED_CALENDAR_SHA256,
    CalendarError,
    calendar_sha256,
    load_calendar,
)

# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_calendar_has_not_changed_without_review() -> None:
    """The calendar declares how every timestamp is interpreted.

    If this fails, the fix is NOT to paste in the new hash. Establish what
    changed in the world, record that decision, and update the hash with it.
    """
    live = calendar_sha256()
    assert live == RECORDED_CALENDAR_SHA256, (
        f"calendar/gold_fxpro.yaml changed.\n"
        f"  recorded: {RECORDED_CALENDAR_SHA256}\n"
        f"  live:     {live}\n"
        f"Pasting the new hash alone is the defect this guard exists to prevent."
    )


def test_calendar_file_is_committed() -> None:
    assert CALENDAR_PATH.exists()


# ---------------------------------------------------------------------------
# What it says
# ---------------------------------------------------------------------------


def test_declares_the_eu_rule_the_probe_measured() -> None:
    """The three-anchor fingerprint returned EU RULE; the file must say so."""
    cal = load_calendar()
    assert cal.clock_rule == "eu"
    assert (cal.offset_winter, cal.offset_summer) == (2, 3)


def test_session_hours_match_the_arithmetic_derivation() -> None:
    """NY 17:00 through an EU clock lands the break at 00:00 / 23:00.

    Recomputed here rather than copied, so the file and the derivation cannot
    drift apart silently.
    """
    cal = load_calendar()
    for day, ny_offset, expect_break in (
        (date(2026, 1, 15), -5, 0),  # both winter:  22:00 UTC, server +2
        (date(2026, 7, 15), -4, 0),  # both summer:  21:00 UTC, server +3
        (date(2026, 3, 15), -4, 23),  # US-only:      21:00 UTC, server +2
    ):
        utc_hour = (17 - ny_offset) % 24
        server_hour = (utc_hour + cal.offset_hours(day)) % 24
        assert server_hour == expect_break, day
        assert cal.break_hour(day) == expect_break, day
        assert cal.close_hour(day) == (expect_break - 1) % 24, day


def test_window_start_is_the_frozen_h006_date() -> None:
    assert load_calendar().window_start == date(2015, 9, 11)


def test_symbol_string_is_pinned_exactly() -> None:
    """DATA_CONTRACT §3. A symbol resolving elsewhere is a whole-project failure."""
    assert load_calendar().symbol == "GOLD"


def test_holiday_list_covers_the_window() -> None:
    cal = load_calendar()
    assert min(cal.holidays) >= date(2015, 1, 1)
    assert max(cal.holidays) >= date(2026, 1, 1)
    assert len(cal.holidays) > 100


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2016, 7, 4), "Independence Day"),
        (date(2017, 4, 14), "Good Friday"),
        (date(2022, 6, 19), "Juneteenth"),
        (date(2019, 12, 26), "Christmas (adjacent)"),
        (date(2019, 6, 5), None),
    ],
)
def test_holiday_lookup(day: date, expected: str | None) -> None:
    assert load_calendar().holiday_near(day) == expected


def test_juneteenth_only_from_2022() -> None:
    """It became a CME holiday in 2022; before that it was a trading day."""
    cal = load_calendar()
    assert date(2022, 6, 19) in cal.holidays
    assert date(2021, 6, 19) not in cal.holidays


# ---------------------------------------------------------------------------
# What it refuses — every one of these is a plausible hand-edit
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "cal.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


MINIMAL = """\
    schema_version: 1
    symbol: {{exact: "GOLD"}}
    server: {{name: "S"}}
    clock:
      rule: "{rule}"
      offset_hours_winter: {winter}
      offset_hours_summer: {summer}
    session:
      daily_break_hour: {{matched: {bm}, mismatch: {bx}}}
      weekly_close_hour: {{matched: {cm}, mismatch: {cx}}}
      eras:
{eras}
    window: {{start: 2015-09-11}}
    holidays:
      - {{date: 2016-07-04, name: "Independence Day"}}
"""


def _calendar_text(**kwargs: object) -> str:
    defaults = {
        "rule": "eu",
        "winter": 2,
        "summer": 3,
        "bm": 0,
        "bx": 23,
        "cm": 23,
        "cx": 22,
        "eras": (
            '        - {start: 2015-09-11, daily_break: true, note: "a"}\n'
            '        - {start: 2017-10-07, daily_break: false, note: "b"}'
        ),
    }
    return MINIMAL.format(**{**defaults, **kwargs})


def test_valid_minimal_calendar_loads(tmp_path: Path) -> None:
    """The fixture itself must be valid, or every rejection below proves nothing."""
    assert load_calendar(_write(tmp_path, _calendar_text())).clock_rule == "eu"


def test_rejects_dst_offsets_that_do_not_differ_by_one(tmp_path: Path) -> None:
    with pytest.raises(CalendarError, match="exactly one hour"):
        load_calendar(_write(tmp_path, _calendar_text(summer=4)))


def test_rejects_fixed_rule_with_differing_offsets(tmp_path: Path) -> None:
    with pytest.raises(CalendarError, match="fixed"):
        load_calendar(_write(tmp_path, _calendar_text(rule="fixed")))


def test_rejects_inverted_mismatch_direction(tmp_path: Path) -> None:
    """Under the EU rule the mismatch hour is one BEFORE the matched hour.

    Typing it one after is the single most likely hand-edit error in the file,
    and it is an hour-sized error in every session feature.
    """
    with pytest.raises(CalendarError, match="one BEFORE"):
        load_calendar(_write(tmp_path, _calendar_text(bx=1, cx=0)))


def test_rejects_close_that_is_not_one_before_the_break(tmp_path: Path) -> None:
    with pytest.raises(CalendarError, match="one hour earlier"):
        load_calendar(_write(tmp_path, _calendar_text(cm=22, cx=21)))


def test_rejects_unknown_clock_rule(tmp_path: Path) -> None:
    with pytest.raises(CalendarError, match=r"clock\.rule"):
        load_calendar(_write(tmp_path, _calendar_text(rule="australia")))


def test_rejects_future_schema_version(tmp_path: Path) -> None:
    """Old code reading a newer calendar is how a convention change gets ignored."""
    body = _calendar_text().replace("schema_version: 1", "schema_version: 2")
    with pytest.raises(CalendarError, match="schema_version"):
        load_calendar(_write(tmp_path, body))


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CalendarError, match="missing"):
        load_calendar(tmp_path / "absent.yaml")


def test_rejects_empty_holiday_list(tmp_path: Path) -> None:
    body = (
        _calendar_text()
        .replace('      - {date: 2016-07-04, name: "Independence Day"}\n', "")
        .replace("holidays:", "holidays: []")
    )
    with pytest.raises(CalendarError, match="empty"):
        load_calendar(_write(tmp_path, body))


def test_rejects_yaml_type_coercion(tmp_path: Path) -> None:
    """YAML turns a bare `no` into False. An hour that is a bool must not pass.

    This is why every field is read through a typed accessor rather than
    trusted to be what it looks like in the file.
    """
    body = _calendar_text().replace("matched: 0,", "matched: no,")
    with pytest.raises(CalendarError, match="expected int"):
        load_calendar(_write(tmp_path, body))


def test_rejects_duplicate_holiday(tmp_path: Path) -> None:
    body = _calendar_text() + '      - {date: 2016-07-04, name: "dup"}\n'
    with pytest.raises(CalendarError, match="twice"):
        load_calendar(_write(tmp_path, body))


# ---------------------------------------------------------------------------
# Session eras
#
# The calendar gained these after the first ingest of the full H1 export
# showed the daily break absent between 2017-10-07 and 2022-10-20. A single
# `daily_break_hour` had been generalising over a structure the feed does not
# have, and the boundaries sit inside H-006's evaluation window.
# ---------------------------------------------------------------------------


def test_eras_are_required(tmp_path: Path) -> None:
    """A calendar with no eras claims a uniformity the feed does not have."""
    body = _calendar_text()
    stripped = "\n".join(
        line
        for line in body.splitlines()
        if "daily_break:" not in line and line.strip() != "eras:"
    )
    with pytest.raises(CalendarError, match="eras"):
        load_calendar(_write(tmp_path, stripped + "\n"))


def test_rejects_out_of_order_eras(tmp_path: Path) -> None:
    """era_for scans linearly; unordered starts would silently misassign days."""
    with pytest.raises(CalendarError, match="strictly increase"):
        load_calendar(
            _write(
                tmp_path,
                _calendar_text(
                    eras=(
                        '        - {start: 2017-10-07, daily_break: false, note: "b"}\n'
                        '        - {start: 2015-09-11, daily_break: true, note: "a"}'
                    )
                ),
            )
        )


def test_rejects_an_era_boundary_that_changes_nothing(tmp_path: Path) -> None:
    """Two adjacent eras with the same structure is a typo or a missing field."""
    with pytest.raises(CalendarError, match="same daily_break"):
        load_calendar(
            _write(
                tmp_path,
                _calendar_text(
                    eras=(
                        '        - {start: 2015-09-11, daily_break: true, note: "a"}\n'
                        '        - {start: 2017-10-07, daily_break: true, note: "b"}'
                    )
                ),
            )
        )


def test_rejects_a_first_era_starting_after_the_window(tmp_path: Path) -> None:
    """Every in-window bar must fall in a declared era."""
    with pytest.raises(CalendarError, match="after window_start"):
        load_calendar(
            _write(
                tmp_path,
                _calendar_text(
                    eras=(
                        '        - {start: 2016-01-01, daily_break: true, note: "a"}\n'
                        '        - {start: 2017-10-07, daily_break: false, note: "b"}'
                    )
                ),
            )
        )


def test_the_real_calendar_declares_the_three_measured_eras() -> None:
    """Pinned against the measurement in scripts/report_session_eras.py."""
    cal = load_calendar()
    assert [(e.start.isoformat(), e.daily_break) for e in cal.eras] == [
        ("2015-09-11", True),
        ("2017-10-07", False),
        ("2022-10-21", True),
    ]


def test_era_lookup_puts_the_boundary_days_on_the_right_side() -> None:
    """The dates the measurement actually pinned, not approximations of them."""
    cal = load_calendar()
    assert cal.has_daily_break(date(2017, 10, 6)) is True  # last 23-bar day
    assert cal.has_daily_break(date(2017, 10, 9)) is False  # first 24-bar day
    assert cal.has_daily_break(date(2022, 10, 20)) is False  # last 24-bar day
    assert cal.has_daily_break(date(2022, 10, 21)) is True  # first 23-bar day


def test_dates_before_every_era_claim_nothing() -> None:
    """The sparse era predates the declaration and the question does not arise."""
    cal = load_calendar()
    assert cal.era_for(date(2010, 1, 1)) is None
    assert cal.has_daily_break(date(2010, 1, 1)) is False
