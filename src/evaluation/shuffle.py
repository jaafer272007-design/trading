"""The shuffled-labels harness — ``EVALUATION.md`` §5.1, gate **K-1**.

Permute the mapping between market state and outcome, then run the
deterministic path. A model trained on scrambled labels has nothing real to
learn, so any measured out-of-sample skill was manufactured by the machinery.

Pass conditions are the three registered in ``HYPOTHESES.md`` H-001 and
mirrored into ``EVALUATION.md`` §5.1. They are constants here, not parameters,
because a threshold that can be passed in at the call site is a threshold that
can be chosen after seeing the numbers (``RESEARCH.md`` §5.3).

What this gate does not cover
-----------------------------

Global permutation destroys the temporal autocorrelation that purge and
embargo exist to control: once ``label[T]`` is a random draw from elsewhere in
the series, a training sample whose label window overlaps the test period
carries no test-period information. **This harness is therefore structurally
blind to a broken purge or embargo**, which needs its own integrity check
(``REPRODUCIBILITY.md`` §6 Tier 1 step 4). It is likewise blind to a feature
that peeks at future prices, since shuffling labels leaves features untouched
— that is §5.3 / K-2's job.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from evaluation.pipeline import LeakMode, run_walk_forward
from evaluation.splits import Fold
from metrics.brier import Interval, bootstrap_ci
from models.logistic import LogisticRegression

SHUFFLED_LABEL_SEEDS: Final = tuple(range(30))
"""REPRODUCIBILITY.md §3: shuffled_labels [0..29], enumerated not generated."""

EPSILON_MEAN_BSS: Final = 0.01
"""Registered researcher degree of freedom. HYPOTHESES.md H-001.

A materiality floor at one fifth of K-3's 0.05, not a test of E[BSS] = 0. A
strict test against zero is hypersensitive: with 30 seeds and low variance a
meaningless +0.0001 bias yields a large statistic and a spurious halt.
"""

MAX_SINGLE_SEED_BSS: Final = 0.05
"""No single seed may reach the threshold the project itself calls skill."""

MAX_MEDIAN_BSS: Final = 0.0
"""The distribution's centre must sit where theory says it must."""


@dataclass(frozen=True, slots=True)
class ShuffleStudy:
    """Result of a shuffled-labels sweep across the enumerated seeds."""

    seeds: tuple[int, ...]
    bss_per_seed: npt.NDArray[np.float64]
    mean_ci: Interval
    n_decisions: int
    leak: LeakMode
    fitted_parameters: int = 0
    """Capacity as fitted. H-010 records the trip/silent set beside it.

    Zero on studies predating H-010, which is honest: they did not measure it.
    """

    estimator: str = ""
    """Combiner class actually fitted, for the same reason."""

    converged: bool | None = None
    """Whether every fold of every seed converged. ``None`` when unreported.

    H-011 makes a non-converged fit VOID rather than negative, and the same
    reasoning applies to the null: a null measured with an underfit combiner
    understates what a fitted one would find.
    """

    worst_gradient_norm: float | None = None
    """Largest gradient infinity-norm across every fold and seed."""

    @property
    def mean_bss(self) -> float:
        """Mean BSS across seeds."""
        return float(np.mean(self.bss_per_seed))

    @property
    def median_bss(self) -> float:
        """Median BSS across seeds."""
        return float(np.median(self.bss_per_seed))

    @property
    def max_bss(self) -> float:
        """Largest single-seed BSS."""
        return float(np.max(self.bss_per_seed))

    @property
    def condition_i(self) -> bool:
        """Upper bound of the 95% bootstrap CI of mean BSS ≤ ε."""
        return self.mean_ci.upper <= EPSILON_MEAN_BSS

    @property
    def condition_ii(self) -> bool:
        """No single seed reaches K-3's skill threshold."""
        return self.max_bss <= MAX_SINGLE_SEED_BSS

    @property
    def condition_iii(self) -> bool:
        """Median BSS at or below zero."""
        return self.median_bss <= MAX_MEDIAN_BSS

    @property
    def passed(self) -> bool:
        """True only when all three registered conditions hold."""
        return self.condition_i and self.condition_ii and self.condition_iii

    def summary(self) -> str:
        """Render a report suitable for a CI log or a run record."""
        verdict = "PASS" if self.passed else "FAIL — K-1"
        tick = {True: "ok", False: "FAIL"}
        return "\n".join(
            [
                f"shuffled-labels gate {verdict}  (leak={self.leak.value})",
                f"  seeds ............ {len(self.seeds)}",
                f"  decisions/seed ... {self.n_decisions}",
                f"  mean BSS ......... {self.mean_bss:+.6f}",
                f"  95% CI of mean ... [{self.mean_ci.lower:+.6f}, "
                f"{self.mean_ci.upper:+.6f}]",
                f"  median BSS ....... {self.median_bss:+.6f}",
                f"  max BSS .......... {self.max_bss:+.6f}",
                f"  (i)   CI upper <= {EPSILON_MEAN_BSS}   {tick[self.condition_i]}",
                f"  (ii)  max      <= {MAX_SINGLE_SEED_BSS}   "
                f"{tick[self.condition_ii]}",
                f"  (iii) median   <= {MAX_MEDIAN_BSS}    {tick[self.condition_iii]}",
            ]
        )


def permute_labels(
    labels: npt.NDArray[np.float64], seed: int
) -> npt.NDArray[np.float64]:
    """Globally permute a label vector.

    Args:
        labels: Labels to permute.
        seed: PRNG seed.

    Returns:
        A permuted copy. The multiset of labels is preserved exactly, so the
        base rate is unchanged and BSS's climatological reference is
        comparable across seeds.
    """
    rng = np.random.default_rng(seed)
    return labels[rng.permutation(labels.size)]


def run_shuffled_label_study(
    features: npt.NDArray[np.float64],
    labels: npt.NDArray[np.float64],
    folds: tuple[Fold, ...],
    *,
    seeds: tuple[int, ...] = SHUFFLED_LABEL_SEEDS,
    leak: LeakMode = LeakMode.NONE,
    model_factory: type[LogisticRegression] = LogisticRegression,
) -> ShuffleStudy:
    """Run the deterministic path once per seed under permuted labels.

    Args:
        features: Design matrix.
        labels: True labels, permuted afresh for each seed.
        folds: Walk-forward folds.
        seeds: Seeds to sweep. Defaults to the 30 enumerated seeds.
        leak: Deliberate corruption, for negative fixtures.
        model_factory: Combiner class. H-010 sweeps the leak suite under both
            registered fitting rules, and the null a gate is judged against is
            a property of the combiner that measured it.

    Returns:
        The :class:`ShuffleStudy`.

    Raises:
        ValueError: If fewer than two seeds are supplied — a single seed is a
            finding about that seed (``REPRODUCIBILITY.md`` §3).
    """
    if len(seeds) < 2:
        raise ValueError(
            f"a seed sweep needs at least 2 seeds, got {len(seeds)}; "
            f"REPRODUCIBILITY.md §3 requires results across a sweep, never a "
            f"single seed"
        )

    scores = np.empty(len(seeds), dtype=np.float64)
    n_decisions = 0
    fitted_parameters = 0
    estimator = ""
    all_converged: bool | None = None
    worst_norm: float | None = None

    for i, seed in enumerate(seeds):
        result = run_walk_forward(
            features,
            permute_labels(labels, seed),
            folds,
            leak=leak,
            model_factory=model_factory,
        )
        scores[i] = result.bss
        n_decisions = result.n_decisions
        fitted_parameters = result.fitted_parameters
        estimator = result.estimator

        if result.converged is not None:
            all_converged = result.converged and (all_converged is not False)
        if result.worst_gradient_norm is not None:
            worst_norm = max(worst_norm or 0.0, result.worst_gradient_norm)

    return ShuffleStudy(
        seeds=tuple(seeds),
        bss_per_seed=scores,
        mean_ci=bootstrap_ci(scores),
        n_decisions=n_decisions,
        leak=leak,
        fitted_parameters=fitted_parameters,
        estimator=estimator,
        converged=all_converged,
        worst_gradient_norm=worst_norm,
    )
