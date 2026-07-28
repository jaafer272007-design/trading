"""Trailing log return per unit of trailing tick volume.

``DATA_CONTRACT.md`` §7 declaration::

    name: volume_weighted_return_<n>
    version: 1
    inputs: [ohlcv, tick_volume]
    lookback_bars: <n + 1>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [-inf, inf], null_allowed: true}
    null_semantics: "insufficient history, or zero trailing volume"
    causal_test: tests/features/test_volume_weighted_return.py
    revision_risk: none
    notes: "Tick volume is BROKER-SPECIFIC. See the caveat below and H-012 §D."

H-012 §B prior (7): a move on thin participation is more likely to revert; a
move on heavy participation is more likely to continue.

The caveat, which is registered and not merely noted
-----------------------------------------------------

**Tick volume counts price updates on one broker's feed, not contracts
traded.** A different broker's tick count for the same hour can differ by an
order of magnitude, and nothing in this repository can distinguish a real
change in participation from a change in FxPro's quoting behaviour.

H-012 §D pre-commits the consequence *before* the run, so it cannot be
softened if this turns out to be the feature that fires: a result resting on
this feature alone is **a finding requiring a second feed before it is
believed, not a result**, and it does not clear H-012's no-conditions (i) or
(ii). The required next step is a second feed, not a larger sweep on this one.
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from features.log_return import LogReturn

VOLUME_COLUMN: Final = "tick_volume"
"""The column read. Named explicitly rather than falling back to alternatives.

A silent fallback to a differently-defined column would be exactly the kind of
fluent wrong answer ``EVALUATION.md`` §14 is about: the feature would compute,
the numbers would look reasonable, and they would mean something else.
"""


class VolumeWeightedReturn:
    """``log(close_T / close_{T-n}) / sum(tick_volume over the window)``."""

    def __init__(self, window: int = 24) -> None:
        """Initialise the feature.

        Args:
            window: Bars spanned by both the return and the volume sum.

        Raises:
            ValueError: If ``window`` is less than 1.
        """
        if window < 1:
            raise ValueError(f"window must be at least 1, got {window}")
        self._window: Final = window
        self._ret: Final = LogReturn(window=window)

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``volume_weighted_return_24``."""
        return f"volume_weighted_return_{self._window}"

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
        """Compute return per unit of trailing tick volume.

        Args:
            df: Bar series with ``close`` and ``tick_volume`` columns.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`.

        Raises:
            ValueError: If the volume column is absent or holds a negative.
        """
        if VOLUME_COLUMN not in df.columns:
            raise ValueError(
                f"{self.name} requires a {VOLUME_COLUMN!r} column; found "
                f"{sorted(df.columns)}. This feature is not computed from a "
                f"substitute column — see the module docstring."
            )

        ret: npt.NDArray[np.float64] = self._ret.compute(df).to_numpy(dtype=np.float64)
        volume: npt.NDArray[np.float64] = df[VOLUME_COLUMN].to_numpy(dtype=np.float64)
        if volume.size and bool((volume < 0.0).any()):
            raise ValueError(f"{self.name}: negative tick volume is a data defect")

        n_bars = ret.size
        out = np.full(n_bars, np.nan, dtype=np.float64)
        window = self._window

        for i in range(window, n_bars):
            if not np.isfinite(ret[i]):
                continue
            total = float(np.sum(volume[i - window + 1 : i + 1]))
            if total <= 0.0:
                continue
            out[i] = ret[i] / total

        return pd.Series(out, index=df.index, name=self.name)
