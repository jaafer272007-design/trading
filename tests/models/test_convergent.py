"""The convergence-stopped combiner, pinned against two independent anchors.

``EVALUATION.md`` §14: a check verified only against code written from the same
understanding is not verified. This estimator gets both anchors §14 names.

**Anchor 1 — the parent.** At ``tolerance=0.0`` the stopping rule never fires,
so the class must reproduce ``LogisticRegression(n_iter=N)`` bit for bit. That
pins the duplicated update against the version the recorded K-1 baseline
describes: if the two ever drift, this fails.

**Anchor 2 — IRLS.** ``tests/models/test_logistic_reference.py`` holds a
Newton-Raphson solver for the same objective. It is a genuine external
reference rather than a re-reading: it uses second-order information the
production path never computes, so an error in the step rule, the learning
rate, or the stopping condition surfaces as disagreement rather than as
agreement on a wrong answer.
"""

import numpy as np
import pytest

from models.convergent import (
    DEFAULT_MAX_ITER,
    DEFAULT_TOLERANCE,
    ConvergentLogisticRegression,
)
from models.diagnostics import Diagnosable, FitDiagnostics
from models.logistic import LogisticRegression


def _separable(
    n: int = 400, d: int = 3, seed: int = 5
) -> tuple[np.ndarray, np.ndarray]:
    """A learnable problem: labels driven by the first feature plus noise."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((n, d))
    logit = 1.4 * x[:, 0] - 0.7 * x[:, 1]
    y = (rng.random(n) < 1.0 / (1.0 + np.exp(-logit))).astype(np.float64)
    return x, y


# ---------------------------------------------------------------------------
# Anchor 1 — bit-identity with the recorded combiner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_iter", [1, 17, 250])
def test_tolerance_zero_reproduces_the_parent_bit_for_bit(n_iter: int) -> None:
    """The update is the parent's. If it drifts, this is where it shows."""
    x, y = _separable()

    parent = LogisticRegression(n_iter=n_iter).fit(x, y)
    child = ConvergentLogisticRegression(tolerance=0.0, max_iter=n_iter).fit(x, y)

    np.testing.assert_array_equal(parent.predict_proba(x), child.predict_proba(x))


def test_tolerance_zero_always_hits_the_cap() -> None:
    x, y = _separable()

    fitted = ConvergentLogisticRegression(tolerance=0.0, max_iter=40).fit(x, y)

    assert fitted.diagnostics.iterations == 40
    assert fitted.diagnostics.hit_cap
    assert not fitted.diagnostics.converged


# ---------------------------------------------------------------------------
# The stopping rule
# ---------------------------------------------------------------------------


def test_a_converged_fit_reports_a_gradient_below_tolerance() -> None:
    x, y = _separable()

    fitted = ConvergentLogisticRegression(tolerance=1e-8, max_iter=200_000).fit(x, y)
    diagnostics = fitted.diagnostics

    assert diagnostics.converged
    assert not diagnostics.hit_cap
    assert diagnostics.gradient_infinity_norm <= 1e-8
    assert diagnostics.iterations < 200_000


def test_a_tighter_tolerance_costs_more_iterations() -> None:
    x, y = _separable()

    loose = ConvergentLogisticRegression(tolerance=1e-4, max_iter=200_000).fit(x, y)
    tight = ConvergentLogisticRegression(tolerance=1e-8, max_iter=200_000).fit(x, y)

    assert tight.diagnostics.iterations > loose.diagnostics.iterations
    assert (
        tight.diagnostics.gradient_infinity_norm
        < loose.diagnostics.gradient_infinity_norm
    )


def test_the_reported_norm_is_at_the_returned_parameters() -> None:
    """Not at the last point visited. They differ when the cap is hit.

    A fit stopped early reports the gradient where it actually stands, because
    that is the quantity H-011's VOID condition is about.
    """
    x, y = _separable()

    fitted = ConvergentLogisticRegression(tolerance=1e-12, max_iter=30).fit(x, y)

    weights = fitted._weights
    assert weights is not None
    intercept = np.float64(fitted._intercept)
    grad_w, grad_b = fitted._gradient(x, y, weights, intercept)
    expected = max(float(np.max(np.abs(grad_w))), abs(float(grad_b)))

    assert fitted.diagnostics.gradient_infinity_norm == pytest.approx(expected, abs=0)


def test_the_intercept_counts_toward_the_norm() -> None:
    """A fit whose intercept has not settled has not settled."""
    rng = np.random.default_rng(1)
    x = rng.standard_normal((300, 2))
    # Heavily imbalanced: the intercept carries the work, the weights do not.
    y = (rng.random(300) < 0.93).astype(np.float64)

    fitted = ConvergentLogisticRegression(tolerance=1e-7, max_iter=500_000).fit(x, y)
    weights = fitted._weights
    assert weights is not None
    _, grad_b = fitted._gradient(x, y, weights, np.float64(fitted._intercept))

    assert abs(float(grad_b)) <= 1e-7
    assert fitted.diagnostics.converged


def test_diagnostics_before_fit_is_an_error_not_a_default() -> None:
    with pytest.raises(RuntimeError, match="diagnostics read before fit"):
        _ = ConvergentLogisticRegression().diagnostics


def test_a_negative_tolerance_is_refused() -> None:
    with pytest.raises(ValueError, match="tolerance must be non-negative"):
        ConvergentLogisticRegression(tolerance=-1e-9)


def test_the_registered_defaults_are_the_registered_values() -> None:
    """H-011: tolerance 1e-6, cap 1e6. Changing either needs a new ID."""
    assert DEFAULT_TOLERANCE == 1e-6
    assert DEFAULT_MAX_ITER == 1_000_000


def test_it_satisfies_the_diagnosable_protocol() -> None:
    """The pipeline captures diagnostics through this protocol."""
    x, y = _separable()

    assert isinstance(ConvergentLogisticRegression(max_iter=10).fit(x, y), Diagnosable)
    assert not isinstance(LogisticRegression(), Diagnosable)


def test_capability_the_planted_label_is_still_detected() -> None:
    """H-010 pass condition (i), at estimator level.

    A combiner that cannot detect a planted leak cannot be trusted to report
    its absence — and that requirement transfers to every capacity and every
    stopping rule.
    """
    x, y = _separable()
    planted = np.column_stack([x, y])

    fitted = ConvergentLogisticRegression(tolerance=1e-6, max_iter=100_000).fit(
        planted, y
    )
    probabilities = fitted.predict_proba(planted)

    assert float(np.mean((probabilities - y) ** 2)) < 0.01


def test_diagnostics_is_immutable() -> None:
    x, y = _separable()
    diagnostics = ConvergentLogisticRegression(max_iter=5).fit(x, y).diagnostics

    with pytest.raises(AttributeError):
        diagnostics.converged = True  # type: ignore[misc]
    assert isinstance(diagnostics, FitDiagnostics)
