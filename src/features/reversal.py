"""The negated short-horizon trailing log return.

``DATA_CONTRACT.md`` §7 declaration::

    name: reversal_<n>
    version: 1
    inputs: [ohlcv]
    lookback_bars: <n + 1>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [-inf, inf], null_allowed: true}
    null_semantics: "insufficient history for the trailing window"
    causal_test: tests/features/test_reversal.py
    revision_risk: none
    notes: "Sign-flipped LogReturn. See the honesty note below."

H-012 §B prior (4): short-horizon overreaction — liquidity provision after a
sharp move, documented intraday-to-daily in many markets. It is the opposite
prior to the momentum features, at a shorter scale, and it is present so that
the feature set is not a one-sided bet on persistence.

Stated plainly, because it would be misleading to leave implicit
-----------------------------------------------------------------

**A linear combiner cannot distinguish this from ``log_return_4``.** The sign
flip is absorbed by a free coefficient, so what the model sees is the 4-bar
return and nothing more. The name records a prior held by a human; it does not
add information the design matrix would otherwise lack.

What makes the momentum/reversal pair meaningful in H-012 is therefore the
**difference in scale** — 4 bars against 120 and 480 — not the sign. Anyone
reading a result should hold it to that weaker claim.
"""

from typing import Final

import numpy as np
import pandas as pd

from features.log_return import LogReturn


class Reversal:
    """Negative of the trailing ``window``-bar log return."""

    def __init__(self, window: int = 4) -> None:
        """Initialise the feature.

        Args:
            window: Bars spanned by the return.

        Raises:
            ValueError: If ``window`` is less than 1.
        """
        if window < 1:
            raise ValueError(f"window must be at least 1, got {window}")
        self._window: Final = window
        self._ret: Final = LogReturn(window=window)

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``reversal_4``."""
        return f"reversal_{self._window}"

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
        """Compute the negated trailing return.

        Args:
            df: Bar series with a ``close`` column.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`.
        """
        values = -self._ret.compute(df).to_numpy(dtype=np.float64)
        return pd.Series(
            np.asarray(values, dtype=np.float64), index=df.index, name=self.name
        )
