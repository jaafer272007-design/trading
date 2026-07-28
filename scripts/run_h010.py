"""H-010 — K-1 sensitivity re-measured at every capacity rung.

The gate H-011 depends on. ``REPRODUCIBILITY.md`` §6: K-1 sensitivity is a
property of the combiner, not of the gate, so a K-1 pass at four parameters
certifies nothing about twenty.

What this measures, per rung of H-011's ladder and under **both** registered
fitting rules:

1. the full five-mode leak suite, 30 seeds, 30,000 synthetic bars;
2. the K-1 null re-measured at that rung rather than inherited from H-001;
3. which modes trip and which stay silent, with the fitted parameter count
   recorded beside each;
4. convergence, because H-011 makes a non-converged fit VOID rather than
   negative and the same reasoning applies to the null that judges it.

Results are appended to a JSON file after every configuration, so a run that
is interrupted leaves measurements rather than nothing. That is not a
convenience: the convergent rule at the higher rungs is expensive enough that
a partial result is the likely outcome, and a partial result that is written
down is evidence while one held in memory is not.

Usage::

    uv run python scripts/run_h010.py [--rules frozen,convergent] [--rungs C-0,C-1]

Emits ``run_type: harness_validation`` and no ``hypothesis_id``: it is a record
of gate behaviour on synthetic bars and is never evidence for H-001 or H-011.
"""

import argparse
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from scripts.run_h001_harness_validation import (
    DATA_SEED,
    FIRST_TEST_START,
    N_BARS,
    N_FOLDS,
    TEST_SIZE,
    build_design,
)

from data.synthetic import generate_ohlcv
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
from evaluation.sensitivity import RECORDED_MEAN_BSS
from evaluation.shuffle import (
    SHUFFLED_LABEL_SEEDS,
    ShuffleStudy,
    run_shuffled_label_study,
)
from evaluation.splits import Fold, assert_no_leakage, walk_forward_folds
from labels.direction import DEFAULT_HORIZON, direction_label
from models.convergent import ConvergentLogisticRegression
from models.expansion import polynomial_expand
from models.logistic import LogisticRegression

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
OUTPUT: Final = REPO_ROOT / "runs" / "h010_capacity_sensitivity.json"

TRIP_THRESHOLD: Final = 0.05
"""K-3's materiality floor, the level at which a leak mode counts as tripping.

Inherited unchanged from the recorded baseline's classification so the two
tables are comparable. It is not re-derived here.
"""


@dataclass(frozen=True, slots=True)
class Rung:
    """One step of H-011's registered capacity ladder."""

    name: str
    degree: int
    diagonal_only: bool
    parameters: int


LADDER: Final = (
    Rung("C-0", 1, False, 4),
    Rung("C-1", 2, True, 7),
    Rung("C-2", 2, False, 10),
    Rung("C-3", 3, False, 20),
    Rung("C-4", 4, False, 35),
    Rung("C-5", 5, False, 56),
)

RULES: Final = {
    "frozen": LogisticRegression,
    "convergent": ConvergentLogisticRegression,
}


def _classify(study: ShuffleStudy) -> str:
    """Trip or silence, on the recorded baseline's own criterion.

    Args:
        study: A completed sweep.

    Returns:
        ``"trips"`` or ``"silent"``.
    """
    return "trips" if study.mean_bss > TRIP_THRESHOLD else "silent"


def _row(
    rung: Rung, rule: str, study: ShuffleStudy, seconds: float
) -> dict[str, object]:
    """One line of the result table.

    Args:
        rung: The capacity rung.
        rule: Fitting rule name.
        study: The completed sweep.
        seconds: Wall time for this configuration.

    Returns:
        A JSON-serialisable record.
    """
    return {
        "rung": rung.name,
        "rule": rule,
        "declared_parameters": rung.parameters,
        "fitted_parameters": study.fitted_parameters,
        "estimator": study.estimator,
        "leak": study.leak.value,
        "mean_bss": study.mean_bss,
        "median_bss": study.median_bss,
        "max_bss": study.max_bss,
        "ci_lower": study.mean_ci.lower,
        "ci_upper": study.mean_ci.upper,
        "classification": _classify(study),
        "k1_passed": study.passed,
        "n_decisions": study.n_decisions,
        "converged": study.converged,
        "worst_gradient_norm": study.worst_gradient_norm,
        "seconds": round(seconds, 3),
    }


def _append(rows: list[dict[str, object]], out: Path) -> None:
    """Rewrite the result file. Called after every configuration.

    Args:
        rows: Every row measured so far.
        out: Destination path.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _clean_control(
    design: npt.NDArray[np.float64],
    labels: npt.NDArray[np.float64],
    folds: tuple[Fold, ...],
    factory: type[LogisticRegression],
) -> dict[str, object]:
    """One unshuffled fit, for convergence evidence on real labels.

    Reported as harness behaviour only. The bars are synthetic, so a BSS here
    is not evidence about any market and must never be cited as H-011's
    quantity.

    Args:
        design: Expanded design matrix.
        labels: True labels.
        folds: Walk-forward folds.
        factory: Combiner class.

    Returns:
        A JSON-serialisable record.
    """
    result = run_walk_forward(design, labels, folds, model_factory=factory)
    return {
        "bss_synthetic_true_labels": result.bss,
        "converged": result.converged,
        "worst_gradient_norm": result.worst_gradient_norm,
        "iterations": [d.iterations for d in result.diagnostics] or None,
    }


def main() -> int:
    """Run the sweep and print a report.

    Returns:
        Process exit code: 0 when every configuration attempted completed.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", default="frozen,convergent")
    parser.add_argument("--rungs", default=",".join(r.name for r in LADDER))
    parser.add_argument("--out", default=str(OUTPUT))
    args = parser.parse_args()

    rules = [r.strip() for r in args.rules.split(",") if r.strip()]
    wanted = {r.strip() for r in args.rungs.split(",") if r.strip()}
    rungs = [r for r in LADDER if r.name in wanted]
    out = Path(args.out)

    started = time.monotonic()
    df = generate_ohlcv(n_bars=N_BARS, seed=DATA_SEED)
    base_design, feature_names = build_design(df)
    labels = direction_label(df, horizon=DEFAULT_HORIZON).to_numpy(dtype=np.float64)
    valid = ~np.isnan(base_design).any(axis=1) & ~np.isnan(labels)
    folds = walk_forward_folds(
        valid=valid,
        n_folds=N_FOLDS,
        first_test_start=FIRST_TEST_START,
        test_size=TEST_SIZE,
        horizon=DEFAULT_HORIZON,
    )
    assert_no_leakage(folds, horizon=DEFAULT_HORIZON)

    clean_x = np.nan_to_num(base_design)
    clean_y = np.nan_to_num(labels)

    print("=" * 78)
    print("H-010 — K-1 SENSITIVITY AT EVERY CAPACITY RUNG (synthetic bars)")
    print("=" * 78)
    print(f"bars ......... {N_BARS} (seed {DATA_SEED})")
    print(f"features ..... {', '.join(feature_names)}")
    print(f"folds ........ {len(folds)}, {sum(f.test.size for f in folds)} decisions")
    print(f"seeds ........ {len(SHUFFLED_LABEL_SEEDS)}")
    print(f"rungs ........ {', '.join(r.name for r in rungs)}")
    print(f"rules ........ {', '.join(rules)}")
    print()

    rows: list[dict[str, object]] = []
    controls: list[dict[str, object]] = []
    for rung in rungs:
        design = polynomial_expand(
            clean_x, rung.degree, diagonal_only=rung.diagonal_only
        )
        for rule in rules:
            factory = RULES[rule]

            control = _clean_control(design, clean_y, folds, factory)
            control |= {"rung": rung.name, "rule": rule}
            controls.append(control)
            print(
                f"[{rung.name}/{rule}] control: converged={control['converged']} "
                f"grad={control['worst_gradient_norm']} "
                f"iters={control['iterations']}",
                flush=True,
            )

            for mode in LeakMode:
                t = time.monotonic()
                study = run_shuffled_label_study(
                    design, clean_y, folds, leak=mode, model_factory=factory
                )
                row = _row(rung, rule, study, time.monotonic() - t)
                rows.append(row)
                _append(rows, out)

                baseline = RECORDED_MEAN_BSS.get(mode.value)
                delta = (
                    f" (4-param baseline {baseline:+.6f})"
                    if baseline is not None
                    else ""
                )
                print(
                    f"[{rung.name}/{rule}] p={study.fitted_parameters:3d} "
                    f"{mode.value:24s} mean={study.mean_bss:+.6f} "
                    f"max={study.max_bss:+.6f} -> {row['classification']:6s}"
                    f"{delta}  [{row['seconds']:.1f}s]",
                    flush=True,
                )
            print(flush=True)

    manifest = RunManifest(
        run_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(UTC).isoformat(),
        git_commit=git_commit(),
        git_dirty=git_dirty(),
        run_type=RunType.HARNESS_VALIDATION,
        hypothesis_id=None,
        data_snapshot_sha256=frame_sha256(df),
        data_window={"start": str(df.index[0]), "end": str(df.index[-1])},
        evaluation_mode="walk_forward",
        holdout_openings_remaining=3,
        cumulative_hypothesis_count_n_claims=5,
        feature_set_version=feature_set_version(feature_names),
        seeds={
            "shuffled_labels": list(SHUFFLED_LABEL_SEEDS),
            "synthetic_data": DATA_SEED,
        },
        env_lock_sha256=file_sha256(REPO_ROOT / "uv.lock"),
        anonymisation_protocol="none",
        runtime_seconds=round(time.monotonic() - started, 3),
        notes=(
            "H-010 capacity sensitivity sweep. Synthetic data, harness "
            "validation only. Records gate behaviour per capacity rung; never "
            "evidence for H-001 or H-011."
        ),
    )
    path = manifest.write(REPO_ROOT / "runs")
    _append(rows, out)
    (out.parent / "h010_controls.json").write_text(
        json.dumps(controls, indent=2), encoding="utf-8"
    )

    print(f"rows written ..... {out.relative_to(REPO_ROOT)} ({len(rows)})")
    print(f"manifest ......... {path.relative_to(REPO_ROOT)}")
    print(f"git_dirty ........ {manifest.git_dirty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
