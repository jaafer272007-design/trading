"""Tests for the direction label."""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from labels.direction import direction_label, labels_for_snapshot, summarize


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


# ---------------------------------------------------------------------------
# The validity gate — H-001 registers the label as undefined where the forward
# window spans an invalid bar. The module was written without this, which was
# invisible on synthetic bars because they have none.
# ---------------------------------------------------------------------------


def test_a_label_whose_forward_window_spans_an_invalid_bar_is_undefined() -> None:
    """The clause that was missing.

    Bar 10 is invalid. The label's window is ``[T, T+H]`` inclusive — it reads
    the close at both ends — so with H=3 every label from bar 7 to bar 10
    touches the bad bar, not just the one sitting on it. Bar 6's window ends
    at 9 and is unaffected.
    """
    n = 20
    frame = pd.DataFrame(
        {
            "close": np.arange(1.0, n + 1.0),
            "valid": np.ones(n, dtype=bool),
        }
    )
    frame.loc[10, "valid"] = False

    labels = direction_label(frame, horizon=3).to_numpy()
    undefined = set(np.flatnonzero(np.isnan(labels)).tolist())

    assert {7, 8, 9, 10}.issubset(undefined), sorted(undefined)
    assert not np.isnan(labels[6]), "bar 6's window is [6, 9] and misses the hole"
    assert not np.isnan(labels[11]), "bar 11 is past the hole"
    # And the invalidation is bounded — it does not spread beyond the window.
    assert 6 not in undefined
    assert 11 not in undefined


def test_the_gate_costs_nothing_when_every_bar_is_valid() -> None:
    """The negative control: validity present and all True changes nothing."""
    n = 40
    close = np.linspace(100.0, 140.0, n)
    without = direction_label(pd.DataFrame({"close": close}), horizon=5).to_numpy()
    with_valid = direction_label(
        pd.DataFrame({"close": close, "valid": np.ones(n, dtype=bool)}), horizon=5
    ).to_numpy()
    assert np.array_equal(without, with_valid, equal_nan=True)


def test_the_evaluation_entry_point_refuses_a_frame_with_no_validity() -> None:
    """A caller who has to remember will eventually not.

    ``direction_label`` tolerates a frame with no ``valid`` column because
    synthetic fixtures legitimately have none. The path that produces a
    *result* must not inherit that tolerance.
    """
    with pytest.raises(ValueError, match="requires a 'valid' column"):
        labels_for_snapshot(pd.DataFrame({"close": np.arange(50.0)}))


def test_the_evaluation_entry_point_accepts_a_snapshot_frame() -> None:
    n = 60
    frame = pd.DataFrame(
        {"close": np.linspace(100.0, 160.0, n), "valid": np.ones(n, dtype=bool)}
    )
    labels = labels_for_snapshot(frame, horizon=24)
    assert labels.notna().sum() == n - 24


def test_the_tie_rate_and_base_rate_share_a_denominator() -> None:
    """Two rates printed side by side must describe the same population.

    Ties were counted over every row with forward data, including rows whose
    label is undefined. With the validity gate those two populations differ.
    """
    n = 20
    frame = pd.DataFrame(
        {
            "close": np.full(n, 100.0),  # every comparison is a tie
            "valid": np.ones(n, dtype=bool),
        }
    )
    frame.loc[10, "valid"] = False

    labels = direction_label(frame, horizon=3)
    summary = summarize(labels, frame, horizon=3)

    assert summary.n_ties == summary.n_defined
    assert summary.tie_rate == 1.0
    assert summary.base_rate == 0.0, "every tie resolves to 0, so no label is positive"
