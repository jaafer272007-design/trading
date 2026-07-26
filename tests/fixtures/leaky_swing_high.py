"""DELIBERATELY LEAKY NEGATIVE FIXTURE — never import this from ``src/``.

.. danger::

   **This feature is broken on purpose. It is not a candidate implementation,
   not a starting point, and not something to fix.**

   Its entire job is to fail ``tests/causality.py``. It exists so that the
   harness is pinned from both sides: ATR proves the harness can pass a clean
   feature, and this proves it can *catch a dirty one*. Without a fixture that
   must fail, a green causal suite is unfalsifiable — it would look identical
   whether the harness was working or silently returning "no violations".

   If this fixture ever passes the harness with its default declaration, the
   harness has stopped enforcing ``DATA_CONTRACT.md`` §1 and every causal
   result in the project is void until that is explained.

   It lives under ``tests/`` and must never become importable from ``src/``.
   ``tests/test_causality_harness.py`` asserts that containment.

The leak
--------

This computes an n-bar fractal swing high: bar ``T`` is a swing high when its
high is the maximum of the window ``[T - w, T + w]``. That window **extends
``w`` bars into the future**, so the value at ``T`` is not knowable until bar
``T + w`` — ``DATA_CONTRACT.md`` §2 registers exactly this feature at a
confirmation lag of ``n``.

By default this fixture declares ``confirmation_lag_bars = 0``, and that
mismatch *is* the bug. It is not a strawman. It is the most common way the
leak reaches production:

1. The pattern is drawn on a chart at the bar where the swing sits.
2. The implementation slices ``high[T - w : T + w + 1]`` to match the drawing.
3. NumPy silently clips that slice at the end of the array, so it never raises
   and never warns.
4. The feature is stamped at bar ``T``, where the eye expects it.

The result backtests beautifully, because at bar ``T`` the system is being
told which way the next ``w`` bars went.

Passing ``declared_lag=w`` turns this same arithmetic into a legitimate
feature, and the harness accepts it. The computation was never the problem —
the declaration was.
"""

import numpy as np
import pandas as pd

_REQUIRED_COLUMNS = ("high",)


class LeakySwingHigh:
    """An n-bar fractal swing high that peeks ``window`` bars forward.

    Args:
        window: Bars on each side of the candidate swing. The forward half is
            the leak.
        declared_lag: The confirmation lag this fixture *claims*. Defaults to
            ``0``, which is a lie by exactly ``window`` bars and is what makes
            this a negative fixture. Set it to ``window`` to obtain an honest
            declaration that the harness will accept.
    """

    def __init__(self, window: int = 3, declared_lag: int = 0) -> None:
        """Initialise the fixture.

        Raises:
            ValueError: If ``window`` is not positive.
        """
        if window <= 0:
            raise ValueError(f"window must be positive, got {window}")
        self._window = window
        self._declared_lag = declared_lag

    @property
    def name(self) -> str:
        """Stable identifier."""
        return "leaky_swing_high"

    @property
    def version(self) -> int:
        """Declaration version."""
        return 1

    @property
    def lookback_bars(self) -> int:
        """Bars of history behind the candidate bar."""
        return self._window + 1

    @property
    def confirmation_lag_bars(self) -> int:
        """The declared lag — deliberately understated by default."""
        return self._declared_lag

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the (leaky) swing-high flag.

        Args:
            df: Bar series with a ``high`` column.

        Returns:
            Series of ``1.0`` where the bar is a swing high, ``0.0`` where it
            is not, and ``NaN`` during warmup.

        Raises:
            ValueError: If the ``high`` column is absent.
        """
        missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"{self.name} requires columns {list(_REQUIRED_COLUMNS)}; "
                f"missing {missing}"
            )

        high = df["high"].to_numpy(dtype=np.float64)
        n_bars = len(high)
        out = np.full(n_bars, np.nan, dtype=np.float64)
        window = self._window

        for i in range(window, n_bars):
            start = i - window
            # THE LEAK. `i + window + 1` reaches past bar i, and NumPy clips
            # it to the end of the array without complaint. On full history
            # this reads bars the market had not printed yet at bar i; under
            # truncation those bars are gone and the answer changes. That
            # change is precisely what the harness detects.
            stop = min(i + window + 1, n_bars)
            out[i] = 1.0 if high[i] >= high[start:stop].max() else 0.0

        return pd.Series(out, index=df.index, name=self.name)
