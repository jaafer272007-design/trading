"""Average True Range (Wilder) — the clean reference feature.

ATR is the reference implementation the causal harness is calibrated against:
it is genuinely causal, so the harness must pass it. Paired with the
deliberately leaky negative fixture under ``tests/fixtures/``, it pins the
harness from both sides — a harness that only ever passes proves nothing.

That fixture is named only from ``tests/``, never from here: nothing under
``src/`` may reference it even in prose, so that the containment check in
``tests/test_causality_harness.py`` can stay a blunt substring scan rather
than a parser that a dynamic import could slip past.

``DATA_CONTRACT.md`` §7 declaration::

    name: atr_<period>
    version: 1
    inputs: [ohlcv]
    lookback_bars: <period + 1>
    confirmation_lag_bars: 0
    timezone: UTC
    returns: {type: float, range: [0.0, inf], null_allowed: true}
    null_semantics: "insufficient history for the Wilder seed"
    causal_test: tests/features/test_atr.py
    revision_risk: none
    notes: "Wilder smoothing is a prefix-stable recursion; see _compute_ordering."

``DATA_CONTRACT.md`` §2 lists ATR(n) as defined at bar ``T`` and knowable at
bar ``T`` — confirmation lag 0.
"""

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

_REQUIRED_COLUMNS: Final = ("high", "low", "close")


class ATR:
    """Wilder's Average True Range over a fixed period.

    Definition, with ``p`` the period:

    - ``TR[0]`` is ``NaN``: bar 0 has no previous close, so true range is
      undefined there. It is left null rather than degraded to ``high - low``,
      because a plausible-looking substitute is exactly the silent imputation
      ``DATA_CONTRACT.md`` §6 prohibits.
    - ``TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|,
      |low[i] - close[i-1]|)`` for ``i >= 1``.
    - ``ATR[p] = mean(TR[1..p])`` — the Wilder seed.
    - ``ATR[i] = (ATR[i-1] * (p - 1) + TR[i]) / p`` for ``i > p``.

    Every value therefore depends only on bars at or before its own index, so
    the confirmation lag is 0.
    """

    def __init__(self, period: int = 14) -> None:
        """Initialise the feature.

        Args:
            period: Wilder smoothing period. Must be positive.

        Raises:
            ValueError: If ``period`` is not positive.
        """
        if period <= 0:
            raise ValueError(f"period must be positive, got {period}")
        self._period: Final = period

    @property
    def name(self) -> str:
        """Stable identifier, e.g. ``atr_14``."""
        return f"atr_{self._period}"

    @property
    def version(self) -> int:
        """Declaration version."""
        return 1

    @property
    def lookback_bars(self) -> int:
        """Bars required before the first value.

        The seed needs ``TR[1..period]``, which spans bars ``0..period`` —
        ``period + 1`` bars in total.
        """
        return self._period + 1

    @property
    def confirmation_lag_bars(self) -> int:
        """Zero: ATR at bar ``T`` is knowable at the close of bar ``T``."""
        return 0

    @property
    def session_relative(self) -> bool:
        """Reads no session boundary — only a rolling window of bars.

        Returns:
            False.
        """
        return False

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute ATR over ``df``.

        Args:
            df: Bar series with ``high``, ``low`` and ``close`` columns.

        Returns:
            Series aligned to ``df.index``, named :attr:`name`, holding
            ``NaN`` for the first ``period`` positions.

        Raises:
            ValueError: If a required column is absent.
        """
        missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"{self.name} requires columns {list(_REQUIRED_COLUMNS)}; "
                f"missing {missing}"
            )

        n_bars = len(df)
        out = np.full(n_bars, np.nan, dtype=np.float64)

        # Fewer bars than the lookback: every position is genuinely not
        # computable. Return all-null rather than a partial seed.
        if n_bars >= self.lookback_bars:
            high = df["high"].to_numpy(dtype=np.float64)
            low = df["low"].to_numpy(dtype=np.float64)
            close = df["close"].to_numpy(dtype=np.float64)
            self._fill_wilder(out, high, low, close)

        return pd.Series(out, index=df.index, name=self.name)

    def _fill_wilder(
        self,
        out: npt.NDArray[np.float64],
        high: npt.NDArray[np.float64],
        low: npt.NDArray[np.float64],
        close: npt.NDArray[np.float64],
    ) -> None:
        """Fill ``out`` in place with the Wilder recursion.

        The arithmetic is written as an explicit scalar loop, not a vectorised
        reduction, and this is deliberate. Bit-exactness under truncation
        (``REPRODUCIBILITY.md`` §1, Tier A) requires that the floating-point
        operations reaching index ``i`` be the *same operations in the same
        order* whether the frame ends at ``i`` or 500 bars later. A left-to-
        right scalar recursion guarantees that by construction. Vectorised
        rolling reductions do not: pandas' rolling mean carries a running
        accumulator whose error depends on where the array starts, and
        pairwise summation changes its association tree with array length.
        Either would produce last-bit differences that the harness would
        correctly, and uselessly, report as leaks.

        Args:
            out: Output buffer, pre-filled with ``NaN``.
            high: High prices.
            low: Low prices.
            close: Close prices.
        """
        period = self._period
        n_bars = len(out)

        # True range. Index 0 stays NaN — no previous close exists.
        true_range = np.full(n_bars, np.nan, dtype=np.float64)
        for i in range(1, n_bars):
            prev_close = close[i - 1]
            true_range[i] = max(
                high[i] - low[i],
                abs(high[i] - prev_close),
                abs(low[i] - prev_close),
            )

        # Wilder seed: simple mean of the first `period` true ranges,
        # accumulated left to right.
        total = np.float64(0.0)
        for i in range(1, period + 1):
            total += true_range[i]
        out[period] = total / period

        for i in range(period + 1, n_bars):
            out[i] = (out[i - 1] * (period - 1) + true_range[i]) / period
