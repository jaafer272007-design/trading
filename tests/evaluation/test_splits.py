"""Tests for walk-forward folds with purge and embargo."""

from itertools import pairwise

import numpy as np
import pytest

from evaluation.splits import (
    Fold,
    assert_no_leakage,
    embargo_mask,
    report_embargo_effect,
    walk_forward_folds,
)

HORIZON = 24


def _all_valid(n: int) -> np.ndarray:
    return np.ones(n, dtype=bool)


def _folds(n_bars: int = 30_000) -> tuple[Fold, ...]:
    return walk_forward_folds(
        valid=_all_valid(n_bars),
        n_folds=5,
        first_test_start=10_000,
        test_size=4_000,
        horizon=HORIZON,
    )


def test_produces_the_requested_number_of_folds() -> None:
    assert len(_folds()) == 5


def test_test_windows_tile_forward_without_overlap() -> None:
    folds = _folds()

    for earlier, later in pairwise(folds):
        assert earlier.test_end == later.test_start
        assert np.intersect1d(earlier.test, later.test).size == 0


def test_training_is_strictly_before_the_test_window() -> None:
    for fold in _folds():
        assert int(fold.train.max()) < fold.test_start


def test_purge_removes_exactly_the_horizon_of_bars() -> None:
    """A training label window may not reach the test window."""
    folds = _folds()

    for fold in folds:
        assert fold.n_purged == HORIZON
        assert int(fold.train.max()) + HORIZON < fold.test_start


def test_purge_invariant_holds_for_every_fold() -> None:
    assert_no_leakage(_folds(), horizon=HORIZON)


def test_train_and_test_never_intersect() -> None:
    for fold in _folds():
        assert np.intersect1d(fold.train, fold.test).size == 0


def test_constructing_an_overlapping_fold_raises() -> None:
    """The single most direct leak must not be constructible."""
    with pytest.raises(ValueError, match="overlap"):
        Fold(
            index=0,
            train=np.array([1, 2, 3], dtype=np.int64),
            test=np.array([3, 4], dtype=np.int64),
            test_start=3,
            test_end=5,
            n_purged=0,
            n_embargoed=0,
        )


# ---------------------------------------------------------------------------
# Embargo — measured, not assumed
# ---------------------------------------------------------------------------


def test_embargo_is_vacuous_under_forward_only_tiling() -> None:
    """Documented honestly rather than presented as work being done.

    In expanding-window walk-forward every training index precedes the test
    window, so the embargo zone and the training set do not intersect. This
    test pins the claim in the module docstring so it cannot quietly become
    false.
    """
    effect = report_embargo_effect(_folds())

    assert effect.is_vacuous
    assert effect.additional_bars_removed == 0


def test_embargo_mask_removes_exactly_the_buffer_after_the_test_window() -> None:
    """The rule is implemented, not merely declared.

    Tested directly rather than through a fold geometry in which it is inert,
    so the implementation is verified generally: put training indices after a
    test window and exactly the buffer disappears.
    """
    indices = np.arange(100, 160, dtype=np.int64)

    keep = embargo_mask(indices, test_end=120, horizon=HORIZON)

    assert int((~keep).sum()) == HORIZON
    assert set(indices[~keep].tolist()) == set(range(120, 120 + HORIZON))
    assert keep[indices < 120].all()
    assert keep[indices >= 120 + HORIZON].all()


def test_embargo_mask_is_inert_when_all_indices_precede_the_test_window() -> None:
    """Why the buffer is vacuous for forward-only walk-forward."""
    indices = np.arange(0, 100, dtype=np.int64)

    assert embargo_mask(indices, test_end=500, horizon=HORIZON).all()


def test_embargo_is_not_applied_around_prior_test_windows() -> None:
    """A rejected stricter variant, pinned so it is not reintroduced.

    Embargoing every prior test window removes 144 bars under this geometry
    and looks like the control is working. It prevents nothing: those bars
    neither carry a label window nor a feature lookback reaching the fold's own
    test window. §5.2 says "the test window", singular.
    """
    assert report_embargo_effect(_folds()).additional_bars_removed == 0


def test_invalid_rows_never_enter_train_or_test() -> None:
    valid = _all_valid(30_000)
    valid[:200] = False
    valid[29_800:] = False

    folds = walk_forward_folds(
        valid=valid,
        n_folds=5,
        first_test_start=10_000,
        test_size=4_000,
        horizon=HORIZON,
    )

    for fold in folds:
        assert valid[fold.train].all()
        assert valid[fold.test].all()


# ---------------------------------------------------------------------------
# Decision spacing
# ---------------------------------------------------------------------------


def test_decisions_are_spaced_by_the_horizon() -> None:
    """Non-overlapping decisions, so n counts independent bets."""
    for fold in _folds():
        gaps = np.diff(fold.test)
        assert np.all(gaps == HORIZON)


def test_decision_count_reflects_spacing_not_bar_count() -> None:
    folds = _folds()

    for fold in folds:
        assert fold.test.size == 4_000 // HORIZON + (1 if 4_000 % HORIZON else 0)


def test_pooled_decisions_clear_the_k6_threshold() -> None:
    """K-6: fewer than 150 closed decisions is no result at all."""
    total = sum(fold.test.size for fold in _folds())

    assert total >= 150


# ---------------------------------------------------------------------------
# Geometry validation
# ---------------------------------------------------------------------------


def test_rejects_geometry_longer_than_the_series() -> None:
    with pytest.raises(ValueError, match="only"):
        walk_forward_folds(
            valid=_all_valid(1_000),
            n_folds=5,
            first_test_start=500,
            test_size=400,
            horizon=HORIZON,
        )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"n_folds": 0}, "n_folds"),
        ({"test_size": 0}, "test_size"),
        ({"horizon": 0}, "horizon"),
        ({"first_test_start": 0}, "first_test_start"),
    ],
)
def test_rejects_invalid_geometry(kwargs: dict[str, int], match: str) -> None:
    base = {
        "valid": _all_valid(5_000),
        "n_folds": 2,
        "first_test_start": 1_000,
        "test_size": 500,
        "horizon": HORIZON,
    }
    base.update(kwargs)

    with pytest.raises(ValueError, match=match):
        walk_forward_folds(**base)  # type: ignore[arg-type]
