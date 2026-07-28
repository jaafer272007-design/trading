"""Tests for AtrDistance, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.atr_distance import AtrDistance
from features.base import Feature
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(AtrDistance(window=480), Feature)


def test_declares_contract_metadata() -> None:
    feature = AtrDistance(window=480, atr_period=14)

    assert feature.name == "atr_distance_480"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 480
    assert feature.session_relative is False


def test_matches_a_hand_computed_window() -> None:
    from features.atr import ATR

    df = generate_ohlcv(n_bars=200, seed=6)
    close = df["close"].to_numpy(dtype=np.float64)
    atr = ATR(period=14).compute(df).to_numpy()

    result = AtrDistance(window=20, atr_period=14).compute(df).to_numpy()

    i = 150
    expected = (close[i] - float(np.sum(close[i - 19 : i + 1])) / 20) / atr[i]
    assert result[i] == pytest.approx(expected, rel=0, abs=1e-15)


def test_is_scale_free() -> None:
    """Both numerator and denominator are prices, so doubling cancels."""
    df = generate_ohlcv(n_bars=300, seed=4)
    doubled = df.copy()
    for column in ("open", "high", "low", "close"):
        doubled[column] = doubled[column] * 2.0

    np.testing.assert_allclose(
        AtrDistance(window=48).compute(df).to_numpy(),
        AtrDistance(window=48).compute(doubled).to_numpy(),
        rtol=1e-12,
        equal_nan=True,
    )


def test_zero_atr_returns_none() -> None:
    index = pd.date_range("2020-01-01", periods=40, freq="h", tz="UTC")
    flat = pd.DataFrame(
        {
            "open": [100.0] * 40,
            "high": [100.0] * 40,
            "low": [100.0] * 40,
            "close": [100.0] * 40,
        },
        index=index,
    )

    assert AtrDistance(window=20, atr_period=14).compute(flat).isna().all()


def test_a_missing_close_is_refused() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="h", tz="UTC")
    with pytest.raises(ValueError, match="requires a close column"):
        AtrDistance(window=3).compute(pd.DataFrame({"high": [1.0] * 5}, index=index))


def test_bad_windows_are_refused() -> None:
    with pytest.raises(ValueError, match="window must be at least 2"):
        AtrDistance(window=1)
    with pytest.raises(ValueError, match="atr_period must be at least 1"):
        AtrDistance(window=10, atr_period=0)


def test_survives_truncation_at_every_bar() -> None:
    assert_causal(AtrDistance(window=48), generate_ohlcv(n_bars=300, seed=7))
