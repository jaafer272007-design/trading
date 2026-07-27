"""Two-stage snapshots: raw as exported, derived as interpreted.

``DATA_CONTRACT.md`` §8 requires every evaluation to run against a versioned,
content-hashed, immutable snapshot. This module builds two of them per ingest
and hashes both, because one hash cannot answer the question that matters when
a result stops reproducing.

Why two hashes and not one
--------------------------

============================  ============================================
raw changes, derived changes  **The broker revised history.** Nothing in
                              this repository moved. Investigate the feed.
raw fixed, derived changes    **Our conversion logic changed.** The world is
                              unchanged and we are reading it differently.
                              Investigate the diff.
raw changes, derived fixed    Cosmetic change upstream — different column
                              order, different export tooling — that our
                              reader normalises away. Worth knowing.
neither changes               Reproducible.
============================  ============================================

With a single hash the first two are indistinguishable, and they call for
opposite responses. This is the same reasoning as the append-only hash chain in
``scripts/capture_ticks.py``: the cheap thing is to record one number, and the
useful thing is to record which of two independent stages moved.

What "raw" means here
---------------------

Exactly what ``scripts/mt5_export.py`` wrote, byte for byte: server timestamps
untouched, no conversion, no filtering, no column renaming. The export step
interprets nothing — all interpretation happens in this repository where it is
tested and reviewable. The raw hash is over the exported bytes, not over a
parse of them, so it is stable against any change in how we read the file.

The sparse era is present in both stages
----------------------------------------

H-006 excludes 2008 to 2015-09 from the evaluation window. It is **snapshotted
anyway**, flagged ``in_window=False``. Excluding without snapshotting would
make the exclusion unfalsifiable later: there would be nothing to diff against
if the broker ever backfills, and no way to show a reviewer what was left out.
``src/data/loader.py`` is what refuses to hand out those rows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from data.calendar import MarketCalendar
from data.classify import bar_validity, gap_census, label_validity

#: Columns the derived frame carries, in order. Fixed so a hash over the frame
#: is stable against dict ordering.
DERIVED_COLUMNS: Final = (
    "timestamp_utc",
    "timestamp_server",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread_points",
    "valid",
    "in_window",
)

DEFAULT_LABEL_HORIZON_BARS: Final = 24


class SnapshotError(RuntimeError):
    """A snapshot cannot be built or does not match its manifest."""


@dataclass(frozen=True)
class SnapshotManifest:
    """Provenance for one ingest, recorded beside the data.

    Every field is either measured from the snapshot or copied from the frozen
    calendar. Nothing here is an estimate (``REPRODUCIBILITY.md`` §9).
    """

    created_utc: str
    symbol: str
    server_name: str
    raw_sha256: str
    derived_sha256: str
    calendar_sha256: str
    window_start: str
    window_end: str
    rows_total: int
    rows_in_window: int
    rows_valid_in_window: int
    labels_valid_in_window: int
    label_horizon_bars: int
    gap_census: dict[str, int]
    first_bar_utc: str
    last_bar_utc: str

    def to_json(self) -> str:
        """Serialise deterministically.

        Returns:
            Sorted-key JSON with a trailing newline.
        """
        return json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"


def sha256_bytes(payload: bytes) -> str:
    """Hash raw bytes.

    Args:
        payload: Bytes to hash.

    Returns:
        Lowercase hex SHA-256.
    """
    return hashlib.sha256(payload).hexdigest()


def sha256_frame(frame: pd.DataFrame) -> str:
    """Hash a derived frame by value, not by file layout.

    Serialised through a fixed column order and an explicit textual
    representation rather than a binary dump: a Parquet or pickle hash moves
    when the writer's version moves, which would make every library upgrade
    look like a data change and train people to ignore the guard.

    Args:
        frame: The derived frame.

    Returns:
        Lowercase hex SHA-256.

    Raises:
        SnapshotError: If a required column is absent.
    """
    missing = [c for c in DERIVED_COLUMNS if c not in frame.columns]
    if missing:
        raise SnapshotError(f"derived frame is missing columns: {missing}")
    ordered = frame[list(DERIVED_COLUMNS)]
    return sha256_bytes(ordered.to_csv(index=False, float_format="%.10g").encode())


def build_derived(
    raw: pd.DataFrame,
    calendar: MarketCalendar,
    *,
    label_horizon_bars: int = DEFAULT_LABEL_HORIZON_BARS,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Interpret a raw export: convert, classify, flag.

    This is the only place raw broker output becomes something a feature may
    read, and every judgement it makes comes from the frozen calendar rather
    than from the data in front of it.

    Args:
        raw: As exported — ``time`` (server epoch seconds), ``open``,
            ``high``, ``low``, ``close``, ``tick_volume``, ``spread``.
        calendar: The frozen calendar.
        label_horizon_bars: Forward window for label validity.

    Returns:
        ``(derived, census)``.

    Raises:
        SnapshotError: If required columns are absent or the rows are not
            sorted by time.
    """
    required = {"time", "open", "high", "low", "close", "tick_volume", "spread"}
    missing = required - set(raw.columns)
    if missing:
        raise SnapshotError(f"raw export is missing columns: {sorted(missing)}")

    epochs = raw["time"].to_numpy(dtype=np.int64)
    if len(epochs) > 1 and not bool(np.all(np.diff(epochs) > 0)):
        raise SnapshotError(
            "raw export is not strictly increasing in time. Deduplicate and "
            "sort at export; reordering here would hide a feed defect."
        )

    from data.convert import (
        assert_no_ambiguous_timestamps,
        server_epoch_to_naive,
        to_utc,
    )

    server = server_epoch_to_naive(epochs)
    assert_no_ambiguous_timestamps(server, calendar)
    utc = to_utc(server, calendar)

    valid, gaps = bar_validity(server, calendar)
    in_window = np.array([ts.date() >= calendar.window_start for ts in server])

    # §6: a zero in the spread field means UNRECORDED, and is not
    # distinguishable from a real zero by value. It becomes None in both eras.
    spread = raw["spread"].astype("float64").to_numpy().copy()
    spread[spread == 0.0] = np.nan

    derived = pd.DataFrame(
        {
            "timestamp_utc": utc,
            "timestamp_server": server,
            "open": raw["open"].astype("float64").to_numpy(),
            "high": raw["high"].astype("float64").to_numpy(),
            "low": raw["low"].astype("float64").to_numpy(),
            "close": raw["close"].astype("float64").to_numpy(),
            "tick_volume": raw["tick_volume"].astype("int64").to_numpy(),
            "spread_points": spread,
            "valid": valid,
            "in_window": in_window,
        }
    )
    derived["label_valid"] = label_validity(valid, label_horizon_bars)
    return derived, gap_census(gaps)


def write_snapshot(
    raw_bytes: bytes,
    raw: pd.DataFrame,
    calendar: MarketCalendar,
    out_dir: Path,
    *,
    label_horizon_bars: int = DEFAULT_LABEL_HORIZON_BARS,
) -> SnapshotManifest:
    """Write both stages and their manifest.

    Args:
        raw_bytes: The exported file exactly as written on Windows.
        raw: That file parsed.
        calendar: The frozen calendar.
        out_dir: Snapshot directory. Created if absent; refuses to overwrite.
        label_horizon_bars: Forward window for label validity.

    Returns:
        The manifest, already written to disk.

    Raises:
        SnapshotError: If the directory already holds a snapshot. §8 makes
            snapshots immutable — a correction is a new version, never an
            edit to an old one.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path, derived_path = out_dir / "raw.csv", out_dir / "derived.csv"
    manifest_path = out_dir / "manifest.json"
    for existing in (raw_path, derived_path, manifest_path):
        if existing.exists():
            raise SnapshotError(
                f"{existing} already exists. Snapshots are immutable "
                f"(DATA_CONTRACT §8); write a new version instead."
            )

    derived, census = build_derived(
        raw, calendar, label_horizon_bars=label_horizon_bars
    )
    in_window = derived["in_window"].to_numpy()

    raw_path.write_bytes(raw_bytes)
    derived.to_csv(derived_path, index=False, float_format="%.10g")

    utc = pd.DatetimeIndex(derived["timestamp_utc"])
    manifest = SnapshotManifest(
        created_utc=datetime.now(UTC).isoformat(),
        symbol=calendar.symbol,
        server_name=calendar.server_name,
        raw_sha256=sha256_bytes(raw_bytes),
        derived_sha256=sha256_frame(derived),
        calendar_sha256=calendar.sha256,
        window_start=calendar.window_start.isoformat(),
        window_end=_last_complete_day(utc[in_window]).isoformat()
        if in_window.any()
        else "",
        rows_total=len(derived),
        rows_in_window=int(in_window.sum()),
        rows_valid_in_window=int((derived["valid"].to_numpy() & in_window).sum()),
        labels_valid_in_window=int(
            (derived["label_valid"].to_numpy() & in_window).sum()
        ),
        label_horizon_bars=label_horizon_bars,
        gap_census=census,
        first_bar_utc=utc[0].isoformat() if len(utc) else "",
        last_bar_utc=utc[-1].isoformat() if len(utc) else "",
    )
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    return manifest


def _last_complete_day(utc: pd.DatetimeIndex) -> date:
    """The last day the snapshot covers in full.

    Never the final calendar day present: an export taken mid-session ends
    part-way through a day, and letting that day close the window is the same
    defect that put the probe's density boundary at *today*.

    Args:
        utc: UTC timestamps, sorted.

    Returns:
        The last complete day.
    """
    if len(utc) == 0:
        raise SnapshotError("cannot determine window_end from an empty snapshot")
    return (pd.Timestamp(utc[-1].date()) - pd.Timedelta(days=1)).date()


def read_manifest(path: Path) -> dict[str, Any]:
    """Read a snapshot manifest.

    Args:
        path: Manifest file.

    Returns:
        Its fields.
    """
    return dict(json.loads(path.read_text(encoding="utf-8")))
