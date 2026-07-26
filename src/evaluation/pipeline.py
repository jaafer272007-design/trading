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

    A genuine and serious leak — and one this gate does **not** detect with the
    combiner configured here. Measured at the H-001 geometry: mean BSS
    ``-0.0009``, gate silent.

    The reason is capacity, not correctness. The combiner has three features
    plus an intercept: four parameters. Exploiting overlap requires memorising
    individual rows, and 167 test rows folded into 10,000-26,000 training rows
    contribute under 2% of the gradient while carrying random labels. Four
    parameters cannot represent them, so the fitted coefficients barely move.

    Detectability here is a property of the *estimator*, not of the leak.
    A high-capacity stacker — the gradient-boosted one at ``EVALUATION.md`` §2
    rung 7 — would memorise those rows and trip the gate immediately. Recorded
    rather than removed, because "K-1 with a linear stacker cannot see
    train/test overlap" is a limitation that has to be known before the gate is
    trusted.
    """

    TARGET_ENCODING_ON_ALL = "target_encoding_on_all"
    """Append a target-mean encoding computed over train and test together.

    The member of the "preprocessing fitted on everything" family that actually
    carries label information rather than only feature statistics, and the one
    a low-capacity linear model can still read — because the leak arrives as a
    *feature column* rather than as rows to memorise.

    High-cardinality buckets (~4 rows each) make it severe, which is exactly
    the notorious real-world case: target-encoding a near-continuous or
    near-unique key. Must trip K-1.
    """


_ENCODING_BUCKET_SIZE = 4
"""Rows per target-encoding bucket. Small enough for a severe leak."""


def _target_encode_on_all(
    features: npt.NDArray[np.float64], labels: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Compute a target-mean encoding over every row, train and test alike.

    Buckets are rank-ordered on the first feature, ``_ENCODING_BUCKET_SIZE``
    rows apiece, and each row receives the mean label of its bucket — including
    its own. That is the leak.

    Args:
        features: Design matrix.
        labels: Labels, already permuted by the caller where applicable.

    Returns:
        One encoded column, aligned to ``features`` rows.
    """
    order = np.argsort(features[:, 0], kind="stable")
    bucket = np.empty(order.size, dtype=np.int64)
    bucket[order] = np.arange(order.size) // _ENCODING_BUCKET_SIZE

    sums = np.bincount(bucket, weights=labels)
    counts = np.bincount(bucket)
    return (sums / counts)[bucket]


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
    elif leak is LeakMode.TARGET_ENCODING_ON_ALL:
        design = np.column_stack([features, _target_encode_on_all(features, labels)])

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
