"""Trailing log return over a fixed window.

``DATA_CONTRACT.md`` §7 declaration::

    name: log_return_<n>
    version: 1
    inputs: [ohlcv]
    lookback_bars: <n + 1>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [-inf, inf], null_allowed: true}
    null_semantics: "insufficient history for the trailing window"
    causal_test: tests/features/test_log_return.py
    revision_risk: none
    notes: "Scale-free by construction. Depends only on bars <= T."

Scale-free: a ratio of two prices, so the value is invariant to the level of
the series. ``DATA_CONTRACT.md`` §5 makes the same point in the anonymisation
context — absolute price levels are a date stamp, percentage moves are not —
and the reasoning applies just as well to a linear combiner, which would
otherwise have to learn a coefficient that drifts with price.
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

_REQUIRED_COLUMNS: Final = ("close",)


class LogReturn:
    """Log return of close over a trailing window of ``window`` bars.

    ``log_return[T] = log(close[T] / close[T - window])``, undefined (``NaN``)
    for ``T < window``. Uses only bars at or before ``T``, so the confirmation
    lag is 0.
    """

    def __init__(self, window: int = 24) -> None:
        """Initialise the feature.

        Args:
            window: Trailing window in bars. Must be positive.

        Raises:
            ValueError: If ``window`` is not positive.
        """
        if window <= 0:
            raise ValueError(f"window must be positive, got {window}")
        self._window: Final = window

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``log_return_24``."""
        return f"log_return_{self._window}"

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
        """Compute the trailing log return.

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

        # Scalar loop rather than a vectorised shift: the same argument as
        # features/atr.py. Bit-exactness under truncation requires the
        # operation reaching index i to be identical regardless of how many
        # bars follow, and an explicit loop guarantees that by construction.
        for i in range(window, n_bars):
            out[i] = np.log(close[i] / close[i - window])

        return pd.Series(out, index=df.index, name=self.name)
