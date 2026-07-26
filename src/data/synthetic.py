"""Deterministic synthetic OHLCV generator.

.. warning::

   **This is not a market model, and no result computed on it is evidence of
   anything.**

   It exists for exactly one reason: to give the causal test harness
   (``tests/causality.py``) a reproducible bar series to truncate and
   recompute against. It is scaffolding for testing the *plumbing*, not the
   *strategy*.

   Concretely, this generator is a Gaussian random walk with no drift
   regimes, no volatility clustering, no session structure, no gaps, no
   microstructure, no fat tails, and no autocorrelation. Real gold does all
   of those things. Any backtest, edge estimate, calibration curve, or
   "it works on synthetic data" claim derived from this module is
   **inadmissible** — ``RESEARCH.md`` §4 Tier 4, and it is not promotable to
   any higher tier by any amount of additional analysis.

   The only properties this module promises are the ones the harness relies
   on: bit-level determinism under a fixed seed, prefix stability under
   truncation, and internally consistent OHLC bars.

Conventions, per ``DATA_CONTRACT.md`` §4:

- All timestamps are timezone-aware UTC.
- Bar timestamps are **open-time**.
"""

from typing import Final

import numpy as np
import pandas as pd

# Number of independent normal draws consumed per bar. Randomness is drawn as
# a single (n_bars, _DRAWS_PER_BAR) block so that row `i` always maps to flat
# draws [i * k, (i + 1) * k). That is what makes generating 300 bars produce a
# bit-identical prefix of generating 600 bars — a property the causal harness
# depends on to distinguish a real leak from generator drift.
_DRAWS_PER_BAR: Final = 4

_COLUMNS: Final = ["open", "high", "low", "close", "volume"]


def generate_ohlcv(
    n_bars: int,
    seed: int,
    *,
    start_price: float = 2000.0,
    bar_freq: str = "h",
    start_utc: str = "2020-01-01T00:00:00",
    volatility: float = 0.002,
) -> pd.DataFrame:
    """Generate a deterministic synthetic OHLCV frame.

    Args:
        n_bars: Number of bars to generate. Must be positive.
        seed: Seed for the PRNG. Identical seeds yield bit-identical frames.
        start_price: Opening price of the first bar.
        bar_freq: Pandas offset alias for the bar interval.
        start_utc: Naive ISO-8601 timestamp of the first bar's open, localised
            to UTC.
        volatility: Per-bar standard deviation of log returns.

    Returns:
        A frame indexed by timezone-aware UTC open-time timestamps, with
        columns ``open``, ``high``, ``low``, ``close``, ``volume`` and no
        missing values.

    Raises:
        ValueError: If ``n_bars`` is not positive.
    """
    if n_bars <= 0:
        raise ValueError(f"n_bars must be positive, got {n_bars}")

    rng = np.random.default_rng(seed)
    draws = rng.standard_normal((n_bars, _DRAWS_PER_BAR))

    # Column 0 drives the close-to-close log return; the walk is cumulative,
    # so bar i depends only on draws 0..i and the series is prefix-stable.
    log_returns = draws[:, 0] * volatility
    close = start_price * np.exp(np.cumsum(log_returns))

    # Open of bar i is the close of bar i-1: a continuous series with no
    # synthetic gaps. Gaps are a real market phenomenon this module
    # deliberately does not model.
    open_ = np.empty(n_bars, dtype=np.float64)
    open_[0] = start_price
    open_[1:] = close[:-1]

    # Wick extensions are half-normal, so they are non-negative by
    # construction and the OHLC invariants hold without any clipping pass
    # that could mask a generation bug.
    body_high = np.maximum(open_, close)
    body_low = np.minimum(open_, close)
    high = body_high + np.abs(draws[:, 1]) * volatility * start_price
    low = body_low - np.abs(draws[:, 2]) * volatility * start_price

    # Log-normal volume: strictly positive without a floor or clip.
    volume = np.exp(draws[:, 3]) * 1_000.0

    index = pd.date_range(
        start=pd.Timestamp(start_utc, tz="UTC"),
        periods=n_bars,
        freq=bar_freq,
        name="timestamp",
    )

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
        columns=_COLUMNS,
    )
