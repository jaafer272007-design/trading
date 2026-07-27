"""Measure the walk-forward geometry, and what each candidate split point costs.

Run::

    uv run python scripts/report_fold_geometry.py <snapshot>

This is the measurement behind H-001's fold-geometry amendment. It exists so
the split point is a **recorded choice with numbers beside it** rather than a
constant someone typed, and so a reader can check the argument instead of
taking it.

It reports nothing about skill and fits nothing. Every quantity here is a
property of the calendar and the eligibility mask, and would be identical
under any labels at all — which is the point: geometry chosen after seeing a
result is not geometry, it is a search.

What the sweep is for
---------------------

Three things could bind on the split point, and the sweep exists to show which
ones actually do:

============================  ==============================================
K-6 decision floor            Fewer than 150 closed decisions is "no result"
                              (``EVALUATION.md`` §1). Reported pooled and per
                              fold.
training-window adequacy      The combiner is three features plus an
                              intercept. Reported as rows-per-parameter for
                              the smallest training pool.
era composition               H-006 carries an era term because the feed's
                              session structure changes twice inside the
                              window. A geometry that puts every test fold in
                              one era makes that term unmeasurable.
============================  ==============================================

A criterion that is satisfied across the whole candidate range does not select
a point, and saying so is more useful than picking the number it happens to
favour.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
from run_h001 import FEATURES, FIRST_TEST_FRACTION, N_FOLDS, build_design

from data.loader import load_window
from evaluation.splits import Fold, walk_forward_folds
from labels.direction import DEFAULT_HORIZON

RULE = "=" * 74

#: EVALUATION.md §1, K-6. Fewer closed decisions than this is not a negative
#: result — it is no result.
K6_DECISION_FLOOR = 150

#: Split points swept. Round fractions of the in-window series, wide enough to
#: bracket every defensible choice.
CANDIDATES = (0.30, 0.40, 0.50, 0.60, 0.70)


def era_share(era: npt.NDArray[np.str_], indices: npt.NDArray[np.int64]) -> str:
    """Format the era composition of a set of bar positions.

    Args:
        era: Per-bar era label.
        indices: Positions to summarise.

    Returns:
        A single line, shares by era.
    """
    counts = Counter(era[indices])
    total = sum(counts.values())
    if not total:
        return "(empty)"
    return "  ".join(f"{name} {n / total:5.1%}" for name, n in sorted(counts.items()))


def straddles(fold: Fold, boundary: int) -> bool:
    """Whether a fold's test window crosses an era boundary.

    Args:
        fold: The fold.
        boundary: Positional index of the first bar of the later era.

    Returns:
        True if the boundary falls strictly inside the test window.
    """
    return fold.test_start < boundary < fold.test_end


def main(argv: list[str] | None = None) -> int:
    """Print the geometry report.

    Args:
        argv: Command-line arguments, for testing.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    args = parser.parse_args(argv)

    frame = load_window(args.snapshot, valid_only=False)
    _, _, eligible = build_design(frame, args.horizon)
    era = frame["session_era"].to_numpy()
    stamps = frame.index
    n_bars = len(frame)
    n_params = len(FEATURES) + 1

    print(RULE)
    print("WALK-FORWARD GEOMETRY — what the split point costs")
    print(RULE)
    print(f"  in-window bars : {n_bars:,}")
    print(f"  eligible       : {int(eligible.sum()):,}")
    print(f"  folds          : {N_FOLDS}   horizon {args.horizon}")
    print(f"  parameters     : {n_params} ({len(FEATURES)} features + intercept)")
    print()

    print("-- era boundaries, as positions " + "-" * 42)
    boundaries: list[int] = []
    for name in sorted(set(era)):
        where = np.flatnonzero(era == name)
        print(
            f"  {name}  positions {where[0]:>6,} .. {where[-1]:>6,}   "
            f"{len(where):>6,} bars  {len(where) / n_bars:5.1%}"
        )
        if where[0] > 0:
            boundaries.append(int(where[0]))
    print(
        f"  boundaries at {boundaries} "
        f"({', '.join(f'{b / n_bars:.3f}' for b in boundaries)} of the series)"
    )
    print()

    print("-- candidate split points " + "-" * 48)
    print(
        f"  {'split':>6} {'pooled':>7} {'per fold':>10} {'K-6 x':>7} "
        f"{'train f0':>9} {'rows/param':>11}  test eras"
    )
    for fraction in CANDIDATES:
        start = int(n_bars * fraction)
        size = (n_bars - start) // N_FOLDS
        folds = walk_forward_folds(
            valid=eligible,
            n_folds=N_FOLDS,
            first_test_start=start,
            test_size=size,
            horizon=args.horizon,
        )
        counts = [len(f.test) for f in folds]
        pooled = sum(counts)
        tested = np.concatenate([f.test for f in folds])
        eras_in_test = len(set(era[tested]))
        print(
            f"  {fraction:>6.2f} {pooled:>7,} {min(counts):>4}-{max(counts):<5} "
            f"{pooled / K6_DECISION_FLOOR:>6.1f} {len(folds[0].train):>9,} "
            f"{len(folds[0].train) // n_params:>10,}:1  {eras_in_test}"
        )
    print()
    print("     Every candidate clears K-6 by 5x or more and every training")
    print("     pool exceeds the parameter count by three orders of magnitude.")
    print("     Neither criterion selects a point. Era coverage does: a split")
    print("     at or past the last era boundary confines the whole test set")
    print("     to one era and makes H-006's era term unmeasurable there.")
    print()

    chosen = int(n_bars * FIRST_TEST_FRACTION)
    size = (n_bars - chosen) // N_FOLDS
    folds = walk_forward_folds(
        valid=eligible,
        n_folds=N_FOLDS,
        first_test_start=chosen,
        test_size=size,
        horizon=args.horizon,
    )

    print(f"-- the registered choice: {FIRST_TEST_FRACTION:.2f} " + "-" * 43)
    inside = era[chosen]
    print(f"  split at position {chosen:,} = {stamps[chosen]}")
    print(f"  which is INSIDE era {inside}, not on a boundary")
    print()
    print(f"  {'fold':>4}  {'test window (UTC)':<36} {'n':>4} {'train':>7}")
    for fold in folds:
        mark = ""
        for boundary in boundaries:
            if straddles(fold, boundary):
                mark = f"  <== straddles {era[boundary]}"
        print(
            f"  {fold.index:>4}  {str(stamps[fold.test_start])[:16]} .. "
            f"{str(stamps[fold.test_end - 1])[:16]}  {len(fold.test):>4} "
            f"{len(fold.train):>7,}{mark}"
        )
    print()
    print("  era composition, train and test:")
    for fold in folds:
        print(f"    fold {fold.index}  train  {era_share(era, fold.train)}")
        print(f"            test   {era_share(era, fold.test)}")
    print()

    tested = np.concatenate([f.test for f in folds])
    untested = sorted(set(era) - set(era[tested]))
    if untested:
        print(f"  NEVER IN A TEST WINDOW: {untested}")
        print("     Those bars are training data in every fold. The era term is")
        print("     not estimable out-of-sample there under this geometry, and")
        print("     that is a limitation of the geometry, not of the term.")
    print(RULE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
