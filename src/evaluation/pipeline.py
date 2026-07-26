"""The deterministic path: features → standardiser → combiner → probabilities.

Scope is fixed by ``REPRODUCIBILITY.md`` §6: "run the shuffled-labels gate on
the deterministic path (features → stacker), not the full LLM path." No
agents, no LLM. An LLM anywhere in this loop would inject non-determinism into
the exact test whose purpose is to measure noise.

Leak modes
----------

``LeakMode`` lets a caller deliberately corrupt the pipeline. This is not a
debugging convenience — it is the point. A shuffled-labels run that reports
"no edge" is unfalsifiable unless a deliberately leaky variant is shown to
trip **K-1**, exactly as the deliberately leaky negative fixture under
``tests/fixtures/`` pins the causal harness from the failing side. A gate that
has never fired is indistinguishable from a gate that cannot fire.

That fixture is named only from ``tests/``, never from here: nothing under
``src/`` may reference it even in prose, so the containment check in
``tests/test_causality_harness.py`` can stay a blunt substring scan rather than
a parser that a dynamic import could slip past.
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np
import numpy.typing as npt

from evaluation.splits import Fold
from metrics.brier import brier_skill_score
from models.logistic import LogisticRegression, Standardizer


class LeakMode(Enum):
    """Deliberate corruptions of the pipeline, for negative fixtures."""

    NONE = "none"
    """The honest pipeline."""

    LABEL_IN_FEATURES = "label_in_features"
    """Append the label itself as a feature column.

    The bluntest possible leak, and the one every other leak is a subtler
    version of. Must trip K-1.
    """

    SCALER_FIT_ON_ALL = "scaler_fit_on_all"
    """Fit the standardiser on train and test together.

    The textbook "preprocessing fitted on everything" mistake. Note what it
    does and does not move: it leaks the test set's *feature distribution*, not
    any label information. Under shuffled labels there is no relationship
    between features and labels to exploit, so this is expected **not** to
    produce measurable skill. It is run anyway, and reported, precisely so the
    distinction is measured rather than assumed.
    """

    TRAIN_TEST_OVERLAP = "train_test_overlap"
    """Include the test indices in the training set.

    Label information reaches the model directly, so the combiner can memorise
    the shuffled labels of the very rows it is scored on. Must trip K-1. This
    is the fixture that actually exercises the gate's sensitivity to
    preprocessing-shaped mistakes, because unlike ``SCALER_FIT_ON_ALL`` it
    carries labels rather than only feature statistics.
    """


@dataclass(frozen=True, slots=True)
class FoldResult:
    """Out-of-sample predictions for one fold."""

    fold_index: int
    test_index: npt.NDArray[np.int64]
    probabilities: npt.NDArray[np.float64]
    outcomes: npt.NDArray[np.float64]
    n_train: int


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    """Pooled out-of-sample result across all folds."""

    fold_results: tuple[FoldResult, ...]
    probabilities: npt.NDArray[np.float64]
    outcomes: npt.NDArray[np.float64]
    bss: float

    @property
    def n_decisions(self) -> int:
        """Count of pooled out-of-sample decisions."""
        return int(self.outcomes.size)


def run_walk_forward(
    features: npt.NDArray[np.float64],
    labels: npt.NDArray[np.float64],
    folds: tuple[Fold, ...],
    *,
    leak: LeakMode = LeakMode.NONE,
    model_factory: type[LogisticRegression] = LogisticRegression,
) -> WalkForwardResult:
    """Fit per fold, predict out of sample, pool, and score.

    Args:
        features: Design matrix, shape ``(n_bars, n_features)``.
        labels: Binary labels aligned to ``features`` rows.
        folds: Walk-forward folds.
        leak: Deliberate corruption to apply. Defaults to none.
        model_factory: Combiner class, for substitution in tests.

    Returns:
        The pooled :class:`WalkForwardResult`.

    Raises:
        ValueError: If shapes disagree or no fold produced predictions.
    """
    if features.shape[0] != labels.shape[0]:
        raise ValueError(
            f"row mismatch: features {features.shape[0]}, labels {labels.shape[0]}"
        )

    design = features
    if leak is LeakMode.LABEL_IN_FEATURES:
        design = np.column_stack([features, labels])

    results: list[FoldResult] = []
    for fold in folds:
        train_idx = fold.train
        if leak is LeakMode.TRAIN_TEST_OVERLAP:
            train_idx = np.union1d(fold.train, fold.test)

        if train_idx.size == 0 or fold.test.size == 0:
            continue

        x_train = design[train_idx]
        x_test = design[fold.test]

        scaler = Standardizer()
        if leak is LeakMode.SCALER_FIT_ON_ALL:
            scaler.fit(np.vstack([x_train, x_test]))
        else:
            scaler.fit(x_train)

        model = model_factory()
        model.fit(scaler.transform(x_train), labels[train_idx])
        probabilities = model.predict_proba(scaler.transform(x_test))

        results.append(
            FoldResult(
                fold_index=fold.index,
                test_index=fold.test,
                probabilities=probabilities,
                outcomes=labels[fold.test],
                n_train=int(train_idx.size),
            )
        )

    if not results:
        raise ValueError("no fold produced predictions; check the fold geometry")

    pooled_p = np.concatenate([r.probabilities for r in results])
    pooled_y = np.concatenate([r.outcomes for r in results])

    return WalkForwardResult(
        fold_results=tuple(results),
        probabilities=pooled_p,
        outcomes=pooled_y,
        bss=brier_skill_score(pooled_p, pooled_y),
    )
