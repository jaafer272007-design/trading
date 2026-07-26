"""Hand-rolled logistic regression and standardiser.

No ``scikit-learn``. The dependency is avoided deliberately rather than
incidentally: ``REPRODUCIBILITY.md`` §1 requires Tier A bit-exactness from the
combiner, and §4 warns that parallel float reduction ordering "changes results
in the last bits and will silently break bit-exactness tests." A third-party
solver's numerics are version-dependent and, for some solvers, thread-count
dependent. A fixed-iteration gradient descent written here is fully determined
by its inputs and its declared hyperparameters.

Capacity note. For the shuffled-labels gate the combiner's job is to be
*capable of overfitting*: it must be able to exploit a leak if one exists, so
that the absence of measured skill is evidence of the absence of a leak rather
than evidence of a weak model. Erring toward more iterations therefore makes
the gate more sensitive, not less — the conservative direction. This is why
``models/test_logistic.py`` asserts the combiner reaches near-perfect BSS when
handed the label itself as a feature: a combiner that cannot detect a planted
leak cannot be trusted to report its absence.

The standardiser is a separate object, not folded into the model. That is what
makes ``fit on train+test`` expressible as a leak fixture rather than
unreachable.
"""

from typing import Final, Self

import numpy as np
import numpy.typing as npt

DEFAULT_N_ITER: Final = 1_000
DEFAULT_LEARNING_RATE: Final = 0.5
DEFAULT_L2: Final = 1e-6


class Standardizer:
    """Zero-mean, unit-variance scaling with explicit fit/transform separation.

    Fitting on anything other than the training fold is leakage. Keeping fit
    and transform separate is what allows that mistake to be *written down* as
    a negative fixture instead of being structurally impossible to express —
    and a leak that cannot be expressed cannot be tested for.
    """

    def __init__(self) -> None:
        """Initialise an unfitted standardiser."""
        self._mean: npt.NDArray[np.float64] | None = None
        self._scale: npt.NDArray[np.float64] | None = None

    def fit(self, x: npt.NDArray[np.float64]) -> Self:
        """Learn per-column mean and standard deviation.

        Args:
            x: Design matrix, shape ``(n_samples, n_features)``.

        Returns:
            Self.

        Raises:
            ValueError: If ``x`` has no rows.
        """
        if x.shape[0] == 0:
            raise ValueError("Standardizer.fit requires at least one row")
        self._mean = np.mean(x, axis=0)
        scale = np.std(x, axis=0)
        # A constant column has zero spread; dividing by it would produce inf
        # or NaN. Scale of 1.0 leaves the (already centred) column at zero,
        # which is the honest representation of "this column carries no
        # information" — not an imputed value.
        self._scale = np.where(scale > 0.0, scale, 1.0)
        return self

    def transform(self, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Apply the learned scaling.

        Args:
            x: Design matrix.

        Returns:
            Standardised matrix.

        Raises:
            RuntimeError: If called before :meth:`fit`.
        """
        if self._mean is None or self._scale is None:
            raise RuntimeError("Standardizer.transform called before fit")
        return (x - self._mean) / self._scale


class LogisticRegression:
    """Binary logistic regression by fixed-iteration gradient descent.

    Deterministic by construction: weights initialise to zero, the iteration
    count is fixed rather than convergence-dependent, and no randomness enters
    at any point. Identical inputs give identical outputs, bit for bit.
    """

    def __init__(
        self,
        *,
        n_iter: int = DEFAULT_N_ITER,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        l2: float = DEFAULT_L2,
    ) -> None:
        """Initialise the combiner.

        Args:
            n_iter: Fixed number of gradient steps.
            learning_rate: Step size.
            l2: Ridge penalty on the weights (not the intercept).

        Raises:
            ValueError: If any hyperparameter is out of range.
        """
        if n_iter <= 0:
            raise ValueError(f"n_iter must be positive, got {n_iter}")
        if learning_rate <= 0.0:
            raise ValueError(f"learning_rate must be positive, got {learning_rate}")
        if l2 < 0.0:
            raise ValueError(f"l2 must be non-negative, got {l2}")

        self._n_iter: Final = n_iter
        self._learning_rate: Final = learning_rate
        self._l2: Final = l2
        self._weights: npt.NDArray[np.float64] | None = None
        self._intercept: float = 0.0

    @staticmethod
    def _sigmoid(z: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Numerically stable logistic function.

        Args:
            z: Linear predictor.

        Returns:
            Probabilities in ``(0, 1)``.
        """
        out = np.empty_like(z)
        positive = z >= 0.0
        out[positive] = 1.0 / (1.0 + np.exp(-z[positive]))
        exp_z = np.exp(z[~positive])
        out[~positive] = exp_z / (1.0 + exp_z)
        return out

    def fit(
        self,
        x: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64],
    ) -> Self:
        """Fit by gradient descent for exactly ``n_iter`` steps.

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
            raise ValueError("LogisticRegression.fit requires at least one row")

        n_samples, n_features = x.shape
        weights = np.zeros(n_features, dtype=np.float64)
        intercept = np.float64(0.0)

        for _ in range(self._n_iter):
            residual = self._sigmoid(x @ weights + intercept) - y
            grad_w = (x.T @ residual) / n_samples + self._l2 * weights
            grad_b = np.sum(residual) / n_samples
            weights = weights - self._learning_rate * grad_w
            intercept = intercept - self._learning_rate * grad_b

        self._weights = weights
        self._intercept = float(intercept)
        return self

    def predict_proba(self, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Predict positive-class probabilities.

        Args:
            x: Design matrix.

        Returns:
            Probabilities in ``(0, 1)``, one per row.

        Raises:
            RuntimeError: If called before :meth:`fit`.
        """
        if self._weights is None:
            raise RuntimeError("LogisticRegression.predict_proba called before fit")
        return self._sigmoid(x @ self._weights + self._intercept)
