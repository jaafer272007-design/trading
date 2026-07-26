"""Tests for the LogReturn feature, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.base import Feature
from features.log_return import LogReturn
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(LogReturn(window=24), Feature)


def test_declares_contract_metadata() -> None:
    feature = LogReturn(window=24)

    assert feature.name == "log_return_24"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 25


def test_matches_hand_computed_values() -> None:
    index = pd.date_range("2020-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"close": [100.0, 110.0, 121.0, 121.0]},
        index=index,
    )

    result = LogReturn(window=2).compute(df)

    expected = pd.Series(
        [np.nan, np.nan, np.log(121.0 / 100.0), np.log(121.0 / 110.0)],
        index=index,
        name="log_return_2",
    )
    pd.testing.assert_series_equal(result, expected, check_exact=True)


def test_is_scale_free() -> None:
    """Doubling every price must not change the feature.

    A combiner fed absolute price levels has to learn a coefficient that
    drifts with the level of the series; a ratio does not.
    """
    df = generate_ohlcv(n_bars=200, seed=3)
    scaled = df.copy()
    scaled[["open", "high", "low", "close"]] *= 2.0

    base = LogReturn(window=24).compute(df)
    doubled = LogReturn(window=24).compute(scaled)

    np.testing.assert_allclose(
        base.dropna().to_numpy(), doubled.dropna().to_numpy(), rtol=0, atol=1e-12
    )


def test_is_nan_before_warmup_and_defined_after() -> None:
    result = LogReturn(window=24).compute(generate_ohlcv(n_bars=100, seed=1))

    assert result.iloc[:24].isna().all()
    assert result.iloc[24:].notna().all()


def test_rejects_non_positive_window() -> None:
    with pytest.raises(ValueError, match="window"):
        LogReturn(window=0)


def test_rejects_missing_close_column() -> None:
    df = generate_ohlcv(n_bars=50, seed=1).drop(columns=["close"])

    with pytest.raises(ValueError, match="close"):
        LogReturn(window=24).compute(df)


def test_rejects_non_positive_price() -> None:
    """A non-positive price is a data defect, not something to clip."""
    df = generate_ohlcv(n_bars=50, seed=1)
    prices = df["close"].to_numpy(dtype="float64").copy()
    prices[10] = 0.0
    df["close"] = prices

    with pytest.raises(ValueError, match="strictly positive"):
        LogReturn(window=24).compute(df)


# ---------------------------------------------------------------------------
# CLAUDE.md Hard Rule 1 — the mandated causal test
# ---------------------------------------------------------------------------


def test_is_causal() -> None:
    """Truncated-history equality. Failure trips K-2."""
    assert_causal(LogReturn(window=24), generate_ohlcv(n_bars=600, seed=42))


def test_is_causal_across_multiple_seeds() -> None:
    for seed in range(5):
        assert_causal(LogReturn(window=24), generate_ohlcv(n_bars=400, seed=seed))
