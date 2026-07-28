"""The combiner, stopped on convergence rather than on an iteration count.

H-011's primary fitting rule. The registered wording:

    Iterate until the gradient infinity-norm at the current parameters is
    <= 1e-6, cap 1e6 iterations.

Why this exists as a separate class
-----------------------------------

``models/logistic.py`` is byte-identical to the version the recorded K-1
sensitivity baseline describes, and it stays that way. Editing it to add a
stopping rule would move the combiner fingerprint and invalidate a record that
is still correct for the frozen rule — H-011 reports **both** rules, so both
records must survive.

The K-1 guard is not bypassed by defining the estimator elsewhere:
``evaluation/sensitivity.py`` keys on the estimator class actually fitted, and
``tests/evaluation/test_sensitivity.py`` carries an adversarial fixture proving
the guard fires on exactly this route.

Why the iteration budget is a convergence parameter, not a capacity parameter
-----------------------------------------------------------------------------

1,000 steps at learning rate 0.5 suffices for four parameters. On 56 correlated
polynomial terms it may not, and a non-converged fit *underfits* — which reads
as "capacity did not help" and would make H-011's conclusion an artefact of the
optimiser budget. Holding the budget fixed across the ladder does not hold the
comparison fair; it confounds capacity with optimisation error. Stopping on the
gradient instead removes that term, which is why this is the primary rule and
the frozen one is reported beside it.

The update is character-for-character the parent's. ``tests/models/
test_convergent.py`` pins that from the failing side: at ``tolerance=0.0`` this
class must reproduce ``LogisticRegression(n_iter=N)`` bit for bit.
"""

from typing import Final, Self

import numpy as np
import numpy.typing as npt

from models.diagnostics import FitDiagnostics
from models.logistic import DEFAULT_L2, DEFAULT_LEARNING_RATE, LogisticRegression

DEFAULT_TOLERANCE: Final = 1e-6
"""Gradient infinity-norm at which the fit is called converged. H-011."""

DEFAULT_MAX_ITER: Final = 1_000_000
"""Hard cap. Reaching it makes a run VOID rather than negative. H-011."""


class ConvergentLogisticRegression(LogisticRegression):
    """Logistic regression by gradient descent, stopped on the gradient norm.

    Deterministic by construction, exactly as the parent is: weights
    initialise to zero, no randomness enters, and the stopping rule is a
    function of the data alone.
    """

    def __init__(
        self,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        max_iter: int = DEFAULT_MAX_ITER,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        l2: float = DEFAULT_L2,
    ) -> None:
        """Initialise the combiner.

        Args:
            tolerance: Gradient infinity-norm at which to stop. ``0.0`` never
                triggers, which is how the bit-identity test pins the update
                against the parent's.
            max_iter: Hard iteration cap.
            learning_rate: Step size.
            l2: Ridge penalty on the weights, not the intercept.

        Raises:
            ValueError: If any hyperparameter is out of range.
        """
        super().__init__(n_iter=max_iter, learning_rate=learning_rate, l2=l2)
        if tolerance < 0.0:
            raise ValueError(f"tolerance must be non-negative, got {tolerance}")

        self._tolerance: Final = tolerance
        self._max_iter: Final = max_iter
        self._diagnostics: FitDiagnostics | None = None

    @property
    def diagnostics(self) -> FitDiagnostics:
        """Convergence evidence from the most recent fit.

        Returns:
            The diagnostics.

        Raises:
            RuntimeError: If called before :meth:`fit`.
        """
        if self._diagnostics is None:
            raise RuntimeError("diagnostics read before fit")
        return self._diagnostics

    def _gradient(
        self,
        x: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64],
        weights: npt.NDArray[np.float64],
        intercept: np.float64,
    ) -> tuple[npt.NDArray[np.float64], np.float64]:
        """The parent's gradient, factored out so it can be evaluated twice.

        Args:
            x: Design matrix.
            y: Binary targets.
            weights: Current weights.
            intercept: Current intercept.

        Returns:
            Gradient with respect to the weights and to the intercept.
        """
        n_samples = x.shape[0]
        residual = self._sigmoid(x @ weights + intercept) - y
        grad_w = (x.T @ residual) / n_samples + self._l2 * weights
        grad_b = np.sum(residual) / n_samples
        return grad_w, np.float64(grad_b)

    @staticmethod
    def _infinity_norm(grad_w: npt.NDArray[np.float64], grad_b: np.float64) -> float:
        """Largest absolute component of the full gradient.

        Args:
            grad_w: Weight gradient.
            grad_b: Intercept gradient.

        Returns:
            The infinity-norm over weights and intercept together. The
            intercept is included because a fit whose intercept has not settled
            has not settled.
        """
        return float(max(np.max(np.abs(grad_w)), abs(grad_b)))

    def fit(
        self,
        x: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64],
    ) -> Self:
        """Fit until the gradient is small or the cap is reached.

        Args:
            x: Design matrix, shape ``(n_samples, n_features)``.
            y: Binary targets in ``{0, 1}``.

        Returns:
            Self.

        Raises:
            ValueError: If shapes disagree or the sample is empty.
        """
        if x.shape[0] != y.shape[0]:
            raise ValueError(f"row mismatch: x has {x.shape[0]}, y has {y.shape[0]}")
        if x.shape[0] == 0:
            raise ValueError("ConvergentLogisticRegression.fit requires a row")

        weights = np.zeros(x.shape[1], dtype=np.float64)
        intercept = np.float64(0.0)

        iterations = 0
        for _ in range(self._max_iter):
            grad_w, grad_b = self._gradient(x, y, weights, intercept)
            if self._infinity_norm(grad_w, grad_b) <= self._tolerance:
                break
            weights = weights - self._learning_rate * grad_w
            intercept = intercept - self._learning_rate * grad_b
            iterations += 1

        # Reported at the parameters the caller will predict with, not at the
        # last point visited before the loop exited. When the cap is hit those
        # are different, and it is the former that the VOID condition is about.
        grad_w, grad_b = self._gradient(x, y, weights, intercept)
        norm = self._infinity_norm(grad_w, grad_b)

        self._weights = weights
        self._intercept = float(intercept)
        self._diagnostics = FitDiagnostics(
            iterations=iterations,
            gradient_infinity_norm=norm,
            converged=norm <= self._tolerance,
            tolerance=self._tolerance,
            hit_cap=iterations >= self._max_iter,
        )
        return self
