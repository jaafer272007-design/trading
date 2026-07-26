"""Realised volatility of one-bar log returns over a trailing window.

``DATA_CONTRACT.md`` §7 declaration::

    name: realized_vol_<n>
    version: 1
    inputs: [ohlcv]
    lookback_bars: <n + 1>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [0.0, inf], null_allowed: true}
    null_semantics: "insufficient history for the trailing window"
    causal_test: tests/features/test_realized_vol.py
    revision_risk: none
    notes: "Population SD of log returns. Scale-free. Depends only on bars <= T."
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

_REQUIRED_COLUMNS: Final = ("close",)


class RealizedVol:
    """Population standard deviation of one-bar log returns over ``window`` bars.

    For bar ``T`` the window covers the ``window`` one-bar returns ending at
    ``T`` — that is, returns computed from closes ``T - window .. T``. The
    first value therefore appears at index ``window``, and the confirmation lag
    is 0.

    Population (not sample) SD: the divisor is ``window``, not ``window - 1``.
    The choice is arbitrary for a feature but must be fixed, because switching
    later changes every historical value without changing the feature name.
    """

    def __init__(self, window: int = 24) -> None:
        """Initialise the feature.

        Args:
            window: Number of one-bar returns in the window. Must be ≥ 2.

        Raises:
            ValueError: If ``window`` is less than 2.
        """
        if window < 2:
            raise ValueError(f"window must be at least 2, got {window}")
        self._window: Final = window

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``realized_vol_24``."""
        return f"realized_vol_{self._window}"

    @property
    def version(self) -> int:
        """Declaration version."""
        return 1

    @property
    def lookback_bars(self) -> int:
        """Bars required before the first value: ``window + 1``."""
        return self._window + 1

    @property
    def confirmation_lag_bars(self) -> int:
        """Zero: knowable at the close of bar ``T``."""
        return 0

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute trailing realised volatility.

        Args:
            df: Bar series with a ``close`` column.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`.

        Raises:
            ValueError: If ``close`` is absent, or any close is non-positive.
        """
        missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"{self.name} requires columns {list(_REQUIRED_COLUMNS)}; "
                f"missing {missing}"
            )

        close: npt.NDArray[np.float64] = df["close"].to_numpy(dtype=np.float64)
        if close.size and bool((close <= 0.0).any()):
            raise ValueError(
                f"{self.name}: close must be strictly positive to take a log; "
                f"a non-positive price is a data defect, not something to clip "
                f"(DATA_CONTRACT.md §6)"
            )

        n_bars = len(close)
        out = np.full(n_bars, np.nan, dtype=np.float64)
        window = self._window

        # One-bar log returns; index 0 undefined (no prior close).
        step: npt.NDArray[np.float64] = np.full(n_bars, np.nan, dtype=np.float64)
        for i in range(1, n_bars):
            step[i] = np.log(close[i] / close[i - 1])

        # Explicit left-to-right accumulation per window, for the same
        # bit-exactness reason as features/atr.py: a running accumulator whose
        # error depends on where the array starts would produce last-bit
        # differences that the causal harness reports as leaks.
        for i in range(window, n_bars):
            total = np.float64(0.0)
            for j in range(i - window + 1, i + 1):
                total += step[j]
            mean = total / window

            sq = np.float64(0.0)
            for j in range(i - window + 1, i + 1):
                delta = step[j] - mean
                sq += delta * delta
            out[i] = np.sqrt(sq / window)

        return pd.Series(out, index=df.index, name=self.name)
