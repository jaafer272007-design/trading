"""Tests for the RealizedVol feature, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.base import Feature
from features.realized_vol import RealizedVol
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(RealizedVol(window=24), Feature)


def test_declares_contract_metadata() -> None:
    feature = RealizedVol(window=24)

    assert feature.name == "realized_vol_24"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 25


def test_matches_hand_computed_values() -> None:
    """Constant-ratio series: every one-bar log return is equal, so SD is 0."""
    index = pd.date_range("2020-01-01", periods=5, freq="h", tz="UTC")
    df = pd.DataFrame({"close": [100.0, 110.0, 121.0, 133.1, 146.41]}, index=index)

    result = RealizedVol(window=2).compute(df)

    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    np.testing.assert_allclose(result.iloc[2:].to_numpy(), 0.0, atol=1e-12)


def test_is_zero_only_for_constant_growth() -> None:
    df = generate_ohlcv(n_bars=200, seed=4)

    result = RealizedVol(window=24).compute(df)

    assert (result.dropna() > 0).all()


def test_is_scale_free() -> None:
    df = generate_ohlcv(n_bars=200, seed=3)
    scaled = df.copy()
    scaled[["open", "high", "low", "close"]] *= 2.0

    base = RealizedVol(window=24).compute(df)
    doubled = RealizedVol(window=24).compute(scaled)

    np.testing.assert_allclose(
        base.dropna().to_numpy(), doubled.dropna().to_numpy(), rtol=0, atol=1e-12
    )


def test_is_nan_before_warmup_and_defined_after() -> None:
    result = RealizedVol(window=24).compute(generate_ohlcv(n_bars=100, seed=1))

    assert result.iloc[:24].isna().all()
    assert result.iloc[24:].notna().all()


def test_rejects_window_below_two() -> None:
    with pytest.raises(ValueError, match="window"):
        RealizedVol(window=1)


def test_rejects_non_positive_price() -> None:
    df = generate_ohlcv(n_bars=50, seed=1)
    prices = df["close"].to_numpy(dtype="float64").copy()
    prices[10] = -1.0
    df["close"] = prices

    with pytest.raises(ValueError, match="strictly positive"):
        RealizedVol(window=24).compute(df)


# ---------------------------------------------------------------------------
# CLAUDE.md Hard Rule 1 — the mandated causal test
# ---------------------------------------------------------------------------


def test_is_causal() -> None:
    """Truncated-history equality. Failure trips K-2."""
    assert_causal(RealizedVol(window=24), generate_ohlcv(n_bars=600, seed=42))


def test_is_causal_across_multiple_seeds() -> None:
    for seed in range(5):
        assert_causal(RealizedVol(window=24), generate_ohlcv(n_bars=400, seed=seed))
