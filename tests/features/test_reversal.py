"""Tests for Reversal, including the mandated causal test."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.base import Feature
from features.reversal import Reversal
from tests.causality import assert_causal


def test_satisfies_feature_protocol() -> None:
    assert isinstance(Reversal(window=4), Feature)


def test_declares_contract_metadata() -> None:
    feature = Reversal(window=4)

    assert feature.name == "reversal_4"
    assert feature.version == 1
    assert feature.confirmation_lag_bars == 0
    assert feature.lookback_bars == 5
    assert feature.session_relative is False


def test_it_is_exactly_the_negated_log_return() -> None:
    """The honesty note in the module docstring, asserted.

    A linear combiner cannot distinguish this from ``log_return_4``. This test
    exists so nobody has to take that on trust when reading a result.
    """
    from features.log_return import LogReturn

    df = generate_ohlcv(n_bars=300, seed=5)

    np.testing.assert_array_equal(
        Reversal(window=4).compute(df).to_numpy(),
        -LogReturn(window=4).compute(df).to_numpy(),
    )


def test_matches_hand_computed_values() -> None:
    index = pd.date_range("2020-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame({"close": [100.0, 110.0, 121.0, 121.0]}, index=index)

    result = Reversal(window=2).compute(df)

    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(-np.log(121.0 / 100.0))
    assert result.iloc[3] == pytest.approx(-np.log(121.0 / 110.0))


def test_a_window_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="window must be at least 1"):
        Reversal(window=0)


def test_survives_truncation_at_every_bar() -> None:
    assert_causal(Reversal(window=4), generate_ohlcv(n_bars=260, seed=7))
