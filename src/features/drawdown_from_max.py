"""Fractional drawdown from the trailing maximum close.

``DATA_CONTRACT.md`` §7 declaration::

    name: drawdown_from_max_<n>
    version: 1
    inputs: [ohlcv]
    lookback_bars: <n>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [0.0, 1.0], null_allowed: true}
    null_semantics: "insufficient history for the trailing window"
    causal_test: tests/features/test_drawdown_from_max.py
    revision_risk: none
    notes: "Bounded in [0, 1). Scale-free — a ratio of prices."

H-012 §B prior (6): gold's behaviour near multi-week highs plausibly differs
from its behaviour mid-range — breakout dynamics, and the asymmetry that
commodity trend-following exploits. ``0`` means the current close *is* the
trailing maximum.

Bounded by construction, so it cannot act as a proxy for price level. That
matters here: an unbounded level feature on a series with a secular uptrend
can encode "later in the sample", and a model that learns the trend through a
level feature is learning the base rate. H-007 is the standing lesson.
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd


class DrawdownFromMax:
    """``(max(close over window) - close) / max(close over window)``."""

    def __init__(self, window: int = 480) -> None:
        """Initialise the feature.

        Args:
            window: Bars in the trailing maximum, inclusive of the current bar.

        Raises:
            ValueError: If ``window`` is less than 2.
        """
        if window < 2:
            raise ValueError(f"window must be at least 2, got {window}")
        self._window: Final = window

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``drawdown_from_max_480``."""
        return f"drawdown_from_max_{self._window}"

    @property
    def version(self) -> int:
        """Declaration version."""
        return 1

    @property
    def confirmation_lag_bars(self) -> int:
        """Zero: knowable at the close of bar ``T``."""
        return 0

    @property
    def session_relative(self) -> bool:
        """Reads no session boundary — only a rolling window of bars.

        Returns:
            False.
        """
        return False

    @property
    def lookback_bars(self) -> int:
        """Bars required before the first value: ``window``."""
        return self._window

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the trailing fractional drawdown.

        Args:
            df: Bar series with a ``close`` column.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`.

        Raises:
            ValueError: If ``close`` is absent or any close is non-positive.
        """
        if "close" not in df.columns:
            raise ValueError(f"{self.name} requires a close column")

        close: npt.NDArray[np.float64] = df["close"].to_numpy(dtype=np.float64)
        if close.size and bool((close <= 0.0).any()):
            raise ValueError(
                f"{self.name}: close must be strictly positive; a non-positive "
                f"price is a data defect, not something to clip "
                f"(DATA_CONTRACT.md §6)"
            )

        n_bars = close.size
        out = np.full(n_bars, np.nan, dtype=np.float64)
        window = self._window

        for i in range(window - 1, n_bars):
            peak = float(np.max(close[i - window + 1 : i + 1]))
            out[i] = (peak - close[i]) / peak

        return pd.Series(out, index=df.index, name=self.name)
