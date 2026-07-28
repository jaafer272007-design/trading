"""Distance from a slow moving average, in units of ATR.

``DATA_CONTRACT.md`` §7 declaration::

    name: atr_distance_<n>
    version: 1
    inputs: [ohlcv]
    lookback_bars: max(<n>, atr_period + 1)
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [-inf, inf], null_allowed: true}
    null_semantics: "insufficient history, or zero ATR"
    causal_test: tests/features/test_atr_distance.py
    revision_risk: none
    notes: "Composes ATR. Scale-free: both numerator and denominator are prices."

H-012 §B prior (5): the classic trend-following state variable. Unlike
``range_position_48``, which is bounded and local, this is unbounded and slow
— it distinguishes "far above a slow anchor" from "high within a recent
range", which are different states that the bounded feature maps together.

The window mean is accumulated with an explicit ``numpy`` reduction over a
window-sized slice, never a running or cumulative sum. A cumulative
accumulator's rounding depends on where the array starts, which would make the
value at bar ``T`` differ under truncation and be reported as a leak by the
causal harness — the same reasoning ``features/atr.py`` and
``features/realized_vol.py`` record.
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from features.atr import ATR

_REQUIRED_COLUMNS: Final = ("close",)


class AtrDistance:
    """``(close - SMA(close, window)) / ATR(atr_period)``.

    Where ATR is zero the ratio is undefined and the value is ``NaN`` — a flat
    bar range is a real state, and dividing by it is not.
    """

    def __init__(self, window: int = 480, atr_period: int = 14) -> None:
        """Initialise the feature.

        Args:
            window: Bars in the moving average.
            atr_period: ATR period for the denominator.

        Raises:
            ValueError: If either window is out of range.
        """
        if window < 2:
            raise ValueError(f"window must be at least 2, got {window}")
        if atr_period < 1:
            raise ValueError(f"atr_period must be at least 1, got {atr_period}")
        self._window: Final = window
        self._atr: Final = ATR(period=atr_period)

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``atr_distance_480``."""
        return f"atr_distance_{self._window}"

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
        """Bars required before the first value."""
        return max(self._window, self._atr.lookback_bars)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the ATR-normalised distance from the moving average.

        Args:
            df: Bar series with ``high``, ``low`` and ``close`` columns.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`.

        Raises:
            ValueError: If ``close`` is absent.
        """
        if "close" not in df.columns:
            raise ValueError(f"{self.name} requires a close column")

        close: npt.NDArray[np.float64] = df["close"].to_numpy(dtype=np.float64)
        atr: npt.NDArray[np.float64] = self._atr.compute(df).to_numpy(dtype=np.float64)

        n_bars = close.size
        out = np.full(n_bars, np.nan, dtype=np.float64)
        window = self._window

        for i in range(window - 1, n_bars):
            if not np.isfinite(atr[i]) or atr[i] <= 0.0:
                continue
            mean = float(np.sum(close[i - window + 1 : i + 1])) / window
            out[i] = (close[i] - mean) / atr[i]

        return pd.Series(out, index=df.index, name=self.name)
