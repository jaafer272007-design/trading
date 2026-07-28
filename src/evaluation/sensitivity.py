"""Recorded K-1 sensitivity baseline and the combiner fingerprint that guards it.

``REPRODUCIBILITY.md`` §6: K-1 sensitivity is a property of the combiner, not
of the gate. ``train_test_overlap`` is undetectable at four parameters and
becomes detectable as capacity grows, so a combiner change without a recorded
re-measurement invalidates every subsequent K-1 pass.

This module is the record. ``tests/evaluation/test_sensitivity.py`` compares
the live combiner against :data:`RECORDED_COMBINER_FINGERPRINT` and fails the
build when they diverge — the same filesystem-versus-declaration pattern as the
feature-registry guard in ``tests/test_causality.py``.

Why an AST fingerprint rather than a file hash
-----------------------------------------------

Hashing raw bytes would fire on every comment and docstring edit. That sounds
conservative but is the opposite: a guard that cries wolf on typo fixes trains
people to bump the recorded value without re-measuring, which is precisely the
failure it exists to prevent. The fingerprint is taken over the parsed AST with
docstrings stripped, so prose changes are invisible while any change to logic,
to a hyperparameter default, or to structure moves it.

Capacity is not the module alone
---------------------------------

The combiner has ``n_features + 1`` parameters, so adding a feature to the
H-001 design raises capacity just as surely as swapping the estimator.
:data:`RECORDED_PARAMETER_COUNT` is therefore checked as well.

Why an AST fingerprint is not sufficient — the defect H-010 records
-------------------------------------------------------------------

The fingerprint reads ``models/logistic.py``. Capacity can be raised without
touching a byte of it:

1. **Through the design matrix.** A polynomial expansion of the same three
   features fits 20 parameters at degree 3. ``logistic.py`` is unchanged, the
   fingerprint does not move, and :data:`RECORDED_PARAMETER_COUNT` continues to
   declare 4.
2. **Through a different estimator class.** ``run_walk_forward`` takes a
   ``model_factory``. Passing a subclass with a different stopping rule changes
   what is fitted while leaving the recorded module untouched.

A guard against one route to a change is not a guard against the change. So the
record is keyed on a **capacity signature** — the parameter count as *fitted*,
the estimator class as *used*, and the module fingerprint — of which the first
two are measured by running the pipeline rather than read from source.
``EVALUATION.md`` §14 requires a gate be pinned by an external reference or an
adversarial fixture; ``tests/evaluation/test_sensitivity.py`` supplies the
fixture for both blind routes, and asserts in the same test that the AST
fingerprint stays put — which is what makes the fixture a demonstration rather
than a tautology.
"""

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from evaluation.pipeline import WalkForwardResult

COMBINER_MODULE: Final = (
    Path(__file__).resolve().parent.parent / "models" / "logistic.py"
)

RECORDED_COMBINER_FINGERPRINT: Final = (
    "9b09e2482278a57a8092faba678a63900512d12814fbcb44ebcfcc1ed81f6393"
)
"""Semantic fingerprint of the combiner at the last recorded re-measurement.

Regenerate with::

    uv run python -c "from evaluation.sensitivity import combiner_fingerprint; \\
                      print(combiner_fingerprint())"

Changing this value without re-running the leak-fixture suite and updating
:data:`RECORDED_TRIPPING_MODES` is the exact defect §6 prohibits.
"""

RECORDED_N_FEATURES: Final = 3
"""Features in the H-001 design at the recorded measurement."""

RECORDED_PARAMETER_COUNT: Final = RECORDED_N_FEATURES + 1
"""Combiner capacity: one weight per feature, plus the intercept."""

RECORDED_TRIPPING_MODES: Final = frozenset(
    {"label_in_features", "target_encoding_on_all"}
)
"""Leak modes that trip K-1 at the recorded capacity."""

RECORDED_SILENT_MODES: Final = frozenset({"train_test_overlap", "scaler_fit_on_all"})
"""Leak modes that do NOT trip at the recorded capacity.

``scaler_fit_on_all`` carries no label information and would stay silent at any
capacity. ``train_test_overlap`` is a genuine leak that a higher-capacity
estimator would catch — it is the one that makes this whole guard necessary.
"""

RECORDED_MEAN_BSS: Final = {
    "none": -0.001390,
    "label_in_features": +0.999984,
    "target_encoding_on_all": +0.239781,
    "train_test_overlap": -0.000901,
    "scaler_fit_on_all": -0.001390,
}
"""Mean BSS per mode, 30 seeds, 834 pooled decisions, 30,000 synthetic bars."""

RECORDED_AT_COMMIT: Final = "7d6ed38bd35557e7099206770cc99a578a1ffb6f"
RECORDED_RUN_ID: Final = "5c6c585b-7531-48bd-945c-8c077b759a05"
"""The harness_validation run this baseline came from. run_type is not
`evaluation` and carries no hypothesis_id, so it is a record of gate
behaviour and never evidence for H-001."""

RECORDED_ESTIMATOR: Final = "models.logistic.LogisticRegression"
"""The combiner class actually fitted at the recorded measurement."""


@dataclass(frozen=True, slots=True)
class CapacitySignature:
    """What the pipeline actually fitted, and what it was fitted with.

    Two of the three fields are measured by running the pipeline; only
    :attr:`combiner_fingerprint` is read from source. That asymmetry is
    deliberate — it is the source-only reading that H-010 found to be blind.
    """

    fitted_parameters: int
    estimator: str
    combiner_fingerprint: str

    def differences(self, other: "CapacitySignature") -> tuple[str, ...]:
        """Name every component that disagrees.

        Args:
            other: Signature to compare against.

        Returns:
            One human-readable line per differing component, empty when the
            two agree.
        """
        lines: list[str] = []
        if self.fitted_parameters != other.fitted_parameters:
            lines.append(
                f"fitted_parameters: {self.fitted_parameters} != "
                f"{other.fitted_parameters}"
            )
        if self.estimator != other.estimator:
            lines.append(f"estimator: {self.estimator} != {other.estimator}")
        if self.combiner_fingerprint != other.combiner_fingerprint:
            lines.append(
                f"combiner_fingerprint: {self.combiner_fingerprint} != "
                f"{other.combiner_fingerprint}"
            )
        return tuple(lines)


def capacity_signature(result: WalkForwardResult) -> CapacitySignature:
    """Read the capacity signature off a completed walk-forward.

    Args:
        result: A walk-forward run on the design whose capacity is in question.
            Use :data:`~evaluation.pipeline.LeakMode.NONE`: the leak modes that
            append a column raise the fitted parameter count by construction,
            and that inflation is a property of the fixture, not of the
            combiner.

    Returns:
        The signature, for comparison against
        :data:`RECORDED_CAPACITY_SIGNATURE`.
    """
    return CapacitySignature(
        fitted_parameters=result.fitted_parameters,
        estimator=result.estimator,
        combiner_fingerprint=combiner_fingerprint(),
    )


RECORDED_CAPACITY_SIGNATURE: Final = CapacitySignature(
    fitted_parameters=RECORDED_PARAMETER_COUNT,
    estimator=RECORDED_ESTIMATOR,
    combiner_fingerprint=RECORDED_COMBINER_FINGERPRINT,
)
"""Capacity at the last recorded re-measurement.

Any route that changes what the combiner fits moves at least one component.
Moving one without re-running the leak-fixture suite is the defect
``REPRODUCIBILITY.md`` §6 prohibits, and it is now prohibited by measurement
rather than by reading one file.
"""


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """Remove docstring expressions from a parsed module, in place.

    Args:
        tree: Parsed AST.

    Returns:
        The same tree, with leading string-constant expressions dropped from
        every module, class, and function body.
    """
    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:]
    return tree


def combiner_fingerprint(module: Path | None = None) -> str:
    """Fingerprint the combiner's semantics, ignoring prose and formatting.

    Args:
        module: Module to fingerprint. Defaults to :data:`COMBINER_MODULE`.

    Returns:
        Hex sha256 of the docstring-stripped AST dump.

    Raises:
        FileNotFoundError: If the module is absent.
    """
    path = COMBINER_MODULE if module is None else module
    tree = ast.parse(path.read_text(encoding="utf-8"))
    dumped = ast.dump(_strip_docstrings(tree), include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()
