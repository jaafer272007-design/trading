"""H-007 — does the signal beat always-long? `EVALUATION.md` §2 rung 2.

Usage::

    uv run python scripts/run_h007.py <snapshot> --dry-run
    uv run python scripts/run_h007.py <snapshot>

One change from H-003: the direction source. The decision grid, the signal's
probabilities, the risk geometry, the cost model, the eligibility mask and the
bootstrap all come from ``run_h003`` unchanged, because a run that differs in
two things cannot attribute a difference to either.

Why this run exists
-------------------

H-003 measured the signal beating random entry by +0.060398 R at ``p = 0.0204``.
It also measured the signal going long **56.2%** of the time against a control
that is 50% long by construction, on gold, over a secular uptrend. **A long bias
produces that difference with no directional skill at all.** This is the
registered instrument for separating the two.

What registering this already did to H-003
------------------------------------------

``N_claims`` went 2 to 3, which moved the Benjamini-Hochberg rank-1 critical
value from 0.025 to 0.0167. H-003's ``p = 0.0204`` no longer clears that alone.
BH is a step-up procedure, so H-003 recovers if **this run returns
``p <= 0.0333``** and does not otherwise.

That is the registry working, not a technicality: registering another claim
weakened an accepted one, before the new claim ran. The run reports the
contingency either way.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from run_h001 import FEATURES, FIRST_TEST_FRACTION, N_FOLDS
from run_h003 import (
    BOOTSTRAP_BLOCK,
    BOOTSTRAP_BLOCK_SENSITIVITY,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    BREAKEVEN_HIGH,
    BREAKEVEN_MAX_ITERATIONS,
    BREAKEVEN_TOLERANCE,
    K6_DECISION_FLOOR,
    Setup,
    build_setup,
)

from backtest.costs import CostModel
from backtest.direction import AlwaysLong, LogisticDirection
from backtest.engine import ArmResult, assess_cost_invariance, run_arm
from backtest.execution import build_bars
from backtest.metrics import (
    BootstrapResult,
    bootstrap_mean,
    paired_difference,
    solve_breakeven_spread,
)
from data.aggregate import PRICE_SCALE
from evaluation.manifest import (
    RunManifest,
    RunType,
    feature_set_version,
    file_sha256,
    git_commit,
    git_dirty,
)
from labels.direction import DEFAULT_HORIZON

RULE = "=" * 74

#: H-003's measured p-value at the registered block, and the BH step-up
#: threshold its survival now depends on. Both restated as literals: an
#: assertion that recomputes the number it is guarding is not a guard.
H003_P_VALUE = 0.0204
H003_SURVIVES_IF_P_AT_MOST = 0.0333

#: N_claims after H-007's registration: H-003, H-004, H-007.
N_CLAIMS = 3

#: H-007's own registered prediction of the swap divergence, in R per decision.
#: Written down before the run so the measurement can contradict it.
PREDICTED_SWAP_DIVERGENCE_R = 0.00026


def _bootstrap_line(label: str, result: BootstrapResult) -> str:
    """One formatted bootstrap row."""
    return (
        f"  {label:<22} mean {result.observed:+.6f}  "
        f"95% CI [{result.ci_low:+.6f}, {result.ci_high:+.6f}]  "
        f"p = {result.p_value_one_sided:.4f}"
    )


def run_two_arms(setup: Setup, model: CostModel) -> tuple[ArmResult, ArmResult]:
    """Run the signal and always-long at one cost model.

    Args:
        setup: The prepared grid, from ``run_h003.build_setup``.
        model: Cost model to charge.

    Returns:
        ``(signal, always_long)``.
    """
    bars = build_bars(setup.frame, setup.multipliers, model, PRICE_SCALE)

    def one(name: str, source: object) -> ArmResult:
        """Run one arm. Everything but the source is shared, by design."""
        return run_arm(
            name=name,
            source=source,  # type: ignore[arg-type]
            frame=setup.frame,
            bars=bars,
            decisions=setup.decisions,
            atr_points=setup.atr_points,
            risk=setup.risk,
            model=model,
        )

    return (
        one("signal", LogisticDirection(setup.probabilities)),
        one("always_long", AlwaysLong()),
    )


def difference_at_floor(setup: Setup, base: CostModel, floor: float) -> float:
    """Mean paired difference in R at one spread floor.

    Args:
        setup: The prepared grid.
        base: The registered cost model, cloned at ``floor``.
        floor: Spread floor in points, possibly below the H-005 minimum.

    Returns:
        Mean of ``d_i``.
    """
    signal, control = run_two_arms(setup, base.unsafe_with_spread_floor(floor))
    return float(
        np.mean(paired_difference(signal.r_by_decision, (control.r_by_decision,)))
    )


def main(argv: list[str] | None = None) -> int:
    """Run H-007.

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
    print(
        "H-007 — SIGNAL BEATS ALWAYS-LONG (§2 rung 2)"
        + ("  [DRY RUN]" if args.dry_run else "")
    )
    print(RULE)
    print("  A PASS licenses rung 3 becoming the question. Nothing beyond it.")
    print("  A FAIL withdraws H-003's directional reading: the run stands as a")
    print("  record, the interpretation does not.")
    print()
    print(f"  decisions       : {setup.n:,}   K-6 floor {K6_DECISION_FLOOR}")
    print(f"  cost model      : {model.version()[:16]}…")
    print(f"  git_dirty       : {dirty}")
    print()
    print("-- what registering this run already did to H-003 " + "-" * 24)
    print(f"  N_claims 2 -> {N_CLAIMS}. BH rank-1 critical 0.025 -> 0.0167.")
    print(f"  H-003's p = {H003_P_VALUE} no longer clears alone. BH is step-up, so")
    print(f"  H-003 survives iff this run returns p <= {H003_SURVIVES_IF_P_AT_MOST}.")
    print()

    if args.dry_run:
        print("-- dry run " + "-" * 63)
        print("  Setup built. No arm has been run and no manifest written.")
        print(RULE)
        return 0

    signal, control = run_two_arms(setup, model)
    diff = paired_difference(signal.r_by_decision, (control.r_by_decision,))

    print("-- arms " + "-" * 66)
    print(f"  {'arm':<14} {'expectancy R':>13} {'long':>6} {'short':>6} {'long %':>8}")
    for arm in (signal, control):
        counts = arm.direction_counts()
        share = counts["long"] / arm.n_decisions if arm.n_decisions else float("nan")
        print(
            f"  {arm.name:<14} {arm.expectancy_r:>13.6f} {counts['long']:>6} "
            f"{counts['short']:>6} {share:>7.1%}"
        )
    print()

    print("-- the paired difference " + "-" * 49)
    blocks = (
        BOOTSTRAP_BLOCK_SENSITIVITY[0],
        BOOTSTRAP_BLOCK,
        *BOOTSTRAP_BLOCK_SENSITIVITY[1:],
    )
    results: dict[float, BootstrapResult] = {}
    for block in blocks:
        results[block] = bootstrap_mean(
            diff,
            expected_block=block,
            n_resamples=BOOTSTRAP_RESAMPLES,
            seed=BOOTSTRAP_SEED,
        )
        label = "registered" if block == BOOTSTRAP_BLOCK else "sensitivity"
        print(_bootstrap_line(f"block {block:.0f} ({label})", results[block]))
    primary = results[BOOTSTRAP_BLOCK]
    print()

    print("-- per fold, alongside pooled " + "-" * 44)
    print(f"  {'fold':>4} {'n':>5} {'signal R':>10} {'long R':>10} {'diff R':>10}")
    for index in range(N_FOLDS):
        mask = setup.fold_of_decision == index
        if not mask.any():
            continue
        print(
            f"  {index:>4} {int(mask.sum()):>5} "
            f"{signal.r_by_decision[mask].mean():>10.6f} "
            f"{control.r_by_decision[mask].mean():>10.6f} "
            f"{diff[mask].mean():>10.6f}"
        )
    print(
        f"  {'pool':>4} {setup.n:>5} {signal.expectancy_r:>10.6f} "
        f"{control.expectancy_r:>10.6f} {float(np.mean(diff)):>10.6f}"
    )
    print()

    print("-- realised cost per arm, per decision, in R " + "-" * 29)
    invariance = assess_cost_invariance(signal, (control,))
    print(f"  {'component':<14} {'signal':>12} {'always-long':>12} {'diff':>12}")
    for comparison in invariance.components:
        mark = (
            "  (identical by construction)"
            if (comparison.identical_by_construction)
            else ""
        )
        print(
            f"  {comparison.component:<14} {comparison.signal_r:>12.6f} "
            f"{comparison.control_r:>12.6f} {comparison.divergence_r:>12.6f}{mark}"
        )
    print(
        f"  {'TOTAL':<14} {signal.total_cost_r():>12.6f} "
        f"{control.total_cost_r():>12.6f} {invariance.total_divergence_r:>12.6f}"
    )
    print()
    swap = next(c for c in invariance.components if c.component == "swap")
    print(
        f"  Swap divergence measured {swap.divergence_r:.6f} R against a "
        f"registered prediction of {PREDICTED_SWAP_DIVERGENCE_R:.5f} R."
    )
    print(f"  {invariance.statement()}")
    print()

    print("-- breakeven spread " + "-" * 54)
    breakeven = solve_breakeven_spread(
        lambda floor: difference_at_floor(setup, model, floor),
        high=BREAKEVEN_HIGH,
        tolerance_points=BREAKEVEN_TOLERANCE,
        max_iterations=BREAKEVEN_MAX_ITERATIONS,
    )
    print(f"  paired difference: {breakeven.note}")
    print()

    print("-- K-5, every cost doubled " + "-" * 47)
    doubled_signal, doubled_control = run_two_arms(setup, model.doubled())
    doubled = bootstrap_mean(
        paired_difference(
            doubled_signal.r_by_decision, (doubled_control.r_by_decision,)
        ),
        expected_block=BOOTSTRAP_BLOCK,
        n_resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
    )
    print(_bootstrap_line("doubled costs", doubled))
    print()

    passed = primary.significant_at_5pct and primary.observed > 0

    print("-- H-003's contingency " + "-" * 51)
    survives = primary.p_value_one_sided <= H003_SURVIVES_IF_P_AT_MOST
    print(
        f"  this run's p = {primary.p_value_one_sided:.4f} "
        f"{'<=' if survives else '>'} {H003_SURVIVES_IF_P_AT_MOST}"
    )
    if survives:
        print("  H-003 survives BH at N_claims = 3.")
    else:
        print("  H-003 DOES NOT survive BH at N_claims = 3. Its acceptance does")
        print("  not hold in the enlarged family.")
    print()

    print("-- verdict " + "-" * 63)
    if passed:
        print("  The signal beats always-long at p < 0.05.")
        print("  The H-003 difference survives its most likely confound.")
        print("  Licensed: rung 3 becomes the question. Nothing beyond it.")
    else:
        print("  **Always-long matches or beats the signal.**")
        print("  The H-003 difference is a long bias and carries no directional")
        print("  information. H-003's directional reading is WITHDRAWN — the run")
        print("  stands as a record, the interpretation does not.")
        print("  Halt the ladder. Return to feature research. Do not build rung 3,")
        print("  and do not build an agent.")
    print()

    run_id = str(uuid.uuid4())
    manifest = RunManifest(
        run_id=run_id,
        timestamp_utc=datetime.now(UTC).isoformat(),
        git_commit=git_commit(),
        git_dirty=dirty,
        run_type=RunType.EVALUATION,
        hypothesis_id="H-007",
        data_snapshot_sha256=file_sha256(args.snapshot / "manifest.json"),
        data_window={
            "start": str(setup.frame.index[0]),
            "end": str(setup.frame.index[-1]),
        },
        evaluation_mode="walk_forward",
        holdout_openings_remaining=3,
        cumulative_hypothesis_count_n_claims=N_CLAIMS,
        feature_set_version=feature_set_version(tuple(f.name for f in FEATURES)),
        seeds={"bootstrap": BOOTSTRAP_SEED},
        env_lock_sha256=file_sha256(Path("uv.lock")),
        anonymisation_protocol="none",
        runtime_seconds=time.monotonic() - started,
        cost_model_version=model.version(),
        notes=(
            f"rung 2. difference {primary.observed:+.6f} R, "
            f"p={primary.p_value_one_sided:.4f}; "
            f"{'PASS' if passed else 'FAIL — H-003 directional reading withdrawn'}; "
            f"H-003 BH contingency at N_claims=3: "
            f"{'survives' if survives else 'does not survive'}; "
            f"split {FIRST_TEST_FRACTION:.2f}, {N_FOLDS} folds."
        ),
    )
    path = manifest.write(args.runs_dir)
    print("-- run record " + "-" * 60)
    print(f"  manifest      : {path}")
    print(f"  sha256        : {file_sha256(path)}")
    print(f"  runtime       : {manifest.runtime_seconds:.1f}s")
    print(RULE)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
