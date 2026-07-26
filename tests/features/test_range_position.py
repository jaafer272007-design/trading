"""Tests for the RangePosition feature, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.base import Feature
from features.range_position import RangePosition
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(RangePosition(window=48), Feature)


def test_declares_contract_metadata() -> None:
    feature = RangePosition(window=48)

    assert feature.name == "range_position_48"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 48


def test_matches_hand_computed_values() -> None:
    index = pd.date_range("2020-01-01", periods=3, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "high": [10.0, 12.0, 11.0],
            "low": [8.0, 9.0, 7.0],
            "close": [9.0, 11.0, 8.0],
        },
        index=index,
    )

    result = RangePosition(window=2).compute(df)

    # bar 1: range over bars 0-1 -> hi 12, lo 8, close 11 -> (11-8)/4 = 0.75
    # bar 2: range over bars 1-2 -> hi 12, lo 7, close 8  -> (8-7)/5  = 0.20
    expected = pd.Series([np.nan, 0.75, 0.2], index=index, name="range_position_2")
    pd.testing.assert_series_equal(result, expected, check_exact=True)


def test_is_bounded_in_unit_interval() -> None:
    result = RangePosition(window=48).compute(generate_ohlcv(n_bars=400, seed=6))
    defined = result.dropna()

    assert (defined >= 0.0).all()
    assert (defined <= 1.0).all()


def test_is_scale_free() -> None:
    df = generate_ohlcv(n_bars=300, seed=3)
    scaled = df.copy()
    scaled[["open", "high", "low", "close"]] *= 2.0

    base = RangePosition(window=48).compute(df)
    doubled = RangePosition(window=48).compute(scaled)

    np.testing.assert_allclose(
        base.dropna().to_numpy(), doubled.dropna().to_numpy(), rtol=0, atol=1e-12
    )


def test_degenerate_range_returns_null_not_a_midpoint() -> None:
    """DATA_CONTRACT §6: an undefined ratio propagates loudly.

    Substituting 0.5 for a zero-width range would be plausible-looking silent
    imputation — the exact failure mode §6 prohibits.
    """
    index = pd.date_range("2020-01-01", periods=3, freq="h", tz="UTC")
    flat = pd.DataFrame(
        {"high": [5.0, 5.0, 5.0], "low": [5.0, 5.0, 5.0], "close": [5.0, 5.0, 5.0]},
        index=index,
    )

    result = RangePosition(window=2).compute(flat)

    assert result.iloc[1:].isna().all()


def test_rejects_window_below_two() -> None:
    with pytest.raises(ValueError, match="window"):
        RangePosition(window=1)


def test_rejects_missing_column() -> None:
    df = generate_ohlcv(n_bars=100, seed=1).drop(columns=["high"])

    with pytest.raises(ValueError, match="high"):
        RangePosition(window=48).compute(df)


# ---------------------------------------------------------------------------
# CLAUDE.md Hard Rule 1 — the mandated causal test
# ---------------------------------------------------------------------------


def test_is_causal() -> None:
    """Truncated-history equality. Failure trips K-2."""
    assert_causal(RangePosition(window=48), generate_ohlcv(n_bars=600, seed=42))


def test_is_causal_across_multiple_seeds() -> None:
    for seed in range(5):
        assert_causal(RangePosition(window=48), generate_ohlcv(n_bars=400, seed=seed))
