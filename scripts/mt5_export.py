r"""MT5 raw exporter — dumps bytes, interprets nothing.

.. important::

   **This script converts nothing.** Server timestamps are written exactly as
   MetaTrader hands them over: the raw epoch integer, untouched. No timezone
   conversion, no filtering, no gap classification, no column renaming, no
   sorting beyond what the terminal returns.

   That is the whole design. Every interpretation happens inside the
   repository, in ``src/data/``, where it is version-controlled, type-checked,
   reviewed, and covered by convention-proof tests. Nothing that runs on the
   Windows box gets to make a judgement, because nothing that runs there can
   be tested by CI.

   If you find yourself wanting to "just fix up" a timestamp here, that is the
   bug. ``DATA_CONTRACT.md`` §4 calls a one-bar convention mismatch a leak,
   and an ad-hoc fixup on an untested machine is exactly how one arrives.

What it writes
--------------

One CSV per run, plus a ``.sha256`` sidecar over the exact bytes::

    GOLD-H1-<first>-<last>.csv
    GOLD-H1-<first>-<last>.csv.sha256
    GOLD-H1-<first>-<last>.meta.json

The CSV columns are MT5's own, in MT5's own order and units:

    time,open,high,low,close,tick_volume,spread,real_volume

``time`` is **server wall-clock expressed as a Unix epoch** — the number MT5
gives, which looks like UTC and is not. ``src/data/convert.py`` is the only
place that difference is resolved.

The sidecar hash is what ``src/data/snapshot.py`` records as ``raw_sha256``.
Raw changing across two ingests means the broker revised history; derived
changing while raw holds still means our conversion logic changed. Those need
opposite responses, which is why both are hashed.

Requirements
------------

- Windows. The ``MetaTrader5`` package ships only ``win_amd64`` wheels.
- A running MT5 terminal, logged in, with the symbol in Market Watch.
- ``pip install MetaTrader5``

Credentials are never read, never printed, never stored. The account login is
masked in the metadata file.

Usage::

    python mt5_export.py --symbol GOLD --out D:\\mt5_export
    python mt5_export.py --symbol GOLD --out D:\\mt5_export --timeframe M1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

COLUMNS: Final = (
    "time",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
)

#: MT5 caps a single copy_rates_range call. Chunking by year keeps each call
#: well inside it and makes a partial failure obvious rather than silent.
CHUNK_DAYS: Final = 365

EARLIEST_SEARCH_YEAR: Final = 2000


def require_windows_mt5() -> Any:
    """Import MetaTrader5, failing with a useful message if impossible.

    Returns:
        The imported module.

    Raises:
        SystemExit: If the platform or package is unavailable.
    """
    if platform.system() != "Windows":
        print("FATAL: this exporter must run on Windows.")
        print("  The MetaTrader5 package ships only win_amd64 wheels and")
        print(f"  declares Platform: Windows. Detected: {platform.system()}.")
        raise SystemExit(2)
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except ImportError:
        print("FATAL: MetaTrader5 is not installed.")
        print("  Run:  pip install MetaTrader5")
        raise SystemExit(2) from None
    return mt5


def fetch_all(
    mt5: Any, symbol: str, timeframe: int, label: str
) -> list[tuple[Any, ...]]:
    """Pull every bar the terminal will serve, oldest first.

    Chunked and de-duplicated by timestamp. Overlapping chunk boundaries are
    normal; a duplicate timestamp carrying *different* values is not, and is
    reported rather than silently resolved. Picking one of two disagreeing
    bars is an interpretation, and interpretation does not happen here.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        timeframe: MT5 timeframe constant.
        label: Human-readable timeframe name, for progress output.

    Returns:
        One tuple per bar, in :data:`COLUMNS` order.

    Raises:
        SystemExit: If two bars share a timestamp but disagree.
    """
    now = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=2)
    start = datetime(EARLIEST_SEARCH_YEAR, 1, 1)

    by_time: dict[int, tuple[Any, ...]] = {}
    cursor = start
    print(f"  fetching {label} ", end="", flush=True)
    while cursor < now:
        stop = min(cursor + timedelta(days=CHUNK_DAYS), now)
        rates = mt5.copy_rates_range(symbol, timeframe, cursor, stop)
        if rates is not None and len(rates):
            for row in rates:
                key = int(row["time"])
                value = tuple(row[c] for c in COLUMNS)
                seen = by_time.get(key)
                if seen is not None and seen != value:
                    print()
                    print(f"FATAL: two different bars at epoch {key}:")
                    print(f"  {seen}")
                    print(f"  {value}")
                    print("  The feed disagrees with itself. DATA_CONTRACT §6")
                    print("  says log both and halt; resolving it here would be")
                    print("  an interpretation, and this script makes none.")
                    raise SystemExit(3)
                by_time[key] = value
            print(".", end="", flush=True)
        cursor = stop
    print(f" {len(by_time):,} bars")
    return [by_time[k] for k in sorted(by_time)]


def to_csv_bytes(rows: list[tuple[Any, ...]]) -> bytes:
    """Render rows to CSV bytes, deterministically.

    Explicit newline and no locale-dependent formatting: the bytes are hashed,
    so anything that varies by machine would make the same data look like
    different data.

    Args:
        rows: Bars in :data:`COLUMNS` order.

    Returns:
        UTF-8 CSV bytes, LF line endings.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [
                int(row[0]),
                repr(float(row[1])),
                repr(float(row[2])),
                repr(float(row[3])),
                repr(float(row[4])),
                int(row[5]),
                int(row[6]),
                int(row[7]),
            ]
        )
    return buffer.getvalue().encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    """Export one timeframe and write its hash sidecar.

    Args:
        argv: Command line, or ``None`` for ``sys.argv``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Raw MT5 bar export. Converts nothing.",
    )
    parser.add_argument("--symbol", default="GOLD")
    parser.add_argument("--timeframe", default="H1", choices=["H1", "M1"])
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)

    mt5 = require_windows_mt5()
    if not mt5.initialize():
        print(f"FATAL: mt5.initialize() failed: {mt5.last_error()}")
        return 2

    try:
        if mt5.symbol_info(args.symbol) is None:
            print(f"FATAL: symbol {args.symbol!r} not found on this account.")
            return 2
        mt5.symbol_select(args.symbol, True)

        timeframe = mt5.TIMEFRAME_H1 if args.timeframe == "H1" else mt5.TIMEFRAME_M1
        rows = fetch_all(mt5, args.symbol, timeframe, args.timeframe)
        if not rows:
            print("FATAL: no bars returned.")
            return 2

        payload = to_csv_bytes(rows)
        digest = hashlib.sha256(payload).hexdigest()

        first, last = int(rows[0][0]), int(rows[-1][0])
        stem = (
            f"{args.symbol}-{args.timeframe}-"
            f"{datetime.fromtimestamp(first, tz=UTC):%Y%m%d}-"
            f"{datetime.fromtimestamp(last, tz=UTC):%Y%m%d}"
        )
        out_dir = Path(args.out).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        csv_path = out_dir / f"{stem}.csv"
        if csv_path.exists():
            print(f"FATAL: {csv_path} already exists. Exports are never")
            print("  overwritten — a correction is a new file, not an edit.")
            return 3

        csv_path.write_bytes(payload)
        (out_dir / f"{stem}.csv.sha256").write_text(
            f"{digest}  {csv_path.name}\n", encoding="utf-8"
        )

        account, terminal = mt5.account_info(), mt5.terminal_info()
        version = mt5.version()
        info = mt5.symbol_info(args.symbol)
        (out_dir / f"{stem}.meta.json").write_text(
            json.dumps(
                {
                    "record": "mt5_raw_export",
                    "exported_host_utc": datetime.now(UTC).isoformat(),
                    "symbol": args.symbol,
                    "timeframe": args.timeframe,
                    "rows": len(rows),
                    "first_epoch_server": first,
                    "last_epoch_server": last,
                    "timestamps": "server wall-clock as unix epoch; NOT UTC",
                    "converted": False,
                    "sha256": digest,
                    "account_server": getattr(account, "server", None),
                    "account_company": getattr(account, "company", None),
                    "account_login": "masked",
                    "terminal_build": version[1] if version else None,
                    "terminal_name": getattr(terminal, "name", None),
                    "symbol_digits": getattr(info, "digits", None),
                    "symbol_point": getattr(info, "point", None),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        print()
        print(f"  wrote {csv_path}")
        print(f"  rows      {len(rows):,}")
        print(f"  sha256    {digest}")
        print()
        print("  Timestamps are SERVER wall-clock. Nothing here is converted.")
        print("  Ingest with the repository's snapshot builder; do not read")
        print("  this file directly into anything.")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
