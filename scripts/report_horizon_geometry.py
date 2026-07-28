"""Decision geometry at each candidate horizon, before any horizon is registered.

The feature slice proposes sweeping ``H`` over a set fixed in advance. Changing
``H`` changes three things at once, and only the first is obvious:

1. **Decision spacing.** ``evaluation/splits.py`` spaces decisions ``H`` bars
   apart so that reported ``n`` counts independent bets. Smaller ``H`` means
   more decisions per test window, larger ``H`` means fewer.
2. **Eligibility.** ``label_validity`` requires the forward window
   ``[T, T+H]`` to touch no invalid bar, so a longer horizon disqualifies more
   bars near every gap.
3. **Purge width.** Purge drops training samples whose label window reaches
   ``test_start``, and that width is ``H``.

Everything here is **label-free** — it depends on where labels are *computable*
and on the fixed split rule, never on their values, so it is invariant under
any permutation of label values and can be reported before registration
without being a peek. The same argument H-003 used to answer K-6 in advance.

Usage::

    uv run python scripts/report_horizon_geometry.py data/snapshots/<dir>
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.loader import load_window
from evaluation.splits import walk_forward_folds
from run_h001 import FIRST_TEST_FRACTION, N_FOLDS, _fold_geometry, build_design

CANDIDATE_HORIZONS = (4, 24, 120)
"""Fixed before this report was run. H = 24 is the registered incumbent."""

K6_FLOOR = 150
"""EVALUATION.md §1: fewer than 150 closed decisions is no result."""


def _era_composition(frame: pd.DataFrame, index: np.ndarray) -> Counter[str]:
    """Count decisions per session era.

    Args:
        frame: In-window snapshot rows.
        index: Positional indices of decisions.

    Returns:
        Era label to decision count.
    """
    eras = frame["session_era"].to_numpy()
    return Counter(str(e) for e in eras[index])


def main() -> int:
    """Print the geometry report.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="snapshot directory")
    args = parser.parse_args()

    frame = load_window(args.snapshot, valid_only=False)
    n_bars = len(frame)
    first_test_start, test_size = _fold_geometry(n_bars, N_FOLDS)

    print("=" * 78)
    print("HORIZON GEOMETRY — label-free, before any horizon is registered")
    print("=" * 78)
    print(f"in-window bars ........ {n_bars:,}")
    print(f"FIRST_TEST_FRACTION ... {FIRST_TEST_FRACTION:.2f} (H-001, unchanged)")
    print(f"folds ................. {N_FOLDS}")
    print(f"first_test_start ...... {first_test_start:,}  (bar index)")
    print(f"test_size ............. {test_size:,}  (bars per fold)")
    print()
    print("The split rule is horizon-independent: the fold boundaries above are")
    print("the same at every H. What changes is spacing, eligibility and purge.")
    print()

    all_eras = Counter(str(e) for e in frame["session_era"].to_numpy())
    print(f"era composition of the whole in-window series: {dict(all_eras)}")
    print()

    for horizon in CANDIDATE_HORIZONS:
        design, labels, eligible = build_design(frame, horizon)
        folds = walk_forward_folds(
            valid=eligible,
            n_folds=N_FOLDS,
            first_test_start=first_test_start,
            test_size=test_size,
            horizon=horizon,
        )
        per_fold = [f.test.size for f in folds]
        pooled = sum(per_fold)
        below = [f.index for f in folds if f.test.size < K6_FLOOR]

        print("-" * 78)
        print(f"H = {horizon}")
        print("-" * 78)
        print(f"  eligible bars ....... {int(eligible.sum()):,} of {n_bars:,}")
        print(f"  decision spacing .... {horizon} bars (= H, non-overlapping)")
        print(f"  decisions/fold ...... {per_fold}")
        print(f"  pooled .............. {pooled:,}")
        print(f"  K-6 floor ........... {K6_FLOOR}")
        print(f"  pooled vs K-6 ....... {pooled / K6_FLOOR:.1f}x")
        smallest = min(per_fold)
        print(f"  smallest fold ....... {smallest} ({smallest / K6_FLOOR:.2f}x K-6)")
        if below:
            print(f"  *** FOLDS BELOW K-6 : {below} — per-fold not reportable ***")
        else:
            print("  every fold clears K-6 — per-fold results are reportable")
        print(f"  purged/fold ......... {[f.n_purged for f in folds]}")
        print(f"  embargoed/fold ...... {[f.n_embargoed for f in folds]}")
        print(f"  train sizes ......... {[f.train.size for f in folds]}")

        print("  era composition of each test window:")
        for fold in folds:
            comp = _era_composition(frame, fold.test)
            print(f"    fold {fold.index}: {dict(comp)}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
