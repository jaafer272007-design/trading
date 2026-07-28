"""The statistics H-003 §F registers, and the solver H-005 (ii) requires.

Nothing here chooses anything. Every constant the functions take — block length,
resample count, seed — arrives from the caller and is registered in
``HYPOTHESES.md`` before the run, because a bootstrap tuned after seeing its own
output is not a bootstrap.

Why a stationary bootstrap and not an ordinary one
--------------------------------------------------

The decisions are already non-overlapping — ``evaluation/splits.py`` spaces them
a full horizon apart — so the dependence an i.i.d. bootstrap would ignore is not
label-window overlap. It is regime persistence: gold's volatility and drift
cluster over weeks, and consecutive decisions sit days apart, not months. An
i.i.d. resample would understate the variance of the mean and overstate
significance.

The stationary bootstrap (Politis and Romano) resamples blocks of geometrically
distributed length, which keeps the resampled series stationary — unlike a fixed
block length, which does not. Its one parameter is the expected block length,
and H-003 §F registers it at 10 decisions with sensitivity reported at 1 and 25.
Block length 1 is exactly the i.i.d. bootstrap, so the sensitivity report
contains its own null case.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """A resampled mean, its interval, and a one-sided p-value."""

    observed: float
    ci_low: float
    ci_high: float
    p_value_one_sided: float
    n_resamples: int
    expected_block: float
    seed: int

    @property
    def significant_at_5pct(self) -> bool:
        """Whether the one-sided p-value clears 0.05."""
        return self.p_value_one_sided < 0.05


def stationary_bootstrap_indices(
    n: int, expected_block: float, rng: np.random.Generator
) -> npt.NDArray[np.int64]:
    """One stationary-bootstrap resample of positions ``0…n-1``.

    Args:
        n: Series length.
        expected_block: Mean block length. Must be at least 1.
        rng: Seeded generator.

    Returns:
        ``n`` positions, wrapping circularly.

    Raises:
        ValueError: If ``n`` is not positive or the block length is below 1.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if expected_block < 1:
        raise ValueError(f"expected_block must be at least 1, got {expected_block}")

    restart = 1.0 / expected_block
    positions = np.arange(n, dtype=np.int64)

    # A block starts wherever the geometric coin says so, and always at 0.
    starts = rng.random(n) < restart
    starts[0] = True
    fresh = rng.integers(0, n, size=n).astype(np.int64)

    # Each position continues from the most recent block start, wrapping. The
    # accumulate is the loop, written so the cost does not scale with Python:
    # this runs 10,000 times per bootstrap over 1,364 decisions.
    last_start = np.maximum.accumulate(np.where(starts, positions, -1))
    return ((fresh[last_start] + (positions - last_start)) % n).astype(np.int64)


def bootstrap_mean(
    values: npt.NDArray[np.float64],
    *,
    expected_block: float,
    n_resamples: int,
    seed: int,
    alpha: float = 0.05,
) -> BootstrapResult:
    """Resample the mean of a dependent series.

    The p-value tests ``H0: mean = 0`` against ``H1: mean > 0``, one-sided, by
    recentring the bootstrap distribution on zero. It uses the ``(1 + count) /
    (B + 1)`` form so it is never reported as exactly zero — a p-value of 0 is a
    statement no finite resample can support.

    Args:
        values: One observation per decision.
        expected_block: Mean block length.
        n_resamples: Number of resamples.
        seed: Generator seed.
        alpha: Two-sided interval width, ``0.05`` giving a 95% interval.

    Returns:
        The result.

    Raises:
        ValueError: If ``values`` is empty.
    """
    if values.size == 0:
        raise ValueError("cannot bootstrap an empty series")

    rng = np.random.default_rng(seed)
    observed = float(np.mean(values))
    means = np.empty(n_resamples, dtype=np.float64)
    for b in range(n_resamples):
        idx = stationary_bootstrap_indices(values.size, expected_block, rng)
        means[b] = float(np.mean(values[idx]))

    low, high = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    exceed = int(np.sum(means - observed >= observed))
    return BootstrapResult(
        observed=observed,
        ci_low=float(low),
        ci_high=float(high),
        p_value_one_sided=(1 + exceed) / (n_resamples + 1),
        n_resamples=n_resamples,
        expected_block=expected_block,
        seed=seed,
    )


def paired_difference(
    signal_r: npt.NDArray[np.float64],
    control_r: tuple[npt.NDArray[np.float64], ...],
) -> npt.NDArray[np.float64]:
    """The per-decision difference H-003 §F tests.

    ``d_i = pnl_signal,i - mean_s pnl_random,s,i``. Averaging the controls before
    differencing, rather than differencing against each control separately, is
    what makes this one statistic instead of thirty — thirty would be thirty
    tests and would need correcting as such.

    Args:
        signal_r: Signal arm result per decision, in R.
        control_r: One array per control arm, each aligned to the same grid.

    Returns:
        One difference per decision.

    Raises:
        ValueError: If there are no controls or the lengths disagree.
    """
    if not control_r:
        raise ValueError("paired_difference needs at least one control arm")
    lengths = {signal_r.size} | {c.size for c in control_r}
    if len(lengths) != 1:
        raise ValueError(f"arms disagree in decision count: {sorted(lengths)}")
    return signal_r - np.mean(np.vstack(control_r), axis=0)


@dataclass(frozen=True, slots=True)
class BreakevenSpread:
    """Where the edge reaches zero, in spread points.

    ``points`` is ``None`` when the answer is outside the bracket, and ``note``
    says which side. That is not a failure to compute — "the edge is negative at
    zero spread" and "the edge survives past 2,000 points" are both answers, and
    both are more informative than a number produced by extrapolation.
    """

    points: float | None
    expectancy_at_low: float
    expectancy_at_high: float
    low: float
    high: float
    iterations: int
    note: str


#: Points at which the curve is sampled before bisecting, to find out whether
#: bisection is a legitimate thing to do to it. Nine is enough to catch the
#: oscillation H-007 exhibited and cheap enough to run every time.
MONOTONICITY_PROBE_POINTS: Final = 9


def solve_breakeven_spread(
    evaluate: Callable[[float], float],
    *,
    low: float = 0.0,
    high: float = 2000.0,
    tolerance_points: float = 1.0,
    max_iterations: int = 40,
    probe_points: int = MONOTONICITY_PROBE_POINTS,
) -> BreakevenSpread:
    """Find the spread floor at which expectancy reaches zero, if there is one.

    H-005 (ii): "every result reported while this gate is open must state the
    breakeven spread". The point of the requirement is to turn an argument about
    whether x5 is the right inflation factor into a measured quantity a reader
    can apply their own judgement to.

    Solved by re-simulation rather than by algebra. A wider spread does not just
    subtract a constant: it moves the executable price, which moves the trigger,
    which changes *which* bar a position exits on.

    Why this probes before it bisects
    ---------------------------------

    Bisection assumes one sign change. This curve is not guaranteed to have one,
    and **H-007 is the case that proved it**: the paired difference measured
    ``+0.00055`` at a zero floor, ``-0.00014`` at 75, ``+0.0107`` at 150,
    ``-0.0040`` at 500, ``+0.0028`` at 1000 — noise oscillating around zero,
    because when the effect is near zero the exit-bar reshuffling dominates it.
    Bisection on that returned "1076.2 points", a real crossing and a
    meaningless number, stated with a tolerance that made it look precise.

    So the curve is sampled first. More than one sign change across the probe
    grid means there is no breakeven to report, and saying that is the correct
    answer rather than a failure to produce one.

    Args:
        evaluate: Maps a spread floor in points to expectancy in R.
        low: Lower bracket, in points.
        high: Upper bracket, in points.
        tolerance_points: Stop when the bracket is narrower than this.
        max_iterations: Hard cap on bisection steps.
        probe_points: Grid size for the monotonicity check. Two disables it.

    Returns:
        The breakeven spread, or a non-answer that says which kind it is.

    Raises:
        ValueError: If the bracket is empty or the probe grid is too small.
    """
    if high <= low:
        raise ValueError(f"empty bracket: low={low}, high={high}")
    if probe_points < 2:
        raise ValueError(f"probe_points must be at least 2, got {probe_points}")

    at_low = evaluate(low)
    at_high = evaluate(high)

    grid = [low + (high - low) * i / (probe_points - 1) for i in range(probe_points)]
    values = [at_low, *(evaluate(x) for x in grid[1:-1]), at_high]
    crossings = sum(1 for a, b in pairwise(values) if (a > 0) != (b > 0))
    if crossings > 1:
        sample = ", ".join(
            f"{x:.0f}:{v:+.6f}" for x, v in zip(grid, values, strict=True)
        )
        return BreakevenSpread(
            points=None,
            expectancy_at_low=at_low,
            expectancy_at_high=at_high,
            low=low,
            high=high,
            iterations=0,
            note=(
                f"no breakeven: expectancy changes sign {crossings} times across "
                f"the bracket, so there is no single spread at which the edge "
                f"reaches zero. Sampled — {sample}. A bisection on this would "
                f"return one of those crossings and present it as the answer."
            ),
        )

    if at_low <= 0:
        return BreakevenSpread(
            points=None,
            expectancy_at_low=at_low,
            expectancy_at_high=at_high,
            low=low,
            high=high,
            iterations=0,
            note=(
                f"expectancy is {at_low:.6f} R at a spread floor of {low:.0f} "
                f"points — non-positive before any spread is charged. There is "
                f"no breakeven: the edge does not exist at any cost assumption."
            ),
        )
    if at_high > 0:
        return BreakevenSpread(
            points=None,
            expectancy_at_low=at_low,
            expectancy_at_high=at_high,
            low=low,
            high=high,
            iterations=0,
            note=(
                f"expectancy is still {at_high:.6f} R at a spread floor of "
                f"{high:.0f} points. The breakeven is above the bracket; widen "
                f"it rather than reporting the bound as the answer."
            ),
        )

    lo, hi = low, high
    iterations = 0
    while hi - lo > tolerance_points and iterations < max_iterations:
        mid = 0.5 * (lo + hi)
        if evaluate(mid) > 0:
            lo = mid
        else:
            hi = mid
        iterations += 1

    return BreakevenSpread(
        points=0.5 * (lo + hi),
        expectancy_at_low=at_low,
        expectancy_at_high=at_high,
        low=low,
        high=high,
        iterations=iterations,
        note=(
            f"expectancy crosses zero at a spread floor of {0.5 * (lo + hi):.1f} "
            f"points, bracketed to within {hi - lo:.1f}."
        ),
    )
