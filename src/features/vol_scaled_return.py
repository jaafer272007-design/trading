"""Trailing log return divided by trailing realised volatility.

``DATA_CONTRACT.md`` §7 declaration::

    name: vol_scaled_return_<n>
    version: 1
    inputs: [ohlcv]
    lookback_bars: <n + 1>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [-inf, inf], null_allowed: true}
    null_semantics: "insufficient history, or zero realised volatility"
    causal_test: tests/features/test_vol_scaled_return.py
    revision_risk: none
    notes: "Composes LogReturn and RealizedVol. No second estimator."

H-012 §B prior (3): momentum per unit of risk. Standard in managed-futures
construction, and **not redundant with raw momentum** — dividing by
contemporaneous volatility *re-ranks* past moves rather than rescaling them,
so a large move in a calm regime outranks a larger move in a violent one. A
linear combiner given both can express either.

It composes :class:`~features.log_return.LogReturn` and
:class:`~features.realized_vol.RealizedVol` rather than recomputing them. A
second implementation of an estimator that already ships is a place for the
two to drift, and H-009 made the same choice for the same reason.
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from features.log_return import LogReturn
from features.realized_vol import RealizedVol


class VolScaledReturn:
    """``log_return_<n>`` divided by ``realized_vol_<n>``.

    Where realised volatility is zero the ratio is undefined and the value is
    ``NaN``. It is not clipped, floored, or replaced by the unscaled return:
    ``DATA_CONTRACT.md`` §6 requires missing to propagate loudly.
    """

    def __init__(self, window: int = 120) -> None:
        """Initialise the feature.

        Args:
            window: Bars in both the return and the volatility window.

        Raises:
            ValueError: If ``window`` is less than 2.
        """
        if window < 2:
            raise ValueError(f"window must be at least 2, got {window}")
        self._window: Final = window
        self._ret: Final = LogReturn(window=window)
        self._vol: Final = RealizedVol(window=window)

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``vol_scaled_return_120``."""
        return f"vol_scaled_return_{self._window}"

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
        """Bars required before the first value: ``window + 1``."""
        return self._window + 1

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the volatility-scaled trailing return.

        Args:
            df: Bar series with a ``close`` column.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`.
        """
        ret: npt.NDArray[np.float64] = self._ret.compute(df).to_numpy(dtype=np.float64)
        vol: npt.NDArray[np.float64] = self._vol.compute(df).to_numpy(dtype=np.float64)

        out = np.full(ret.size, np.nan, dtype=np.float64)
        usable = np.isfinite(ret) & np.isfinite(vol) & (vol > 0.0)
        out[usable] = ret[usable] / vol[usable]
        return pd.Series(out, index=df.index, name=self.name)
