"""Tests for VolScaledReturn, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.base import Feature
from features.vol_scaled_return import VolScaledReturn
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(VolScaledReturn(window=120), Feature)


def test_declares_contract_metadata() -> None:
    feature = VolScaledReturn(window=120)

    assert feature.name == "vol_scaled_return_120"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 121
    assert feature.session_relative is False


def test_it_is_the_ratio_of_the_two_shipped_features() -> None:
    """Composition, not a second estimator. If it drifts, this fails."""
    from features.log_return import LogReturn
    from features.realized_vol import RealizedVol

    df = generate_ohlcv(n_bars=400, seed=3)
    ret = LogReturn(window=24).compute(df).to_numpy()
    vol = RealizedVol(window=24).compute(df).to_numpy()

    result = VolScaledReturn(window=24).compute(df).to_numpy()

    usable = np.isfinite(ret) & np.isfinite(vol) & (vol > 0.0)
    np.testing.assert_array_equal(result[usable], (ret / vol)[usable])
    assert np.isnan(result[~usable]).all()


def test_zero_volatility_returns_none_rather_than_a_substitute() -> None:
    """DATA_CONTRACT §6: missing propagates, it is not replaced."""
    index = pd.date_range("2020-01-01", periods=8, freq="h", tz="UTC")
    flat = pd.DataFrame({"close": [100.0] * 8}, index=index)

    result = VolScaledReturn(window=3).compute(flat)

    assert result.iloc[3:].isna().all()


def test_a_window_below_two_is_refused() -> None:
    with pytest.raises(ValueError, match="window must be at least 2"):
        VolScaledReturn(window=1)


def test_is_scale_free() -> None:
    df = generate_ohlcv(n_bars=300, seed=4)
    doubled = df.copy()
    for column in ("open", "high", "low", "close"):
        doubled[column] = doubled[column] * 2.0

    np.testing.assert_allclose(
        VolScaledReturn(window=24).compute(df).to_numpy(),
        VolScaledReturn(window=24).compute(doubled).to_numpy(),
        rtol=1e-12,
        equal_nan=True,
    )


def test_survives_truncation_at_every_bar() -> None:
    assert_causal(VolScaledReturn(window=24), generate_ohlcv(n_bars=300, seed=7))
