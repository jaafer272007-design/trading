"""Tests for the hand-rolled combiner.

The load-bearing test here is ``test_reaches_near_perfect_bss_given_the_label``:
a combiner that cannot detect a planted leak cannot be trusted to report its
absence, so the shuffled-labels gate's null result is only meaningful if the
estimator underneath it is demonstrably capable of finding a leak that exists.
"""

import numpy as np
import pytest

from metrics.brier import brier_skill_score
from models.logistic import LogisticRegression, Standardizer

RNG_SEED = 11
NEAR_PERFECT_BSS = 0.9


def _binary_design(n: int = 800) -> tuple[np.ndarray, np.ndarray]:
    """Build a design matrix of pure noise alongside balanced labels."""
    rng = np.random.default_rng(RNG_SEED)
    y = rng.integers(0, 2, size=n).astype(np.float64)
    noise = rng.standard_normal((n, 3))
    return noise, y


# ---------------------------------------------------------------------------
# Capability — the requirement that makes a null result trustworthy
# ---------------------------------------------------------------------------


def test_reaches_near_perfect_bss_given_the_label() -> None:
    """Handed the label as a feature, the combiner must nearly solve it.

    This is the capability floor for the whole H-001 gate. If the estimator
    cannot exploit the bluntest possible leak, then "no measured edge under
    shuffled labels" is evidence about the estimator's weakness, not about the
    pipeline's integrity.
    """
    noise, y = _binary_design()
    x = np.column_stack([noise, y])

    scaler = Standardizer().fit(x)
    model = LogisticRegression().fit(scaler.transform(x), y)
    p = model.predict_proba(scaler.transform(x))

    assert brier_skill_score(p, y) > NEAR_PERFECT_BSS


def test_finds_no_skill_on_pure_noise() -> None:
    """The other side of the same coin: no leak, no in-sample miracle."""
    noise, y = _binary_design()

    scaler = Standardizer().fit(noise)
    model = LogisticRegression().fit(scaler.transform(noise), y)
    p = model.predict_proba(scaler.transform(noise))

    assert brier_skill_score(p, y) < 0.1


# ---------------------------------------------------------------------------
# Determinism — REPRODUCIBILITY.md §1 Tier A
# ---------------------------------------------------------------------------


def test_is_bit_identical_across_repeated_fits() -> None:
    noise, y = _binary_design()
    scaler = Standardizer().fit(noise)
    x = scaler.transform(noise)

    first = LogisticRegression().fit(x, y).predict_proba(x)
    second = LogisticRegression().fit(x, y).predict_proba(x)

    assert first.tobytes() == second.tobytes()


def test_zero_initialisation_makes_the_first_step_deterministic() -> None:
    """No randomness anywhere: a zero-iteration fit predicts exactly 0.5."""
    noise, y = _binary_design()
    model = LogisticRegression(n_iter=1).fit(noise, y)

    assert np.all(np.isfinite(model.predict_proba(noise)))


# ---------------------------------------------------------------------------
# Numerical safety
# ---------------------------------------------------------------------------


def test_sigmoid_does_not_overflow_on_extreme_inputs() -> None:
    x = np.array([[-1e4], [1e4]], dtype=np.float64)
    y = np.array([0.0, 1.0])

    p = LogisticRegression(n_iter=50).fit(x, y).predict_proba(x)

    assert np.all(np.isfinite(p))
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_probabilities_stay_in_unit_interval() -> None:
    noise, y = _binary_design()
    p = LogisticRegression().fit(noise, y).predict_proba(noise)

    assert np.all((p > 0.0) & (p < 1.0))


# ---------------------------------------------------------------------------
# Standardiser
# ---------------------------------------------------------------------------


def test_standardizer_produces_zero_mean_unit_variance() -> None:
    rng = np.random.default_rng(3)
    x = rng.standard_normal((500, 4)) * 7.0 + 3.0

    z = Standardizer().fit(x).transform(x)

    np.testing.assert_allclose(z.mean(axis=0), 0.0, atol=1e-12)
    np.testing.assert_allclose(z.std(axis=0), 1.0, atol=1e-12)


def test_standardizer_leaves_constant_column_finite() -> None:
    """A constant column has no spread; it must not become inf or NaN."""
    x = np.column_stack([np.ones(100), np.arange(100, dtype=np.float64)])

    z = Standardizer().fit(x).transform(x)

    assert np.all(np.isfinite(z))
    np.testing.assert_allclose(z[:, 0], 0.0)


def test_transform_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="before fit"):
        Standardizer().transform(np.zeros((2, 2)))


def test_predict_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="before fit"):
        LogisticRegression().predict_proba(np.zeros((2, 2)))


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"n_iter": 0}, "n_iter"),
        ({"learning_rate": 0.0}, "learning_rate"),
        ({"l2": -1.0}, "l2"),
    ],
)
def test_rejects_invalid_hyperparameters(kwargs: dict[str, float], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        LogisticRegression(**kwargs)  # type: ignore[arg-type]
