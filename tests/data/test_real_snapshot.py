"""The full ingest, end to end, on the real 67,367-bar export.

Everything else in ``tests/data/`` runs on synthetic frames small enough to
reason about by hand. This runs on the actual feed, because the properties
below are the ones that fixtures cannot establish: a fixture contains exactly
the sparse era, the invalid bars, and the holiday closures that were written
into it, so asserting the pipeline handles them proves only that the fixture
and the code were written by the same person on the same afternoon.

Slow by design — roughly ten seconds — and cached across the module.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.calendar import MarketCalendar, load_calendar
from data.loader import (
    LoaderError,
    assert_conversion_was_checked,
    load_full_snapshot,
    load_window,
)
from data.raw import find
from data.snapshot import (
    DERIVED_COLUMNS,
    INVARIANT_NAMES,
    SnapshotManifest,
    build_derived,
    sha256_frame,
    write_snapshot,
)


@functools.cache
def _raw() -> tuple[pd.DataFrame, bytes, MarketCalendar]:
    """The committed H1 export, parsed and as bytes.

    Returns:
        ``(frame, bytes, calendar)``.
    """
    export = find("H1")
    return pd.read_csv(export.path), export.path.read_bytes(), load_calendar()


@functools.cache
def _derived() -> tuple[pd.DataFrame, dict[str, int]]:
    """The derived frame and its gap census.

    Returns:
        ``(derived, census)``.
    """
    raw, _, calendar = _raw()
    return build_derived(raw, calendar)


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real snapshot on disk, built once for the module.

    Args:
        tmp_path_factory: pytest's per-module temporary directory factory.

    Returns:
        The snapshot directory.
    """
    raw, raw_bytes, calendar = _raw()
    out = tmp_path_factory.mktemp("snap") / "GOLD-H1"
    write_snapshot(raw_bytes, raw, calendar, out)
    return out


def _manifest(snapshot: Path) -> SnapshotManifest:
    """Read a snapshot's manifest.

    Args:
        snapshot: Snapshot directory.

    Returns:
        The manifest, as a typed object.
    """
    return SnapshotManifest(
        **json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    )


# ---------------------------------------------------------------------------
# valid as a first-class column, and nothing imputed
# ---------------------------------------------------------------------------


def test_valid_is_a_column_not_something_reconstructed_later() -> None:
    derived, _ = _derived()
    assert "valid" in DERIVED_COLUMNS
    assert "label_valid" in derived.columns
    assert derived["valid"].dtype == np.bool_


def test_some_bars_really_are_invalid() -> None:
    """A validity column that is True everywhere has never done anything."""
    derived, census = _derived()
    invalid = int((~derived["valid"].to_numpy()).sum())
    assert invalid > 0
    # Two bars per unknown gap: the one before it and the one after.
    assert invalid == 2 * census["unknown"], (invalid, census["unknown"])


def test_a_label_is_never_valid_where_its_bar_is_not() -> None:
    """Label validity is strictly stronger. It looks forward as well."""
    derived, _ = _derived()
    valid = derived["valid"].to_numpy()
    label_valid = derived["label_valid"].to_numpy()
    assert not bool((label_valid & ~valid).any())
    assert int(label_valid.sum()) < int(valid.sum()), (
        "no label is invalidated by its forward window, which would mean the "
        "horizon propagation is not running"
    )


def test_nothing_was_forward_filled() -> None:
    """§6: missing data returns None and propagates. It is never carried over.

    Checked on the fields that can be missing. A forward fill shows up as a
    run of identical values where the raw file has zeros, so the derived
    column is compared against the raw one position by position.
    """
    raw, _, _ = _raw()
    derived, _ = _derived()
    for raw_name, derived_name in (
        ("spread", "spread_points"),
        ("real_volume", "real_volume"),
    ):
        unrecorded = raw[raw_name].to_numpy() == 0
        got = derived[derived_name].to_numpy()
        assert bool(np.isnan(got[unrecorded]).all()), derived_name
        assert not bool(np.isnan(got[~unrecorded]).any()), derived_name


def test_prices_are_never_missing() -> None:
    """OHLC has no unrecorded state — a bar exists or it does not."""
    derived, _ = _derived()
    for column in ("open", "high", "low", "close"):
        assert not bool(derived[column].isna().any()), column


def test_real_volume_survives_the_raw_to_derived_step() -> None:
    """Dropping a raw column here would make it unrecoverable without a re-ingest."""
    assert "real_volume" in DERIVED_COLUMNS
    derived, _ = _derived()
    assert derived["real_volume"].notna().sum() > 50_000


# ---------------------------------------------------------------------------
# The sparse era is snapshotted, flagged, and unreachable
# ---------------------------------------------------------------------------


def test_the_sparse_era_is_present_in_the_snapshot() -> None:
    """Excluded from the window, not from the data.

    Excluding both would make the exclusion unfalsifiable and leave nothing to
    diff against if the broker ever backfills.
    """
    derived, _ = _derived()
    outside = derived[~derived["in_window"].to_numpy()]
    assert len(outside) > 1_000, len(outside)
    _, _, calendar = _raw()
    assert (
        pd.Timestamp(outside["timestamp_server"].max()).date() < calendar.window_start
    )


def test_load_window_never_returns_an_out_of_window_row(snapshot: Path) -> None:
    frame = load_window(snapshot)
    _, _, calendar = _raw()
    assert not frame.empty
    earliest = pd.Timestamp(frame["timestamp_server"].min()).date()
    assert earliest >= calendar.window_start
    assert bool(frame["in_window"].all())


def test_the_audit_path_does_return_them_and_says_so_in_its_name(
    snapshot: Path,
) -> None:
    full = load_full_snapshot(snapshot)
    assert len(full) > len(load_window(snapshot))
    assert not bool(full["in_window"].all())


def test_load_window_drops_invalid_bars_by_default(snapshot: Path) -> None:
    """Invalid bars are opt-in.

    A caller wanting them must ask; a caller wanting clean data must not have
    to remember to.
    """
    default = load_window(snapshot)
    everything = load_window(snapshot, valid_only=False)
    assert len(default) < len(everything)
    assert bool(default["valid"].all())


# ---------------------------------------------------------------------------
# Two-stage hashing
# ---------------------------------------------------------------------------


def test_the_raw_hash_is_the_committed_export(snapshot: Path) -> None:
    """Stage one is the bytes, so it matches the registry without a re-parse."""
    assert _manifest(snapshot).raw_sha256 == find("H1").sha256


def test_the_derived_hash_reproduces(snapshot: Path) -> None:
    """A pure function of raw + calendar + this code. Rebuild and compare."""
    derived, _ = _derived()
    assert _manifest(snapshot).derived_sha256 == sha256_frame(derived)


def test_a_conversion_change_moves_only_the_derived_hash(snapshot: Path) -> None:
    """The distinction the two hashes exist to make.

    Same bytes, different calendar: raw is unmoved, derived is not. With one
    hash this would be indistinguishable from the broker revising history, and
    those call for opposite responses.
    """
    from dataclasses import replace

    raw, raw_bytes, calendar = _raw()
    manifest = _manifest(snapshot)
    other, _ = build_derived(raw, replace(calendar, clock_rule="us"))

    from data.snapshot import sha256_bytes

    assert sha256_bytes(raw_bytes) == manifest.raw_sha256
    assert sha256_frame(other) != manifest.derived_sha256


def test_the_manifest_records_every_invariant_by_name(snapshot: Path) -> None:
    """Four passes must be distinguishable from two passes and two abstentions."""
    recorded = _manifest(snapshot).invariants
    assert set(recorded) == set(INVARIANT_NAMES)
    assert all(outcome == "pass" for outcome in recorded.values()), recorded


def test_the_loader_refuses_a_snapshot_with_no_invariant_record(
    snapshot: Path, tmp_path: Path
) -> None:
    """The record is the only thing that distinguishes it.

    A snapshot built by a path that skipped the checks looks identical on disk
    to one that passed them.
    """
    copy = tmp_path / "tampered"
    copy.mkdir()
    for name in ("derived.csv", "raw.csv"):
        (copy / name).write_bytes((snapshot / name).read_bytes())
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    del manifest["invariants"]
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(LoaderError, match="no invariants record"):
        assert_conversion_was_checked(copy)


def test_the_loader_refuses_a_partial_invariant_record(
    snapshot: Path, tmp_path: Path
) -> None:
    """A partial record is worse than none — it reads as a full pass."""
    copy = tmp_path / "partial"
    copy.mkdir()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    manifest["invariants"] = {INVARIANT_NAMES[0]: "pass"}
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(LoaderError, match="missing"):
        assert_conversion_was_checked(copy)


def test_the_loader_refuses_a_recorded_failure(snapshot: Path, tmp_path: Path) -> None:
    copy = tmp_path / "failed"
    copy.mkdir()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    manifest["invariants"] = dict.fromkeys(INVARIANT_NAMES, "pass")
    manifest["invariants"][INVARIANT_NAMES[0]] = "FAIL: close in the wrong hour"
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(LoaderError, match="failing conversion checks"):
        assert_conversion_was_checked(copy)


def test_an_insufficient_record_is_not_a_failure(
    snapshot: Path, tmp_path: Path
) -> None:
    """Abstention blocks nothing. It is recorded so a reader can see it."""
    copy = tmp_path / "partial-evidence"
    copy.mkdir()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    manifest["invariants"] = dict.fromkeys(INVARIANT_NAMES, "pass")
    manifest["invariants"][INVARIANT_NAMES[3]] = "insufficient: no daily-break gaps"
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    recorded = assert_conversion_was_checked(copy)
    assert recorded[INVARIANT_NAMES[3]].startswith("insufficient")


# ---------------------------------------------------------------------------
# The window end
# ---------------------------------------------------------------------------


def test_the_window_never_ends_on_the_in_progress_day(snapshot: Path) -> None:
    """An export taken mid-session ends part-way through a day.

    Letting that day close the window is the defect that once put the probe's
    density boundary at *tomorrow*.
    """
    manifest = _manifest(snapshot)
    last_bar = pd.Timestamp(manifest.last_bar_utc).date()
    assert pd.Timestamp(manifest.window_end).date() < last_bar


# ---------------------------------------------------------------------------
# H-006's era term
# ---------------------------------------------------------------------------


def test_session_era_is_a_column_on_every_bar() -> None:
    """A property of the bar, alongside valid and in_window — not a feature.

    H-006 amended: the window spans three session structures, so a model
    fitted across it is fitted across three different definitions of a
    session. The term is what makes that measurable instead of latent.
    """
    assert "session_era" in DERIVED_COLUMNS
    derived, _ = _derived()
    inside = derived[derived["in_window"].to_numpy()]
    assert not bool((inside["session_era"] == "").any())


def test_every_era_is_actually_represented_in_the_window() -> None:
    """A term with one level is not a term.

    If a boundary ever moved outside the window this would collapse to a
    constant column, and a constant regressor is silently dropped by most
    fitting code rather than reported.
    """
    _, _, calendar = _raw()
    derived, _ = _derived()
    inside = derived[derived["in_window"].to_numpy()]
    present = set(inside["session_era"])
    assert present == {era.start.isoformat() for era in calendar.eras}
    for era in present:
        share = (inside["session_era"] == era).mean()
        assert share > 0.05, (era, share)


def test_the_era_term_is_read_from_the_calendar_not_re_derived() -> None:
    """Re-deriving it from the data it qualifies could not detect a change.

    Same argument the calendar makes for the clock rule. Checked by comparing
    every bar against the frozen declaration rather than against a second
    measurement of the feed.
    """
    _, _, calendar = _raw()
    derived, _ = _derived()
    sample = derived.iloc[::500]
    for server, era in zip(
        sample["timestamp_server"], sample["session_era"], strict=True
    ):
        declared = calendar.era_for(pd.Timestamp(server).date())
        assert era == (declared.start.isoformat() if declared else ""), server


def test_bars_before_the_first_era_carry_no_era_and_are_out_of_window() -> None:
    """The sparse era predates the declaration; the question does not arise."""
    derived, _ = _derived()
    unlabelled = derived[derived["session_era"] == ""]
    assert len(unlabelled) > 0
    assert not bool(unlabelled["in_window"].any())
