"""Report the cross-timeframe convention proof.

Run::

    uv run python scripts/prove_aggregation.py

The measurement itself lives in ``src/data/aggregate.py`` and is pinned by
``tests/data/test_aggregation.py``. This script only prints it, because a
number quoted in a report should be reproducible by the person reading the
report — ``REPRODUCIBILITY.md`` §9 requires every quantitative claim to carry
its provenance, and ``MEASURED`` means someone can re-run this and get the
same figure.

Reads only ``data/raw/``. Writes nothing.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data.aggregate import (
    HOUR_SECONDS,
    MIN_DECISIVE_BARS,
    MINUTE_SECONDS,
    compare_readings,
    load_bars,
    scan_offsets,
)
from data.raw import find

RULE = "=" * 74


def server(epoch: int) -> str:
    """Format a server epoch as the wall-clock reading it is.

    Args:
        epoch: MT5 ``time`` value.

    Returns:
        ``YYYY-MM-DD HH:MM`` on the **server's** clock, not UTC.
    """
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    """Print the proof.

    Returns:
        Process exit code: 0 if the verdict is determined, 1 if not.
    """
    h1 = load_bars(find("H1").path)
    m1 = load_bars(find("M1").path)

    print(RULE)
    print("CROSS-TIMEFRAME CONVENTION PROOF — what does a bar's timestamp mean?")
    print(RULE)
    print(f"  H1 {len(h1):>7,} bars   {server(h1.epoch[0])} .. {server(h1.epoch[-1])}")
    print(f"  M1 {len(m1):>7,} bars   {server(m1.epoch[0])} .. {server(m1.epoch[-1])}")
    print("  (server wall-clock; the proof needs no timezone and uses none)")
    print()

    result = compare_readings(h1, m1)

    print("-- eligibility " + "-" * 59)
    print(f"  overlap tested : {server(result.overlap_first)} .. ", end="")
    print(server(result.overlap_last))
    print(f"  eligible bars  : {result.eligible:,}")
    print(f"  DECISIVE bars  : {result.decisive:,}  (minimum {MIN_DECISIVE_BARS:,})")
    print("     Read this first. A reading can only be shown wrong on a bar")
    print("     where it predicts something its rival does not; a clean sweep")
    print("     across bars that cannot separate them proves nothing.")
    print()

    for name, r in result.results.items():
        print(f"-- {name}: {r.meaning}")
        print(f"     tested {r.tested:,}   empty window {r.empty:,}")
        print(f"     OHLC exact  : {r.ohlc_match:,} / {r.tested:,}")
        print(
            f"     full hours  : {r.full_hour_ohlc_match:,} / {r.full_hour_tested:,} "
            f"(exactly 60 constituent minutes)"
        )
        fields = "  ".join(f"{k}={v:,}" for k, v in r.field_match.items())
        print(f"     per field   : {fields}")
        for m in r.mismatches[:2]:
            print(f"       e.g. {server(m.epoch)} n={m.constituents} wrong={m.fields}")
        print()

    print("-- ruling out a convention nobody proposed " + "-" * 31)
    rows = scan_offsets(h1, m1, step=MINUTE_SECONDS, span=2 * HOUR_SECONDS, sample=400)
    print("     For what shift k does H1[t] == aggregate of M1 in [t+k, t+k+3600)?")
    for shift, matches, tested in rows[:4]:
        tag = "  <- LEFT" if shift == 0 else ""
        if shift == -HOUR_SECONDS + MINUTE_SECONDS:
            tag = "  <- RIGHT"
        print(f"       {shift:+6d}s : {matches:>4,} / {tested:,}{tag}")
    print(f"     shifts with any match at all: {sum(1 for r in rows if r[1] > 0)}")
    print()

    print(RULE)
    verdict = result.verdict
    if verdict is None:
        print("VERDICT: UNDETERMINED — HALT")
        print()
        print("  The measurement did not separate the readings. Do not proceed to")
        print("  conversion, and do not break the tie with vendor documentation:")
        print("  the entire reason this proof exists is that the documentation is")
        print("  not evidence about THIS feed.")
        print(RULE)
        return 1

    print(f"VERDICT: {verdict}")
    winner = result.results[verdict]
    print(f"  {winner.meaning}")
    print()
    print(f"  {winner.ohlc_match:,} of {winner.tested:,} eligible bars reproduced")
    print(f"  exactly, on {result.decisive:,} bars that genuinely separate the two")
    print("  readings, with no tolerance anywhere: prices are compared as exact")
    print("  scaled integers.")
    print(RULE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
