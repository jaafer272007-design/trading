"""Brier score, Brier Skill Score, and bootstrap confidence intervals.

Implements ``EVALUATION.md`` §3.1-§3.2. BSS is the project's headline number,
so the reference term matters as much as the model term: ``BS_reference`` is
the base rate (climatology) **over the same window**, not a fixed 0.5. Under
shuffled labels the base rate drifts from 0.5 by sampling noise alone, and
scoring against a fixed 0.5 would manufacture apparent skill from that drift.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

BOOTSTRAP_SEED: Final = 1337
"""REPRODUCIBILITY.md §3 — named, logged, not generated."""

BOOTSTRAP_RESAMPLES: Final = 10_000


@dataclass(frozen=True, slots=True)
class Interval:
    """A confidence interval."""

    lower: float
    upper: float

    def contains(self, value: float) -> bool:
        """True when ``value`` lies within the closed interval."""
        return self.lower <= value <= self.upper


def brier_score(
    forecasts: npt.NDArray[np.float64],
    outcomes: npt.NDArray[np.float64],
) -> float:
    """Mean squared error of probabilistic forecasts (``EVALUATION.md`` §3.1).

    Args:
        forecasts: Predicted probabilities in ``[0, 1]``.
        outcomes: Realised outcomes in ``{0, 1}``.

    Returns:
        ``(1/N) · Σ (f_i - o_i)²``. Lower is better.

    Raises:
        ValueError: If the inputs are empty or misaligned.
    """
    if forecasts.shape != outcomes.shape:
        raise ValueError(
            f"shape mismatch: forecasts {forecasts.shape} vs outcomes {outcomes.shape}"
        )
    if forecasts.size == 0:
        raise ValueError("brier_score requires at least one observation")

    diff = forecasts - outcomes
    return float(np.mean(diff * diff))


def brier_skill_score(
    forecasts: npt.NDArray[np.float64],
    outcomes: npt.NDArray[np.float64],
) -> float:
    """Brier Skill Score against the in-window base rate (``EVALUATION.md`` §3.2).

    ``BSS = 1 - BS_model / BS_reference``, where the reference forecast is the
    constant base rate of ``outcomes`` over this same window.

    Args:
        forecasts: Predicted probabilities in ``[0, 1]``.
        outcomes: Realised outcomes in ``{0, 1}``.

    Returns:
        BSS. ``≤ 0`` means no better than predicting the base rate.

    Raises:
        ValueError: If inputs are empty/misaligned, or the window is degenerate
            (all outcomes identical), which makes the reference score zero and
            the skill ratio undefined.
    """
    base_rate = float(np.mean(outcomes))
    reference = np.full_like(outcomes, base_rate)
    bs_reference = brier_score(reference, outcomes)

    if bs_reference == 0.0:
        raise ValueError(
            "degenerate evaluation window: every outcome is identical, so the "
            "climatological reference is perfect and BSS is undefined. This is "
            "a sample-construction defect, not a result."
        )

    return 1.0 - brier_score(forecasts, outcomes) / bs_reference


def bootstrap_ci(
    values: npt.NDArray[np.float64],
    *,
    confidence: float = 0.95,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> Interval:
    """Percentile bootstrap CI for the mean of ``values``.

    ``EVALUATION.md`` §3.2: "Report with bootstrap 95% CI. A BSS of 0.08
    [-0.04, 0.19] is not a result."

    Args:
        values: Sample to resample, e.g. one BSS per seed.
        confidence: Coverage, default 0.95.
        resamples: Bootstrap resamples.
        seed: PRNG seed. Fixed and logged per ``REPRODUCIBILITY.md`` §3.

    Returns:
        The percentile :class:`Interval` of the resampled means.

    Raises:
        ValueError: If ``values`` is empty or ``confidence`` is out of range.
    """
    if values.size == 0:
        raise ValueError("bootstrap_ci requires at least one value")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    rng = np.random.default_rng(seed)
    n = values.size
    means = np.empty(resamples, dtype=np.float64)
    for i in range(resamples):
        draw = rng.integers(0, n, size=n)
        means[i] = float(np.mean(values[draw]))

    tail = (1.0 - confidence) / 2.0
    lower = float(np.quantile(means, tail))
    upper = float(np.quantile(means, 1.0 - tail))
    return Interval(lower=lower, upper=upper)
