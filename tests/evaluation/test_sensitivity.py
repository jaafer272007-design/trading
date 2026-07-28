"""The K-1 sensitivity guard — REPRODUCIBILITY.md §6.

``test_combiner_has_not_changed_without_re_measurement`` is the load-bearing
test. It is the same filesystem-versus-declaration pattern as the
feature-registry guard: the build fails when the combiner moves and the
recorded sensitivity does not move with it.
"""

import ast
import tempfile
from pathlib import Path

import numpy as np
import pytest

from data.synthetic import generate_ohlcv
from evaluation.pipeline import LeakMode, WalkForwardResult, run_walk_forward
from evaluation.sensitivity import (
    COMBINER_MODULE,
    RECORDED_AT_COMMIT,
    RECORDED_CAPACITY_SIGNATURE,
    RECORDED_COMBINER_FINGERPRINT,
    RECORDED_MEAN_BSS,
    RECORDED_N_FEATURES,
    RECORDED_PARAMETER_COUNT,
    RECORDED_SILENT_MODES,
    RECORDED_TRIPPING_MODES,
    CapacitySignature,
    capacity_signature,
    combiner_fingerprint,
)
from evaluation.splits import walk_forward_folds
from labels.direction import DEFAULT_HORIZON, direction_label
from models.expansion import polynomial_expand
from models.logistic import LogisticRegression

# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_combiner_has_not_changed_without_re_measurement() -> None:
    """A combiner change invalidates every subsequent K-1 pass.

    REPRODUCIBILITY.md §6: "Any change to the combiner — different estimator,
    added parameters, changed regularisation — requires re-running the full
    leak-fixture suite and recording which modes trip."

    If this fails, the fix is NOT to paste in the new fingerprint. Re-run
    ``scripts/run_h001_harness_validation.py``, update RECORDED_TRIPPING_MODES
    and RECORDED_MEAN_BSS from its output, and record the new fingerprint and
    commit together.
    """
    live = combiner_fingerprint()

    assert live == RECORDED_COMBINER_FINGERPRINT, (
        f"the combiner changed ({COMBINER_MODULE.name}) but the recorded K-1 "
        f"sensitivity did not.\n"
        f"  recorded: {RECORDED_COMBINER_FINGERPRINT}\n"
        f"  live:     {live}\n"
        f"Re-run scripts/run_h001_harness_validation.py and update the record. "
        f"Pasting the new fingerprint alone is the defect this guard exists to "
        f"prevent."
    )


def test_recorded_capacity_matches_the_h001_design() -> None:
    """Adding a feature raises capacity just as surely as swapping estimators."""
    from scripts.run_h001_harness_validation import build_design

    from data.synthetic import generate_ohlcv

    _, names = build_design(generate_ohlcv(n_bars=200, seed=1))

    assert len(names) == RECORDED_N_FEATURES
    assert RECORDED_PARAMETER_COUNT == RECORDED_N_FEATURES + 1


# ---------------------------------------------------------------------------
# The capacity signature — the guard that does not read source alone
# ---------------------------------------------------------------------------


def _canonical_run(
    degree: int = 1,
    *,
    model_factory: type[LogisticRegression] = LogisticRegression,
) -> WalkForwardResult:
    """Run the H-001 design through the live pipeline on a small fixture.

    Small and synthetic on purpose: this measures *what was fitted*, which is
    a structural property, so it needs no statistical power at all.
    """
    from scripts.run_h001_harness_validation import build_design

    df = generate_ohlcv(n_bars=1_200, seed=3)
    design, _ = build_design(df)
    labels = direction_label(df, horizon=DEFAULT_HORIZON).to_numpy(dtype=np.float64)
    valid = ~np.isnan(design).any(axis=1) & ~np.isnan(labels)
    folds = walk_forward_folds(
        valid=valid,
        n_folds=2,
        first_test_start=600,
        test_size=200,
        horizon=DEFAULT_HORIZON,
    )
    return run_walk_forward(
        polynomial_expand(np.nan_to_num(design), degree),
        np.nan_to_num(labels),
        folds,
        model_factory=model_factory,
    )


def test_the_live_capacity_signature_matches_the_record() -> None:
    """The load-bearing guard. REPRODUCIBILITY.md §6.

    If this fails, the fix is NOT to paste in the new signature. Re-run the
    leak-fixture suite at the new capacity, record which modes trip, and commit
    the measurement and the signature together.
    """
    live = capacity_signature(_canonical_run())

    assert live == RECORDED_CAPACITY_SIGNATURE, "\n".join(
        live.differences(RECORDED_CAPACITY_SIGNATURE)
    )


def test_the_signature_names_every_component_that_moved() -> None:
    moved = CapacitySignature(
        fitted_parameters=20, estimator="x", combiner_fingerprint="y"
    )

    assert len(moved.differences(RECORDED_CAPACITY_SIGNATURE)) == 3
    assert not RECORDED_CAPACITY_SIGNATURE.differences(RECORDED_CAPACITY_SIGNATURE)


# ---------------------------------------------------------------------------
# Adversarial fixtures — EVALUATION.md §14, for the guard itself
# ---------------------------------------------------------------------------
#
# H-010 records that the AST fingerprint guards one route to a capacity change
# and is blind to two others. Each fixture below raises capacity through a
# blind route and requires the guard to fire -- and asserts in the same test
# that the fingerprint does NOT move, which is what makes it a demonstration of
# the blindness rather than a restatement of the guard.


def test_capacity_raised_through_the_design_matrix_is_caught() -> None:
    """Route 1: a polynomial expansion. `logistic.py` never changes."""
    live = capacity_signature(_canonical_run(degree=3))

    assert live.fitted_parameters == 20
    assert live != RECORDED_CAPACITY_SIGNATURE
    assert "fitted_parameters: 20 != 4" in live.differences(RECORDED_CAPACITY_SIGNATURE)

    # The old guard, on the same change, sees nothing.
    assert live.combiner_fingerprint == RECORDED_COMBINER_FINGERPRINT
    assert combiner_fingerprint() == RECORDED_COMBINER_FINGERPRINT


class _WiderBudget(LogisticRegression):
    """A combiner that differs from the recorded one, defined outside it."""

    def __init__(self) -> None:
        super().__init__(n_iter=50)


def test_capacity_raised_through_a_substituted_estimator_is_caught() -> None:
    """Route 2: `model_factory`. `logistic.py` never changes here either."""
    live = capacity_signature(_canonical_run(model_factory=_WiderBudget))

    assert live != RECORDED_CAPACITY_SIGNATURE
    assert any(
        line.startswith("estimator:")
        for line in live.differences(RECORDED_CAPACITY_SIGNATURE)
    )

    assert live.combiner_fingerprint == RECORDED_COMBINER_FINGERPRINT


def test_the_unchanged_pipeline_is_not_flagged() -> None:
    """A guard that fires on everything is not a guard.

    The two fixtures above are only evidence if the clean path stays silent
    through the same measurement code.
    """
    assert not capacity_signature(_canonical_run()).differences(
        RECORDED_CAPACITY_SIGNATURE
    )


# ---------------------------------------------------------------------------
# The record is complete and internally consistent
# ---------------------------------------------------------------------------


def test_every_leak_mode_is_classified() -> None:
    """No mode may be silently absent from the record."""
    classified = RECORDED_TRIPPING_MODES | RECORDED_SILENT_MODES
    all_leaks = {m.value for m in LeakMode} - {LeakMode.NONE.value}

    assert classified == all_leaks, (
        f"unclassified leak modes: {sorted(all_leaks - classified)}; "
        f"recorded but nonexistent: {sorted(classified - all_leaks)}"
    )


def test_tripping_and_silent_modes_are_disjoint() -> None:
    assert not (RECORDED_TRIPPING_MODES & RECORDED_SILENT_MODES)


def test_recorded_bss_covers_every_mode_including_the_clean_path() -> None:
    assert set(RECORDED_MEAN_BSS) == {m.value for m in LeakMode}


def test_recorded_bss_is_consistent_with_the_classification() -> None:
    """A mode recorded as tripping must have a BSS that would trip."""
    for mode in RECORDED_TRIPPING_MODES:
        assert RECORDED_MEAN_BSS[mode] > 0.05, mode
    for mode in RECORDED_SILENT_MODES:
        assert abs(RECORDED_MEAN_BSS[mode]) < 0.01, mode


def test_clean_path_null_is_at_or_below_zero() -> None:
    """Under permuted labels, overfitting costs skill."""
    assert RECORDED_MEAN_BSS[LeakMode.NONE.value] <= 0.0


def test_records_the_commit_it_was_measured_at() -> None:
    assert len(RECORDED_AT_COMMIT) == 40
    assert all(c in "0123456789abcdef" for c in RECORDED_AT_COMMIT)


def test_train_test_overlap_is_recorded_as_a_capacity_limitation() -> None:
    """The finding that motivates this whole guard.

    It must stay in the record: a K-1 pass certifies no label-reaching-model
    leak, not the absence of all leakage.
    """
    assert LeakMode.TRAIN_TEST_OVERLAP.value in RECORDED_SILENT_MODES


# ---------------------------------------------------------------------------
# Fingerprint semantics
# ---------------------------------------------------------------------------


@pytest.fixture
def combiner_source() -> str:
    return COMBINER_MODULE.read_text(encoding="utf-8")


def _fingerprint_of(source: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidate.py"
        path.write_text(source, encoding="utf-8")
        return combiner_fingerprint(path)


def test_prose_changes_do_not_move_the_fingerprint(combiner_source: str) -> None:
    """A guard that fires on typo fixes trains people to bump it blindly."""
    reworded = combiner_source.replace(
        "Numerically stable logistic function.", "An entirely rewritten docstring."
    )
    assert reworded != combiner_source, "anchor text absent; update this test"

    assert _fingerprint_of(reworded) == RECORDED_COMBINER_FINGERPRINT


def test_comment_changes_do_not_move_the_fingerprint(combiner_source: str) -> None:
    commented = combiner_source.replace(
        "# A constant column has zero spread",
        "# NOTE: a constant column has zero spread",
    )
    assert commented != combiner_source, "anchor comment absent; update this test"

    assert _fingerprint_of(commented) == RECORDED_COMBINER_FINGERPRINT


@pytest.mark.parametrize(
    ("old", "new", "what"),
    [
        ("DEFAULT_N_ITER: Final = 1_000", "DEFAULT_N_ITER: Final = 5_000", "capacity"),
        ("DEFAULT_L2: Final = 1e-6", "DEFAULT_L2: Final = 1e-2", "regularisation"),
        (
            "DEFAULT_LEARNING_RATE: Final = 0.5",
            "DEFAULT_LEARNING_RATE: Final = 0.05",
            "step size",
        ),
    ],
)
def test_hyperparameter_changes_move_the_fingerprint(
    combiner_source: str, old: str, new: str, what: str
) -> None:
    changed = combiner_source.replace(old, new)
    assert changed != combiner_source, f"anchor not found for {what}"

    assert _fingerprint_of(changed) != RECORDED_COMBINER_FINGERPRINT


def test_logic_changes_move_the_fingerprint(combiner_source: str) -> None:
    changed = combiner_source.replace(
        "weights = np.zeros(n_features, dtype=np.float64)",
        "weights = np.ones(n_features, dtype=np.float64)",
    )
    assert changed != combiner_source, "anchor absent; update this test"

    assert _fingerprint_of(changed) != RECORDED_COMBINER_FINGERPRINT


def test_fingerprint_is_stable_across_calls() -> None:
    assert combiner_fingerprint() == combiner_fingerprint()


def test_fingerprint_rejects_unparseable_source() -> None:
    with pytest.raises(SyntaxError):
        _fingerprint_of("def broken(:\n")


def test_fingerprint_reads_the_real_combiner_module() -> None:
    assert COMBINER_MODULE.name == "logistic.py"
    assert COMBINER_MODULE.exists()
    ast.parse(COMBINER_MODULE.read_text(encoding="utf-8"))
