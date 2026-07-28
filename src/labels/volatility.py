"""Forward realised-volatility label, registered as H-009 §B.

.. important::

   **This module looks forward, and that is correct** — for the same reason
   ``labels/direction.py`` does. A label is the outcome being predicted, so it
   is necessarily a function of bars after ``T``.

   The part that must *not* look forward is the **threshold**. It is a
   trailing statistic and is held to ``DATA_CONTRACT.md`` §1 exactly as a
   feature would be, by ``tests/labels/test_volatility.py``, which recomputes
   it on truncated history and demands bit-identical values. That test ships
   with an adversarial fixture -- a deliberately centred threshold that the
   same check must reject -- per ``EVALUATION.md`` §14.

Why the forward volatility is the trailing feature read 24 bars later
---------------------------------------------------------------------

``RealizedVol(w).compute(df)[k]`` is the population SD of the one-bar log
returns from closes ``k - w .. k``. So with ``w == horizon``::

    rv[T + horizon]  ==  SD of returns over closes T .. T + horizon

which is the window *after* ``T``. There is no second implementation of the
estimator to drift from the one in the feature column, and there is nothing to
keep in sync.

The two windows share no returns. Trailing at ``T`` uses returns indexed
``T-23 .. T``; forward uses ``T+1 .. T+24``. Disjoint, so the comparison
carries no mechanical correlation from an overlapping bar.

``DATA_CONTRACT.md`` §7-style declaration, for review rather than for the
causal harness -- a label must never enter ``FEATURE_REGISTRY``::

    name: vol_above_median_<horizon>
    version: 1
    inputs: [ohlcv]
    backward_span_bars: threshold_window + vol_window
    forward_span_bars: horizon
    timezone: UTC
    returns: {type: float, range: [0.0, 1.0], null_allowed: true}
    null_semantics: "forward window unavailable or invalid; threshold undefined"
    causal_test: tests/labels/test_volatility.py (threshold only -- see above)
    revision_risk: none
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from features.realized_vol import RealizedVol

DEFAULT_HORIZON: Final = 24
"""Bars ahead. H-009 §I classes this **forced**: it matches H-001's registered
horizon so that this result is comparable to H-003 and H-007 without a caveat."""

DEFAULT_VOL_WINDOW: Final = 24
"""Returns per volatility estimate. **Forced** to equal the horizon -- that
equality is what makes ``rv[T + horizon]`` the forward realised volatility."""

DEFAULT_THRESHOLD_WINDOW: Final = 1000
"""Trailing bars in the median. H-009 §I classes this **judgement**, the only
one this hypothesis introduces.

Roughly six weeks of H1 bars: long relative to volatility's persistence
half-life, so the label asks about *level* rather than about change; short
enough that it is not effectively a whole-sample constant, which would import
the global distribution into the label.

**Registered and not swept.** Varying it does not vary a nuisance parameter --
it changes the label, therefore the question, therefore the hypothesis. Three
windows would be three hypotheses under ``EVALUATION.md`` §9.
"""


@dataclass(frozen=True, slots=True)
class VolatilityLabelSummary:
    """Descriptive counts for a computed volatility-label series."""

    name: str
    horizon: int
    vol_window: int
    threshold_window: int
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
        """Fraction of defined labels produced by an exact tie.

        Ties in a continuous SD are vanishingly rare, which is the reason to
        report the rate rather than to assume it away: a non-zero value here
        would mean the volatility series has repeated exactly, and that is a
        data property worth seeing rather than a rounding curiosity.
        """
        if self.n_defined == 0:
            return float("nan")
        return self.n_ties / self.n_defined

    @property
    def backward_span_bars(self) -> int:
        """Bars of history the label reads at ``T``, through its threshold."""
        return self.threshold_window + self.vol_window


def rolling_median(
    values: npt.NDArray[np.float64], window: int
) -> npt.NDArray[np.float64]:
    """Trailing median over ``window`` values ending at each position inclusive.

    Position ``T`` reads ``values[T - window + 1 .. T]`` and nothing else. A
    position whose window is short, or contains any NaN, is NaN -- never
    partially filled (``DATA_CONTRACT.md`` §6).

    Written as an explicit slice rather than ``Series.rolling().median()``
    because the causal claim should be visible in the indices rather than
    inherited from a library's default, and because an incremental
    order-statistic algorithm's result can in principle depend on where the
    series started. The cost is a C-level ``np.median`` per bar, which is
    milliseconds over this snapshot.

    Args:
        values: Series to take medians of.
        window: Trailing window length. Must be positive.

    Returns:
        Array aligned to ``values``.

    Raises:
        ValueError: If ``window`` is not positive.
    """
    if window <= 0:
        raise ValueError(f"window must be positive, got {window}")

    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        chunk = values[i - window + 1 : i + 1]
        if np.isnan(chunk).any():
            continue
        out[i] = float(np.median(chunk))
    return out


def volatility_threshold(
    df: pd.DataFrame,
    *,
    vol_window: int = DEFAULT_VOL_WINDOW,
    threshold_window: int = DEFAULT_THRESHOLD_WINDOW,
) -> pd.Series:
    """The trailing reference level the forward volatility is compared against.

    Exposed as its own function, and not folded into :func:`volatility_label`,
    for one reason: it is the part of the label that makes a causal claim, so
    it has to be testable on its own. A truncation check buried inside a
    forward-looking label cannot be written.

    Args:
        df: Bar series with a ``close`` column.
        vol_window: Returns per volatility estimate.
        threshold_window: Trailing bars in the median.

    Returns:
        Series aligned to ``df.index``, named
        ``vol_median_<threshold_window>``.
    """
    rv = RealizedVol(window=vol_window).compute(df).to_numpy(dtype=np.float64)
    return pd.Series(
        rolling_median(rv, threshold_window),
        index=df.index,
        name=f"vol_median_{threshold_window}",
    )


def volatility_label(
    df: pd.DataFrame,
    *,
    horizon: int = DEFAULT_HORIZON,
    vol_window: int = DEFAULT_VOL_WINDOW,
    threshold_window: int = DEFAULT_THRESHOLD_WINDOW,
) -> pd.Series:
    """Compute the binary volatility label registered as H-009 §B.

    ``label[T] = 1.0`` if ``rv[T + horizon] > threshold[T]``, else ``0.0``.
    The comparison is strict, so an exact tie resolves to ``0`` -- the same
    convention as the direction label, stated rather than left implicit
    because an undefined tie rule is a silent asymmetry in the base rate.

    A label is ``NaN`` where any of these hold:

    * the forward window runs off the end of the series;
    * the threshold is undefined (insufficient trailing history);
    * the forward window ``[T, T+horizon]`` touches a bar marked invalid;
    * the backward span ``[T - threshold_window - vol_window + 1, T]`` touches
      a bar marked invalid.

    The last two apply only when the frame carries a ``valid`` column, and are
    read automatically rather than taken as an argument for the reason
    ``labels/direction.py`` gives: a caller who has to remember to pass
    validity is a caller who will eventually not, and labels computed across a
    hole look exactly like every other label.

    Args:
        df: Bar series with a ``close`` column, and optionally ``valid``.
        horizon: Forward horizon in bars. Must be positive.
        vol_window: Returns per volatility estimate.
        threshold_window: Trailing bars in the median.

    Returns:
        Series aligned to ``df.index``, named ``vol_above_median_<horizon>``.

    Raises:
        ValueError: If ``horizon`` is not positive or ``close`` is absent.
    """
    if horizon <= 0:
        raise ValueError(f"horizon must be positive, got {horizon}")
    if "close" not in df.columns:
        raise ValueError("volatility_label requires a 'close' column")

    rv = RealizedVol(window=vol_window).compute(df).to_numpy(dtype=np.float64)
    threshold = rolling_median(rv, threshold_window)

    n_bars = len(rv)
    out = np.full(n_bars, np.nan, dtype=np.float64)
    for i in range(n_bars - horizon):
        forward = rv[i + horizon]
        level = threshold[i]
        if np.isnan(forward) or np.isnan(level):
            continue
        out[i] = 1.0 if forward > level else 0.0

    if "valid" in df.columns:
        from data.classify import feature_validity, label_validity

        bar_valid = df["valid"].to_numpy(dtype=np.bool_)
        usable = label_validity(bar_valid, horizon) & feature_validity(
            bar_valid, threshold_window + vol_window
        )
        out[~usable] = np.nan

    return pd.Series(out, index=df.index, name=f"vol_above_median_{horizon}")


def volatility_labels_for_snapshot(
    df: pd.DataFrame,
    *,
    horizon: int = DEFAULT_HORIZON,
    vol_window: int = DEFAULT_VOL_WINDOW,
    threshold_window: int = DEFAULT_THRESHOLD_WINDOW,
) -> pd.Series:
    """The evaluation path's entry point. Requires validity to be present.

    :func:`volatility_label` tolerates a frame with no ``valid`` column
    because synthetic fixtures legitimately have none. That tolerance is
    exactly what would let a real run compute labels across a hole with
    nothing saying so, so the path that produces a *result* refuses instead.

    Args:
        df: A derived snapshot frame.
        horizon: Forward horizon in bars.
        vol_window: Returns per volatility estimate.
        threshold_window: Trailing bars in the median.

    Returns:
        The label series.

    Raises:
        ValueError: If the frame carries no ``valid`` column.
    """
    if "valid" not in df.columns:
        raise ValueError(
            "volatility_labels_for_snapshot requires a 'valid' column. A frame "
            "without one cannot say whether a window spans a hole, and H-009 "
            "§B registers the label as undefined where it does."
        )
    return volatility_label(
        df,
        horizon=horizon,
        vol_window=vol_window,
        threshold_window=threshold_window,
    )


def summarize_volatility(
    labels: pd.Series,
    df: pd.DataFrame,
    *,
    horizon: int = DEFAULT_HORIZON,
    vol_window: int = DEFAULT_VOL_WINDOW,
    threshold_window: int = DEFAULT_THRESHOLD_WINDOW,
) -> VolatilityLabelSummary:
    """Describe a volatility-label series, including the tie rate.

    Ties are counted over **defined** labels only, so ``tie_rate`` and
    ``base_rate`` share a denominator. Two rates printed side by side must
    describe the same population -- a defect this project has already made
    once, in ``labels/direction.py``.

    Args:
        labels: Output of :func:`volatility_label`.
        df: The frame the labels were computed from.
        horizon: The horizon used.
        vol_window: The volatility window used.
        threshold_window: The threshold window used.

    Returns:
        A :class:`VolatilityLabelSummary`.
    """
    rv = RealizedVol(window=vol_window).compute(df).to_numpy(dtype=np.float64)
    threshold = rolling_median(rv, threshold_window)
    values = labels.to_numpy(dtype=np.float64)
    defined = ~np.isnan(values)

    ties = 0
    for i in range(len(rv) - horizon):
        if defined[i] and rv[i + horizon] == threshold[i]:
            ties += 1

    return VolatilityLabelSummary(
        name=str(labels.name),
        horizon=horizon,
        vol_window=vol_window,
        threshold_window=threshold_window,
        n_total=len(values),
        n_defined=int(defined.sum()),
        n_positive=int(np.nansum(values)),
        n_ties=ties,
    )
