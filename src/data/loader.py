"""The only way a feature gets a bar, and the boundary it cannot cross.

H-006 condition (iv) is the one that does the work: **bars outside the
declared window are absent from the loaded frame, not filtered downstream.**
Filtering late leaves a window that is whatever survived the last filter, which
is the silent truncation the gate exists to prevent. Excluding at load makes
the window a property of the data, so a feature cannot quietly widen it: there
is nothing there to widen it to.

The sparse era is on disk and unreachable
-----------------------------------------

``src/data/snapshot.py`` stores every bar the broker gave us, including the
2008-2015 one-bar-a-day era, flagged ``in_window=False``. That is deliberate:
the exclusion stays auditable and a future backfill stays diffable. This module
is the wall. :func:`load_window` never returns those rows, and
:func:`load_full_snapshot` — which does — exists only for audit and says so in
its name.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.calendar import (
    RECORDED_CALENDAR_SHA256,
    CalendarError,
    MarketCalendar,
    load_calendar,
)
from data.snapshot import read_manifest


class LoaderError(RuntimeError):
    """A snapshot cannot be loaded under the declared window."""


def assert_calendar_is_frozen(calendar: MarketCalendar) -> None:
    """Refuse to load if the calendar file has moved.

    The freeze that makes the calendar a declaration rather than a
    suggestion. The correct response to this failing is never to paste in the
    new hash: it is to establish whether the broker changed, and to record
    that decision.

    Args:
        calendar: The loaded calendar.

    Raises:
        CalendarError: If the file hash differs from the recorded one.
    """
    if calendar.sha256 != RECORDED_CALENDAR_SHA256:
        raise CalendarError(
            f"calendar/gold_fxpro.yaml changed.\n"
            f"  recorded: {RECORDED_CALENDAR_SHA256}\n"
            f"  on disk:  {calendar.sha256}\n"
            f"This file declares how every timestamp is interpreted. Confirm "
            f"what changed in the world before updating the recorded hash; "
            f"updating it to silence this is the defect the guard exists to "
            f"prevent."
        )


def assert_snapshot_matches_calendar(
    snapshot_dir: Path, calendar: MarketCalendar
) -> None:
    """Refuse to load a snapshot derived under a different calendar.

    A derived frame is only meaningful under the calendar that produced it. A
    snapshot built when the clock rule said ``us`` and read back when it says
    ``eu`` is off by an hour in a way nothing downstream can see.

    Args:
        snapshot_dir: Snapshot directory.
        calendar: The frozen calendar.

    Raises:
        LoaderError: If the manifest is absent or names a different calendar.
    """
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise LoaderError(
            f"{manifest_path}: missing. A snapshot without a manifest has no "
            f"provenance and is void (DATA_CONTRACT §8)."
        )
    recorded = read_manifest(manifest_path).get("calendar_sha256")
    if recorded != calendar.sha256:
        raise LoaderError(
            f"{snapshot_dir} was derived under calendar {recorded}, but the "
            f"calendar on disk is {calendar.sha256}. Re-derive the snapshot; "
            f"do not read it under a calendar it was not built with."
        )


def load_full_snapshot(snapshot_dir: Path) -> pd.DataFrame:
    """Load every row, including out-of-window bars: audit use only.

    Named to be hard to reach for by accident. Nothing in the evaluation path
    may call this: it returns the sparse era, whose bars cannot carry a 24-bar
    label and whose presence in a design matrix would be invisible.

    Args:
        snapshot_dir: Snapshot directory.

    Returns:
        Every row in the derived frame.

    Raises:
        LoaderError: If the derived frame is absent.
    """
    derived_path = snapshot_dir / "derived.csv"
    if not derived_path.exists():
        raise LoaderError(f"{derived_path}: missing")
    return pd.read_csv(derived_path, parse_dates=["timestamp_utc", "timestamp_server"])


def load_window(
    snapshot_dir: Path,
    *,
    calendar: MarketCalendar | None = None,
    valid_only: bool = True,
) -> pd.DataFrame:
    """Load the bars a feature is allowed to see.

    Three gates, all before the caller gets anything: the calendar is frozen,
    the snapshot was derived under it, and out-of-window rows are dropped
    rather than flagged.

    Args:
        snapshot_dir: Snapshot directory.
        calendar: The frozen calendar. Loaded from disk if omitted.
        valid_only: Drop bars marked invalid under §6. Default on — a caller
            that wants invalid bars must say so, rather than a caller that
            wants clean data having to remember to ask.

    Returns:
        In-window rows, indexed by ``timestamp_utc``, sorted.

    Raises:
        LoaderError: If the window is empty, or the frame still carries
            out-of-window rows after filtering.
    """
    cal = calendar if calendar is not None else load_calendar()
    assert_calendar_is_frozen(cal)
    assert_snapshot_matches_calendar(snapshot_dir, cal)

    frame = load_full_snapshot(snapshot_dir)
    frame = frame[frame["in_window"].astype(bool)]
    if valid_only:
        frame = frame[frame["valid"].astype(bool)]

    if frame.empty:
        raise LoaderError(
            f"{snapshot_dir}: no rows inside the window starting "
            f"{cal.window_start}. An empty window is a configuration error, "
            f"not a small sample."
        )

    earliest = pd.Timestamp(frame["timestamp_server"].min()).date()
    if earliest < cal.window_start:
        raise LoaderError(
            f"{snapshot_dir}: a row dated {earliest} survived window "
            f"filtering, before window_start {cal.window_start}. The "
            f"in_window flag disagrees with the calendar."
        )

    return frame.set_index("timestamp_utc").sort_index()
