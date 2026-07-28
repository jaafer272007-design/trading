"""Tests for DrawdownFromMax, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.base import Feature
from features.drawdown_from_max import DrawdownFromMax
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(DrawdownFromMax(window=480), Feature)


def test_declares_contract_metadata() -> None:
    feature = DrawdownFromMax(window=480)

    assert feature.name == "drawdown_from_max_480"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 480
    assert feature.session_relative is False


def test_matches_hand_computed_values() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="h", tz="UTC")
    df = pd.DataFrame({"close": [100.0, 120.0, 90.0, 110.0, 60.0]}, index=index)

    result = DrawdownFromMax(window=3).compute(df)

    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx((120.0 - 90.0) / 120.0)
    assert result.iloc[3] == pytest.approx((120.0 - 110.0) / 120.0)
    assert result.iloc[4] == pytest.approx((110.0 - 60.0) / 110.0)


def test_is_zero_at_a_new_high() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="h", tz="UTC")
    rising = pd.DataFrame({"close": [10.0, 20.0, 30.0, 40.0, 50.0]}, index=index)

    result = DrawdownFromMax(window=3).compute(rising)

    assert (result.dropna() == 0.0).all()


def test_is_bounded_in_the_unit_interval() -> None:
    """It cannot act as a proxy for price level. That is the point."""
    values = (
        DrawdownFromMax(window=48).compute(generate_ohlcv(n_bars=600, seed=8)).dropna()
    )

    assert (values >= 0.0).all()
    assert (values < 1.0).all()


def test_is_scale_free() -> None:
    df = generate_ohlcv(n_bars=300, seed=4)
    doubled = df.copy()
    for column in ("open", "high", "low", "close"):
        doubled[column] = doubled[column] * 2.0

    np.testing.assert_allclose(
        DrawdownFromMax(window=48).compute(df).to_numpy(),
        DrawdownFromMax(window=48).compute(doubled).to_numpy(),
        rtol=1e-12,
        equal_nan=True,
    )


def test_a_non_positive_close_is_refused() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="h", tz="UTC")
    with pytest.raises(ValueError, match="strictly positive"):
        DrawdownFromMax(window=3).compute(
            pd.DataFrame({"close": [1.0, 0.0, 1.0, 1.0, 1.0]}, index=index)
        )


def test_survives_truncation_at_every_bar() -> None:
    assert_causal(DrawdownFromMax(window=48), generate_ohlcv(n_bars=300, seed=7))
