"""Directional outcome label over a fixed forward horizon.

.. important::

   **This module looks forward, and that is correct.** A label is the outcome
   being predicted, so it is necessarily a function of bars after ``T``.
   Nothing here is a causality violation and nothing here should be "fixed" to
   use only past data — that would make the label unlearnable rather than
   safe.

   The distinction that matters: a *feature* at bar ``T`` may use only bars
   ``<= T`` (``DATA_CONTRACT.md`` §1, enforced by ``tests/causality.py``); a
   *label* at bar ``T`` describes ``(T, T+H]`` and is only knowable at
   ``T + H``. That is exactly why this module lives in ``src/labels/`` and not
   ``src/features/`` — it must never enter ``FEATURE_REGISTRY``, where the
   causal sweep would (correctly) reject it.

   The forward reach is also what makes purge and embargo necessary: a
   training sample at ``T`` whose label window overlaps a test window carries
   test-period information. See ``EVALUATION.md`` §5.2 and
   ``evaluation/splits.py``.

Horizon is fixed at 24 bars, registered in ``HYPOTHESES.md`` H-001 before any
run. Trying h1/h4/h24 and keeping the best would be three hypotheses under
``EVALUATION.md`` §9 and metric shopping under ``RESEARCH.md`` §5.3.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

DEFAULT_HORIZON: Final = 24
"""Bars ahead. See REPRODUCIBILITY.md §7, which enumerates h1/h4/h24."""


@dataclass(frozen=True, slots=True)
class LabelSummary:
    """Descriptive counts for a computed label series."""

    name: str
    horizon: int
    n_total: int
    n_defined: int
    n_positive: int
    n_ties: int

    @property
    def base_rate(self) -> float:
        """Fraction of defined labels that are positive."""
        if self.n_defined == 0:
            return float("nan")
        return self.n_positive / self.n_defined

    @property
    def tie_rate(self) -> float:
        """Fraction of defined labels produced by an exact tie."""
        if self.n_defined == 0:
            return float("nan")
        return self.n_ties / self.n_defined


def direction_label(
    df: pd.DataFrame,
    horizon: int = DEFAULT_HORIZON,
) -> pd.Series:
    """Compute the binary direction label over ``horizon`` bars.

    ``label[T] = 1.0`` if ``close[T + horizon] > close[T]``, else ``0.0``.
    The comparison is strict, so an exact tie resolves to ``0`` — a rule that
    must be stated rather than left implicit, because an undefined tie
    convention is a silent asymmetry in the base rate.

    The final ``horizon`` rows have no forward data and are ``NaN``. They are
    never imputed (``DATA_CONTRACT.md`` §6).

    Args:
        df: Bar series with a ``close`` column.
        horizon: Forward horizon in bars. Must be positive.

    Returns:
        Series aligned to ``df.index``, named ``direction_<horizon>``.

    Raises:
        ValueError: If ``horizon`` is not positive or ``close`` is absent.
    """
    if horizon <= 0:
        raise ValueError(f"horizon must be positive, got {horizon}")
    if "close" not in df.columns:
        raise ValueError("direction_label requires a 'close' column")

    close: npt.NDArray[np.float64] = df["close"].to_numpy(dtype=np.float64)
    n_bars = len(close)
    out = np.full(n_bars, np.nan, dtype=np.float64)

    for i in range(n_bars - horizon):
        out[i] = 1.0 if close[i + horizon] > close[i] else 0.0

    return pd.Series(out, index=df.index, name=f"direction_{horizon}")


def summarize(labels: pd.Series, df: pd.DataFrame, horizon: int) -> LabelSummary:
    """Describe a label series, including the tie rate.

    Args:
        labels: Output of :func:`direction_label`.
        df: The frame the labels were computed from.
        horizon: The horizon used.

    Returns:
        A :class:`LabelSummary`.
    """
    close: npt.NDArray[np.float64] = df["close"].to_numpy(dtype=np.float64)
    values = labels.to_numpy(dtype=np.float64)
    defined = ~np.isnan(values)

    ties = 0
    for i in range(len(close) - horizon):
        if close[i + horizon] == close[i]:
            ties += 1

    return LabelSummary(
        name=str(labels.name),
        horizon=horizon,
        n_total=len(values),
        n_defined=int(defined.sum()),
        n_positive=int(np.nansum(values)),
        n_ties=ties,
    )
