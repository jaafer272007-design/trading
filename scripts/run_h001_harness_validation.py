"""Run the shuffled-labels harness on synthetic data as a harness validation.

.. warning::

   **This is not a run of H-001 and must never be cited as one.**

   It emits a manifest with ``run_type: harness_validation`` and
   ``hypothesis_id: null``. H-001 stays ``REGISTERED``. A verdict on H-001
   requires real market data: synthetic bars have no vintages, no revisions,
   no session boundaries, no DST, no gaps and no missing bars, so they cannot
   exercise the ``DATA_CONTRACT.md`` §3/§4/§6 hazards that a real ingestion
   layer introduces. What this run *can* establish is that the gate machinery
   works — which is why the planted-leak fixtures are reported alongside the
   clean result rather than as an afterthought.

Usage::

    uv run python scripts/run_h001_harness_validation.py
"""

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

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
from evaluation.pipeline import LeakMode
from evaluation.shuffle import SHUFFLED_LABEL_SEEDS, run_shuffled_label_study
from evaluation.splits import (
    assert_no_leakage,
    report_embargo_effect,
    walk_forward_folds,
)
from features.log_return import LogReturn
from features.range_position import RangePosition
from features.realized_vol import RealizedVol
from labels.direction import DEFAULT_HORIZON, direction_label, summarize

N_BARS = 30_000
DATA_SEED = 42
N_FOLDS = 5
FIRST_TEST_START = 10_000
TEST_SIZE = 4_000
REPO_ROOT = Path(__file__).resolve().parent.parent


def build_design(
    df: pd.DataFrame,
) -> tuple[npt.NDArray[np.float64], tuple[str, ...]]:
    """Compute the scale-free feature matrix.

    Args:
        df: Bar series.

    Returns:
        The design matrix and the ordered feature names.
    """
    features = (
        LogReturn(window=24),
        RealizedVol(window=24),
        RangePosition(window=48),
    )
    columns = [f.compute(df).to_numpy(dtype=np.float64) for f in features]
    return np.column_stack(columns), tuple(f.name for f in features)


def main() -> int:
    """Run the validation and print a report.

    Returns:
        Process exit code: 0 when every fixture behaved as registered.
    """
    started = time.monotonic()

    df = generate_ohlcv(n_bars=N_BARS, seed=DATA_SEED)
    design, feature_names = build_design(df)
    labels_series = direction_label(df, horizon=DEFAULT_HORIZON)
    labels = labels_series.to_numpy(dtype=np.float64)
    label_summary = summarize(labels_series, df, horizon=DEFAULT_HORIZON)

    valid = ~np.isnan(design).any(axis=1) & ~np.isnan(labels)
    folds = walk_forward_folds(
        valid=valid,
        n_folds=N_FOLDS,
        first_test_start=FIRST_TEST_START,
        test_size=TEST_SIZE,
        horizon=DEFAULT_HORIZON,
    )
    assert_no_leakage(folds, horizon=DEFAULT_HORIZON)
    embargo = report_embargo_effect(folds)

    clean_design = np.nan_to_num(design)
    clean_labels = np.nan_to_num(labels)

    print("=" * 72)
    print("H-001 HARNESS VALIDATION — synthetic data, NOT a run of H-001")
    print("=" * 72)
    print(f"bars ................. {N_BARS} (synthetic, seed {DATA_SEED})")
    print(f"features ............. {', '.join(feature_names)}")
    print(f"label ................ {label_summary.name}")
    print(f"  defined ............ {label_summary.n_defined}")
    print(f"  base rate .......... {label_summary.base_rate:.6f}")
    print(f"  tie rate ........... {label_summary.tie_rate:.6f}")
    print(f"folds ................ {len(folds)}")
    print(f"  purged/fold ........ {folds[0].n_purged}")
    print(
        f"  embargoed (total) .. {embargo.additional_bars_removed} "
        f"(vacuous={embargo.is_vacuous}; see evaluation/splits.py)"
    )
    print(f"  decisions/fold ..... {folds[0].test.size}")
    print(f"  decisions pooled ... {sum(f.test.size for f in folds)}")
    print(f"seeds ................ {len(SHUFFLED_LABEL_SEEDS)} enumerated")
    print()

    # Expected gate outcome per leak mode. The two `True` entries are
    # documented limitations, not oversights: SCALER_FIT_ON_ALL leaks feature
    # statistics but no label information, and TRAIN_TEST_OVERLAP is a real
    # leak that a four-parameter linear combiner lacks the capacity to exploit.
    # Both are asserted so the limitation stays measured rather than assumed.
    expectations = {
        LeakMode.NONE: True,
        LeakMode.LABEL_IN_FEATURES: False,
        LeakMode.TARGET_ENCODING_ON_ALL: False,
        LeakMode.TRAIN_TEST_OVERLAP: True,
        LeakMode.SCALER_FIT_ON_ALL: True,
    }

    ok = True
    for mode, expect_pass in expectations.items():
        study = run_shuffled_label_study(clean_design, clean_labels, folds, leak=mode)
        print(study.summary())
        matched = study.passed is expect_pass
        verdict = "as registered" if matched else "*** UNEXPECTED ***"
        print(f"  expected {'PASS' if expect_pass else 'FAIL'} -> {verdict}")
        print()
        ok = ok and matched

    manifest = RunManifest(
        run_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(UTC).isoformat(),
        git_commit=git_commit(),
        git_dirty=git_dirty(),
        run_type=RunType.HARNESS_VALIDATION,
        hypothesis_id=None,
        data_snapshot_sha256=frame_sha256(df),
        data_window={
            "start": str(df.index[0]),
            "end": str(df.index[-1]),
        },
        evaluation_mode="walk_forward",
        holdout_openings_remaining=3,
        cumulative_hypothesis_count_n_claims=2,
        feature_set_version=feature_set_version(feature_names),
        seeds={
            "shuffled_labels": list(SHUFFLED_LABEL_SEEDS),
            "bootstrap": 1337,
            "synthetic_data": DATA_SEED,
        },
        env_lock_sha256=file_sha256(REPO_ROOT / "uv.lock"),
        anonymisation_protocol="none",
        runtime_seconds=round(time.monotonic() - started, 3),
        notes=(
            "Synthetic data. Harness validation only — may never be cited as "
            "evidence for H-001, which remains REGISTERED pending real data."
        ),
    )
    path = manifest.write(REPO_ROOT / "runs")
    print(f"manifest written: {path.relative_to(REPO_ROOT)}")
    print(f"  run_type ......... {manifest.run_type.value}")
    print(f"  hypothesis_id .... {manifest.hypothesis_id}")
    print(f"  snapshot sha256 .. {manifest.data_snapshot_sha256[:16]}...")
    print(f"  git_dirty ........ {manifest.git_dirty}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
