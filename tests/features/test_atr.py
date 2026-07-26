"""Tests for the ATR reference feature.

The causal test mandated by CLAUDE.md Hard Rule 1 lives at the bottom of this
module; the tests above it pin down ATR's arithmetic so that a causal-test
failure can be attributed to a temporal bug rather than a broken formula.
"""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.atr import ATR
from features.base import Feature
from tests.causality import assert_causal


@pytest.fixture
def hand_frame() -> pd.DataFrame:
    """A four-bar frame with hand-computable Wilder ATR(2).

    ===  ====  ====  =====  ==========  =========
    bar  high   low  close  TR          ATR(2)
    ===  ====  ====  =====  ==========  =========
    0      10     8      9  NaN         NaN
    1      11     9     10  2           NaN
    2      12    10     11  2           2.0
    3      10     7      8  4           3.0
    ===  ====  ====  =====  ==========  =========

    TR[0] is NaN because bar 0 has no previous close. ATR seeds at bar 2 with
    the simple mean of TR[1:3], then applies Wilder smoothing.
    """
    index = pd.date_range("2020-01-01", periods=4, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "open": [9.0, 10.0, 11.0, 9.0],
            "high": [10.0, 11.0, 12.0, 10.0],
            "low": [8.0, 9.0, 10.0, 7.0],
            "close": [9.0, 10.0, 11.0, 8.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )


def test_atr_satisfies_feature_protocol() -> None:
    assert isinstance(ATR(period=14), Feature)


def test_atr_declares_contract_metadata() -> None:
    """DATA_CONTRACT §2 lists ATR(n) as knowable at bar T — lag 0."""
    atr = ATR(period=14)

    assert atr.name == "atr_14"
    assert atr.version == 1
    assert atr.confirmation_lag_bars == 0
    assert atr.lookback_bars == 15


def test_atr_matches_hand_computed_values(hand_frame: pd.DataFrame) -> None:
    result = ATR(period=2).compute(hand_frame)

    expected = pd.Series(
        [np.nan, np.nan, 2.0, 3.0],
        index=hand_frame.index,
        name="atr_2",
    )
    pd.testing.assert_series_equal(result, expected, check_exact=True)


def test_atr_is_nan_before_warmup_and_defined_after() -> None:
    df = generate_ohlcv(n_bars=100, seed=1)
    result = ATR(period=14).compute(df)

    assert result.iloc[:14].isna().all()
    assert result.iloc[14:].notna().all()


def test_atr_is_strictly_positive_once_defined() -> None:
    df = generate_ohlcv(n_bars=300, seed=2)
    result = ATR(period=14).compute(df)

    assert (result.dropna() > 0).all()


def test_atr_returns_all_nan_when_history_is_shorter_than_lookback() -> None:
    """DATA_CONTRACT §6: insufficient history propagates loudly, never a guess."""
    df = generate_ohlcv(n_bars=5, seed=1)
    result = ATR(period=14).compute(df)

    assert len(result) == 5
    assert result.isna().all()


def test_atr_rejects_non_positive_period() -> None:
    with pytest.raises(ValueError, match="period"):
        ATR(period=0)


def test_atr_rejects_frame_missing_required_columns() -> None:
    df = generate_ohlcv(n_bars=50, seed=1).drop(columns=["low"])

    with pytest.raises(ValueError, match="low"):
        ATR(period=14).compute(df)


# ---------------------------------------------------------------------------
# CLAUDE.md Hard Rule 1 — the mandated causal test
# ---------------------------------------------------------------------------


def test_atr_is_causal() -> None:
    """Truncated-history equality, per CLAUDE.md Hard Rule 1.

    Failure trips K-2 (EVALUATION.md §1): halt, fix, no further runs.
    """
    assert_causal(ATR(period=14), generate_ohlcv(n_bars=600, seed=42))


def test_atr_is_causal_across_multiple_seeds() -> None:
    """One seed is a finding about that seed (REPRODUCIBILITY.md §3)."""
    for seed in range(5):
        assert_causal(ATR(period=14), generate_ohlcv(n_bars=400, seed=seed))


def test_atr_is_causal_across_periods() -> None:
    for period in (2, 5, 14, 50):
        assert_causal(ATR(period=period), generate_ohlcv(n_bars=600, seed=9))
