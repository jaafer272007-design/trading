"""Measure the feed's session eras, and check the calendar declares them.

Run::

    uv run python scripts/report_session_eras.py

This is the measurement behind ``session.eras`` in ``calendar/gold_fxpro.yaml``.
It exists so that block is reproducible rather than asserted: the calendar is a
declaration about the world, and a declaration nobody can re-derive is a claim
nobody can check.

What it measures
----------------

The number of bars on each server day. Nothing else — no conversion, no
timezone, no assumption about what a timestamp means. A day with 24 bars has no
whole-hour break; a day with 23 has one, and the missing hour says where.

Friday and Sunday are excluded throughout. The week ends early on one and
starts late on the other, so both carry 23 bars for reasons that have nothing
to do with the daily break. Including them puts a phantom era boundary on
every Friday, which is how the first pass at this got 2022-10-21 wrong.

What it cannot see
------------------

A break shorter than an hour. H1 bars cannot resolve one, and the M1 export
covers only 2026-04 onward — entirely inside the third era. So "no break" here
means *no whole-hour break*, and the report says so rather than claiming more
than the resolution supports.

Reads only ``data/raw/``. Writes nothing.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data.calendar import load_calendar
from data.raw import find

RULE = "=" * 74
FULL_DAY_BARS = 24
BREAK_DAY_BARS = 23
MID_WEEK = (0, 1, 2, 3)  # Monday to Thursday

#: Shortest run of days that may be called an era rather than an anomaly.
MIN_ERA_DAYS = 30


def bars_per_server_day(path: Path) -> dict[date, set[int]]:
    """Which server hours carry a bar, per server day.

    Args:
        path: A raw MT5 export.

    Returns:
        Server date to the set of hours present.
    """
    hours: dict[date, set[int]] = defaultdict(set)
    with path.open(encoding="utf-8") as handle:
        next(handle)
        for line in handle:
            epoch = int(line.split(",", 1)[0])
            # The epoch is a server wall-clock reading; divmod recovers the
            # clock face directly and needs no timezone at all.
            days, seconds = divmod(epoch, 86_400)
            hours[date(1970, 1, 1) + timedelta(days=days)].add(seconds // 3600)
    return dict(hours)


def main() -> int:
    """Print the era measurement.

    Returns:
        0 if the measurement agrees with the calendar, 1 otherwise.
    """
    calendar = load_calendar()
    hours = bars_per_server_day(find("H1").path)
    days = sorted(d for d in hours if d >= calendar.window_start)

    print(RULE)
    print("SESSION ERAS — does this feed have a daily break, and when?")
    print(RULE)
    print(f"  in-window server days: {len(days):,}   from {days[0]} to {days[-1]}")
    print()

    histogram = Counter(len(hours[d]) for d in days)
    print("  bars per server day (all days):")
    for count in sorted(histogram):
        print(f"     {count:2d} bars : {histogram[count]:6,} days")
    print()

    # US/EU mismatch windows are excluded, not merged away afterwards. On
    # those days the server clock and New York disagree by an hour, and a
    # whole server hour goes missing in EVERY era — so a mismatch day carries
    # no information about which era it is in. Leaving them in fragments the
    # no-break era into eleven pieces separated by phantom "BREAK" runs, which
    # is what the first version of this script reported.
    graded = [
        (d, len(hours[d]))
        for d in days
        if d.weekday() in MID_WEEK
        and len(hours[d]) in (BREAK_DAY_BARS, FULL_DAY_BARS)
        and not calendar.calendars_disagree(d)
    ]
    mismatch_dropped = sum(
        1
        for d in days
        if d.weekday() in MID_WEEK
        and len(hours[d]) in (BREAK_DAY_BARS, FULL_DAY_BARS)
        and calendar.calendars_disagree(d)
    )
    print(f"  Mon-Thu days carrying 23 or 24 bars: {len(graded):,}")
    print(f"     (excluding {mismatch_dropped:,} in US/EU mismatch windows)")
    print(f"     24 bars (no break) : {sum(1 for _, n in graded if n == 24):,}")
    print(f"     23 bars (a break)  : {sum(1 for _, n in graded if n == 23):,}")
    print()

    runs = _coalesce(_runs(graded), min_days=MIN_ERA_DAYS)

    print(f"  contiguous runs, after absorbing runs shorter than {MIN_ERA_DAYS} days:")
    for start_day, end_day, no_break, n in runs:
        label = "NO BREAK" if no_break else "BREAK   "
        print(f"     {label}  {start_day} .. {end_day}   {n:>4} days")
    print()
    print("  Absorbing short runs is not cosmetic. A single anomalous day —")
    print("  2021-01-21 carries a one-hour hole at 16:00 server, the only")
    print("  unexplained gap left in the census — otherwise splits the middle")
    print("  era in two and makes the feed look like it has four eras.")
    print()

    declared = [e.start for e in calendar.eras]
    print(RULE)
    print(f"  calendar declares : {[str(d) for d in declared]}")
    boundaries = [run[0] for run in runs]
    print(f"  measurement finds : {[str(d) for d in boundaries]}")
    agree = _boundaries_agree(declared, boundaries)
    if agree:
        print(
            "  AGREE — every declared boundary is within a weekend of a measured one."
        )
        print(RULE)
        return 0
    print("  DISAGREE. The feed changed its session structure, or the calendar")
    print("  is wrong about it. Do not edit calendar/gold_fxpro.yaml to match")
    print("  this output without establishing which — that edit is exactly what")
    print("  the frozen-calendar guard exists to force a human to think about.")
    print(RULE)
    return 1


Run = tuple[date, date, bool, int]


def _runs(graded: list[tuple[date, int]]) -> list[Run]:
    """Group consecutive days by whether they carry a break.

    Args:
        graded: ``(day, bar_count)`` pairs, ascending.

    Returns:
        ``(start, end, no_break, days)`` per run.
    """
    out: list[Run] = []
    for day, count in graded:
        no_break = count == FULL_DAY_BARS
        if out and out[-1][2] == no_break:
            first, _, state, n = out[-1]
            out[-1] = (first, day, state, n + 1)
        else:
            out.append((day, day, no_break, 1))
    return out


def _coalesce(runs: list[Run], min_days: int) -> list[Run]:
    """Absorb runs too short to be an era into their surroundings.

    A single odd day should not split an era. Repeatedly drops the shortest
    sub-threshold run and merges whatever it was separating, until only runs
    long enough to be real remain.

    Args:
        runs: Output of :func:`_runs`.
        min_days: Shortest run that may stand on its own.

    Returns:
        The coalesced runs.
    """
    working = list(runs)
    while True:
        short = [i for i, run in enumerate(working) if run[3] < min_days]
        if not short or len(working) == 1:
            return working
        index = min(short, key=lambda i: working[i][3])
        working.pop(index)
        merged: list[Run] = []
        for run in working:
            if merged and merged[-1][2] == run[2]:
                first, _, state, n = merged[-1]
                merged[-1] = (first, run[1], state, n + run[3])
            else:
                merged.append(run)
        working = merged


def _boundaries_agree(declared: list[date], measured: list[date]) -> bool:
    """Whether the declared era starts match the measured ones.

    Compared with a three-day tolerance: a boundary falls on a weekend, so the
    first *observed* day of a new era can be up to three days after the day the
    change actually took effect.

    Args:
        declared: Era starts from the calendar.
        measured: Run starts from this measurement.

    Returns:
        True if the two agree in count and position.
    """
    if len(declared) != len(measured):
        return False
    return all(abs((a - b).days) <= 3 for a, b in zip(declared, measured, strict=True))


if __name__ == "__main__":
    raise SystemExit(main())
