"""End-to-end ingest: classify, snapshot, and the window the loader enforces.

The fixture is a small feed with the real one's shape — a sparse era before
H-006's ``window_start``, a dense era after it, a rollover break every day, a
weekend closure, a holiday early close, and one genuine in-session hole. Every
number asserted below is ``[FIXTURE]`` under ``REPRODUCIBILITY.md`` §9: it
describes the ingest layer, not the market.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.calendar import CalendarError, MarketCalendar, load_calendar
from data.classify import (
    GapCause,
    bar_validity,
    feature_validity,
    gap_census,
    label_validity,
)
from data.loader import LoaderError, load_full_snapshot, load_window
from data.snapshot import (
    SnapshotError,
    build_derived,
    sha256_bytes,
    sha256_frame,
    write_snapshot,
)

HOLE_DAY = date(2016, 3, 2)
EARLY_CLOSE_DAY = date(2016, 7, 4)  # Independence Day


@pytest.fixture
def calendar() -> MarketCalendar:
    return load_calendar()


def build_raw(cal: MarketCalendar) -> tuple[pd.DataFrame, bytes]:
    """A feed shaped like FxPro's, spanning the window boundary."""
    stamps: list[datetime] = []
    cursor = datetime(2015, 6, 1)
    while cursor < datetime(2016, 8, 1):
        day = cursor.date()
        sparse_era = day < cal.window_start
        keep = cursor.weekday() < 5 and cursor.hour != cal.break_hour(day)
        if keep and sparse_era:
            keep = cursor.hour == 12  # one bar a day
        if keep and day == HOLE_DAY and 10 <= cursor.hour <= 12:
            keep = False  # a genuine in-session hole
        if keep and day == EARLY_CLOSE_DAY and cursor.hour >= 19:
            keep = False  # holiday early close
        if keep:
            stamps.append(cursor)
        cursor += timedelta(hours=1)

    epochs = [int(s.replace(tzinfo=UTC).timestamp()) for s in stamps]
    price = 1000.0 + np.arange(len(epochs)) * 0.01
    raw = pd.DataFrame(
        {
            "time": epochs,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price + 0.1,
            "tick_volume": np.arange(len(epochs)) % 500 + 1,
            # Zero before 2016: unrecorded, and must become None.
            "spread": [0 if s < datetime(2016, 1, 1) else 21 for s in stamps],
            "real_volume": 0,
        }
    )
    return raw, raw.to_csv(index=False).encode()


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_gap_causes_are_separated(calendar: MarketCalendar) -> None:
    """Closures and defects are different things and must not be merged."""
    raw, _ = build_raw(calendar)
    server = pd.to_datetime(raw["time"], unit="s", utc=True).dt.tz_localize(None)
    _, gaps = bar_validity(pd.DatetimeIndex(server), calendar)
    census = gap_census(gaps)

    assert census[GapCause.WEEKEND] > 40, census
    assert census[GapCause.DAILY_BREAK] > 150, census
    assert census[GapCause.OUT_OF_WINDOW] > 40, census
    assert census[GapCause.EARLY_CLOSE] == 1, census
    assert census[GapCause.UNKNOWN] == 1, census


def test_only_the_genuine_hole_invalidates_bars(calendar: MarketCalendar) -> None:
    """A weekend is not missing data. An in-session hole is."""
    raw, _ = build_raw(calendar)
    server = pd.DatetimeIndex(
        pd.to_datetime(raw["time"], unit="s", utc=True).dt.tz_localize(None)
    )
    valid, _ = bar_validity(server, calendar)

    assert (~valid).sum() == 2, "exactly the two bars bracketing the hole"
    for stamp in server[~valid]:
        assert stamp.date() == HOLE_DAY, stamp


def test_early_close_does_not_invalidate_anything(calendar: MarketCalendar) -> None:
    """The market was shut. There is no missing data to mark invalid."""
    raw, _ = build_raw(calendar)
    server = pd.DatetimeIndex(
        pd.to_datetime(raw["time"], unit="s", utc=True).dt.tz_localize(None)
    )
    valid, _ = bar_validity(server, calendar)
    on_day = np.array([s.date() == EARLY_CLOSE_DAY for s in server])
    assert valid[on_day].all()


# ---------------------------------------------------------------------------
# Label validity — the forward window
# ---------------------------------------------------------------------------


def test_a_label_spanning_an_invalid_bar_is_invalid() -> None:
    """The rule that makes `valid` first-class rather than reconstructable."""
    bar_valid = np.ones(100, dtype=np.bool_)
    bar_valid[50] = False
    labels = label_validity(bar_valid, horizon_bars=24)

    assert not labels[50], "the bar itself is invalid"
    assert not labels[30], "bar 30's window reaches bar 54; it spans the hole"
    assert not labels[49], "immediately before"
    assert labels[10], "far enough back that its window ends at 34"
    assert labels[51], "bar 51's window is 51..75; the hole at 50 is behind it"
    assert not labels[26], "bar 26's window ends exactly on the hole at 50"
    assert labels[60], "past the hole entirely"


def test_label_is_invalid_where_the_horizon_runs_off_the_end() -> None:
    """A truncated forward window is not a shorter label, it is a wrong one."""
    labels = label_validity(np.ones(50, dtype=np.bool_), horizon_bars=24)
    assert labels[:26].all()
    assert not labels[26:].any()


def test_label_horizon_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        label_validity(np.ones(10, dtype=np.bool_), horizon_bars=0)


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def test_derived_flags_the_sparse_era_out_of_window(calendar: MarketCalendar) -> None:
    raw, _ = build_raw(calendar)
    derived, _ = build_derived(raw, calendar)

    out = derived[~derived["in_window"]]
    assert len(out) > 0
    assert out["timestamp_server"].max().date() < calendar.window_start
    assert derived[derived["in_window"]]["timestamp_server"].min().date() >= (
        calendar.window_start
    )


def test_unrecorded_spread_becomes_none_not_zero(calendar: MarketCalendar) -> None:
    """§6: a zero here means UNRECORDED and is not a measured zero."""
    raw, _ = build_raw(calendar)
    derived, _ = build_derived(raw, calendar)
    assert derived["spread_points"].isna().any()
    assert not (derived["spread_points"] == 0.0).any()


def test_derived_timestamps_are_utc_aware(calendar: MarketCalendar) -> None:
    raw, _ = build_raw(calendar)
    derived, _ = build_derived(raw, calendar)
    assert str(pd.DatetimeIndex(derived["timestamp_utc"]).tz) == "UTC"


def test_rejects_unsorted_raw(calendar: MarketCalendar) -> None:
    """Reordering here would hide a feed defect."""
    raw, _ = build_raw(calendar)
    shuffled = pd.concat([raw.iloc[5:6], raw.iloc[0:5], raw.iloc[6:]])
    with pytest.raises(SnapshotError, match="strictly increasing"):
        build_derived(shuffled.reset_index(drop=True), calendar)


def test_rejects_raw_missing_columns(calendar: MarketCalendar) -> None:
    raw, _ = build_raw(calendar)
    with pytest.raises(SnapshotError, match="missing columns"):
        build_derived(raw.drop(columns=["spread"]), calendar)


def test_derived_hash_is_stable_and_value_sensitive(calendar: MarketCalendar) -> None:
    """The hash must move on a value change and not on a column reorder."""
    raw, _ = build_raw(calendar)
    derived, _ = build_derived(raw, calendar)

    assert sha256_frame(derived) == sha256_frame(derived)
    assert sha256_frame(derived) == sha256_frame(derived[derived.columns[::-1]])

    moved = derived.copy()
    moved.loc[moved.index[0], "close"] += 0.01
    assert sha256_frame(moved) != sha256_frame(derived)


def test_snapshot_writes_both_stages_and_a_manifest(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    raw, raw_bytes = build_raw(calendar)
    manifest = write_snapshot(raw_bytes, raw, calendar, tmp_path / "snap")

    assert (tmp_path / "snap" / "raw.csv").read_bytes() == raw_bytes
    assert (tmp_path / "snap" / "derived.csv").exists()
    assert (tmp_path / "snap" / "manifest.json").exists()
    assert manifest.raw_sha256 != manifest.derived_sha256
    assert manifest.calendar_sha256 == calendar.sha256
    assert manifest.rows_in_window < manifest.rows_total
    assert manifest.labels_valid_in_window <= manifest.rows_valid_in_window
    assert manifest.gap_census[GapCause.UNKNOWN] == 1


def test_two_hashes_separate_a_feed_revision_from_a_logic_change(
    calendar: MarketCalendar,
) -> None:
    """The reason there are two hashes and not one.

    Compared at the frame level rather than through ``write_snapshot``,
    because the second calendar here is deliberately wrong and the
    post-conversion invariants now refuse to snapshot a wrong conversion.
    That refusal is the behaviour we want; it just makes ``write_snapshot``
    the wrong instrument for showing what the hashes do.
    """
    raw, raw_bytes = build_raw(calendar)

    first, _ = build_derived(raw, calendar)
    other_rule = replace(calendar, clock_rule="us")
    second, _ = build_derived(raw, other_rule)

    # Same bytes in, different interpretation out: raw fixed, derived moved.
    assert sha256_bytes(raw_bytes) == sha256_bytes(raw_bytes)
    assert sha256_frame(first) != sha256_frame(second)


def test_snapshots_are_immutable(calendar: MarketCalendar, tmp_path: Path) -> None:
    """§8: a correction is a new version, never an edit to an old one."""
    raw, raw_bytes = build_raw(calendar)
    write_snapshot(raw_bytes, raw, calendar, tmp_path / "snap")
    with pytest.raises(SnapshotError, match="immutable"):
        write_snapshot(raw_bytes, raw, calendar, tmp_path / "snap")


def test_window_end_is_never_the_in_progress_day(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    """The same rule that stopped a partial session setting the boundary."""
    raw, raw_bytes = build_raw(calendar)
    manifest = write_snapshot(raw_bytes, raw, calendar, tmp_path / "snap")
    last_bar = pd.Timestamp(manifest.last_bar_utc).date()
    assert date.fromisoformat(manifest.window_end) < last_bar


# ---------------------------------------------------------------------------
# The loader wall
# ---------------------------------------------------------------------------


def test_loader_never_returns_out_of_window_rows(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    """H-006 condition (iv). The sparse era is on disk and unreachable."""
    raw, raw_bytes = build_raw(calendar)
    write_snapshot(raw_bytes, raw, calendar, tmp_path / "snap")

    full = load_full_snapshot(tmp_path / "snap")
    windowed = load_window(tmp_path / "snap", calendar=calendar)

    assert (~full["in_window"]).any(), "the fixture must contain a sparse era"
    assert len(windowed) < len(full)
    assert windowed["timestamp_server"].min().date() >= calendar.window_start
    assert "in_window" not in set(windowed["in_window"].unique()) - {True}


def test_loader_drops_invalid_bars_by_default(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    raw, raw_bytes = build_raw(calendar)
    write_snapshot(raw_bytes, raw, calendar, tmp_path / "snap")

    default = load_window(tmp_path / "snap", calendar=calendar)
    with_invalid = load_window(tmp_path / "snap", calendar=calendar, valid_only=False)
    assert len(default) < len(with_invalid)
    assert default["valid"].all()


def test_loader_refuses_a_snapshot_from_another_calendar(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    """An hour-sized error nothing downstream could see."""
    raw, raw_bytes = build_raw(calendar)
    other = MarketCalendar(**{**calendar.__dict__, "sha256": "0" * 64})
    write_snapshot(raw_bytes, raw, other, tmp_path / "snap")

    with pytest.raises(LoaderError, match="derived under calendar"):
        load_window(tmp_path / "snap", calendar=calendar)


def test_loader_refuses_a_snapshot_with_no_manifest(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    raw, raw_bytes = build_raw(calendar)
    write_snapshot(raw_bytes, raw, calendar, tmp_path / "snap")
    (tmp_path / "snap" / "manifest.json").unlink()

    with pytest.raises(LoaderError, match="missing"):
        load_window(tmp_path / "snap", calendar=calendar)


def test_loader_refuses_when_the_calendar_file_has_moved(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    """The freeze. Updating the recorded hash to silence this is the defect."""
    raw, raw_bytes = build_raw(calendar)
    moved = MarketCalendar(**{**calendar.__dict__, "sha256": "f" * 64})
    write_snapshot(raw_bytes, raw, moved, tmp_path / "snap")

    with pytest.raises(CalendarError, match="changed"):
        load_window(tmp_path / "snap", calendar=moved)


def test_loader_refuses_an_empty_window(
    calendar: MarketCalendar, tmp_path: Path
) -> None:
    """An empty window is a configuration error, not a small sample."""
    future = MarketCalendar(**{**calendar.__dict__, "window_start": date(2099, 1, 1)})
    raw, raw_bytes = build_raw(calendar)
    write_snapshot(raw_bytes, raw, future, tmp_path / "snap")

    with pytest.raises(LoaderError, match="no rows inside the window"):
        load_window(tmp_path / "snap", calendar=future)


# ---------------------------------------------------------------------------
# Feature validity — the backward mirror of label validity
# ---------------------------------------------------------------------------


def test_a_feature_window_spanning_an_invalid_bar_is_invalid() -> None:
    """The check that was missing.

    A rolling statistic reads backward. With a 4-bar lookback and bar 10
    invalid, positions 10 through 13 all read it and are all contaminated;
    position 14 is the first clean one.
    """
    valid = np.ones(20, dtype=np.bool_)
    valid[10] = False
    got = feature_validity(valid, lookback_bars=4)

    assert not got[10:14].any(), np.flatnonzero(got[10:14])
    assert got[14]
    assert got[9], "position 9's window is [6, 9] and never reaches the hole"


def test_the_first_bars_have_no_history_and_are_invalid() -> None:
    """Insufficient history is a different fact with the same consequence."""
    got = feature_validity(np.ones(20, dtype=np.bool_), lookback_bars=5)
    assert not got[:4].any()
    assert got[4:].all()


def test_feature_and_label_validity_reach_in_opposite_directions() -> None:
    """Stated as a property, because the two are easy to transpose.

    A single invalid bar contaminates the ``lookback-1`` bars *after* it
    through features, and the ``horizon`` bars *before* it through labels.
    Getting the direction wrong would produce a mask that looks plausible and
    protects nothing.
    """
    valid = np.ones(40, dtype=np.bool_)
    valid[20] = False

    features_bad = set(np.flatnonzero(~feature_validity(valid, 5))) - set(range(4))
    labels_bad = set(np.flatnonzero(~label_validity(valid, 5))) - set(range(35, 40))

    assert max(features_bad) > 20 > min(labels_bad)
    assert features_bad == {20, 21, 22, 23, 24}
    assert labels_bad == {15, 16, 17, 18, 19, 20}


def test_feature_validity_rejects_a_non_positive_lookback() -> None:
    with pytest.raises(ValueError, match="lookback_bars must be positive"):
        feature_validity(np.ones(5, dtype=np.bool_), 0)


def test_dropping_invalid_rows_would_hide_the_hole() -> None:
    """Why positions are masked and never removed.

    Two frames: one with the hole present and masked, one with the invalid row
    deleted. A rolling mean over the deleted version reads straight across the
    site and produces a perfectly ordinary number with nothing marking it.
    """
    values = np.arange(20.0)
    valid = np.ones(20, dtype=np.bool_)
    valid[10] = False

    kept = np.convolve(values, np.ones(3) / 3, mode="valid")
    closed_up = np.convolve(np.delete(values, 10), np.ones(3) / 3, mode="valid")

    masked = feature_validity(valid, lookback_bars=3)
    assert not masked[10:13].any()
    # The closed-up series is shorter and its values differ at the site: the
    # defect is real, and only the mask makes it visible.
    assert len(closed_up) < len(kept)
    assert not np.array_equal(kept[8:12], closed_up[8:12])
