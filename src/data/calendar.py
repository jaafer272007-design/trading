"""The frozen market calendar, and the guard that keeps it frozen.

``calendar/gold_fxpro.yaml`` is a **declaration about the world** — the
server's daylight-saving rule, its session boundaries, the exchange holiday
list, and the H-006 evaluation window. It is committed, hashed, and asserted
against on every ingest.

Why it is frozen rather than derived
------------------------------------

The probe can derive all of it from the feed. Deriving it at ingest time would
be simpler and would be wrong, for the reason the probe's own output states: a
rule re-derived from the data it validates can never detect that the broker
changed it. If FxPro moves its clock next spring, a self-deriving pipeline
quietly follows and every session feature silently shifts by an hour;
``DATA_CONTRACT.md`` §4 calls a one-bar convention mismatch a leak, and one bar
is enough. A frozen file turns that silent shift into a halt.

The same reasoning as ``tests/test_causality.py``'s feature registry and the
K-1 sensitivity record in ``evaluation/sensitivity.py``: the filesystem is
checked against a declaration, and the build fails when they diverge.

Why every field is type-checked
-------------------------------

YAML coerces. A bare ``no`` becomes ``False``, a bare ``2015-09-11`` becomes a
``date``, ``01:00`` may become a string or an integer depending on quoting.
Most of that coercion is what we want here, but "what we want" and "what we
got" must not be assumed equal in a file that decides how timestamps are
interpreted. Every field is therefore read through an explicit typed accessor
that raises rather than returning something plausible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

import yaml

CALENDAR_PATH: Final = (
    Path(__file__).resolve().parents[2] / "calendar" / "gold_fxpro.yaml"
)

SUNDAY: Final = 6
SCHEMA_VERSION: Final = 1

#: Recorded SHA-256 of the calendar file, and the guard that makes it a freeze
#: rather than a suggestion. If this does not match, the calendar changed: a
#: human must confirm the world changed before the number here is updated.
#: Updating it to silence a failure is the defect this exists to prevent.
RECORDED_CALENDAR_SHA256: Final = (
    "38114b46ded97a92e76e56d75b4dd923f1a6cded3c2e7b2ecfc2dbdb156bdd59"
)

#: Every hash this file has carried, oldest first, with why it moved. Kept
#: because the guard above is only as good as the record of when it was
#: deliberately stepped past: a bare constant that someone edits shows nothing
#: in a later diff except a number changing, which is exactly what a silenced
#: failure looks like.
CALENDAR_HISTORY: Final = (
    (
        "c1152b3fd18dcd9ac53e87007936b43fd78554f43729c50725c676349eb1a387",
        "initial freeze, 2026-07-27, from scripts/mt5_probe.py",
    ),
    (
        "38114b46ded97a92e76e56d75b4dd923f1a6cded3c2e7b2ecfc2dbdb156bdd59",
        "added session.eras — the first ingest of the full H1 export showed "
        "the daily break absent between 2017-10-07 and 2022-10-20, which the "
        "single daily_break_hour declaration had generalised over",
    ),
)

VALID_CLOCK_RULES: Final = frozenset({"eu", "us", "fixed"})


class CalendarError(RuntimeError):
    """The calendar is missing, malformed, or disagrees with the feed."""


# ---------------------------------------------------------------------------
# Typed accessors — no field is read without asserting what it is
# ---------------------------------------------------------------------------


def _require(block: Any, key: str, kind: type, where: str) -> Any:  # noqa: ANN401
    """Fetch one key and assert its type.

    Args:
        block: The mapping to read from.
        key: Key name.
        kind: Required Python type.
        where: Dotted path, for the error message.

    Returns:
        The value.

    Raises:
        CalendarError: If the block is not a mapping, the key is absent, or
            the value is not ``kind``.
    """
    if not isinstance(block, dict):
        raise CalendarError(f"{where}: expected a mapping, got {type(block).__name__}")
    if key not in block:
        raise CalendarError(f"{where}.{key}: missing")
    value = block[key]
    # bool is a subclass of int; a `yes` where an hour belongs must not pass.
    if isinstance(value, bool) is not (kind is bool) or not isinstance(value, kind):
        raise CalendarError(
            f"{where}.{key}: expected {kind.__name__}, "
            f"got {type(value).__name__} ({value!r})"
        )
    return value


def _require_hour(block: Any, key: str, where: str) -> int:  # noqa: ANN401
    """Fetch a server hour and assert it is one.

    Args:
        block: The mapping to read from.
        key: Key name.
        where: Dotted path, for the error message.

    Returns:
        An hour in ``0..23``.

    Raises:
        CalendarError: If absent, not an int, or out of range.
    """
    hour = int(_require(block, key, int, where))
    if not 0 <= hour <= 23:
        raise CalendarError(f"{where}.{key}: hour {hour} outside 0..23")
    return hour


# ---------------------------------------------------------------------------
# The calendar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionEra:
    """A span over which the session's shape was constant.

    The feed does not have one session structure. It has three, and the
    boundaries are inside H-006's evaluation window. Declaring them here makes
    the change visible to anything that cares; leaving them out made the
    calendar quietly claim a uniformity the data does not have.
    """

    start: date
    daily_break: bool
    note: str


@dataclass(frozen=True)
class MarketCalendar:
    """Everything the data layer needs to interpret a server timestamp.

    Frozen: nothing downstream may adjust a boundary at runtime. A conversion
    that can be tuned per-call is not a convention.
    """

    symbol: str
    server_name: str
    clock_rule: str
    offset_winter: int
    offset_summer: int
    break_hour_matched: int
    break_hour_mismatch: int
    close_hour_matched: int
    close_hour_mismatch: int
    window_start: date
    holidays: dict[date, str]
    eras: tuple[SessionEra, ...]
    sha256: str

    # -- session eras ------------------------------------------------------

    def era_for(self, day: date) -> SessionEra | None:
        """The session era a date falls in.

        Args:
            day: A calendar date on the server's clock.

        Returns:
            The era, or ``None`` for a date before the first declared era —
            which is the sparse pre-window period, where the question does
            not arise.
        """
        found: SessionEra | None = None
        for era in self.eras:
            if era.start <= day:
                found = era
            else:
                break
        return found

    def has_daily_break(self, day: date) -> bool:
        """Whether a whole-hour daily break is expected on a date.

        Args:
            day: A calendar date on the server's clock.

        Returns:
            False outside every declared era, where nothing is claimed.
        """
        era = self.era_for(day)
        return era.daily_break if era is not None else False

    # -- daylight saving ---------------------------------------------------

    def eu_is_summer(self, day: date) -> bool:
        """Whether Europe is on summer time.

        Args:
            day: A calendar date.

        Returns:
            True between the last Sunday in March and the last Sunday in
            October.
        """
        return _last_sunday(day.year, 3) <= day < _last_sunday(day.year, 10)

    def us_is_summer(self, day: date) -> bool:
        """Whether New York is on daylight time.

        Args:
            day: A calendar date.

        Returns:
            True between the second Sunday in March and the first Sunday in
            November.
        """
        return _nth_sunday(day.year, 3, 2) <= day < _nth_sunday(day.year, 11, 1)

    def offset_hours(self, day: date) -> int:
        """The server's UTC offset on a given date.

        Args:
            day: A calendar date, read on the **server's** clock.

        Returns:
            Whole hours ahead of UTC.

        Raises:
            CalendarError: If the clock rule is not one this code implements.
        """
        if self.clock_rule == "fixed":
            return self.offset_winter
        if self.clock_rule == "eu":
            return self.offset_summer if self.eu_is_summer(day) else self.offset_winter
        if self.clock_rule == "us":
            return self.offset_summer if self.us_is_summer(day) else self.offset_winter
        raise CalendarError(f"unimplemented clock rule {self.clock_rule!r}")

    def calendars_disagree(self, day: date) -> bool:
        """Whether the US has changed over and Europe has not.

        The ~4 weeks a year in which the session boundaries sit one hour
        earlier in server time. It is the only window in which the three
        candidate clock rules are distinguishable, and the only one in which
        a boundary check must expect the shifted hour.

        Args:
            day: A calendar date.

        Returns:
            True in the US-only-summer window.
        """
        return self.us_is_summer(day) and not self.eu_is_summer(day)

    def break_hour(self, day: date) -> int:
        """The server hour of the daily rollover break.

        Args:
            day: A calendar date on the server's clock.

        Returns:
            The hour whose bar is absent.
        """
        return (
            self.break_hour_mismatch
            if self.calendars_disagree(day)
            else self.break_hour_matched
        )

    def close_hour(self, day: date) -> int:
        """The server hour of the last bar of the trading week.

        Args:
            day: A calendar date on the server's clock.

        Returns:
            The hour of the weekly close bar.
        """
        return (
            self.close_hour_mismatch
            if self.calendars_disagree(day)
            else self.close_hour_matched
        )

    # -- holidays ----------------------------------------------------------

    def holiday_near(self, day: date, tolerance_days: int = 2) -> str | None:
        """Name the exchange holiday on or adjacent to a date.

        Adjacency is deliberate: a holiday shortens the session before it and
        the session that reopens after it, so requiring an exact match would
        send genuine closures back to the defect pile.

        Args:
            day: A calendar date.
            tolerance_days: How far either side to look.

        Returns:
            The holiday name, or ``None``.
        """
        for offset in range(-tolerance_days, tolerance_days + 1):
            name = self.holidays.get(day + timedelta(days=offset))
            if name is not None:
                return name if offset == 0 else f"{name} (adjacent)"
        return None


def _nth_sunday(year: int, month: int, n: int) -> date:
    """Return the n-th Sunday of a month, 1-based.

    Args:
        year: Calendar year.
        month: Calendar month.
        n: Which Sunday.

    Returns:
        The date.
    """
    first = date(year, month, 1)
    return first + timedelta(days=(SUNDAY - first.weekday()) % 7 + 7 * (n - 1))


def _last_sunday(year: int, month: int) -> date:
    """Return the last Sunday of a month.

    Args:
        year: Calendar year.
        month: Calendar month.

    Returns:
        The date.
    """
    after = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = after - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - SUNDAY) % 7)


def calendar_sha256(path: Path = CALENDAR_PATH) -> str:
    """Hash the calendar file exactly as it sits on disk.

    Byte-level, not semantic. A reformatting that leaves the meaning unchanged
    still trips the guard, which is the intended behaviour: this file is
    reviewed by reading it, so any edit to it deserves a human look.

    Args:
        path: Calendar file.

    Returns:
        Lowercase hex SHA-256.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_calendar(path: Path = CALENDAR_PATH) -> MarketCalendar:
    """Load, validate, and hash the frozen calendar.

    Args:
        path: Calendar file.

    Returns:
        The validated calendar.

    Raises:
        CalendarError: If the file is missing, the schema version is
            unrecognised, a field is absent or of the wrong type, or the
            declared values are internally inconsistent.
    """
    if not path.exists():
        raise CalendarError(f"{path}: missing. Ingestion cannot run without it.")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CalendarError(f"{path}: top level is not a mapping")

    version = _require(raw, "schema_version", int, "root")
    if version != SCHEMA_VERSION:
        raise CalendarError(
            f"schema_version {version} but this code implements {SCHEMA_VERSION}. "
            f"Reading a newer calendar with older code is how a convention change "
            f"gets silently ignored."
        )

    clock = _require(raw, "clock", dict, "root")
    rule = _require(clock, "rule", str, "clock")
    if rule not in VALID_CLOCK_RULES:
        raise CalendarError(f"clock.rule {rule!r} not in {sorted(VALID_CLOCK_RULES)}")

    session = _require(raw, "session", dict, "root")
    break_block = _require(session, "daily_break_hour", dict, "session")
    close_block = _require(session, "weekly_close_hour", dict, "session")

    holidays_raw = _require(raw, "holidays", list, "root")
    holidays: dict[date, str] = {}
    for i, entry in enumerate(holidays_raw):
        day = _require(entry, "date", date, f"holidays[{i}]")
        name = _require(entry, "name", str, f"holidays[{i}]")
        if day in holidays:
            raise CalendarError(f"holidays[{i}]: {day} listed twice")
        holidays[day] = name

    eras_raw = _require(session, "eras", list, "session")
    eras: list[SessionEra] = []
    for i, entry in enumerate(eras_raw):
        eras.append(
            SessionEra(
                start=_require(entry, "start", date, f"session.eras[{i}]"),
                daily_break=_require(entry, "daily_break", bool, f"session.eras[{i}]"),
                note=_require(entry, "note", str, f"session.eras[{i}]"),
            )
        )

    symbol_block = _require(raw, "symbol", dict, "root")
    server_block = _require(raw, "server", dict, "root")
    window_block = _require(raw, "window", dict, "root")

    cal = MarketCalendar(
        symbol=_require(symbol_block, "exact", str, "symbol"),
        server_name=_require(server_block, "name", str, "server"),
        clock_rule=rule,
        offset_winter=_require_hour(clock, "offset_hours_winter", "clock"),
        offset_summer=_require_hour(clock, "offset_hours_summer", "clock"),
        break_hour_matched=_require_hour(break_block, "matched", "session.break"),
        break_hour_mismatch=_require_hour(break_block, "mismatch", "session.break"),
        close_hour_matched=_require_hour(close_block, "matched", "session.close"),
        close_hour_mismatch=_require_hour(close_block, "mismatch", "session.close"),
        window_start=_require(window_block, "start", date, "window"),
        holidays=holidays,
        eras=tuple(eras),
        sha256=calendar_sha256(path),
    )
    _check_internal_consistency(cal)
    return cal


def _check_internal_consistency(cal: MarketCalendar) -> None:
    """Reject a calendar whose own fields contradict each other.

    These are cheap and they catch the realistic edit mistakes: a rule changed
    without its offsets, or a mismatch hour typed in the wrong direction. None
    of them can detect a calendar that is wrong about the world — only the
    ingest-time assertion against the feed does that.

    Args:
        cal: The loaded calendar.

    Raises:
        CalendarError: On any inconsistency.
    """
    if cal.clock_rule == "fixed":
        if cal.offset_summer != cal.offset_winter:
            raise CalendarError(
                "clock.rule is 'fixed' but the summer and winter offsets differ"
            )
    elif cal.offset_summer != cal.offset_winter + 1:
        raise CalendarError(
            f"a DST clock advances by exactly one hour, but winter="
            f"{cal.offset_winter} summer={cal.offset_summer}"
        )

    # The mismatch window is the US ahead of Europe, so boundaries sit one hour
    # EARLIER in server time. A calendar declaring them later has the sign
    # inverted — the single most likely hand-edit error in this file.
    for label, matched, mismatch in (
        ("daily_break_hour", cal.break_hour_matched, cal.break_hour_mismatch),
        ("weekly_close_hour", cal.close_hour_matched, cal.close_hour_mismatch),
    ):
        if cal.clock_rule == "eu" and mismatch != (matched - 1) % 24:
            raise CalendarError(
                f"session.{label}: under the EU rule the mismatch hour is one "
                f"BEFORE the matched hour, but matched={matched:02d} "
                f"mismatch={mismatch:02d}"
            )
        if cal.clock_rule == "us" and mismatch != matched:
            raise CalendarError(
                f"session.{label}: under the US rule the server moves with New "
                f"York, so the mismatch hour equals the matched hour, but "
                f"matched={matched:02d} mismatch={mismatch:02d}"
            )

    if cal.close_hour_matched != (cal.break_hour_matched - 1) % 24:
        raise CalendarError(
            f"the weekly close is the last bar before the daily break, so it "
            f"must be one hour earlier; break={cal.break_hour_matched:02d} "
            f"close={cal.close_hour_matched:02d}"
        )

    if not cal.holidays:
        raise CalendarError("holidays: empty. A vacuous calendar confirms nothing.")

    if not cal.eras:
        raise CalendarError(
            "session.eras: empty. The feed's session structure changed twice "
            "inside the evaluation window; a calendar that declares no eras is "
            "claiming a uniformity the data does not have."
        )

    # Ordered and strictly increasing, so era_for's linear scan is correct and
    # two eras cannot claim the same day.
    for previous, current in zip(cal.eras, cal.eras[1:], strict=False):
        if current.start <= previous.start:
            raise CalendarError(
                f"session.eras: starts must strictly increase, but "
                f"{previous.start} is followed by {current.start}"
            )
        if current.daily_break == previous.daily_break:
            raise CalendarError(
                f"session.eras: the era starting {current.start} declares the "
                f"same daily_break as the one before it. An era boundary that "
                f"changes nothing is either a typo or a missing field, and it "
                f"makes the count of eras meaningless."
            )

    if cal.eras[0].start > cal.window_start:
        raise CalendarError(
            f"session.eras: the first era starts {cal.eras[0].start}, after "
            f"window_start {cal.window_start}. Every in-window bar must fall "
            f"in a declared era or nothing knows what session it belongs to."
        )
