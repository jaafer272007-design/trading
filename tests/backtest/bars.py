"""Hand-built bars for the execution tests.

The lifecycle tests use bars written out by hand rather than generated, because
what they check is exact: which bar a stop fired on, what price it filled at,
whether an ambiguous bar resolved the unfavourable way. A random walk cannot be
asked those questions and answered reliably, and a test that tolerates a range
of answers would not notice the intrabar rule being inverted.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from backtest.execution import BarArrays

#: Monday, so bar 0 of a fixture is a weekly open unless a test says otherwise.
DEFAULT_START = "2021-06-07T00:00:00+00:00"


def bars_from(
    rows: Sequence[tuple[float, float, float]],
    *,
    start: str = DEFAULT_START,
    half_spread: float = 0.0,
) -> BarArrays:
    """Build :class:`~backtest.execution.BarArrays` from ``(open, high, low)``.

    Args:
        rows: One tuple per bar, in points.
        start: First bar's UTC timestamp.
        half_spread: Constant half-spread applied to every bar. Zero by default
            so a test that is not about spread reads levels literally.

    Returns:
        The arrays.
    """
    index = pd.date_range(start=start, periods=len(rows), freq="h", tz="UTC")
    return BarArrays(
        index=index,
        open=np.array([r[0] for r in rows], dtype=np.float64),
        high=np.array([r[1] for r in rows], dtype=np.float64),
        low=np.array([r[2] for r in rows], dtype=np.float64),
        half_spread=np.full(len(rows), half_spread, dtype=np.float64),
    )


def flat_bars(
    n: int,
    price: float = 200_000.0,
    *,
    start: str = DEFAULT_START,
    half_spread: float = 0.0,
) -> BarArrays:
    """``n`` bars that never move.

    Useful as padding after the bar a test cares about: the holding period must
    be able to run to its end without anything else happening.

    Args:
        n: Number of bars.
        price: Open, high and low, all equal.
        start: First bar's UTC timestamp.
        half_spread: Constant half-spread.

    Returns:
        The arrays.
    """
    return bars_from([(price, price, price)] * n, start=start, half_spread=half_spread)


def frame_from(bars: BarArrays, points_per_price_unit: float = 100.0) -> pd.DataFrame:
    """A price frame matching a :class:`BarArrays`, for sources that read one.

    Args:
        bars: The arrays.
        points_per_price_unit: Scale used when the arrays were built.

    Returns:
        A frame with ``open``/``high``/``low``/``close`` in price units.
    """
    return pd.DataFrame(
        {
            "open": bars.open / points_per_price_unit,
            "high": bars.high / points_per_price_unit,
            "low": bars.low / points_per_price_unit,
            "close": bars.open / points_per_price_unit,
        },
        index=bars.index,
    )
