"""Build a derived snapshot from a committed raw export.

Run::

    uv run python scripts/build_snapshot.py            # H1, default location
    uv run python scripts/build_snapshot.py --timeframe M1

Reads ``data/raw/``, writes ``data/snapshots/<symbol>-<timeframe>-<derived
hash prefix>/``. The output directory is gitignored: a derived snapshot is a
pure function of the raw bytes, the frozen calendar, and ``src/data/``, all of
which are committed, so storing it would record the same information twice.
The manifest's ``derived_sha256`` is what makes the rebuild checkable.

What this refuses to do
-----------------------

Every gate is upstream of the write, so a snapshot that exists is a snapshot
that passed:

* the raw file must match its hash in ``src/data/raw.py``;
* the calendar must match ``RECORDED_CALENDAR_SHA256``;
* no two bars may convert to the same UTC instant;
* the four post-conversion invariants must not fail, and whichever of them
  could not run is recorded by name in the manifest;
* the directory must not already exist — ``DATA_CONTRACT.md`` §8 makes
  snapshots immutable, so a correction is a new one.

It does not check that the git tree is clean. That is CLAUDE.md rule 10 and it
belongs to the evaluation runner, not here: building a snapshot while
iterating is normal, citing one in a result is not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from data.calendar import load_calendar
from data.loader import assert_calendar_is_frozen
from data.raw import RawExportError, find, verify
from data.snapshot import write_snapshot

RULE = "=" * 74
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "snapshots"


def main(argv: list[str] | None = None) -> int:
    """Build one snapshot.

    Args:
        argv: Command-line arguments, for testing.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", default="H1", help="registered timeframe")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot root")
    args = parser.parse_args(argv)

    calendar = load_calendar()
    assert_calendar_is_frozen(calendar)

    export = find(args.timeframe)
    try:
        verify(export)
    except RawExportError as why:
        print(f"raw export guard failed:\n{why}", file=sys.stderr)
        return 1

    raw_bytes = export.path.read_bytes()
    raw = pd.read_csv(export.path)

    print(RULE)
    print(f"INGEST — {calendar.symbol} {export.timeframe} from {export.filename}")
    print(RULE)
    print(f"  raw rows        : {len(raw):,}")
    print(f"  calendar        : {calendar.sha256[:16]}…  rule={calendar.clock_rule}")
    print(f"  window opens    : {calendar.window_start}")
    print(f"  session eras    : {len(calendar.eras)}")
    for era in calendar.eras:
        print(f"      {era.start}  daily_break={era.daily_break!s:<5}  {era.note}")
    print()

    # Named from the derived hash, so two runs that produce the same frame
    # collide by name rather than silently accumulating near-duplicates.
    from data.snapshot import build_derived, sha256_frame

    preview, _ = build_derived(raw, calendar)
    out_dir = (
        args.out / f"{calendar.symbol}-{export.timeframe}-{sha256_frame(preview)[:12]}"
    )
    if out_dir.exists():
        print(f"  {out_dir} already exists — this exact frame has been built.")
        print("  Snapshots are immutable (DATA_CONTRACT §8). Nothing to do.")
        return 0

    manifest = write_snapshot(raw_bytes, raw, calendar, out_dir)

    print(f"  written to      : {out_dir}")
    print()
    print("-- two-stage hashes " + "-" * 54)
    print(f"  raw_sha256      : {manifest.raw_sha256}")
    print(f"  derived_sha256  : {manifest.derived_sha256}")
    print("     Two, not one. Raw moving means the broker revised history;")
    print("     derived moving alone means our conversion changed. Those need")
    print("     opposite responses and one hash cannot tell them apart.")
    print()
    print("-- window " + "-" * 64)
    print(f"  rows total      : {manifest.rows_total:,}")
    print(f"  rows in window  : {manifest.rows_in_window:,}")
    print(f"  valid in window : {manifest.rows_valid_in_window:,}")
    print(
        f"  labels valid    : {manifest.labels_valid_in_window:,} "
        f"(horizon {manifest.label_horizon_bars} bars)"
    )
    print(f"  window          : {manifest.window_start} .. {manifest.window_end}")
    print()
    print("-- gap census " + "-" * 60)
    for cause, count in sorted(manifest.gap_census.items(), key=lambda kv: -kv[1]):
        print(f"  {cause:>16s} : {count:,}")
    print("     Only `unknown` invalidates data. Everything else is the market")
    print("     being shut, which is not missing data.")
    print()
    print("-- post-conversion invariants " + "-" * 44)
    for name, outcome in manifest.invariants.items():
        print(f"  {name:<24s} : {outcome}")
    print("     Recorded per check, not summarised. A check that could not run")
    print("     says so by name, so four passes cannot be confused with two")
    print("     passes and two abstentions.")
    print(RULE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
