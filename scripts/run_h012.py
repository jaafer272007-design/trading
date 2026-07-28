"""H-012 — does any deterministic feature set carry directional information?

Ten features, eleven parameters, three horizons, one claim with a mandatory
ablation. Everything reported here was registered in ``HYPOTHESES.md`` H-012
at commit ``64141a7``, before this file existed.

What is run, per horizon in ``{4, 24, 120}``:

1. the **baseline** — H-001's three features, four parameters;
2. the **full set** — ten features, eleven parameters;
3. the **ablation** — each of the seven new features added individually to the
   baseline, seven arms, per §F mandatory because widening the feature set is
   also a capacity change and the two are otherwise inseparable;
4. the **K-1 re-measurement** the capacity guard forces at eleven parameters;
5. **always-long attribution** in probability space, per §E;
6. **convergence** per configuration.

Paired by construction
----------------------

Eligibility is computed once from the **full ten-feature design** and used by
every arm, so the baseline and the full set decide on identical rows in
identical order. The per-decision Brier improvement is then a paired
difference and the bootstrap is the one H-003 §F registered.

The fitting rule is the registered frozen 1,000 iterations. It is reached
through ``ConvergentLogisticRegression(tolerance=0.0, max_iter=1000)``, which
``tests/models/test_convergent.py`` pins as **bit-identical** to
``LogisticRegression(n_iter=1000)`` — the same rule, through a class that also
reports the gradient norm at the parameters it returns.

Usage::

    uv run python scripts/run_h012.py data/snapshots/<dir>
"""

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_h001 import FIRST_TEST_FRACTION, N_FOLDS, _fold_geometry

from backtest.metrics import bootstrap_mean
from data.loader import load_window
from evaluation.manifest import (
    RunManifest,
    RunType,
    feature_set_version,
    file_sha256,
    frame_sha256,
    git_commit,
    git_dirty,
)
from evaluation.pipeline import LeakMode, run_walk_forward
from evaluation.shuffle import SHUFFLED_LABEL_SEEDS, run_shuffled_label_study
from evaluation.splits import Fold, assert_no_leakage, walk_forward_folds
from features.atr_distance import AtrDistance
from features.base import Feature
from features.drawdown_from_max import DrawdownFromMax
from features.log_return import LogReturn
from features.range_position import RangePosition
from features.realized_vol import RealizedVol
from features.reversal import Reversal
from features.vol_scaled_return import VolScaledReturn
from features.volume_weighted_return import VolumeWeightedReturn
from labels.direction import labels_for_snapshot
from models.convergent import ConvergentLogisticRegression

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
OUTPUT: Final = REPO_ROOT / "runs" / "h012_feature_slice.json"

HORIZONS: Final = (4, 24, 120)
"""H-012 §I, fixed before the run."""

K6_FLOOR: Final = 150
BSS_FLOOR: Final = 0.010
"""H-012 §A (i)."""

BH_THRESHOLD: Final = 0.05 / 6.0
"""H-012 §J: rank 1 at N_claims = 6. 0.008333..."""

BLOCK_LENGTHS: Final = (1, 10, 25)
REGISTERED_BLOCK: Final = 10
N_RESAMPLES: Final = 10_000
BOOTSTRAP_SEED: Final = 1337
FROZEN_ITERATIONS: Final = 1_000

BASELINE: Final[tuple[Feature, ...]] = (
    LogReturn(window=24),
    RealizedVol(window=24),
    RangePosition(window=48),
)
"""H-001's three features. Four parameters."""

ADDED: Final[tuple[Feature, ...]] = (
    LogReturn(window=120),
    LogReturn(window=480),
    VolScaledReturn(window=120),
    Reversal(window=4),
    AtrDistance(window=480, atr_period=14),
    DrawdownFromMax(window=480),
    VolumeWeightedReturn(window=24),
)
"""H-012 §B's seven priors, in registered order."""

FULL: Final[tuple[Feature, ...]] = BASELINE + ADDED


class FrozenBudget(ConvergentLogisticRegression):
    """The registered fitting rule, with diagnostics.

    ``tolerance=0.0`` never triggers, so this takes exactly
    :data:`FROZEN_ITERATIONS` steps and is bit-identical to
    ``LogisticRegression(n_iter=1000)`` — asserted by
    ``tests/models/test_convergent.py``. The only difference is that it
    reports the gradient infinity-norm at the parameters it returns, which is
    how convergence is reported per configuration without changing the rule.
    """

    def __init__(self) -> None:
        """Initialise at the registered budget."""
        super().__init__(tolerance=0.0, max_iter=FROZEN_ITERATIONS)


@dataclass(frozen=True, slots=True)
class ArmResult:
    """One fitted configuration."""

    name: str
    n_features: int
    fitted_parameters: int
    bss: float
    per_decision_brier: npt.NDArray[np.float64]
    per_fold_bss: tuple[float, ...]
    long_share: float
    directional_accuracy: float
    converged: bool | None
    worst_gradient_norm: float | None


def build_matrix(
    frame: pd.DataFrame, features: tuple[Feature, ...]
) -> npt.NDArray[np.float64]:
    """Compute a design matrix from a feature tuple.

    Args:
        frame: In-window snapshot rows.
        features: Features, in order.

    Returns:
        The design matrix, aligned to ``frame`` rows.
    """
    return np.column_stack(
        [f.compute(frame).to_numpy(dtype=np.float64) for f in features]
    )


def run_arm(
    name: str,
    design: npt.NDArray[np.float64],
    labels: npt.NDArray[np.float64],
    folds: tuple[Fold, ...],
    n_features: int,
) -> ArmResult:
    """Fit one configuration and score it.

    Args:
        name: Arm label.
        design: Design matrix restricted to this arm's columns.
        labels: True labels.
        folds: Walk-forward folds.
        n_features: Column count, for the record.

    Returns:
        The scored arm.
    """
    result = run_walk_forward(design, labels, folds, model_factory=FrozenBudget)

    per_fold = tuple(
        float(
            1.0
            - np.mean((f.probabilities - f.outcomes) ** 2)
            / np.mean((np.mean(f.outcomes) - f.outcomes) ** 2)
        )
        if np.mean((np.mean(f.outcomes) - f.outcomes) ** 2) > 0
        else float("nan")
        for f in result.fold_results
    )

    calls_long = result.probabilities > 0.5
    return ArmResult(
        name=name,
        n_features=n_features,
        fitted_parameters=result.fitted_parameters,
        bss=result.bss,
        per_decision_brier=(result.probabilities - result.outcomes) ** 2,
        per_fold_bss=per_fold,
        long_share=float(np.mean(calls_long)),
        directional_accuracy=float(np.mean(calls_long == (result.outcomes > 0.5))),
        converged=result.converged,
        worst_gradient_norm=result.worst_gradient_norm,
    )


def paired_test(baseline: ArmResult, arm: ArmResult) -> dict[str, object]:
    """Bootstrap the per-decision Brier improvement of ``arm`` over ``baseline``.

    Args:
        baseline: The three-feature arm.
        arm: The arm under test.

    Returns:
        One record per block length, plus the observed mean.
    """
    improvement = baseline.per_decision_brier - arm.per_decision_brier
    out: dict[str, object] = {"mean_improvement": float(np.mean(improvement))}
    for block in BLOCK_LENGTHS:
        boot = bootstrap_mean(
            improvement,
            expected_block=float(block),
            n_resamples=N_RESAMPLES,
            seed=BOOTSTRAP_SEED,
        )
        out[f"block_{block}"] = {
            "p_one_sided": boot.p_value_one_sided,
            "ci_low": boot.ci_low,
            "ci_high": boot.ci_high,
        }
    return out


def main() -> int:
    """Run H-012 and print the report.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="snapshot directory")
    args = parser.parse_args()

    started = time.monotonic()
    frame = load_window(args.snapshot, valid_only=False)
    n_bars = len(frame)
    first_test_start, test_size = _fold_geometry(n_bars, N_FOLDS)

    print("=" * 78)
    print("H-012 — DOES ANY DETERMINISTIC FEATURE SET CARRY DIRECTION?")
    print("=" * 78)
    print(f"snapshot ......... {args.snapshot}")
    print(f"in-window bars ... {n_bars:,}")
    print(f"baseline ......... {', '.join(f.name for f in BASELINE)}")
    print(f"added ............ {', '.join(f.name for f in ADDED)}")
    print(f"BSS floor ........ {BSS_FLOOR:+.3f}   BH threshold {BH_THRESHOLD:.5f}")
    print()

    print("computing designs ...", flush=True)
    full_design = build_matrix(frame, FULL)
    bar_valid = frame["valid"].to_numpy(dtype=np.bool_)
    print(f"  full design {full_design.shape}", flush=True)

    from data.classify import feature_validity, label_validity

    longest = max(f.lookback_bars for f in FULL)
    feature_ok = feature_validity(bar_valid, longest) & np.isfinite(full_design).all(
        axis=1
    )

    records: list[dict[str, object]] = []
    for horizon in HORIZONS:
        labels = labels_for_snapshot(frame, horizon).to_numpy(dtype=np.float64)
        eligible = feature_ok & label_validity(bar_valid, horizon) & ~np.isnan(labels)
        folds = walk_forward_folds(
            valid=eligible,
            n_folds=N_FOLDS,
            first_test_start=first_test_start,
            test_size=test_size,
            horizon=horizon,
        )
        assert_no_leakage(folds, horizon=horizon)

        clean_design = np.nan_to_num(full_design)
        clean_labels = np.nan_to_num(labels)
        per_fold_n = [f.test.size for f in folds]
        pooled_n = sum(per_fold_n)
        below_k6 = [f.index for f in folds if f.test.size < K6_FLOOR]

        print("-" * 78)
        print(f"H = {horizon}   pooled n = {pooled_n:,}   per fold {per_fold_n}")
        if below_k6:
            print(
                f"  *** FOLDS BELOW K-6: {below_k6} — per-fold NOT reportable; "
                f"H-012 §C: pooled-only at this horizon ***"
            )
        print("-" * 78, flush=True)

        baseline = run_arm("baseline_3", clean_design[:, :3], clean_labels, folds, 3)
        full = run_arm("full_10", clean_design, clean_labels, folds, len(FULL))

        arms = [baseline, full]
        # Ablation — each added feature alone, on top of the baseline.
        for i, feature in enumerate(ADDED):
            columns = [0, 1, 2, 3 + i]
            arms.append(
                run_arm(
                    f"+{feature.name}",
                    clean_design[:, columns],
                    clean_labels,
                    folds,
                    4,
                )
            )

        base_rate = float(
            np.mean(clean_labels[np.concatenate([f.test for f in folds])])
        )
        for arm in arms:
            paired = paired_test(baseline, arm) if arm.name != "baseline_3" else None
            p10 = (
                paired[f"block_{REGISTERED_BLOCK}"]["p_one_sided"]  # type: ignore[index]
                if paired
                else None
            )
            records.append(
                {
                    "horizon": horizon,
                    "arm": arm.name,
                    "n_features": arm.n_features,
                    "fitted_parameters": arm.fitted_parameters,
                    "bss": arm.bss,
                    "per_fold_bss": list(arm.per_fold_bss),
                    "per_fold_n": per_fold_n,
                    "pooled_n": pooled_n,
                    "per_fold_reportable": not below_k6,
                    "long_share": arm.long_share,
                    "base_rate": base_rate,
                    "directional_accuracy": arm.directional_accuracy,
                    "converged": arm.converged,
                    "worst_gradient_norm": arm.worst_gradient_norm,
                    "paired": paired,
                }
            )
            print(
                f"  {arm.name:30s} p={arm.fitted_parameters:3d} "
                f"BSS={arm.bss:+.6f} long={arm.long_share:.3f} "
                f"acc={arm.directional_accuracy:.4f} "
                f"p10={p10 if p10 is None else f'{p10:.4f}'} "
                f"grad={arm.worst_gradient_norm:.2e}",
                flush=True,
            )
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps(records, indent=2), encoding="utf-8")

        # K-1 at eleven parameters, on this horizon's labels and folds.
        print("  K-1 re-measurement at 11 parameters ...", flush=True)
        for mode in (LeakMode.NONE, LeakMode.LABEL_IN_FEATURES):
            study = run_shuffled_label_study(
                clean_design,
                clean_labels,
                folds,
                seeds=SHUFFLED_LABEL_SEEDS,
                leak=mode,
                model_factory=FrozenBudget,
            )
            records.append(
                {
                    "horizon": horizon,
                    "arm": f"k1_{mode.value}",
                    "fitted_parameters": study.fitted_parameters,
                    "mean_bss": study.mean_bss,
                    "max_bss": study.max_bss,
                    "median_bss": study.median_bss,
                    "ci_upper": study.mean_ci.upper,
                    "k1_passed": study.passed,
                    "converged": study.converged,
                    "worst_gradient_norm": study.worst_gradient_norm,
                }
            )
            print(
                f"    {mode.value:24s} p={study.fitted_parameters:3d} "
                f"mean={study.mean_bss:+.6f} max={study.max_bss:+.6f} "
                f"K-1 {'PASS' if study.passed else 'FAIL'}",
                flush=True,
            )
        OUTPUT.write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(flush=True)

    manifest = RunManifest(
        run_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(UTC).isoformat(),
        git_commit=git_commit(),
        git_dirty=git_dirty(),
        run_type=RunType.EVALUATION,
        hypothesis_id="H-012",
        data_snapshot_sha256=frame_sha256(frame),
        data_window={"start": str(frame.index[0]), "end": str(frame.index[-1])},
        evaluation_mode="walk_forward",
        holdout_openings_remaining=3,
        cumulative_hypothesis_count_n_claims=6,
        feature_set_version=feature_set_version(tuple(f.name for f in FULL)),
        seeds={
            "shuffled_labels": list(SHUFFLED_LABEL_SEEDS),
            "bootstrap": BOOTSTRAP_SEED,
        },
        env_lock_sha256=file_sha256(REPO_ROOT / "uv.lock"),
        anonymisation_protocol="none",
        runtime_seconds=round(time.monotonic() - started, 3),
        notes=(
            "H-012 feature slice. Ten features, eleven parameters, horizons "
            "4/24/120. Probability quality only: no cost model, no trade, no "
            "baseline ladder. The EVALUATION.md §2 ladder remains halted at "
            "rung 2. FIRST_TEST_FRACTION "
            f"{FIRST_TEST_FRACTION}, {N_FOLDS} folds."
        ),
    )
    path = manifest.write(REPO_ROOT / "runs")
    OUTPUT.write_text(json.dumps(records, indent=2), encoding="utf-8")

    print(f"rows ......... {OUTPUT.relative_to(REPO_ROOT)} ({len(records)})")
    print(f"manifest ..... {path.relative_to(REPO_ROOT)}")
    print(f"manifest sha . {file_sha256(path)}")
    print(f"git_dirty .... {manifest.git_dirty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
