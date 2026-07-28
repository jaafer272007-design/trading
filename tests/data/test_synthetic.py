"""Tests for the synthetic OHLCV generator.

The generator is test scaffolding, not a market model. These tests assert the
two properties the causal harness actually depends on: bit-level determinism
under a fixed seed, and internally consistent OHLC bars.
"""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv


def test_same_seed_produces_bit_identical_frames() -> None:
    a = generate_ohlcv(n_bars=300, seed=42)
    b = generate_ohlcv(n_bars=300, seed=42)

    pd.testing.assert_frame_equal(a, b, check_exact=True)


def test_different_seed_produces_different_prices() -> None:
    a = generate_ohlcv(n_bars=300, seed=42)
    b = generate_ohlcv(n_bars=300, seed=43)

    assert not np.array_equal(a["close"].to_numpy(), b["close"].to_numpy())


def test_prefix_of_longer_run_is_identical_to_shorter_run() -> None:
    """Truncation must be a pure prefix.

    The causal harness truncates history and recomputes. If generating 300
    bars did not yield the same first 300 bars as generating 600, every
    harness failure would be ambiguous between a real leak and generator
    drift.
    """
    short = generate_ohlcv(n_bars=300, seed=7)
    long = generate_ohlcv(n_bars=600, seed=7)

    pd.testing.assert_frame_equal(short, long.iloc[:300], check_exact=True)


def test_ohlc_bars_are_internally_consistent() -> None:
    df = generate_ohlcv(n_bars=500, seed=11)

    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert (df["high"] >= df["low"]).all()


def test_volume_is_strictly_positive() -> None:
    df = generate_ohlcv(n_bars=500, seed=11)

    assert (df["volume"] > 0).all()


def test_index_is_utc_and_strictly_increasing() -> None:
    df = generate_ohlcv(n_bars=200, seed=3)

    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is not None
    assert str(df.index.tz) == "UTC"
    assert df.index.is_monotonic_increasing
    assert df.index.is_unique


def test_columns_are_exactly_ohlcv_in_order() -> None:
    df = generate_ohlcv(n_bars=50, seed=1)

    assert list(df.columns) == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "tick_volume",
    ]


def test_tick_volume_is_an_exact_copy_of_volume() -> None:
    """The claim that adding it consumed no PRNG draw, made checkable.

    ``tick_volume`` exists so H-012's volume feature can read the column name
    the real feed uses without falling back to a substitute. If it were ever
    given its own draw, every OHLC value downstream would shift and the
    recorded K-1 sensitivity baseline measured on this generator would stop
    describing the data it was measured on.
    """
    df = generate_ohlcv(n_bars=200, seed=1)

    np.testing.assert_array_equal(
        df["tick_volume"].to_numpy(), df["volume"].to_numpy()
    )


def test_contains_no_missing_values() -> None:
    """DATA_CONTRACT §6: nothing is silently imputed.

    The generator must emit complete bars, so that any NaN appearing
    downstream is unambiguously a feature signalling 'not computable'.
    """
    df = generate_ohlcv(n_bars=500, seed=5)

    assert not df.isna().to_numpy().any()


def test_rejects_non_positive_bar_count() -> None:
    with pytest.raises(ValueError, match="n_bars"):
        generate_ohlcv(n_bars=0, seed=1)
