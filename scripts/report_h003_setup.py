"""What H-003 will run against, measured before it runs.

Run::

    uv run python scripts/report_h003_setup.py <snapshot>

Fits nothing, simulates nothing, writes nothing. Every number here is a property
of the calendar, the eligibility mask and the registered constants, and would be
identical under any labels at all — which is what makes it reportable in advance
without the report being a peek at the answer.

Three things it exists to surface
---------------------------------

**The trade window is one bar longer than the label window.** H-003 §D fills at
the open of ``T+1`` and times out after 24 bars, so a decision at ``T`` touches
bars through ``T+25``. H-001's eligibility mask validates ``[T, T+24]``. That one
extra bar is not covered by the registered mask, and a decision whose 25th bar is
invalid would be simulated across a hole. The count after that constraint is
reported here rather than discovered in a result.

**The risk geometry depends on a feature the design matrix does not contain.**
Stops and sizing come from ``atr_14``, which is registered and passes H-002 but
is deliberately not in H-003's signal (§A). Its own validity is therefore a new
eligibility condition: an ATR averaged across an unexplained gap sets a stop
distance that looks perfectly ordinary.

**The event model reaches very little of the series.** ``costs.spread_multipliers``
knows the weekly open and the payrolls hour and no other release. The share of
bars it touches is a number, and printing it is the difference between a stated
limitation and an omission.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import pandas as pd
from run_h001 import FEATURES, FIRST_TEST_FRACTION, N_FOLDS, build_design

from backtest.costs import (
    COMMISSION_POINTS_PER_LOT_PER_SIDE,
    LATENCY_DEFAULT_SECONDS,
    SLIPPAGE_ATR_COEFF,
    SPREAD_FLOOR_POINTS,
    SWAP_LONG_POINTS_PER_LOT_PER_NIGHT,
    SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT,
    CostModel,
    multiplier_coverage,
    spread_multipliers,
)
from backtest.engine import COST_DIVERGENCE_TOLERANCE
from backtest.execution import RiskModel
from data.classify import feature_validity, trade_window_validity
from data.loader import load_window
from evaluation.splits import walk_forward_folds
from features.atr import ATR
from labels.direction import DEFAULT_HORIZON

RULE = "=" * 74

#: EVALUATION.md §1, K-6.
K6_DECISION_FLOOR = 150

#: H-003 §D, registered. Restated here rather than imported from a runner so the
#: report describes the registration rather than whatever a script happens to
#: hold.
STOP_ATR_MULT = 1.5
TARGET_ATR_MULT = 1.5
MAX_HOLD_BARS = 24
RISK_PER_TRADE = 100.0
N_RANDOM_SEEDS = 30
BOOTSTRAP_BLOCK = 10
BOOTSTRAP_BLOCK_SENSITIVITY = (1, 25)
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 1337

#: The ATR feature the risk geometry reads. Not part of the signal (§A).
RISK_FEATURE = ATR(period=14)


def _grid(
    eligible: npt.NDArray[np.bool_], n_bars: int, horizon: int
) -> npt.NDArray[np.int64]:
    """The registered decision grid under one eligibility mask.

    Args:
        eligible: Eligibility mask.
        n_bars: Series length.
        horizon: Label horizon, which is also the decision spacing.

    Returns:
        Pooled decision positions across all folds.
    """
    start = int(n_bars * FIRST_TEST_FRACTION)
    size = (n_bars - start) // N_FOLDS
    folds = walk_forward_folds(
        valid=eligible,
        n_folds=N_FOLDS,
        first_test_start=start,
        test_size=size,
        horizon=horizon,
    )
    return np.concatenate([fold.test for fold in folds]).astype(np.int64)


def main(argv: list[str] | None = None) -> int:
    """Print the setup report.

    Args:
        argv: Command-line arguments, for testing.

    Returns:
        Process exit code. Non-zero if K-6 would not clear.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    args = parser.parse_args(argv)

    frame = load_window(args.snapshot, valid_only=False)
    design, _, h001_eligible = build_design(frame, args.horizon)
    bar_valid = frame["valid"].to_numpy(dtype=np.bool_)
    n_bars = len(frame)
    model = CostModel()

    print(RULE)
    print("H-003 SETUP — measured before the run, fits nothing")
    print(RULE)
    print(f"  snapshot       : {args.snapshot}")
    print(f"  in-window bars : {n_bars:,}")
    print(f"  horizon        : {args.horizon}   hold {MAX_HOLD_BARS} bars")
    print()

    print("-- eligibility, constraint by constraint " + "-" * 33)
    atr = RISK_FEATURE.compute(frame).to_numpy(dtype=np.float64)
    atr_ok = (
        np.isfinite(atr)
        & (atr > 0)
        & feature_validity(bar_valid, RISK_FEATURE.lookback_bars)
    )
    window_ok = trade_window_validity(bar_valid, MAX_HOLD_BARS)

    stages: list[tuple[str, npt.NDArray[np.bool_]]] = [
        ("H-001 registered mask", h001_eligible),
        ("+ atr_14 valid and finite", h001_eligible & atr_ok),
        ("+ trade window [T, T+25] valid", h001_eligible & atr_ok & window_ok),
    ]

    print(f"  {'constraint':<34} {'eligible bars':>14} {'decisions':>10}")
    counts: list[int] = []
    for label, mask in stages:
        decisions = _grid(mask, n_bars, args.horizon)
        counts.append(len(decisions))
        print(f"  {label:<34} {int(mask.sum()):>14,} {len(decisions):>10,}")
    print()

    final = counts[-1]
    lost = counts[0] - final
    print(f"  The registered grid gives {counts[0]:,} decisions.")
    if lost == 0:
        print("  Neither new constraint removes any of them: every decision on")
        print("  the grid already has a valid ATR and a valid trade window.")
    else:
        print(f"  The two additional constraints remove {lost:,} of them.")
        print("  That is a change to the registered decision count and must be")
        print("  recorded in H-003 before the run, not explained after it.")
    print()

    print("-- K-6 " + "-" * 67)
    print(f"  decisions              : {final:,}")
    print(f"  floor (EVALUATION.md §1): {K6_DECISION_FLOOR}")
    print(f"  margin                 : {final / K6_DECISION_FLOOR:.1f}x")
    verdict = "clears" if final >= K6_DECISION_FLOOR else "DOES NOT CLEAR"
    print(f"  K-6 {verdict}")
    print()

    print("-- the cost model " + "-" * 56)
    multipliers = spread_multipliers(pd.DatetimeIndex(frame.index), model)
    coverage = multiplier_coverage(multipliers)
    print(f"  cost_model_version     : {model.version()[:16]}…")
    print(f"  spread floor           : {SPREAD_FLOOR_POINTS:.0f} points (H-005 (i))")
    print(f"  weekly-open bars       : {coverage.n_weekly_open:,}")
    print(f"  payrolls-hour bars     : {coverage.n_news:,}")
    print(f"  share above the floor  : {coverage.share_elevated:.2%}")
    print()
    print("     The other 97%+ of bars are priced at the flat floor, including")
    print("     every scheduled release that is not payrolls. That error is")
    print("     optimistic and is bounded by K-5 and the breakeven spread, not")
    print("     removed by them.")
    print()

    print("-- registered constants " + "-" * 50)
    risk = RiskModel(
        stop_atr_mult=STOP_ATR_MULT,
        target_atr_mult=TARGET_ATR_MULT,
        max_hold_bars=MAX_HOLD_BARS,
        risk_per_trade_currency=RISK_PER_TRADE,
    )
    rows: list[tuple[str, object]] = [
        ("signal features", ", ".join(f.name for f in FEATURES)),
        ("risk feature (not signal)", RISK_FEATURE.name),
        ("signal threshold tau", 0.0),
        ("stop / target", f"{risk.stop_atr_mult} / {risk.target_atr_mult} x ATR"),
        ("max hold", f"{risk.max_hold_bars} bars"),
        ("risk per trade", f"{risk.risk_per_trade_currency:.0f} currency units"),
        ("spread floor", f"{model.spread_floor_points:.0f} points"),
        ("slippage coeff", SLIPPAGE_ATR_COEFF),
        ("commission", f"{COMMISSION_POINTS_PER_LOT_PER_SIDE} points/lot/side"),
        (
            "swap long / short",
            f"{SWAP_LONG_POINTS_PER_LOT_PER_NIGHT} / "
            f"{SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT} points/lot/night",
        ),
        ("latency", f"{LATENCY_DEFAULT_SECONDS} s"),
        ("random seeds", f"{N_RANDOM_SEEDS}, enumerated 0-{N_RANDOM_SEEDS - 1}"),
        (
            "bootstrap block",
            f"{BOOTSTRAP_BLOCK} (sensitivity {BOOTSTRAP_BLOCK_SENSITIVITY})",
        ),
        ("bootstrap resamples", f"{BOOTSTRAP_RESAMPLES:,} at seed {BOOTSTRAP_SEED}"),
        ("cost divergence tolerance", f"{COST_DIVERGENCE_TOLERANCE:.0%}"),
    ]
    for label, value in rows:
        print(f"  {label:<28} {value}")
    print()

    print("-- what has NOT been done " + "-" * 48)
    print("  No arm has been run. No combiner has been fitted. No manifest has")
    print("  been written. The design matrix was built only to compute the")
    print(f"  eligibility mask above ({design.shape[0]:,} x {design.shape[1]}).")
    print(RULE)
    return 0 if final >= K6_DECISION_FLOOR else 1


if __name__ == "__main__":
    raise SystemExit(main())
