"""Tests for the direction label."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from labels.direction import direction_label, summarize


def _frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(closes), freq="h", tz="UTC")
    return pd.DataFrame({"close": closes}, index=index)


def test_matches_hand_computed_values() -> None:
    df = _frame([100.0, 101.0, 99.0, 100.0, 100.0])

    result = direction_label(df, horizon=2)

    # T0: close[2]=99  vs 100 -> down -> 0
    # T1: close[3]=100 vs 101 -> down -> 0
    # T2: close[4]=100 vs 99  -> up   -> 1
    # T3, T4: no forward bar -> NaN
    expected = pd.Series(
        [0.0, 0.0, 1.0, np.nan, np.nan], index=df.index, name="direction_2"
    )
    pd.testing.assert_series_equal(result, expected, check_exact=True)


def test_exact_tie_resolves_to_zero() -> None:
    """The tie rule is stated, not implicit — it shifts the base rate."""
    df = _frame([100.0, 50.0, 100.0])

    result = direction_label(df, horizon=2)

    assert result.iloc[0] == 0.0


def test_final_horizon_rows_are_null_not_imputed() -> None:
    """DATA_CONTRACT §6: no forward data means no label, never a guess."""
    df = generate_ohlcv(n_bars=100, seed=1)

    result = direction_label(df, horizon=24)

    assert result.iloc[-24:].isna().all()
    assert result.iloc[:-24].notna().all()


def test_labels_are_binary() -> None:
    result = direction_label(generate_ohlcv(n_bars=500, seed=2), horizon=24)

    assert set(np.unique(result.dropna().to_numpy())) <= {0.0, 1.0}


def test_summary_reports_base_rate_and_tie_rate() -> None:
    df = generate_ohlcv(n_bars=1000, seed=3)
    labels = direction_label(df, horizon=24)

    summary = summarize(labels, df, horizon=24)

    assert summary.n_total == 1000
    assert summary.n_defined == 976
    assert 0.0 <= summary.base_rate <= 1.0
    assert summary.tie_rate == 0.0  # continuous synthetic prices never tie


def test_rejects_non_positive_horizon() -> None:
    with pytest.raises(ValueError, match="horizon"):
        direction_label(_frame([1.0, 2.0]), horizon=0)


def test_rejects_missing_close() -> None:
    df = generate_ohlcv(n_bars=50, seed=1).drop(columns=["close"])

    with pytest.raises(ValueError, match="close"):
        direction_label(df)


def test_label_module_is_not_in_the_feature_registry() -> None:
    """A label looks forward by design and must never be swept as a feature.

    If it were registered, tests/test_causality.py would correctly fail it —
    which is the right outcome, but the containment should be structural.
    """
    from tests.test_causality import FEATURE_REGISTRY

    assert all("direction" not in f.name for f in FEATURE_REGISTRY)
