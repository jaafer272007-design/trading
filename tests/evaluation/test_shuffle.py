"""Acceptance tests for the shuffled-labels gate (K-1).

Same argument as ``tests/test_causality_harness.py``: a gate that has never
fired is indistinguishable from a gate that cannot fire. The planted-leak
fixtures here are the load-bearing tests — they are what make a clean
shuffled-labels result mean something rather than merely look reassuring.
"""

import numpy as np
import numpy.typing as npt
import pytest

from data.synthetic import generate_ohlcv
from evaluation.pipeline import LeakMode, run_walk_forward
from evaluation.shuffle import (
    SHUFFLED_LABEL_SEEDS,
    permute_labels,
    run_shuffled_label_study,
)
from evaluation.splits import Fold, walk_forward_folds
from features.log_return import LogReturn
from features.range_position import RangePosition
from features.realized_vol import RealizedVol
from labels.direction import direction_label

Dataset = tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], tuple[Fold, ...]]

HORIZON = 24
N_BARS = 6_000
# A reduced sweep keeps these tests inside the CI budget; the full 30-seed
# sweep is exercised by scripts/run_h001_harness_validation.py.
TEST_SEEDS = (0, 1, 2, 3, 4)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    """Features, labels, and folds over a synthetic series."""
    df = generate_ohlcv(n_bars=N_BARS, seed=42)
    columns = [
        LogReturn(window=24).compute(df),
        RealizedVol(window=24).compute(df),
        RangePosition(window=48).compute(df),
    ]
    features = np.column_stack([c.to_numpy(dtype=np.float64) for c in columns])
    labels = direction_label(df, horizon=HORIZON).to_numpy(dtype=np.float64)

    valid = ~np.isnan(features).any(axis=1) & ~np.isnan(labels)
    folds = walk_forward_folds(
        valid=valid,
        n_folds=5,
        first_test_start=1_000,
        test_size=1_000,
        horizon=HORIZON,
    )
    return np.nan_to_num(features), np.nan_to_num(labels), folds


# ---------------------------------------------------------------------------
# The clean path
# ---------------------------------------------------------------------------


def test_clean_pipeline_shows_no_edge_under_shuffled_labels(dataset: Dataset) -> None:
    features, labels, folds = dataset

    study = run_shuffled_label_study(features, labels, folds, seeds=TEST_SEEDS)

    assert study.passed, study.summary()


# ---------------------------------------------------------------------------
# Planted leaks — these must trip K-1
# ---------------------------------------------------------------------------


def test_label_in_feature_matrix_trips_the_gate(dataset: Dataset) -> None:
    """The bluntest leak. If this passes, the gate is decoration."""
    features, labels, folds = dataset

    study = run_shuffled_label_study(
        features, labels, folds, seeds=TEST_SEEDS, leak=LeakMode.LABEL_IN_FEATURES
    )

    assert not study.passed
    assert study.mean_bss > 0.5, study.summary()


def test_target_encoding_on_all_data_trips_the_gate(dataset: Dataset) -> None:
    """Preprocessing that carries *label* information, fitted on everything.

    Unlike train/test overlap this arrives as a feature column rather than as
    rows to memorise, so a four-parameter linear combiner can read it. This is
    the fixture that genuinely covers the "preprocessing fitted on all data"
    category.
    """
    features, labels, folds = dataset

    study = run_shuffled_label_study(
        features,
        labels,
        folds,
        seeds=TEST_SEEDS,
        leak=LeakMode.TARGET_ENCODING_ON_ALL,
    )

    assert not study.passed
    assert study.mean_bss > 0.05, study.summary()


def test_train_test_overlap_is_invisible_to_a_low_capacity_combiner(
    dataset: Dataset,
) -> None:
    """A real leak this gate does not catch. Recorded, not hidden.

    Measured at the H-001 geometry: mean BSS -0.0009, gate silent. The combiner
    has four parameters and cannot memorise the 167 overlapped rows, which
    carry random labels and under 2% of the gradient.

    Detectability is a property of the estimator, not of the leak: a
    high-capacity stacker would trip immediately. This test exists so the
    limitation is a measured fact rather than an assumption, and so nobody
    reads a green K-1 as proof that fold construction is sound.

    An earlier draft asserted the opposite. It tripped on a 6,000-bar sample
    with five seeds and stayed silent at full scale — a fixture that appeared
    to work for the wrong reason, which is worse than none.

    What is asserted here is the *effect size*, not the verdict. At five seeds
    the pass/fail outcome is noise-dominated: the median BSS straddles zero and
    flips sign between configurations. The stable, reportable fact is that the
    leak yields no material skill — orders of magnitude away from
    ``LABEL_IN_FEATURES`` (+0.9999) or ``TARGET_ENCODING_ON_ALL`` (+0.24).
    """
    features, labels, folds = dataset

    study = run_shuffled_label_study(
        features, labels, folds, seeds=TEST_SEEDS, leak=LeakMode.TRAIN_TEST_OVERLAP
    )

    assert abs(study.mean_bss) < 0.01, study.summary()


def test_scaler_fit_on_all_data_does_not_trip_the_gate(dataset: Dataset) -> None:
    """Documented negative result, not an oversight.

    Fitting the standardiser on train+test leaks the test set's *feature
    distribution*, never any label information. Under shuffled labels there is
    no feature/label relationship to exploit, so this cannot produce skill and
    the gate correctly stays silent.

    It is pinned here so the limitation is a measured property of the gate
    rather than an assumption — and so nobody later mistakes this fixture for
    evidence that preprocessing leakage is covered. Detecting it needs the
    purge/embargo-style structural checks, not K-1.
    """
    features, labels, folds = dataset

    study = run_shuffled_label_study(
        features, labels, folds, seeds=TEST_SEEDS, leak=LeakMode.SCALER_FIT_ON_ALL
    )

    assert study.passed, study.summary()


# ---------------------------------------------------------------------------
# Permutation and seed discipline
# ---------------------------------------------------------------------------


def test_permutation_preserves_the_label_multiset() -> None:
    """The base rate must not move, or BSS's reference moves with it."""
    labels = np.array([1.0] * 30 + [0.0] * 70)

    shuffled = permute_labels(labels, seed=7)

    assert labels.sum() == shuffled.sum()
    assert not np.array_equal(shuffled, labels)


def test_permutation_is_deterministic_per_seed() -> None:
    labels = np.arange(100, dtype=np.float64)

    assert np.array_equal(permute_labels(labels, 3), permute_labels(labels, 3))
    assert not np.array_equal(permute_labels(labels, 3), permute_labels(labels, 4))


def test_enumerated_seeds_are_exactly_zero_through_twenty_nine() -> None:
    """REPRODUCIBILITY §3: enumerated, not generated."""
    assert tuple(range(30)) == SHUFFLED_LABEL_SEEDS
    assert len(SHUFFLED_LABEL_SEEDS) == 30


def test_single_seed_sweep_is_refused(dataset: Dataset) -> None:
    """A finding on one seed is a finding about that seed."""
    features, labels, folds = dataset

    with pytest.raises(ValueError, match="at least 2 seeds"):
        run_shuffled_label_study(features, labels, folds, seeds=(0,))


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_study_is_reproducible(dataset: Dataset) -> None:
    features, labels, folds = dataset

    first = run_shuffled_label_study(features, labels, folds, seeds=TEST_SEEDS)
    second = run_shuffled_label_study(features, labels, folds, seeds=TEST_SEEDS)

    assert first.bss_per_seed.tobytes() == second.bss_per_seed.tobytes()


def test_walk_forward_is_reproducible(dataset: Dataset) -> None:
    features, labels, folds = dataset

    first = run_walk_forward(features, labels, folds)
    second = run_walk_forward(features, labels, folds)

    assert first.probabilities.tobytes() == second.probabilities.tobytes()


def test_summary_names_the_verdict_and_leak_mode(dataset: Dataset) -> None:
    features, labels, folds = dataset

    summary = run_shuffled_label_study(
        features, labels, folds, seeds=TEST_SEEDS, leak=LeakMode.LABEL_IN_FEATURES
    ).summary()

    assert "K-1" in summary
    assert "label_in_features" in summary
