"""H-009 -- does the feature layer forecast volatility at H = 24?

Usage::

    uv run python scripts/run_h009.py <snapshot> --dry-run   # setup only
    uv run python scripts/run_h009.py <snapshot>             # execute

Exactly one thing differs from H-001's unshuffled control: **the label**. The
feature set, the fold geometry, the combiner, the standardiser and the scorer
are imported from ``run_h001`` rather than restated here, so their identity is
a property of the import graph instead of a claim in a comment.

What a FAIL means, restated here because it is the whole point
--------------------------------------------------------------

Not that ``H = 24`` is the wrong horizon for volatility. Volatility
persistence is the strongest prior available on this instrument,
``realized_vol_24`` is a direct measurement of the quantity being forecast,
and the forecast window is the same length as the measurement window. A direct
measurement of a persistent quantity that cannot forecast that quantity one
window ahead indicates a defect **upstream** -- in feature computation, bar
alignment, fold geometry, the eligibility mask, or the label path.

H-009 §J registers the required action on FAIL: audit the feature layer
against external references, and **do not run slice 1**. A capacity-ceiling
measurement taken on a broken instrument returns a low ceiling, and a low
ceiling would be misread as "no signal exists on this instrument".

What this run is not
--------------------

There is no cost model, no trade, no baseline ladder and no holdout here.
Volatility forecastability as defined in H-009 §B is not a tradeable edge and
must never be reported as one. ``EVALUATION.md`` §2 remains halted at rung 2.
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
from run_h001 import (  # the H-001 setup, imported so it cannot drift
    FEATURES,
    FIRST_TEST_FRACTION,
    N_FOLDS,
    _fold_geometry,
    _snapshot_derived_sha256,
)

from backtest.metrics import bootstrap_mean
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
from evaluation.pipeline import LeakMode, WalkForwardResult, run_walk_forward
from evaluation.shuffle import SHUFFLED_LABEL_SEEDS, run_shuffled_label_study
from evaluation.splits import Fold, assert_no_leakage, walk_forward_folds
from labels.volatility import (
    DEFAULT_HORIZON,
    DEFAULT_THRESHOLD_WINDOW,
    DEFAULT_VOL_WINDOW,
    summarize_volatility,
    volatility_labels_for_snapshot,
)
from metrics.brier import brier_score, brier_skill_score
from models.logistic import LogisticRegression, Standardizer

RULE = "=" * 74

# --- Registered in HYPOTHESES.md H-009 before this file existed -------------

BSS_THRESHOLD = 0.05
"""H-009 §D. K-3's existing materiality floor, not a new number."""

BH_THRESHOLD = 0.025
"""H-009 §D, derived. At m = 4 the step-up critical values are 0.0125, 0.025,
0.0375, 0.05; with H-003 at 0.0204 already in the family, k = 2 rejects
whenever this run's p is at or below 0.025."""

N_CLAIMS = 4
"""H-003, H-004, H-007, H-009."""

H003_P_VALUE = 0.0204
"""The family member H-009 is coupled to through the BH step-up."""

BOOTSTRAP_BLOCK = 10.0
"""H-003 §F, reused unchanged so the three runs are comparable."""

BOOTSTRAP_SENSITIVITY_BLOCKS = (1.0, 25.0)
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 1337

K6_MINIMUM_DECISIONS = 150
"""EVALUATION.md §1."""

PREDICTED_VOL_RESPONSE_SIGN = +1
"""H-009 §G (i), registered before the run. Reported, not a pass condition."""


def build_design(
    frame: pd.DataFrame,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Compute features, the volatility label, and the eligibility mask.

    The mask differs from H-001's in one term: the backward span is the
    label's ``threshold_window + vol_window`` where H-001 used the longest
    *feature* lookback, because H-009's threshold reaches back further than
    any feature does.

    Args:
        frame: In-window snapshot rows, positions intact.

    Returns:
        ``(features, labels, eligible)``, all aligned to ``frame``.
    """
    design = np.column_stack(
        [feature.compute(frame).to_numpy(dtype=np.float64) for feature in FEATURES]
    )
    labels = volatility_labels_for_snapshot(frame).to_numpy(dtype=np.float64)

    bar_valid = frame["valid"].to_numpy(dtype=np.bool_)
    backward = max(
        max(feature.lookback_bars for feature in FEATURES),
        DEFAULT_THRESHOLD_WINDOW + DEFAULT_VOL_WINDOW,
    )

    eligible = (
        label_validity(bar_valid, DEFAULT_HORIZON)
        & feature_validity(bar_valid, backward)
        & np.isfinite(design).all(axis=1)
        & ~np.isnan(labels)
    )
    return design, labels, eligible


def per_decision_improvement(
    result: WalkForwardResult,
) -> tuple[npt.NDArray[np.float64], float]:
    """The per-decision quantity H-009 §E bootstraps.

    ``d_i = (base_rate - y_i)^2 - (p_i - y_i)^2`` -- the improvement in
    squared error over the climatological forecast. ``mean(d) > 0`` exactly
    when ``BSS > 0``, and ``BSS = mean(d) / BS_reference``.

    Args:
        result: A pooled walk-forward result.

    Returns:
        ``(d, bs_reference)``.
    """
    y = result.outcomes
    base_rate = float(np.mean(y))
    reference_error = (base_rate - y) ** 2
    model_error = (result.probabilities - y) ** 2
    return reference_error - model_error, float(np.mean(reference_error))


def fold_bss(result: WalkForwardResult) -> list[tuple[int, int, float | None]]:
    """Per-fold BSS, with ``None`` where the fold is degenerate.

    H-009 §H requires the per-fold series so a level-shift signature is
    visible rather than confounded into the pooled figure. A fold whose
    outcomes are all identical has no climatological reference and therefore
    no BSS; that is reported as absent rather than as zero.

    Args:
        result: A pooled walk-forward result.

    Returns:
        ``(fold_index, n, bss_or_None)`` per fold.
    """
    rows: list[tuple[int, int, float | None]] = []
    for fold in result.fold_results:
        try:
            score: float | None = brier_skill_score(fold.probabilities, fold.outcomes)
        except ValueError:
            score = None
        rows.append((fold.fold_index, int(fold.outcomes.size), score))
    return rows


def probe_responses(
    design: npt.NDArray[np.float64],
    labels: npt.NDArray[np.float64],
    folds: tuple[Fold, ...],
    result: WalkForwardResult,
) -> tuple[list[tuple[int, npt.NDArray[np.float64]]], bool]:
    """Probe each fold model's response to a one-SD step in each feature.

    H-009 §G (i) registers the *sign* of the model's response to
    ``realized_vol_24``. This reads it by asking the fitted model rather than
    by reading its weights: the predicted probability at a point one standard
    deviation along one feature, minus the predicted probability at the
    standardised origin. The sigmoid is monotone in the linear predictor, so
    the sign of that difference is the sign of the coefficient, and the
    magnitude is in probability units.

    Why a probe and not an accessor: adding a ``coefficients`` property to
    ``models/logistic.py`` moved ``combiner_fingerprint()`` and failed
    ``tests/evaluation/test_sensitivity.py``, which guards K-1's sensitivity
    baseline. The guard is right and the combiner is left alone --
    ``HYPOTHESES.md`` H-009 §A records the amendment. Interrogating the fitted
    model from outside is also the better instrument under ``EVALUATION.md``
    §14 on its own merits.

    ``run_walk_forward`` does not return its models, so they are refitted here,
    which raises the obvious objection: a second fit is a second
    implementation. That is answered by measurement rather than by argument --
    each refitted model's probabilities on its own test rows are compared
    bitwise with the evaluation path's. If any differ, nothing is reported.

    Args:
        design: Full design matrix.
        labels: Full label vector.
        folds: The folds used for the run.
        result: The result to reconcile against.

    Returns:
        ``(per-fold response vectors, reconciled)``.
    """
    by_index = {fold.index: fold for fold in folds}
    n_features = design.shape[1]
    origin = np.zeros((1, n_features), dtype=np.float64)
    step = np.eye(n_features, dtype=np.float64)

    responses: list[tuple[int, npt.NDArray[np.float64]]] = []
    reconciled = True

    for fold_result in result.fold_results:
        fold = by_index[fold_result.fold_index]
        scaler = Standardizer().fit(design[fold.train])
        model = LogisticRegression().fit(
            scaler.transform(design[fold.train]), labels[fold.train]
        )
        probabilities = model.predict_proba(scaler.transform(design[fold.test]))
        if not np.array_equal(probabilities, fold_result.probabilities):
            reconciled = False
        baseline = float(model.predict_proba(origin)[0])
        responses.append((fold.index, model.predict_proba(step) - baseline))

    return responses, reconciled


def main(argv: list[str] | None = None) -> int:
    """Set up H-009, and optionally run it.

    Args:
        argv: Command-line arguments, for testing.

    Returns:
        Process exit code. 0 on a completed run or a dry run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="snapshot directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build everything and print the setup; fit nothing, write nothing",
    )
    args = parser.parse_args(argv)

    started = time.time()
    frame = load_window(args.snapshot, valid_only=False)

    print(RULE)
    print(f"H-009 {'SETUP (dry run)' if args.dry_run else 'RUN'} -- volatility label")
    print(RULE)
    print(f"  snapshot        : {args.snapshot}")
    print(f"  in-window bars  : {len(frame):,}")
    print(f"  span            : {frame.index[0]} .. {frame.index[-1]}")
    print(f"  invalid bars    : {int((~frame['valid'].to_numpy()).sum()):,}")
    print()

    design, labels, eligible = build_design(frame)
    vol_name = f"realized_vol_{DEFAULT_VOL_WINDOW}"
    vol_column = next(i for i, f in enumerate(FEATURES) if f.name == vol_name)

    print("-- the label (H-009 §B) " + "-" * 50)
    print(f"  rv           = RealizedVol({DEFAULT_VOL_WINDOW}), the shipped feature")
    print(f"  threshold[T] = median(rv[T-{DEFAULT_THRESHOLD_WINDOW - 1}] .. rv[T])")
    print(f"  label[T]     = 1 if rv[T+{DEFAULT_HORIZON}] > threshold[T] else 0")
    print(
        f"     rv[T+{DEFAULT_HORIZON}] is the SD of returns over closes "
        f"T .. T+{DEFAULT_HORIZON} -- the forward window. The trailing and"
    )
    print("     forward windows share no returns.")
    summary = summarize_volatility(volatility_labels_for_snapshot(frame), frame)
    print(f"  defined      : {summary.n_defined:,} / {summary.n_total:,}")
    print(f"  base rate    : {summary.base_rate:.6f}")
    print(f"  tie rate     : {summary.tie_rate:.6f}  ({summary.n_ties:,} ties)")
    print(f"  backward span: {summary.backward_span_bars:,} bars")
    print()

    print("-- feature set: identical to H-001, imported not restated " + "-" * 16)
    for i, feature in enumerate(FEATURES):
        marker = "  <- H-009 §G probes this response" if i == vol_column else ""
        print(f"  {feature.name:<20} lookback={feature.lookback_bars:>4}{marker}")
    print(f"  {'intercept':<20} (the fourth parameter)")
    print()

    bar_valid = frame["valid"].to_numpy(dtype=np.bool_)
    backward = DEFAULT_THRESHOLD_WINDOW + DEFAULT_VOL_WINDOW
    print("-- eligibility " + "-" * 59)
    print(f"  bars in window            : {len(frame):>7,}")
    print(
        f"  label window clean H={DEFAULT_HORIZON:<3}  : "
        f"{int(label_validity(bar_valid, DEFAULT_HORIZON).sum()):>7,}"
    )
    print(
        f"  backward span clean L={backward:<4}: "
        f"{int(feature_validity(bar_valid, backward).sum()):>7,}"
    )
    print(f"  ELIGIBLE                  : {int(eligible.sum()):>7,}")
    print("     The backward term is the label's, not the longest feature's:")
    print("     the threshold reaches back further than any feature does.")
    print()

    first_test_start, test_size = _fold_geometry(len(frame), N_FOLDS)
    folds = walk_forward_folds(
        valid=eligible,
        n_folds=N_FOLDS,
        first_test_start=first_test_start,
        test_size=test_size,
        horizon=DEFAULT_HORIZON,
    )
    assert_no_leakage(folds, DEFAULT_HORIZON)
    total_decisions = sum(len(f.test) for f in folds)

    print("-- folds " + "-" * 65)
    print(f"  {'fold':>4}  {'train':>8}  {'test':>6}  {'purged':>7}")
    for fold in folds:
        print(
            f"  {fold.index:>4}  {len(fold.train):>8,}  {len(fold.test):>6,}  "
            f"{fold.n_purged:>7,}"
        )
    print(f"  decisions (spaced {DEFAULT_HORIZON} bars apart) : {total_decisions:,}")
    print("     assert_no_leakage: PASS")
    print()

    print("-- K-6, label-free and therefore known before any result " + "-" * 17)
    k6_ok = total_decisions >= K6_MINIMUM_DECISIONS
    headroom = total_decisions / K6_MINIMUM_DECISIONS
    k6_note = f"CLEAR at {headroom:.1f}x" if k6_ok else "*** K-6 TRIPS ***"
    print(
        f"  {total_decisions:,} decisions against a floor of "
        f"{K6_MINIMUM_DECISIONS} -- {k6_note}"
    )
    print()

    print("-- registered before the run, restated so the order is visible " + "-" * 11)
    print(f"  primary       : pooled out-of-sample BSS >= {BSS_THRESHOLD}")
    print(
        f"  significance  : one-sided bootstrap p <= {BH_THRESHOLD} "
        f"(BH, m = {N_CLAIMS})"
    )
    print("  H-009 §D      : BH is step-up. p <= 0.025 rejects the two smallest,")
    print(f"                  which includes H-003 at {H003_P_VALUE}. That does NOT")
    print("                  restore H-003's withdrawn directional reading.")
    print("  H-009 §G (i)  : the model's response to realized_vol_24 is predicted")
    print("                  POSITIVE in every fold. Reported, not a pass condition.")
    print("  H-009 §G (ii) : realized_vol_24 alone should account for most of the")
    print("                  skill. Attribution only; it cannot become the primary.")
    print("  H-009 §H      : per-fold BSS is reported and does NOT rescue a pooled")
    print("                  failure.")
    print(f"  BSS of {BSS_THRESHOLD - 0.02:.2f} is a FAIL. Registered in advance.")
    print()

    if args.dry_run:
        print(RULE)
        print("DRY RUN -- nothing fitted, no manifest written, H-009 unchanged.")
        print(RULE)
        return 0

    if git_dirty():
        print(
            "REFUSING TO RUN: the git tree is dirty. CLAUDE.md Hard Rule 10 and "
            "REPRODUCIBILITY.md §5 make the run void, so it is not started.",
            file=sys.stderr,
        )
        return 2

    fitted = np.nan_to_num(design)
    outcome = np.nan_to_num(labels)

    # ---- K-1 on THIS label ------------------------------------------------
    print("-- K-1: shuffled labels on this label, not inherited " + "-" * 21)
    study = run_shuffled_label_study(fitted, outcome, folds)
    print(study.summary())
    print("     H-001 cleared K-1 for the DIRECTION label. The label is the one")
    print("     thing changing here, and the label path is where a new leak would")
    print("     enter, so the clearance is re-measured rather than inherited.")
    print()

    print("-- K-1 leak fixtures: these MUST trip " + "-" * 36)
    fixture_ok = True
    for mode in (LeakMode.LABEL_IN_FEATURES, LeakMode.TARGET_ENCODING_ON_ALL):
        leaked = run_shuffled_label_study(fitted, outcome, folds, leak=mode)
        tripped = not leaked.passed
        fixture_ok = fixture_ok and tripped
        print(
            f"  {mode.value:<24} mean BSS {leaked.mean_bss:+.6f}  "
            f"{'TRIPPED -- correct' if tripped else '*** DID NOT TRIP ***'}"
        )
    print()

    # ---- the primary metric -----------------------------------------------
    result = run_walk_forward(fitted, outcome, folds)
    d, bs_reference = per_decision_improvement(result)

    print("-- primary: pooled out-of-sample BSS " + "-" * 37)
    print(f"  BSS            : {result.bss:+.6f}   n = {result.n_decisions:,}")
    print(f"  base rate      : {float(np.mean(result.outcomes)):.6f}")
    print(
        f"  BS model       : {brier_score(result.probabilities, result.outcomes):.6f}"
    )
    print(f"  BS climatology : {bs_reference:.6f}")
    print(f"  threshold      : {BSS_THRESHOLD}   ", end="")
    print("CLEARED" if result.bss >= BSS_THRESHOLD else "NOT CLEARED")
    print()

    print(
        "-- per fold (H-009 §H: reported, does not rescue a pooled failure) " + "-" * 6
    )
    print(f"  {'fold':>4}  {'n':>6}  {'BSS':>11}")
    for index, n, score in fold_bss(result):
        rendered = f"{score:+.6f}" if score is not None else "degenerate"
        print(f"  {index:>4}  {n:>6,}  {rendered:>11}")
    print()

    # ---- significance ------------------------------------------------------
    print(
        "-- significance: stationary bootstrap on per-decision improvement " + "-" * 7
    )
    print("  d_i = (base_rate - y_i)^2 - (p_i - y_i)^2;  BSS = mean(d) / BS_ref")
    print(
        f"  {'block':>6}  {'mean d':>12}  {'95% CI of mean d':>28}  "
        f"{'p':>8}  {'BSS CI':>24}"
    )
    primary_p: float | None = None
    for block in (
        BOOTSTRAP_SENSITIVITY_BLOCKS[0],
        BOOTSTRAP_BLOCK,
        BOOTSTRAP_SENSITIVITY_BLOCKS[1],
    ):
        boot = bootstrap_mean(
            d,
            expected_block=block,
            n_resamples=BOOTSTRAP_RESAMPLES,
            seed=BOOTSTRAP_SEED,
        )
        if block == BOOTSTRAP_BLOCK:
            primary_p = boot.p_value_one_sided
        marker = "*" if block == BOOTSTRAP_BLOCK else " "
        print(
            f" {marker}{block:>5.0f}  {boot.observed:+12.6f}  "
            f"[{boot.ci_low:+.6f}, {boot.ci_high:+.6f}]  "
            f"{boot.p_value_one_sided:8.4f}  "
            f"[{boot.ci_low / bs_reference:+.4f}, {boot.ci_high / bs_reference:+.4f}]"
        )
    print("  * = the registered block. 1 is the i.i.d. case; 25 is the stress.")
    print("     The BSS interval scales the mean-d interval by BS_reference held")
    print("     fixed. BS_reference itself moves under resampling, so that column")
    print("     is a first-order transform and not an exact interval.")
    print()
    assert primary_p is not None

    # ---- registered predictions -------------------------------------------
    print("-- H-009 §G (i): the model's response, predicted POSITIVE " + "-" * 15)
    print("  change in predicted probability from a one-SD step in each feature,")
    print("  the others held at the standardised origin. Sign = coefficient sign.")
    responses, reconciled = probe_responses(fitted, outcome, folds, result)
    signs_ok = True
    if not reconciled:
        print("  *** REFIT DID NOT REPRODUCE THE EVALUATION PATH -- not reported ***")
    else:
        print("  refit reproduces the evaluation path's probabilities bitwise.")
        print(f"  {'fold':>4}  " + "  ".join(f"{f.name:>18}" for f in FEATURES))
        for index, response in responses:
            print(f"  {index:>4}  " + "  ".join(f"{r:>+18.6f}" for r in response))
            if np.sign(response[vol_column]) != PREDICTED_VOL_RESPONSE_SIGN:
                signs_ok = False
        print(
            f"  realized_vol_{DEFAULT_VOL_WINDOW} response matches the registered "
            f"prediction in every fold: {'YES' if signs_ok else 'NO -- FLAG'}"
        )
        if not signs_ok:
            print("     A high BSS with the wrong sign means the model is winning")
            print("     for a reason opposite to the registered mechanism. H-009 §G")
            print("     makes that a flag requiring explanation before a PASS is")
            print("     acted on -- not a verdict.")
    print()

    print("-- H-009 §G (ii): attribution, NOT a competing configuration " + "-" * 13)
    single = run_walk_forward(fitted[:, [vol_column]], outcome, folds)
    print(f"  three features            BSS {result.bss:+.6f}   <- the primary")
    print(f"  realized_vol_{DEFAULT_VOL_WINDOW} alone      BSS {single.bss:+.6f}")
    share = single.bss / result.bss if result.bss != 0.0 else float("nan")
    print(f"  share of the skill        {share:.1%}")
    print("     Reported for attribution. It cannot become the primary whatever")
    print("     it scores -- running two and keeping the better one is metric")
    print("     shopping under RESEARCH.md §5.3.")
    print()

    # ---- manifest ----------------------------------------------------------
    calendar = load_calendar()
    manifest = RunManifest(
        run_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(UTC).isoformat(),
        git_commit=git_commit(),
        git_dirty=git_dirty(),
        run_type=RunType.EVALUATION,
        hypothesis_id="H-009",
        data_snapshot_sha256=_snapshot_derived_sha256(args.snapshot),
        data_window={
            "start": str(frame.index[0]),
            "end": str(frame.index[-1]),
            "window_start": calendar.window_start.isoformat(),
            "first_test_fraction": str(FIRST_TEST_FRACTION),
            "label": f"vol_above_median_{DEFAULT_HORIZON}",
            "threshold_window": str(DEFAULT_THRESHOLD_WINDOW),
        },
        evaluation_mode="walk_forward",
        holdout_openings_remaining=3,
        cumulative_hypothesis_count_n_claims=N_CLAIMS,
        feature_set_version=feature_set_version(tuple(f.name for f in FEATURES)),
        seeds={
            "shuffled_labels": list(SHUFFLED_LABEL_SEEDS),
            "bootstrap": BOOTSTRAP_SEED,
        },
        env_lock_sha256=file_sha256(Path(__file__).resolve().parents[1] / "uv.lock"),
        anonymisation_protocol="none",
        runtime_seconds=round(time.time() - started, 3),
        notes=(
            f"H-009 volatility label on the H-001 geometry. Raw export "
            f"{find_export('H1').filename}. Pooled BSS {result.bss:+.6f}, "
            f"one-sided p {primary_p:.4f} at block {BOOTSTRAP_BLOCK:.0f}. No cost "
            f"model and no trade in this run, so H-005's deviation does not apply "
            f"and no §10 claim is made."
        ),
    )
    written = manifest.write(Path(__file__).resolve().parents[1] / "runs")

    print("-- run manifest " + "-" * 58)
    print(f"  path      : runs/{written.name}")
    print(f"  sha256    : {file_sha256(written)}")
    print(f"  run_id    : {manifest.run_id}")
    print(f"  commit    : {manifest.git_commit}   dirty={manifest.git_dirty}")
    print(f"  N_claims  : {manifest.cumulative_hypothesis_count_n_claims}")
    print()

    # ---- verdict -----------------------------------------------------------
    print(RULE)
    if not k6_ok:
        print("VERDICT: NO RESULT -- K-6. Do not conclude anything.")
        print(RULE)
        return 2
    if not fixture_ok:
        print("VERDICT: VOID -- a K-1 leak fixture did not trip.")
        print(RULE)
        return 2
    if not study.passed:
        print("VERDICT: K-1 TRIPS. HALT. The result below is void, not negative.")
        print(RULE)
        return 1

    passed = result.bss >= BSS_THRESHOLD and primary_p <= BH_THRESHOLD
    if passed:
        print("VERDICT: H-009 PASSES.")
        print(
            f"  BSS {result.bss:+.6f} >= {BSS_THRESHOLD}, "
            f"p {primary_p:.4f} <= {BH_THRESHOLD}."
        )
        print("  The feature layer measures something real and the pipeline can")
        print("  extract and score it out of sample at H = 24. The directional")
        print("  null is therefore about DIRECTION, not about the wiring.")
        print("  Licenses slice 1 and nothing else. No trading claim is made.")
        print(f"  BH at m = {N_CLAIMS}: p <= {BH_THRESHOLD} also rejects H-003 at")
        print(f"  {H003_P_VALUE} through the step-up. That does NOT restore H-003's")
        print("  withdrawn directional reading -- see H-009 §D.")
    else:
        print("VERDICT: H-009 FAILS.")
        print(
            f"  BSS {result.bss:+.6f} against {BSS_THRESHOLD}; "
            f"p {primary_p:.4f} against {BH_THRESHOLD}."
        )
        print("  Per H-009 §J this puts THE FEATURE LAYER in question, not the")
        print("  horizon. Volatility persistence is the strongest prior available")
        print("  on this instrument and realized_vol_24 measures it directly.")
        print("  Required action: audit the feature layer against external")
        print("  references. DO NOT RUN SLICE 1 -- a ceiling measured on a broken")
        print("  instrument returns a low ceiling and would be misread as 'no")
        print("  signal exists'.")
    print(RULE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
