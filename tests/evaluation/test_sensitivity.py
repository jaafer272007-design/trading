"""The K-1 sensitivity guard — REPRODUCIBILITY.md §6.

``test_combiner_has_not_changed_without_re_measurement`` is the load-bearing
test. It is the same filesystem-versus-declaration pattern as the
feature-registry guard: the build fails when the combiner moves and the
recorded sensitivity does not move with it.
"""

import ast
import tempfile
from pathlib import Path

import pytest

from evaluation.pipeline import LeakMode
from evaluation.sensitivity import (
    COMBINER_MODULE,
    RECORDED_AT_COMMIT,
    RECORDED_COMBINER_FINGERPRINT,
    RECORDED_MEAN_BSS,
    RECORDED_N_FEATURES,
    RECORDED_PARAMETER_COUNT,
    RECORDED_SILENT_MODES,
    RECORDED_TRIPPING_MODES,
    combiner_fingerprint,
)

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
