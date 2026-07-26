"""Tests for the run manifest — REPRODUCIBILITY.md §5."""

import json
from pathlib import Path

import pytest

from data.synthetic import generate_ohlcv
from evaluation.manifest import (
    RunManifest,
    RunType,
    feature_set_version,
    file_sha256,
    frame_sha256,
)

BASE = {
    "run_id": "test-run",
    "timestamp_utc": "2026-07-26T00:00:00+00:00",
    "git_commit": "abc123",
    "git_dirty": False,
    "data_snapshot_sha256": "deadbeef",
    "data_window": {"start": "2020-01-01", "end": "2020-06-01"},
    "evaluation_mode": "walk_forward",
    "holdout_openings_remaining": 3,
    "cumulative_hypothesis_count_n_claims": 2,
    "feature_set_version": "cafe",
    "seeds": {"shuffled_labels": [0, 1]},
    "env_lock_sha256": "1234",
    "anonymisation_protocol": "none",
    "runtime_seconds": 1.0,
}


def _manifest(**overrides: object) -> RunManifest:
    return RunManifest(**{**BASE, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# run_type / hypothesis_id contract
# ---------------------------------------------------------------------------


def test_harness_validation_requires_null_hypothesis_id() -> None:
    manifest = _manifest(run_type=RunType.HARNESS_VALIDATION, hypothesis_id=None)

    assert manifest.hypothesis_id is None


def test_harness_validation_with_a_hypothesis_id_raises() -> None:
    """A synthetic run must never be citable as evidence for a hypothesis."""
    with pytest.raises(ValueError, match="never be cited"):
        _manifest(run_type=RunType.HARNESS_VALIDATION, hypothesis_id="H-001")


def test_evaluation_without_a_hypothesis_id_raises() -> None:
    """CLAUDE.md Hard Rule 3: runs without one are void."""
    with pytest.raises(ValueError, match="Hard Rule 3"):
        _manifest(run_type=RunType.EVALUATION, hypothesis_id=None)


def test_evaluation_from_a_dirty_tree_raises() -> None:
    """REPRODUCIBILITY.md §5: a dirty tree voids the run, no exceptions."""
    with pytest.raises(ValueError, match="dirty"):
        _manifest(run_type=RunType.EVALUATION, hypothesis_id="H-003", git_dirty=True)


def test_harness_validation_tolerates_a_dirty_tree() -> None:
    """It records the fact rather than blocking; it is not evidence anyway."""
    manifest = _manifest(
        run_type=RunType.HARNESS_VALIDATION, hypothesis_id=None, git_dirty=True
    )

    assert manifest.git_dirty is True


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_serialises_run_type_as_a_plain_string() -> None:
    manifest = _manifest(run_type=RunType.HARNESS_VALIDATION, hypothesis_id=None)

    payload = json.loads(manifest.to_json())

    assert payload["run_type"] == "harness_validation"
    assert payload["hypothesis_id"] is None


def test_writes_a_file_named_for_the_run(tmp_path: Path) -> None:
    manifest = _manifest(run_type=RunType.HARNESS_VALIDATION, hypothesis_id=None)

    path = manifest.write(tmp_path)

    assert path.name == "test-run.json"
    assert json.loads(path.read_text())["git_commit"] == "abc123"


def test_carries_every_reproducibility_section_5_field() -> None:
    payload = json.loads(
        _manifest(run_type=RunType.HARNESS_VALIDATION, hypothesis_id=None).to_json()
    )

    for key in (
        "run_id",
        "timestamp_utc",
        "git_commit",
        "git_dirty",
        "hypothesis_id",
        "data_snapshot_sha256",
        "data_window",
        "evaluation_mode",
        "holdout_openings_remaining",
        "feature_set_version",
        "seeds",
        "env_lock_sha256",
        "anonymisation_protocol",
        "runtime_seconds",
    ):
        assert key in payload, f"missing §5 field: {key}"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_frame_hash_is_stable_for_identical_data() -> None:
    a = generate_ohlcv(n_bars=200, seed=1)
    b = generate_ohlcv(n_bars=200, seed=1)

    assert frame_sha256(a) == frame_sha256(b)


def test_frame_hash_changes_when_any_value_changes() -> None:
    a = generate_ohlcv(n_bars=200, seed=1)
    b = a.copy()
    perturbed = b["close"].to_numpy(dtype="float64").copy()
    perturbed[100] += 1e-9
    b["close"] = perturbed

    assert frame_sha256(a) != frame_sha256(b)


def test_feature_set_version_depends_on_order() -> None:
    assert feature_set_version(("a", "b")) != feature_set_version(("b", "a"))


def test_file_hash_reports_absent_for_a_missing_file(tmp_path: Path) -> None:
    assert file_sha256(tmp_path / "nope.lock") == "absent"
