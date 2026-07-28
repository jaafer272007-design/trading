"""H-003 on real market data — does the signal beat random entry?

Usage::

    uv run python scripts/run_h003.py --dry-run    # build everything, trade nothing
    uv run python scripts/run_h003.py              # execute the run

Everything this script does was registered in ``HYPOTHESES.md`` H-003 §A-§N
before the engine existed and before any arm ran. Nothing here chooses anything:
the feature set, the decision grid, the risk geometry, the cost constants, the
bootstrap block length and the seeds all arrive from that entry.

What a PASS licenses, stated before the result rather than after
----------------------------------------------------------------

**Rung 2 of** ``EVALUATION.md`` **§2, and nothing further.** H-003's original
pre-committed interpretation said PASS meant "proceed to build the agent panel",
which skipped rungs 2, 3 and 4 of a ladder whose whole premise is that skipping
produces false confidence. §G narrowed it. The narrowing binds this run.

A PASS also does not mean profitable. The metric is a *difference* against
random entry. A PASS with negative absolute expectancy says the signal carries
directional information the geometry does not — nothing more.

Two limitations that belong in the result, not in an appendix
--------------------------------------------------------------

**The event model reaches 2.83% of bars** (§M). Every scheduled release that is
not payrolls is priced at the flat floor. That error is *optimistic*: a CPI
print at 75 points is cheaper than a CPI print at 225. It is bounded by K-5 and
by the breakeven spread, and it is not removed by either.

**Nine of the thirteen registered cost constants are judgement calls** (§L). If
the measured difference lands near its threshold, the run reports which of them
the verdict is most sensitive to, because a verdict that turns on an unmeasured
judgement is a different kind of result from one that does not.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import pandas as pd
from run_h001 import FEATURES, FIRST_TEST_FRACTION, N_FOLDS, build_design

from backtest.costs import CostModel, multiplier_coverage, spread_multipliers
from backtest.decision_log import decision_record, write_decision_log
from backtest.direction import (
    DirectionSource,
    LogisticDirection,
    RandomDirection,
)
from backtest.engine import (
    ArmResult,
    assess_cost_invariance,
    run_arm,
)
from backtest.execution import BarArrays, RiskModel, build_bars
from backtest.metrics import (
    BootstrapResult,
    bootstrap_mean,
    paired_difference,
    solve_breakeven_spread,
)
from data.aggregate import PRICE_SCALE
from data.classify import feature_validity, trade_window_validity
from data.loader import load_window
from evaluation.manifest import (
    RunManifest,
    RunType,
    feature_set_version,
    file_sha256,
    git_commit,
    git_dirty,
)
from evaluation.pipeline import run_walk_forward
from evaluation.splits import assert_no_leakage, walk_forward_folds
from features.atr import ATR
from labels.direction import DEFAULT_HORIZON

RULE = "=" * 74

# ---------------------------------------------------------------------------
# Registered constants — HYPOTHESES.md H-003. None of these is chosen here.
# ---------------------------------------------------------------------------

#: §D. Symmetric, so the control's gross expectancy is zero by construction.
STOP_ATR_MULT = 1.5
TARGET_ATR_MULT = 1.5
MAX_HOLD_BARS = 24
RISK_PER_TRADE = 100.0

#: §C. REPRODUCIBILITY.md §3 ``random_entry``, enumerated not generated.
RANDOM_ENTRY_SEEDS = tuple(range(30))

#: §F.
BOOTSTRAP_BLOCK = 10.0
BOOTSTRAP_BLOCK_SENSITIVITY = (1.0, 25.0)
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 1337

#: §J. The risk geometry reads this; it is deliberately not in the signal (§A).
RISK_FEATURE = ATR(period=14)

#: EVALUATION.md §1.
K6_DECISION_FLOOR = 150

#: The breakeven search. Bisection is by re-simulation, so the bracket is kept
#: tight enough to be affordable and the tolerance is reported with the answer.
BREAKEVEN_HIGH = 2000.0
BREAKEVEN_TOLERANCE = 5.0
BREAKEVEN_MAX_ITERATIONS = 12

#: §L. The judgement-class constants, in the order a sensitivity report walks
#: them. Named here so the report cannot silently cover fewer than all nine.
JUDGEMENT_CONSTANTS = (
    "weekly_open_bars",
    "slippage_atr_coeff",
    "slippage size scaling (sqrt)",
    "commission_points_per_lot_per_side",
    "swap_long_points_per_lot_per_night",
    "swap_short_points_per_lot_per_night",
    "latency_atr_coeff_per_second",
    "stop/target ATR multiple",
    "cost divergence tolerance",
)


@dataclass(frozen=True, slots=True)
class Setup:
    """Everything the arms need, built once."""

    frame: pd.DataFrame
    bars: BarArrays
    decisions: npt.NDArray[np.int64]
    fold_of_decision: npt.NDArray[np.int64]
    probabilities: tuple[float, ...]
    atr_points: npt.NDArray[np.float64]
    multipliers: npt.NDArray[np.float64]
    risk: RiskModel
    design: npt.NDArray[np.float64]

    @property
    def n(self) -> int:
        """Decision count."""
        return len(self.decisions)


def build_setup(snapshot: Path, horizon: int, model: CostModel) -> Setup:
    """Load the snapshot and produce the decision grid and the signal.

    Args:
        snapshot: Derived snapshot directory.
        horizon: Label horizon, which is also the decision spacing.
        model: Cost model, for the per-bar half-spreads.

    Returns:
        The setup.

    Raises:
        ValueError: If the pipeline and the fold geometry disagree on decisions.
    """
    frame = load_window(snapshot, valid_only=False)
    design, labels, h001_eligible = build_design(frame, horizon)
    bar_valid = frame["valid"].to_numpy(dtype=np.bool_)

    # §J: two eligibility conditions the H-001 mask does not cover.
    atr = RISK_FEATURE.compute(frame).to_numpy(dtype=np.float64)
    atr_ok = (
        np.isfinite(atr)
        & (atr > 0)
        & feature_validity(bar_valid, RISK_FEATURE.lookback_bars)
    )
    eligible = h001_eligible & atr_ok & trade_window_validity(bar_valid, MAX_HOLD_BARS)

    n_bars = len(frame)
    start = int(n_bars * FIRST_TEST_FRACTION)
    folds = walk_forward_folds(
        valid=eligible,
        n_folds=N_FOLDS,
        first_test_start=start,
        test_size=(n_bars - start) // N_FOLDS,
        horizon=horizon,
    )
    assert_no_leakage(folds, horizon)

    result = run_walk_forward(design, labels, folds)
    decisions = np.concatenate([f.test for f in folds]).astype(np.int64)
    fold_of = np.concatenate(
        [np.full(len(f.test), f.index, dtype=np.int64) for f in folds]
    )
    probabilities = np.concatenate([r.probabilities for r in result.fold_results])
    pipeline_index = np.concatenate([r.test_index for r in result.fold_results])
    if not np.array_equal(pipeline_index, decisions):
        raise ValueError(
            "the pipeline's test indices do not match the fold geometry's — a "
            "misalignment here attaches one bar's view to another bar's trade"
        )

    multipliers = spread_multipliers(pd.DatetimeIndex(frame.index), model)
    return Setup(
        frame=frame,
        bars=build_bars(frame, multipliers, model, PRICE_SCALE),
        decisions=decisions,
        fold_of_decision=fold_of,
        probabilities=tuple(float(p) for p in probabilities),
        atr_points=atr[decisions] * PRICE_SCALE,
        multipliers=multipliers,
        risk=RiskModel(
            stop_atr_mult=STOP_ATR_MULT,
            target_atr_mult=TARGET_ATR_MULT,
            max_hold_bars=MAX_HOLD_BARS,
            risk_per_trade_currency=RISK_PER_TRADE,
        ),
        design=design,
    )


def run_all_arms(
    setup: Setup, model: CostModel
) -> tuple[ArmResult, tuple[ArmResult, ...]]:
    """Run the signal arm and the thirty controls at one cost model.

    Args:
        setup: The prepared grid.
        model: Cost model to charge.

    Returns:
        ``(signal, controls)``.
    """
    bars = build_bars(setup.frame, setup.multipliers, model, PRICE_SCALE)

    def one(name: str, source: DirectionSource) -> ArmResult:
        """Run one arm. Every argument but the source is the same, by design."""
        return run_arm(
            name=name,
            source=source,
            frame=setup.frame,
            bars=bars,
            decisions=setup.decisions,
            atr_points=setup.atr_points,
            risk=setup.risk,
            model=model,
        )

    signal = one("signal", LogisticDirection(setup.probabilities))
    controls = tuple(
        one(f"random_s{s}", RandomDirection(seed=s)) for s in RANDOM_ENTRY_SEEDS
    )
    return signal, controls


def difference_at_floor(setup: Setup, base: CostModel, floor: float) -> float:
    """Mean paired difference in R at one spread floor.

    Args:
        setup: The prepared grid.
        base: The registered cost model, cloned at ``floor``.
        floor: Spread floor in points. May be below the H-005 minimum — that is
            the question the breakeven solver exists to answer.

    Returns:
        Mean of ``d_i``.
    """
    signal, controls = run_all_arms(setup, base.unsafe_with_spread_floor(floor))
    diff = paired_difference(
        signal.r_by_decision, tuple(c.r_by_decision for c in controls)
    )
    return float(np.mean(diff))


def signal_expectancy_at_floor(setup: Setup, base: CostModel, floor: float) -> float:
    """The signal arm's own absolute expectancy in R at one spread floor.

    Args:
        setup: The prepared grid.
        base: The registered cost model.
        floor: Spread floor in points.

    Returns:
        Mean R per decision.
    """
    model = base.unsafe_with_spread_floor(floor)
    bars = build_bars(setup.frame, setup.multipliers, model, PRICE_SCALE)
    arm = run_arm(
        name="signal",
        source=LogisticDirection(setup.probabilities),
        frame=setup.frame,
        bars=bars,
        decisions=setup.decisions,
        atr_points=setup.atr_points,
        risk=setup.risk,
        model=model,
    )
    return arm.expectancy_r


def _bootstrap_line(label: str, result: BootstrapResult) -> str:
    """One formatted bootstrap row."""
    return (
        f"  {label:<22} mean {result.observed:+.6f}  "
        f"95% CI [{result.ci_low:+.6f}, {result.ci_high:+.6f}]  "
        f"p = {result.p_value_one_sided:.4f}"
    )


def main(argv: list[str] | None = None) -> int:
    """Run H-003.

    Args:
        argv: Command-line arguments, for testing.

    Returns:
        Process exit code. 0 on PASS or dry run, 1 on FAIL.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    args = parser.parse_args(argv)

    started = time.monotonic()
    dirty = git_dirty()
    if dirty and not args.dry_run:
        print("REFUSING TO RUN: the working tree is dirty.")
        print("CLAUDE.md Hard Rule 10 — a dirty tree voids the run. Commit first.")
        return 1

    model = CostModel()
    setup = build_setup(args.snapshot, args.horizon, model)

    print(RULE)
    print("H-003 — SIGNAL BEATS RANDOM ENTRY" + ("  [DRY RUN]" if args.dry_run else ""))
    print(RULE)
    print("  A PASS licenses EVALUATION.md §2 rung 2 and nothing further (H-003 §G).")
    print("  It is not a profitability claim: the metric is a difference against")
    print("  random entry, and H-005 keeps any result at RESEARCH.md Tier 2 at best.")
    print()
    print(f"  snapshot        : {args.snapshot}")
    print(f"  decisions       : {setup.n:,}   K-6 floor {K6_DECISION_FLOOR}")
    print(f"  folds           : {N_FOLDS}   split {FIRST_TEST_FRACTION:.2f}")
    print(f"  cost model      : {model.version()[:16]}…")
    print(f"  git_dirty       : {dirty}")
    print()

    coverage = multiplier_coverage(setup.multipliers)
    print("-- the cost model's blind spot, stated up front " + "-" * 26)
    print(
        f"  {coverage.n_weekly_open:,} weekly-open bars, {coverage.n_news:,} "
        f"payrolls-hour bars: {coverage.share_elevated:.2%} of the series."
    )
    print("  Every other scheduled release is priced at the flat 75-point floor.")
    print("  That error is OPTIMISTIC. K-5 and the breakeven spread bound it;")
    print("  neither removes it.")
    print()

    if setup.n < K6_DECISION_FLOOR:
        print(f"K-6: {setup.n} decisions is below the floor. NO RESULT.")
        return 1

    if args.dry_run:
        print("-- dry run " + "-" * 63)
        print("  Setup built. No arm has been run and no manifest written.")
        print(RULE)
        return 0

    signal, controls = run_all_arms(setup, model)
    diff = paired_difference(
        signal.r_by_decision, tuple(c.r_by_decision for c in controls)
    )

    print("-- arms " + "-" * 66)
    print(f"  {'arm':<12} {'expectancy R':>13} {'long':>6} {'short':>6} {'flat':>5}")
    counts = signal.direction_counts()
    print(
        f"  {'signal':<12} {signal.expectancy_r:>13.6f} {counts['long']:>6} "
        f"{counts['short']:>6} {counts['flat']:>5}"
    )
    control_means = np.array([c.expectancy_r for c in controls])
    print(
        f"  {'random (30)':<12} {control_means.mean():>13.6f}   "
        f"min {control_means.min():+.6f}  max {control_means.max():+.6f}"
    )
    better = int((control_means >= signal.expectancy_r).sum())
    print(f"  control arms at least as good as the signal: {better} of 30")
    print()

    print("-- the paired difference " + "-" * 49)
    primary = bootstrap_mean(
        diff,
        expected_block=BOOTSTRAP_BLOCK,
        n_resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
    )
    print(_bootstrap_line(f"block {BOOTSTRAP_BLOCK:.0f} (registered)", primary))
    sensitivity = []
    for block in BOOTSTRAP_BLOCK_SENSITIVITY:
        alt = bootstrap_mean(
            diff,
            expected_block=block,
            n_resamples=BOOTSTRAP_RESAMPLES,
            seed=BOOTSTRAP_SEED,
        )
        sensitivity.append((block, alt))
        print(_bootstrap_line(f"block {block:.0f} (sensitivity)", alt))
    print()

    print("-- per fold, alongside pooled " + "-" * 44)
    print(f"  {'fold':>4} {'n':>5} {'signal R':>10} {'control R':>10} {'diff R':>10}")
    for index in range(N_FOLDS):
        mask = setup.fold_of_decision == index
        if not mask.any():
            continue
        control_slice = float(np.mean([c.r_by_decision[mask].mean() for c in controls]))
        print(
            f"  {index:>4} {int(mask.sum()):>5} "
            f"{signal.r_by_decision[mask].mean():>10.6f} "
            f"{control_slice:>10.6f} {diff[mask].mean():>10.6f}"
        )
    print(
        f"  {'pooled':>4} {setup.n:>5} {signal.expectancy_r:>10.6f} "
        f"{control_means.mean():>10.6f} {float(np.mean(diff)):>10.6f}"
    )
    print()

    print("-- realised cost per arm, per decision, in R " + "-" * 29)
    invariance = assess_cost_invariance(signal, controls)
    print(f"  {'component':<14} {'signal':>12} {'control':>12} {'diff':>12}")
    for comparison in invariance.components:
        marker = (
            "  (identical by construction)"
            if (comparison.identical_by_construction)
            else ""
        )
        print(
            f"  {comparison.component:<14} {comparison.signal_r:>12.6f} "
            f"{comparison.control_r:>12.6f} {comparison.divergence_r:>12.6f}"
            f"{marker}"
        )
    print(
        f"  {'gap_through':<14} {signal.cost_r('gap_through'):>12.6f} "
        f"{float(np.mean([c.cost_r('gap_through') for c in controls])):>12.6f}"
        f"{'':>12}  (diagnostic, already inside gross)"
    )
    print(
        f"  {'TOTAL':<14} {signal.total_cost_r():>12.6f} "
        f"{float(np.mean([c.total_cost_r() for c in controls])):>12.6f} "
        f"{invariance.total_divergence_r:>12.6f}"
    )
    print()
    print(f"  {invariance.statement()}")
    print()

    print("-- breakeven spread " + "-" * 54)
    signal_breakeven = solve_breakeven_spread(
        lambda floor: signal_expectancy_at_floor(setup, model, floor),
        high=BREAKEVEN_HIGH,
        tolerance_points=BREAKEVEN_TOLERANCE,
        max_iterations=BREAKEVEN_MAX_ITERATIONS,
    )
    print("  signal arm, absolute expectancy (H-005 (ii)):")
    print(f"    {signal_breakeven.note}")
    difference_breakeven = solve_breakeven_spread(
        lambda floor: difference_at_floor(setup, model, floor),
        high=BREAKEVEN_HIGH,
        tolerance_points=BREAKEVEN_TOLERANCE,
        max_iterations=BREAKEVEN_MAX_ITERATIONS,
    )
    print("  paired difference:")
    print(f"    {difference_breakeven.note}")
    print()

    print("-- K-5, every cost doubled " + "-" * 47)
    doubled_signal, doubled_controls = run_all_arms(setup, model.doubled())
    doubled_diff = paired_difference(
        doubled_signal.r_by_decision,
        tuple(c.r_by_decision for c in doubled_controls),
    )
    doubled_boot = bootstrap_mean(
        doubled_diff,
        expected_block=BOOTSTRAP_BLOCK,
        n_resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
    )
    print(_bootstrap_line("doubled costs", doubled_boot))
    print()

    passed = primary.significant_at_5pct and primary.observed > 0
    print("-- verdict " + "-" * 63)
    if passed:
        print("  K-4 does not trip. H-003 PASSES.")
        print("  Licensed: EVALUATION.md §2 rung 2. Nothing further.")
    else:
        print("  **K-4.** The signal does not beat random entry at p < 0.05.")
        print("  Pre-committed action: do not add agents. Return to feature")
        print("  research. Adding agents to a signal with no information")
        print("  produces a more expensive way to be wrong.")
    print()

    margin = abs(primary.p_value_one_sided - 0.05)
    if margin < 0.02 or abs(primary.observed) < 2 * invariance.total_divergence_r:
        print("  NEAR THE THRESHOLD — judgement-constant sensitivity applies.")
        print("  Nine of thirteen registered constants are judgement (§L):")
        for name in JUDGEMENT_CONSTANTS:
            print(f"    - {name}")
        print("  The verdict should not be reported without saying which of")
        print("  these it turns on.")
    else:
        print(
            f"  Not near the threshold: p = {primary.p_value_one_sided:.4f}, "
            f"effect {primary.observed:+.6f} R against a cost divergence of "
            f"{invariance.total_divergence_r:.6f} R."
        )
    print()

    run_id = str(uuid.uuid4())
    log_path = args.runs_dir / f"{run_id}-decisions.jsonl"
    records = []
    for slot, position in enumerate(setup.decisions):
        by_decision = {t.decision_index: t for t in signal.trades}
        control_by_decision = {t.decision_index: t for t in controls[0].trades}
        features = {
            feature.name: float(setup.design[position, i])
            for i, feature in enumerate(FEATURES)
        }
        versions = {feature.name: feature.version for feature in FEATURES}
        for method, confidence, trade in (
            ("logistic", setup.probabilities[slot], by_decision.get(int(position))),
            ("random", None, control_by_decision.get(int(position))),
        ):
            records.append(
                decision_record(
                    run_id=run_id,
                    snapshot_sha256=file_sha256(args.snapshot / "manifest.json"),
                    index=pd.DatetimeIndex(setup.frame.index),
                    close=setup.frame["close"].to_numpy(dtype=np.float64),
                    decision_index=int(position),
                    features=features,
                    feature_versions=versions,
                    decision_method=method,
                    confidence=confidence,
                    trade=trade,
                )
            )
    write_decision_log(records, log_path)

    manifest = RunManifest(
        run_id=run_id,
        timestamp_utc=datetime.now(UTC).isoformat(),
        git_commit=git_commit(),
        git_dirty=dirty,
        run_type=RunType.EVALUATION,
        hypothesis_id="H-003",
        data_snapshot_sha256=file_sha256(args.snapshot / "manifest.json"),
        data_window={
            "start": str(setup.frame.index[0]),
            "end": str(setup.frame.index[-1]),
        },
        evaluation_mode="walk_forward",
        holdout_openings_remaining=3,
        cumulative_hypothesis_count_n_claims=2,
        feature_set_version=feature_set_version(tuple(f.name for f in FEATURES)),
        seeds={
            "random_entry": list(RANDOM_ENTRY_SEEDS),
            "bootstrap": BOOTSTRAP_SEED,
        },
        env_lock_sha256=file_sha256(Path("uv.lock")),
        anonymisation_protocol="none",
        runtime_seconds=time.monotonic() - started,
        cost_model_version=model.version(),
        notes=(
            f"decisions={setup.n}; paired difference {primary.observed:+.6f} R, "
            f"p={primary.p_value_one_sided:.4f}; cost invariance "
            f"{'holds' if invariance.holds else 'VOID'}; decision log "
            f"{log_path.name} (signal + control seed 0; the other 29 control "
            f"arms are a deterministic function of their seeds)."
        ),
    )
    path = manifest.write(args.runs_dir)
    print("-- run record " + "-" * 60)
    print(f"  manifest      : {path}")
    print(f"  sha256        : {file_sha256(path)}")
    print(f"  decision log  : {log_path}  ({len(records):,} records)")
    print(f"  runtime       : {manifest.runtime_seconds:.1f}s")
    print(RULE)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
