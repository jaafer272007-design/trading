"""What a fit reports about itself.

H-011 registers a VOID condition rather than a negative one: "If the cap is
reached without the gradient tolerance being met at any rung the primary
statements are evaluated at, the run is VOID, not negative. A fit that did not
converge cannot support 'capacity is not the constraint'."

That condition is only enforceable if convergence is *measured*. A fixed
iteration budget that silently underfits a 56-parameter design would read as
"capacity did not help" — fluent, internally consistent, and wrong, which is
the pattern ``EVALUATION.md`` §14 was written about. So the fit reports the
gradient infinity-norm at the parameters it returned, and the caller records
it per fold.

This module holds nothing but the report, so that ``evaluation/pipeline.py``
can carry it without importing an estimator and ``models/logistic.py`` can stay
byte-identical to the version the recorded K-1 baseline describes.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class FitDiagnostics:
    """Convergence evidence for a single fit."""

    iterations: int
    """Gradient steps taken."""

    gradient_infinity_norm: float
    """Infinity-norm of the gradient **at the returned parameters**.

    Not at the last point visited before stopping — at the point the caller
    will actually predict with. The distinction matters when the loop exits on
    its iteration cap.
    """

    converged: bool
    """Whether :attr:`gradient_infinity_norm` met the requested tolerance."""

    tolerance: float
    """The tolerance requested, recorded so the verdict is reproducible."""

    hit_cap: bool
    """Whether the iteration cap was reached. Implies ``not converged``."""


@runtime_checkable
class Diagnosable(Protocol):
    """An estimator that reports how its fit terminated."""

    @property
    def diagnostics(self) -> FitDiagnostics:
        """Convergence evidence from the most recent fit."""
        ...
