"""Walk-forward folds with purge and embargo (``EVALUATION.md`` §5.2).

    **Purge:** drop training samples whose label window overlaps the test
    window. **Embargo:** additionally drop a buffer of length ``H``
    immediately after the test window.

Both are implemented. One of them does nothing under the fold geometry this
project currently uses, and that is stated here rather than left for a reader
to assume otherwise.

Why embargo is vacuous for forward-only walk-forward
-----------------------------------------------------

Embargo exists to stop a training sample that sits *after* a test window from
reaching back into it — through its own feature lookback, or through a label
window that began inside it. In expanding-window walk-forward every training
index is strictly less than ``test_start``, so no training sample is ever
positioned after the test window of the fold being evaluated, and the embargo
zone never intersects the training set.

The consequence, stated plainly: **under this geometry purge is the binding
constraint and embargo removes zero bars.** ``report_embargo_effect`` exists so
this is measured rather than asserted.

A rejected stricter variant, recorded because it is an easy mistake to make
twice: an earlier draft embargoed the buffer after *every prior* test window,
which does remove bars (144 under the H-001 geometry) and so looks like the
control is working. It is not. Fold 2 is scored on ``[18000, 22000)``; a
training bar at 14010 carries a label window ending 14034 and a feature
lookback ending 14010, neither of which touches that test window. Those 144
bars were discarded to prevent nothing. §5.2 says "immediately after **the**
test window" — singular, the fold's own — and the literal reading is also the
correct one.

Embargo is still implemented in full, because the geometry is a parameter
rather than a law: interspersed or combinatorial test blocks put training data
after a test window and make the buffer bite immediately. :func:`embargo_mask`
is a pure function so that rule is tested directly, instead of being inferred
from a geometry in which it happens to be inert.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class Fold:
    """One walk-forward fold."""

    index: int
    train: npt.NDArray[np.int64]
    test: npt.NDArray[np.int64]
    test_start: int
    test_end: int
    n_purged: int
    n_embargoed: int

    def __post_init__(self) -> None:
        """Reject any fold whose train and test sets intersect."""
        if np.intersect1d(self.train, self.test).size > 0:
            raise ValueError(
                f"fold {self.index}: train and test indices overlap — this is "
                f"the single most direct form of leakage and must never be "
                f"constructible"
            )


@dataclass(frozen=True, slots=True)
class EmbargoEffect:
    """How many training bars embargo removed that purge had not already."""

    additional_bars_removed: int
    is_vacuous: bool


def embargo_mask(
    indices: npt.NDArray[np.int64],
    *,
    test_end: int,
    horizon: int,
) -> npt.NDArray[np.bool_]:
    """Keep-mask excluding the embargo buffer after a test window.

    ``EVALUATION.md`` §5.2: "drop a buffer of length ``H`` immediately after
    the test window." The buffer is the half-open range
    ``[test_end, test_end + horizon)``.

    Exposed as a pure function so the rule is verified directly rather than
    inferred from a fold geometry in which it happens to be inert.

    Args:
        indices: Candidate training indices.
        test_end: One past the last bar of the test window.
        horizon: Label horizon ``H``.

    Returns:
        Boolean mask, ``True`` for indices to keep.
    """
    in_zone = (indices >= test_end) & (indices < test_end + horizon)
    return ~in_zone


def walk_forward_folds(
    *,
    valid: npt.NDArray[np.bool_],
    n_folds: int,
    first_test_start: int,
    test_size: int,
    horizon: int,
    decision_spacing: int | None = None,
) -> tuple[Fold, ...]:
    """Build expanding-window folds with purge and embargo applied.

    Args:
        valid: Boolean mask over all bars; ``True`` where features and label
            are both defined. Invalid bars never enter train or test.
        n_folds: Number of folds.
        first_test_start: Bar index where the first test window opens.
        test_size: Bars per test window.
        horizon: Label horizon ``H``, used for both purge and embargo width.
        decision_spacing: Spacing between evaluation decisions inside a test
            window. Defaults to ``horizon``, giving non-overlapping decisions
            so that reported ``n`` counts independent bets rather than ``H``
            overlapping restatements of the same one.

    Returns:
        Folds in chronological order.

    Raises:
        ValueError: If the geometry is inconsistent or runs past the series.
    """
    if n_folds <= 0:
        raise ValueError(f"n_folds must be positive, got {n_folds}")
    if test_size <= 0:
        raise ValueError(f"test_size must be positive, got {test_size}")
    if horizon <= 0:
        raise ValueError(f"horizon must be positive, got {horizon}")
    if first_test_start <= 0:
        raise ValueError(f"first_test_start must be positive, got {first_test_start}")

    spacing = horizon if decision_spacing is None else decision_spacing
    if spacing <= 0:
        raise ValueError(f"decision_spacing must be positive, got {spacing}")

    n_bars = valid.size
    required = first_test_start + n_folds * test_size
    if required > n_bars:
        raise ValueError(
            f"geometry needs {required} bars but only {n_bars} are available "
            f"(first_test_start={first_test_start}, n_folds={n_folds}, "
            f"test_size={test_size})"
        )

    all_idx = np.arange(n_bars, dtype=np.int64)
    folds: list[Fold] = []

    for k in range(n_folds):
        test_start = first_test_start + k * test_size
        test_end = test_start + test_size

        # Test decisions: spaced `spacing` apart, valid only.
        test_candidates = all_idx[test_start:test_end:spacing]
        test = test_candidates[valid[test_candidates]]

        # Training pool: everything strictly before the test window.
        pool = all_idx[:test_start]
        pool = pool[valid[pool]]

        # Purge — drop samples whose label window [i, i+H] reaches test_start.
        keep_purge = (pool + horizon) < test_start
        n_purged = int((~keep_purge).sum())

        # Embargo — drop a buffer of `horizon` bars immediately after *this
        # fold's* test window, per EVALUATION.md §5.2 ("the test window",
        # singular). Applied unconditionally; see the module docstring for why
        # it removes nothing under forward-only tiling.
        keep_embargo = embargo_mask(pool, test_end=test_end, horizon=horizon)
        n_embargoed = int((keep_purge & ~keep_embargo).sum())

        train = pool[keep_purge & keep_embargo]

        folds.append(
            Fold(
                index=k,
                train=train,
                test=test,
                test_start=test_start,
                test_end=test_end,
                n_purged=n_purged,
                n_embargoed=n_embargoed,
            )
        )

    return tuple(folds)


def report_embargo_effect(folds: tuple[Fold, ...]) -> EmbargoEffect:
    """Measure how much work embargo actually did.

    Args:
        folds: Folds produced by :func:`walk_forward_folds`.

    Returns:
        The count of training bars embargo removed beyond purge, and whether
        that count is zero.
    """
    total = sum(fold.n_embargoed for fold in folds)
    return EmbargoEffect(additional_bars_removed=total, is_vacuous=total == 0)


def assert_no_leakage(folds: tuple[Fold, ...], horizon: int) -> None:
    """Assert the purge invariant holds for every fold.

    Args:
        folds: Folds to check.
        horizon: Label horizon.

    Raises:
        ValueError: If any training sample's label window reaches its test
            window, or train and test intersect.
    """
    for fold in folds:
        if fold.train.size and int((fold.train + horizon).max()) >= fold.test_start:
            raise ValueError(
                f"fold {fold.index}: a training label window reaches into the "
                f"test window — purge is not being applied"
            )
        if np.intersect1d(fold.train, fold.test).size > 0:
            raise ValueError(f"fold {fold.index}: train/test overlap")
