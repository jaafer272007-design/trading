"""An independent solver for the same objective — the §14 external reference.

``EVALUATION.md`` §14 requires every gate be pinned by an external reference or
an adversarial fixture. H-010 carries both, and this file is the reference: a
Newton-Raphson / IRLS solver for the identical penalised logistic objective,
written here and **never imported by ``src``**.

Why this is a reference and not a re-reading
--------------------------------------------

IRLS solves the same problem by a different route. It forms the Hessian and
takes a Newton step; the production path forms only the gradient and takes a
fixed-size step. Nothing about the learning rate, the step count, or the
stopping rule is shared. An error in any of those surfaces as *disagreement* —
whereas a second gradient-descent implementation would share the assumption and
agree with the defect, which is what §14 records happened to three of the five
instrument defects this project has found.

Agreement is asserted on fitted probabilities rather than on coefficients.
Probabilities are what the pipeline consumes; coefficients of a near-collinear
polynomial design can differ materially while the fitted function does not, and
asserting on them would produce failures that mean nothing.
"""

import numpy as np
import numpy.typing as npt
import pytest

from models.convergent import ConvergentLogisticRegression
from models.expansion import polynomial_expand
from models.logistic import DEFAULT_L2

AGREEMENT_TOLERANCE = 1e-6
"""Max absolute deviation in fitted probability. H-010's registered value."""


def irls_fit(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    *,
    l2: float = DEFAULT_L2,
    n_iter: int = 100,
) -> tuple[npt.NDArray[np.float64], float]:
    """Fit penalised logistic regression by Newton-Raphson.

    Solves the same objective as ``models.logistic``: mean negative
    log-likelihood plus ``l2/2`` times the squared weight norm, intercept
    unpenalised. Newton's method on a strictly convex objective converges
    quadratically, so a hundred iterations is far past machine precision.

    Args:
        x: Design matrix.
        y: Binary targets in ``{0, 1}``.
        l2: Ridge penalty on the weights, not the intercept.
        n_iter: Newton steps.

    Returns:
        Fitted weights and intercept.
    """
    n_samples, n_features = x.shape
    design = np.column_stack([np.ones(n_samples), x])

    penalty = np.full(n_features + 1, l2, dtype=np.float64)
    penalty[0] = 0.0

    beta = np.zeros(n_features + 1, dtype=np.float64)
    for _ in range(n_iter):
        eta = design @ beta
        p = 1.0 / (1.0 + np.exp(-eta))
        # Bound the weights away from zero: a saturated probability makes the
        # Hessian singular, and a silently singular solve is the kind of fluent
        # wrong answer this file exists to catch.
        w = np.clip(p * (1.0 - p), 1e-10, None)

        gradient = design.T @ (p - y) / n_samples + penalty * beta
        hessian = (design.T * w) @ design / n_samples + np.diag(penalty)
        step = np.linalg.solve(hessian, gradient)
        beta = beta - step
        if float(np.max(np.abs(step))) < 1e-14:
            break

    return beta[1:], float(beta[0])


def _probabilities(
    weights: npt.NDArray[np.float64], intercept: float, x: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Logistic probabilities from an explicit parameter vector."""
    return 1.0 / (1.0 + np.exp(-(x @ weights + intercept)))


def _design(n: int, d: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Standardised features with a real but noisy relationship to the label."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((n, d))
    x = (x - x.mean(axis=0)) / x.std(axis=0)
    logit = x @ rng.normal(0.0, 0.8, size=d)
    y = (rng.random(n) < 1.0 / (1.0 + np.exp(-logit))).astype(np.float64)
    return x, y


# ---------------------------------------------------------------------------
# The reference itself is checked before it is used to check anything
# ---------------------------------------------------------------------------


def test_irls_recovers_a_known_separating_boundary() -> None:
    """A reference nobody has tested is not a reference."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal((600, 2))
    y = (x[:, 0] > 0.0).astype(np.float64)

    weights, _ = irls_fit(x, y, l2=1e-3)

    assert weights[0] > 5.0 * abs(weights[1])


def test_irls_agrees_with_a_closed_form_intercept_only_fit() -> None:
    """With no features, the MLE intercept is the logit of the base rate.

    The one place in this project where a fitted parameter has a closed form,
    so it is the one place the reference can be checked against arithmetic
    rather than against another program.
    """
    y = np.concatenate([np.ones(300), np.zeros(700)])
    x = np.zeros((1_000, 0))

    weights, intercept = irls_fit(x, y, l2=0.0)

    assert weights.size == 0
    assert intercept == pytest.approx(float(np.log(0.3 / 0.7)), abs=1e-9)


# ---------------------------------------------------------------------------
# The production path against the reference, across the H-011 ladder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rung", "degree", "diagonal", "parameters"),
    [
        ("C-0", 1, False, 4),
        ("C-1", 2, True, 7),
        ("C-2", 2, False, 10),
        ("C-3", 3, False, 20),
    ],
)
def test_the_converged_fit_agrees_with_irls(
    rung: str, degree: int, diagonal: bool, parameters: int
) -> None:
    """H-010's external reference, at every rung it is affordable to run.

    Standardised as the pipeline standardises, because an unstandardised
    degree-3 design is badly enough conditioned that the two solvers would be
    comparing their conditioning rather than their answers.
    """
    x, y = _design(1_200, 3, seed=20 + degree)
    design = polynomial_expand(x, degree, diagonal_only=diagonal)
    design = (design - design.mean(axis=0)) / design.std(axis=0)
    assert design.shape[1] + 1 == parameters, rung

    fitted = ConvergentLogisticRegression(tolerance=1e-9, max_iter=2_000_000).fit(
        design, y
    )
    assert fitted.diagnostics.converged, f"{rung}: production fit did not converge"

    reference_w, reference_b = irls_fit(design, y)
    deviation = float(
        np.max(
            np.abs(
                fitted.predict_proba(design)
                - _probabilities(reference_w, reference_b, design)
            )
        )
    )

    assert deviation <= AGREEMENT_TOLERANCE, f"{rung}: deviation {deviation:.3e}"


def test_the_frozen_budget_does_not_agree_with_irls_at_higher_capacity() -> None:
    """The finding that makes the convergence rule H-011's primary one.

    A thousand steps is not a fitted model at twenty parameters, and this is
    the measurement that says so rather than the argument that says so. If
    this ever starts passing, the convergence rule has stopped being load
    bearing and H-011's design should be revisited by a new hypothesis.
    """
    x, y = _design(1_200, 3, seed=23)
    design = polynomial_expand(x, 3)
    design = (design - design.mean(axis=0)) / design.std(axis=0)

    frozen = ConvergentLogisticRegression(tolerance=0.0, max_iter=1_000).fit(design, y)
    reference_w, reference_b = irls_fit(design, y)
    deviation = float(
        np.max(
            np.abs(
                frozen.predict_proba(design)
                - _probabilities(reference_w, reference_b, design)
            )
        )
    )

    assert deviation > AGREEMENT_TOLERANCE
