"""Polynomial basis expansion of a design matrix.

This is the capacity axis H-011 registers. It adds no information: every
produced column is a deterministic, label-free, pointwise function of the same
row of the input. What grows is the function class the combiner searches, which
is the definition of capacity — and it is the *only* thing H-011 varies.

Why capacity is raised here rather than by swapping the estimator
-----------------------------------------------------------------

A tree ensemble or an MLP would raise capacity further and faster, and would
also change the optimiser, the initialisation, the convexity of the objective
and the seed surface. Four changes bundled with the one under test leave any
difference unattributable, which is the failure H-007 was designed to avoid.
Feeding a wider design matrix to the *same* convex objective and the *same*
optimiser leaves parameter count as the sole difference.

Term ordering
-------------

Terms are emitted in ascending total degree, and within a degree in
``itertools.combinations_with_replacement`` order over feature indices. That
order is canonical and stable, so a fitted coefficient vector means the same
thing across runs and the expansion is reproducible bit for bit.

The constant term is deliberately absent: the combiner carries its own
intercept, and emitting a column of ones as well would make the design rank
deficient.
"""

from itertools import combinations_with_replacement
from typing import Final

import numpy as np
import numpy.typing as npt

MIN_DEGREE: Final = 1
"""Degree 1 is the identity expansion — the H-001 design, unchanged."""


def polynomial_terms(
    n_features: int, degree: int, *, diagonal_only: bool = False
) -> tuple[tuple[int, ...], ...]:
    """Enumerate the monomials of a polynomial basis, excluding the constant.

    Args:
        n_features: Number of input columns.
        degree: Maximum total degree. ``1`` reproduces the input exactly.
        diagonal_only: Emit only pure powers of a single feature, dropping
            every cross term. At ``degree=2`` this is the ``C-1`` rung.

    Returns:
        One tuple of feature indices per term. A term is the product of the
        input columns it names, so ``(0, 0, 1)`` means ``x0 * x0 * x1``.

    Raises:
        ValueError: If ``n_features`` or ``degree`` is out of range.
    """
    if n_features <= 0:
        raise ValueError(f"n_features must be positive, got {n_features}")
    if degree < MIN_DEGREE:
        raise ValueError(f"degree must be at least {MIN_DEGREE}, got {degree}")

    terms: list[tuple[int, ...]] = []
    for d in range(1, degree + 1):
        for combo in combinations_with_replacement(range(n_features), d):
            if diagonal_only and len(set(combo)) > 1:
                continue
            terms.append(combo)
    return tuple(terms)


def n_polynomial_terms(
    n_features: int, degree: int, *, diagonal_only: bool = False
) -> int:
    """Count the terms without materialising them.

    Args:
        n_features: Number of input columns.
        degree: Maximum total degree.
        diagonal_only: Restrict to pure powers.

    Returns:
        The term count. Add one for the combiner's intercept to get the
        fitted parameter count.
    """
    return len(polynomial_terms(n_features, degree, diagonal_only=diagonal_only))


def polynomial_expand(
    x: npt.NDArray[np.float64], degree: int, *, diagonal_only: bool = False
) -> npt.NDArray[np.float64]:
    """Expand a design matrix into a polynomial basis.

    Pointwise and label-free: row ``i`` of the output is a function of row
    ``i`` of the input alone, so the expansion cannot move information across
    time. ``tests/features/test_polynomial_expansion.py`` asserts that from the
    failing side rather than taking it on the argument.

    Args:
        x: Design matrix, shape ``(n_samples, n_features)``.
        degree: Maximum total degree. ``1`` returns a copy of the input.
        diagonal_only: Emit only pure powers of a single feature.

    Returns:
        The expanded matrix, shape ``(n_samples, n_terms)``.

    Raises:
        ValueError: If ``x`` is not two-dimensional, or the degree is invalid.
    """
    if x.ndim != 2:
        raise ValueError(f"expected a 2-D design matrix, got shape {x.shape}")

    terms = polynomial_terms(x.shape[1], degree, diagonal_only=diagonal_only)
    out = np.empty((x.shape[0], len(terms)), dtype=np.float64)
    for j, combo in enumerate(terms):
        column = x[:, combo[0]].astype(np.float64, copy=True)
        for index in combo[1:]:
            column *= x[:, index]
        out[:, j] = column
    return out


def term_names(
    names: tuple[str, ...], degree: int, *, diagonal_only: bool = False
) -> tuple[str, ...]:
    """Name each expanded column after the inputs it multiplies.

    Args:
        names: Input column names.
        degree: Maximum total degree.
        diagonal_only: Restrict to pure powers.

    Returns:
        One name per expanded column, in the same order as
        :func:`polynomial_expand`.
    """
    terms = polynomial_terms(len(names), degree, diagonal_only=diagonal_only)
    return tuple("*".join(names[i] for i in combo) for combo in terms)
