"""Run manifest emitter — ``REPRODUCIBILITY.md`` §5.

    Emitted for every run. Without it, the result does not exist.

``run_type`` extends the §5 schema. It exists so that a run against synthetic
data can never be mistaken, later, for evidence about the real pipeline:

- ``evaluation`` — a run that may be cited as evidence for a hypothesis.
  Requires a ``hypothesis_id`` (``CLAUDE.md`` Hard Rule 3) and a clean tree.
- ``harness_validation`` — a run that evaluates *code*, not a trading claim.
  Carries ``hypothesis_id: null`` by construction and may never be cited as
  evidence for any hypothesis.

The distinction is enforced here rather than left to discipline: constructing
an ``evaluation`` manifest without a hypothesis id, or a
``harness_validation`` manifest with one, raises.
"""

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd


class RunType(StrEnum):
    """Whether a run may be cited as evidence."""

    EVALUATION = "evaluation"
    HARNESS_VALIDATION = "harness_validation"


@dataclass(frozen=True, slots=True)
class RunManifest:
    """A record sufficient to reproduce a run, per ``REPRODUCIBILITY.md`` §5."""

    run_id: str
    timestamp_utc: str
    git_commit: str
    git_dirty: bool
    run_type: RunType
    hypothesis_id: str | None
    data_snapshot_sha256: str
    data_window: dict[str, str]
    evaluation_mode: str
    holdout_openings_remaining: int
    cumulative_hypothesis_count_n_claims: int
    feature_set_version: str
    seeds: dict[str, Any]
    env_lock_sha256: str
    anonymisation_protocol: str
    runtime_seconds: float
    notes: str = ""
    llm: dict[str, Any] | None = field(default=None)

    def __post_init__(self) -> None:
        """Enforce the run_type / hypothesis_id contract.

        Raises:
            ValueError: If the pairing is invalid, or an evaluation run was
                produced from a dirty tree.
        """
        if self.run_type is RunType.EVALUATION:
            if not self.hypothesis_id:
                raise ValueError(
                    "an evaluation run requires a hypothesis_id — CLAUDE.md "
                    "Hard Rule 3: runs without one are void"
                )
            if self.git_dirty:
                raise ValueError(
                    "git_dirty is true — REPRODUCIBILITY.md §5: a dirty tree "
                    "voids the run, no exceptions"
                )
        elif self.hypothesis_id is not None:
            raise ValueError(
                f"a harness_validation run must carry hypothesis_id: null, "
                f"got {self.hypothesis_id!r}. It evaluates code, not a trading "
                f"claim, and may never be cited as evidence for a hypothesis."
            )

    def to_json(self) -> str:
        """Serialise to indented JSON.

        Returns:
            The manifest as a JSON string.
        """
        payload = asdict(self)
        payload["run_type"] = self.run_type.value
        return json.dumps(payload, indent=2, sort_keys=True)

    def write(self, directory: Path) -> Path:
        """Write the manifest under ``directory``.

        Args:
            directory: Destination directory; created if absent.

        Returns:
            The path written.
        """
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.run_id}.json"
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path


def frame_sha256(df: pd.DataFrame) -> str:
    """Content-hash a bar series.

    A stand-in for the snapshot hashing of ``DATA_CONTRACT.md`` §8 until a real
    data layer exists. It hashes the actual float bytes and the index, so any
    change to the data changes the hash.

    Args:
        df: Frame to hash.

    Returns:
        Hex sha256 digest.
    """
    digest = hashlib.sha256()
    for column in sorted(df.columns):
        digest.update(column.encode("utf-8"))
        digest.update(df[column].to_numpy(dtype="float64").tobytes())
    digest.update(df.index.astype("int64").to_numpy().tobytes())
    return digest.hexdigest()


def feature_set_version(names: tuple[str, ...]) -> str:
    """Hash the ordered feature set so a manifest pins what was computed.

    Args:
        names: Feature names, in the column order used.

    Returns:
        Hex sha256 digest.
    """
    return hashlib.sha256("|".join(names).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """Hash a file's bytes.

    Args:
        path: File to hash.

    Returns:
        Hex sha256 digest, or ``"absent"`` if the file does not exist.
    """
    if not path.exists():
        return "absent"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str:
    """Return HEAD's commit hash, or ``"unknown"`` outside a repository."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return out.stdout.strip()


def git_dirty() -> bool:
    """Return whether the working tree has uncommitted changes."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return True
    return bool(out.stdout.strip())
