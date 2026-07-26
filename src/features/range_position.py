"""Position of the close within the trailing high-low range.

``DATA_CONTRACT.md`` §7 declaration::

    name: range_position_<n>
    version: 1
    inputs: [ohlcv]
    lookback_bars: <n>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [0.0, 1.0], null_allowed: true}
    null_semantics: "insufficient history, or a degenerate (zero-width) range"
    causal_test: tests/features/test_range_position.py
    revision_risk: none
    notes: "Scale-free ratio in [0,1]. Depends only on bars <= T."
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

_REQUIRED_COLUMNS: Final = ("high", "low", "close")


class RangePosition:
    """Where the close sits inside the trailing ``window``-bar range.

    ``range_position[T] = (close[T] - min(low[T-w+1..T]))
                          / (max(high[T-w+1..T]) - min(low[T-w+1..T]))``

    with ``w = window``. Bounded in ``[0, 1]`` and scale-free.

    A zero-width range (every high equal to every low across the window)
    yields ``NaN`` rather than a substituted 0.5 — an undefined ratio is not
    computable, and inventing a midpoint is exactly the silent imputation
    ``DATA_CONTRACT.md`` §6 prohibits. On real bars this is essentially a
    halted-market signature and should propagate loudly.
    """

    def __init__(self, window: int = 48) -> None:
        """Initialise the feature.

        Args:
            window: Trailing window in bars. Must be ≥ 2.

        Raises:
            ValueError: If ``window`` is less than 2.
        """
        if window < 2:
            raise ValueError(f"window must be at least 2, got {window}")
        self._window: Final = window

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``range_position_48``."""
        return f"range_position_{self._window}"

    @property
    def version(self) -> int:
        """Declaration version."""
        return 1

    @property
    def lookback_bars(self) -> int:
        """Bars required before the first value: ``window``."""
        return self._window

    @property
    def confirmation_lag_bars(self) -> int:
        """Zero: knowable at the close of bar ``T``."""
        return 0

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the trailing range position.

        Args:
            df: Bar series with ``high``, ``low`` and ``close`` columns.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`.

        Raises:
            ValueError: If a required column is absent.
        """
        missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"{self.name} requires columns {list(_REQUIRED_COLUMNS)}; "
                f"missing {missing}"
            )

        high: npt.NDArray[np.float64] = df["high"].to_numpy(dtype=np.float64)
        low: npt.NDArray[np.float64] = df["low"].to_numpy(dtype=np.float64)
        close: npt.NDArray[np.float64] = df["close"].to_numpy(dtype=np.float64)

        n_bars = len(close)
        out = np.full(n_bars, np.nan, dtype=np.float64)
        window = self._window

        for i in range(window - 1, n_bars):
            start = i - window + 1
            hi = high[start]
            lo = low[start]
            for j in range(start + 1, i + 1):
                if high[j] > hi:
                    hi = high[j]
                if low[j] < lo:
                    lo = low[j]
            span = hi - lo
            if span > 0.0:
                out[i] = (close[i] - lo) / span

        return pd.Series(out, index=df.index, name=self.name)
