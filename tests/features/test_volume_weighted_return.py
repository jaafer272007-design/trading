"""Tests for VolumeWeightedReturn, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.base import Feature
from features.volume_weighted_return import VolumeWeightedReturn
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(VolumeWeightedReturn(window=24), Feature)


def test_declares_contract_metadata() -> None:
    feature = VolumeWeightedReturn(window=24)

    assert feature.name == "volume_weighted_return_24"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 25
    assert feature.session_relative is False


def test_matches_hand_computed_values() -> None:
    index = pd.date_range("2020-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"close": [100.0, 110.0, 121.0, 121.0], "tick_volume": [5.0, 10.0, 20.0, 40.0]},
        index=index,
    )

    result = VolumeWeightedReturn(window=2).compute(df)

    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(np.log(121.0 / 100.0) / 30.0)
    assert result.iloc[3] == pytest.approx(np.log(121.0 / 110.0) / 60.0)


def test_a_missing_volume_column_is_refused_not_substituted() -> None:
    """No silent fallback. EVALUATION.md §14 — the fluent wrong answer."""
    index = pd.date_range("2020-01-01", periods=5, freq="h", tz="UTC")
    df = pd.DataFrame({"close": [1.0] * 5, "volume": [1.0] * 5}, index=index)

    with pytest.raises(ValueError, match="requires a 'tick_volume' column"):
        VolumeWeightedReturn(window=2).compute(df)


def test_zero_trailing_volume_returns_none() -> None:
    index = pd.date_range("2020-01-01", periods=6, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0], "tick_volume": [0.0] * 6},
        index=index,
    )

    assert VolumeWeightedReturn(window=2).compute(df).isna().all()


def test_negative_volume_is_refused() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"close": [1.0] * 5, "tick_volume": [1.0, -1.0, 1.0, 1.0, 1.0]}, index=index
    )

    with pytest.raises(ValueError, match="negative tick volume"):
        VolumeWeightedReturn(window=2).compute(df)


def test_a_window_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="window must be at least 1"):
        VolumeWeightedReturn(window=0)


def test_survives_truncation_at_every_bar() -> None:
    assert_causal(VolumeWeightedReturn(window=24), generate_ohlcv(n_bars=300, seed=7))
