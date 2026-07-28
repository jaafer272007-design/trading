"""H-001 on real market data — the shuffled-labels gate.

Usage::

    uv run python scripts/run_h001.py --dry-run    # build everything, run nothing
    uv run python scripts/run_h001.py              # execute the 30-seed sweep

.. important::

   **This is the first thing in this project that produces a result rather
   than an instrument.** Everything before it was a measurement of the feed or
   of the machinery. ``--dry-run`` exists so the setup can be read and argued
   with before it executes: it loads the snapshot, computes features and
   labels, builds folds, asserts no leakage, and prints every number that
   determines what the sweep will see — then stops without fitting anything.

   A dry run emits no manifest and is not a run of H-001.

What the eligibility mask is, and why it is three things
--------------------------------------------------------

A bar enters train or test only if all of these hold:

=====================  ====================================================
label validity         The forward window ``[T, T+24]`` touches no invalid
                       bar, and does not run off the end of the series.
                       ``data.classify.label_validity``.
feature validity       The backward window ``[T-L+1, T]`` touches no invalid
                       bar, for ``L`` the longest lookback in the feature
                       set. ``data.classify.feature_validity``.
finite features        Every feature is non-null at ``T``. Warmup positions
                       are null by construction and are not imputed.
=====================  ====================================================

The middle one is the one that is easy to omit, and omitting it is invisible.
A 48-bar rolling statistic computed across a hole is not missing and not
flagged — it is an average over two sides of a gap, and it looks exactly like
every other value in the column.

Rows are **masked, never dropped**. Dropping the invalid rows would close the
series up, and then every rolling window crossing the site would read across
it with nothing at all to indicate that it had.

What a pass certifies
---------------------

Less than it sounds like, and H-001's own standing-limitation clause says so:
a pass certifies that no label reaches the model. It does not cover
train/test overlap (below this combiner's capacity), purge or embargo defects
(global permutation destroys the autocorrelation those controls exist for), or
features that peek (shuffling labels leaves features untouched — that is K-2's
job).
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import numpy.typing as npt
import pandas as pd

from data.calendar import load_calendar
from data.classify import feature_validity, label_validity
from data.loader import load_window
from data.raw import find as find_export
from evaluation.manifest import (
    RunManifest,
    RunType,
    feature_set_version,
    file_sha256,
    git_commit,
    git_dirty,
)
from evaluation.pipeline import LeakMode, run_walk_forward
from evaluation.sensitivity import (
    RECORDED_AT_COMMIT,
    RECORDED_MEAN_BSS,
    RECORDED_PARAMETER_COUNT,
    RECORDED_RUN_ID,
    RECORDED_SILENT_MODES,
    RECORDED_TRIPPING_MODES,
    combiner_fingerprint,
)
from evaluation.shuffle import SHUFFLED_LABEL_SEEDS, run_shuffled_label_study
from evaluation.splits import (
    assert_no_leakage,
    report_embargo_effect,
    walk_forward_folds,
)
from features.base import Feature
from features.log_return import LogReturn
from features.range_position import RangePosition
from features.realized_vol import RealizedVol
from labels.direction import DEFAULT_HORIZON, labels_for_snapshot, summarize

RULE = "=" * 74

#: The H-001 feature set, exactly as the harness validation ran it: three
#: features plus an intercept. Not the whole FEATURE_REGISTRY — ATR ships and
#: is causally swept, but H-001's standing-limitation clause quantifies
#: combiner sensitivity at *this* capacity, and changing the set changes what
#: that measurement describes.
FEATURES: tuple[Feature, ...] = (
    LogReturn(window=24),
    RealizedVol(window=24),
    RangePosition(window=48),
)

N_FOLDS = 5

#: Where the first test window opens, as a fraction of the in-window series.
#:
#: REGISTERED in HYPOTHESES.md H-001, amended 2026-07-27, before any run. It is
#: a researcher degree of freedom in the same class as epsilon = 0.01: H-001
#: fixes the fold count and the purge/embargo rule but not this, and the
#: criteria that could have selected it — K-6 headroom, training adequacy —
#: are satisfied across the whole 0.30-0.60 range and therefore select nothing.
#:
#: Changing it requires a new hypothesis ID. Changing it after a run is
#: geometry chosen to suit a result, which is RESEARCH.md §5.3 whatever the
#: accompanying reasoning.
FIRST_TEST_FRACTION = 0.50


def build_design(
    frame: pd.DataFrame, horizon: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Compute features, labels, and the eligibility mask.

    Args:
        frame: In-window snapshot rows, positions intact.
        horizon: Label horizon.

    Returns:
        ``(features, labels, eligible)``, all aligned to ``frame``.
    """
    columns = [
        feature.compute(frame).to_numpy(dtype=np.float64) for feature in FEATURES
    ]
    design = np.column_stack(columns)
    labels = labels_for_snapshot(frame, horizon).to_numpy(dtype=np.float64)

    bar_valid = frame["valid"].to_numpy(dtype=np.bool_)
    longest_lookback = max(feature.lookback_bars for feature in FEATURES)

    eligible = (
        label_validity(bar_valid, horizon)
        & feature_validity(bar_valid, longest_lookback)
        & np.isfinite(design).all(axis=1)
        & ~np.isnan(labels)
    )
    return design, labels, eligible


def main(argv: list[str] | None = None) -> int:
    """Set up H-001, and optionally run it.

    Args:
        argv: Command-line arguments, for testing.

    Returns:
        Process exit code. 0 if the gate passed or the run was a dry run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="snapshot directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build everything and print the setup; fit nothing, write nothing",
    )
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    args = parser.parse_args(argv)

    started = time.time()

    # valid_only=False on purpose: positions must stay intact so a rolling
    # window cannot silently close over a hole. Invalidity is handled by the
    # eligibility mask below, not by deleting rows.
    frame = load_window(args.snapshot, valid_only=False)

    print(RULE)
    print(f"H-001 {'SETUP (dry run)' if args.dry_run else 'RUN'} — shuffled labels")
    print(RULE)
    print(f"  snapshot        : {args.snapshot}")
    print(f"  in-window bars  : {len(frame):,}")
    print(f"  span            : {frame.index[0]} .. {frame.index[-1]}")
    print(f"  invalid bars    : {int((~frame['valid'].to_numpy()).sum()):,}")
    print("  era composition : ", end="")
    shares = frame["session_era"].value_counts(normalize=True).sort_index()
    print("  ".join(f"{era} {share:.1%}" for era, share in shares.items()))
    print()

    design, labels, eligible = build_design(frame, args.horizon)

    print("-- feature set " + "-" * 59)
    for feature in FEATURES:
        print(
            f"  {feature.name:<20} lookback={feature.lookback_bars:>3}  "
            f"lag={feature.confirmation_lag_bars}  "
            f"session_relative={feature.session_relative}"
        )
    print(f"  {'intercept':<20} (the fourth parameter)")
    print()

    bar_valid = frame["valid"].to_numpy(dtype=np.bool_)
    longest = max(f.lookback_bars for f in FEATURES)
    print("-- eligibility " + "-" * 59)
    n_label_ok = int(label_validity(bar_valid, args.horizon).sum())
    n_feature_ok = int(feature_validity(bar_valid, longest).sum())
    n_finite = int(np.isfinite(design).all(axis=1).sum())
    print(f"  bars in window            : {len(frame):>7,}")
    print(f"  label window clean        : {n_label_ok:>7,}")
    print(f"  feature window clean L={longest:<3} : {n_feature_ok:>7,}")
    print(f"  all features finite       : {n_finite:>7,}")
    print(f"  ELIGIBLE                  : {int(eligible.sum()):>7,}")
    print("     Masked, never dropped. Deleting the invalid rows would close")
    print("     the series up and let every rolling window read across the hole.")
    print()

    summary = summarize(labels_for_snapshot(frame, args.horizon), frame, args.horizon)
    print("-- label " + "-" * 65)
    print(f"  name        : {summary.name}   horizon {summary.horizon}")
    print(f"  defined     : {summary.n_defined:,} / {summary.n_total:,}")
    print(f"  base rate   : {summary.base_rate:.6f}")
    print(f"  tie rate    : {summary.tie_rate:.6f}  ({summary.n_ties:,} ties)")
    print("     Ties resolve to 0 by the registered rule, so the tie rate is")
    print("     an asymmetry pushed into the negative class. Reported, per")
    print("     H-001's Label clause, rather than left implicit.")
    print()

    first_test_start, test_size = _fold_geometry(len(frame), N_FOLDS)
    folds = walk_forward_folds(
        valid=eligible,
        n_folds=N_FOLDS,
        first_test_start=first_test_start,
        test_size=test_size,
        horizon=args.horizon,
    )
    assert_no_leakage(folds, args.horizon)
    effect = report_embargo_effect(folds)

    print("-- folds " + "-" * 65)
    print(f"  {'fold':>4}  {'train':>8}  {'test':>6}  {'purged':>7}  {'embargoed':>9}")
    for fold in folds:
        print(
            f"  {fold.index:>4}  {len(fold.train):>8,}  {len(fold.test):>6,}  "
            f"{fold.n_purged:>7,}  {fold.n_embargoed:>9,}"
        )
    total_decisions = sum(len(f.test) for f in folds)
    print(f"  decisions (spaced {args.horizon} bars apart) : {total_decisions:,}")
    print(
        f"  embargo removed  : {effect.additional_bars_removed:,} training bars "
        f"beyond purge"
    )
    if effect.is_vacuous:
        print("     Zero, and that is expected, not a defect. Under forward-only")
        print("     tiling every training bar precedes its test window, so the")
        print("     embargo zone is empty. It is applied and reported anyway —")
        print("     a control that removes nothing must say so rather than")
        print("     appear in a list of applied controls (REPRODUCIBILITY §10).")
    print("     assert_no_leakage: PASS — no training index reaches a test window.")
    print()

    if args.dry_run:
        print(RULE)
        print("DRY RUN — nothing was fitted, no manifest written, H-001 unchanged.")
        print(f"  the sweep would run {len(SHUFFLED_LABEL_SEEDS)} seeds over")
        print(f"  {total_decisions:,} decisions per seed.")
        print(RULE)
        return 0

    if git_dirty():
        print(
            "REFUSING TO RUN: the git tree is dirty. CLAUDE.md Hard Rule 10 and "
            "REPRODUCIBILITY.md §5 make the run void, so it is not started.",
            file=sys.stderr,
        )
        return 2

    # NaN never reaches the combiner: ineligible rows are excluded by the fold
    # mask, and what remains is finite. Zeroing is a shape convenience for the
    # rows nobody reads, not an imputation — DATA_CONTRACT §6 forbids filling a
    # value that anything downstream could consume, and nothing consumes these.
    fitted = np.nan_to_num(design)
    outcome = np.nan_to_num(labels)

    print("-- the null distribution " + "-" * 49)
    study = run_shuffled_label_study(fitted, outcome, folds)
    order = np.argsort(study.bss_per_seed)
    print(f"  {len(study.seeds)} seeds, {study.n_decisions:,} decisions each")
    for row in range(0, len(study.seeds), 6):
        chunk = order[row : row + 6]
        print(
            "    "
            + "  ".join(
                f"s{study.seeds[i]:<2} {study.bss_per_seed[i]:+.6f}" for i in chunk
            )
        )
    print(
        f"  ascending. min {study.bss_per_seed.min():+.6f}  "
        f"max {study.bss_per_seed.max():+.6f}  "
        f"sd {study.bss_per_seed.std(ddof=1):.6f}"
    )
    print(
        f"  seeds with BSS > 0: {int((study.bss_per_seed > 0).sum())} of "
        f"{len(study.seeds)}"
    )
    print()
    print(study.summary())
    print()

    print("-- unshuffled control (NOT part of the verdict) " + "-" * 26)
    control = run_walk_forward(fitted, outcome, folds)
    print(f"  BSS on true labels : {control.bss:+.6f}   n = {control.n_decisions:,}")
    print("     Reported because a shuffled-label null is uninterpretable without")
    print("     knowing what the same pipeline does on real labels. It is NOT a")
    print("     skill claim: no cost model, no baseline ladder, no holdout, and")
    print("     H-003's random-entry comparison has not run. K-3 lives on the")
    print("     sealed holdout and this is not it.")
    print()

    print("-- leak fixtures: these MUST trip K-1 " + "-" * 36)
    fixture_ok = True
    for mode in (LeakMode.LABEL_IN_FEATURES, LeakMode.TARGET_ENCODING_ON_ALL):
        leaked = run_shuffled_label_study(fitted, outcome, folds, leak=mode)
        tripped = not leaked.passed
        fixture_ok = fixture_ok and tripped
        print(
            f"  {mode.value:<24} mean BSS {leaked.mean_bss:+.6f}  "
            f"max {leaked.max_bss:+.6f}  "
            f"{'TRIPPED — correct' if tripped else '*** DID NOT TRIP ***'}"
        )
    print("     A gate that has never fired is indistinguishable from one that")
    print("     cannot. If either of these passes, the verdict above means")
    print("     nothing whatever it says.")
    print()

    print("-- K-1 sensitivity at this combiner capacity " + "-" * 29)
    print(
        f"  parameters        : {RECORDED_PARAMETER_COUNT} "
        f"({len(FEATURES)} features + intercept)"
    )
    print(f"  fingerprint       : {combiner_fingerprint()[:16]}…")
    print(f"  baseline run_id   : {RECORDED_RUN_ID}")
    print(
        f"  baseline commit   : {RECORDED_AT_COMMIT[:12]}  (synthetic, "
        f"harness_validation)"
    )
    print(f"  trips at capacity : {sorted(RECORDED_TRIPPING_MODES)}")
    print(f"  SILENT at capacity: {sorted(RECORDED_SILENT_MODES)}")
    for mode in sorted(RECORDED_SILENT_MODES):
        print(f"      {mode:<24} recorded mean BSS {RECORDED_MEAN_BSS[mode]:+.6f}")
    print("     train_test_overlap is a real leak this combiner cannot exploit")
    print("     at four parameters. A pass therefore certifies that no label")
    print("     reaches the model — not the absence of all leakage.")
    print()

    calendar = load_calendar()
    manifest = RunManifest(
        run_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(UTC).isoformat(),
        git_commit=git_commit(),
        git_dirty=git_dirty(),
        run_type=RunType.EVALUATION,
        hypothesis_id="H-001",
        data_snapshot_sha256=_snapshot_derived_sha256(args.snapshot),
        data_window={
            "start": str(frame.index[0]),
            "end": str(frame.index[-1]),
            "window_start": calendar.window_start.isoformat(),
            "first_test_fraction": str(FIRST_TEST_FRACTION),
        },
        evaluation_mode="walk_forward",
        holdout_openings_remaining=3,
        cumulative_hypothesis_count_n_claims=2,
        feature_set_version=feature_set_version(tuple(f.name for f in FEATURES)),
        seeds={"shuffled_labels": list(SHUFFLED_LABEL_SEEDS), "bootstrap": 1337},
        env_lock_sha256=file_sha256(Path(__file__).resolve().parents[1] / "uv.lock"),
        anonymisation_protocol="none",
        runtime_seconds=round(time.time() - started, 3),
        notes=(
            f"H-001 on real market data. Raw export "
            f"{find_export('H1').filename}. Fold geometry registered at commit "
            f"43dafa2 before this run. Unshuffled control BSS "
            f"{control.bss:+.6f} reported alongside and not part of the verdict."
        ),
    )
    written = manifest.write(Path(__file__).resolve().parents[1] / "runs")

    print("-- run manifest " + "-" * 58)
    print(f"  path         : runs/{written.name}")
    print(f"  sha256       : {file_sha256(written)}")
    print(f"  run_id       : {manifest.run_id}")
    print(f"  run_type     : {manifest.run_type.value}")
    print(f"  hypothesis   : {manifest.hypothesis_id}")
    print(f"  git_commit   : {manifest.git_commit}")
    print(f"  git_dirty    : {manifest.git_dirty}")
    print(f"  snapshot     : {manifest.data_snapshot_sha256}")
    print()

    print(RULE)
    if not fixture_ok:
        print("VERDICT: VOID — a leak fixture did not trip.")
        print("  The gate cannot detect a planted leak, so its verdict on the")
        print("  honest pipeline carries no information. This is not a K-1 halt")
        print("  and not a K-1 pass; it is a broken instrument.")
        print(RULE)
        return 2
    if study.passed:
        print("VERDICT: K-1 PASSES.")
        print("  One gate cleared. No label reaches the model along this path,")
        print("  at this combiner capacity, under this geometry. That is all it")
        print("  says: not that the pipeline is correct, not that there is an")
        print("  edge, not that other leak classes are absent.")
    else:
        print("VERDICT: K-1 TRIPS. HALT.")
        print("  EVALUATION.md §1: leakage or bug, nothing downstream is valid.")
        print("  The required action is a full leakage audit. No other work")
        print("  proceeds, and this is not a debugging session — do not adjust")
        print("  the pipeline until the cause is identified.")
    print(RULE)
    return 0 if study.passed else 1


def _snapshot_derived_sha256(snapshot: Path) -> str:
    """Read the derived-frame hash out of a snapshot manifest.

    The snapshot's own record rather than a re-hash: the loader has already
    refused the snapshot if that record disagrees with the calendar it was
    built under, so re-deriving it here would add a number without adding a
    check.

    Args:
        snapshot: Snapshot directory.

    Returns:
        The derived frame's SHA-256.
    """
    import json

    text = (snapshot / "manifest.json").read_text(encoding="utf-8")
    return str(json.loads(text)["derived_sha256"])


def _fold_geometry(n_bars: int, n_folds: int) -> tuple[int, int]:
    """Split the series into a training prefix and ``n_folds`` equal test windows.

    The prefix is :data:`FIRST_TEST_FRACTION` of the series, registered in
    H-001 before any run. See ``scripts/report_fold_geometry.py`` for the sweep
    that argues it and ``HYPOTHESES.md`` H-001 for what it is and is not.

    Args:
        n_bars: Series length.
        n_folds: Number of folds.

    Returns:
        ``(first_test_start, test_size)``.
    """
    first_test_start = int(n_bars * FIRST_TEST_FRACTION)
    test_size = (n_bars - first_test_start) // n_folds
    return first_test_start, test_size


if __name__ == "__main__":
    raise SystemExit(main())
