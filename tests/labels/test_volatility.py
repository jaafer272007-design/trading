"""Tests for the H-009 volatility label.

The load-bearing tests here are the last two sections. Everything above them
checks that the label computes what H-009 §B says it computes; those two check
that the *threshold* -- the one part of this module that makes a causal claim
-- cannot see the future, and that the check saying so is capable of failing.

``EVALUATION.md`` §14 is the reason the second of those exists. Three of the
five instrument defects this project has found had a self-check that agreed
with them because the check shared the defect's assumption. A truncation test
written from the same understanding as the code it tests is exactly that
shape, so it ships with a deliberately non-causal threshold it is required to
reject.
"""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.realized_vol import RealizedVol
from labels.volatility import (
    DEFAULT_THRESHOLD_WINDOW,
    DEFAULT_VOL_WINDOW,
    rolling_median,
    summarize_volatility,
    volatility_label,
    volatility_labels_for_snapshot,
    volatility_threshold,
)
from tests.causality import CausalityError, assert_causal

# Small windows keep the causal sweep cheap without changing the code path --
# rolling_median is window-agnostic. The registered windows get their own,
# slower sweep at the end.
SMALL_VOL = 3
SMALL_THRESHOLD = 5


def _frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(closes), freq="h", tz="UTC")
    return pd.DataFrame({"close": closes}, index=index)


# ---------------------------------------------------------------------------
# rolling_median -- trailing, inclusive, never partially filled
# ---------------------------------------------------------------------------


def test_the_median_window_ends_at_t_and_includes_it() -> None:
    values = np.array([5.0, 1.0, 3.0, 9.0, 7.0], dtype=np.float64)

    result = rolling_median(values, 3)

    # Position 2 sees [5, 1, 3] -> 3.  Position 3 sees [1, 3, 9] -> 3.
    # Position 4 sees [3, 9, 7] -> 7.  Positions 0-1 have no full window.
    assert np.isnan(result[0])
    assert np.isnan(result[1])
    assert result[2] == 3.0
    assert result[3] == 3.0
    assert result[4] == 7.0


def test_a_window_containing_a_nan_is_undefined_not_partially_filled() -> None:
    """DATA_CONTRACT §6: missing propagates, it is never worked around."""
    values = np.array([1.0, np.nan, 3.0, 4.0, 5.0], dtype=np.float64)

    result = rolling_median(values, 3)

    assert np.isnan(result[2]), "window [1, nan, 3] must not silently become 2.0"
    assert np.isnan(result[3]), "window [nan, 3, 4] likewise"
    assert result[4] == 4.0, "window [3, 4, 5] is clean and must produce a value"


def test_a_non_positive_median_window_is_refused() -> None:
    with pytest.raises(ValueError, match="window must be positive"):
        rolling_median(np.zeros(5), 0)


# ---------------------------------------------------------------------------
# The label itself
# ---------------------------------------------------------------------------


def test_the_forward_volatility_is_the_trailing_feature_read_horizon_bars_later() -> (
    None
):
    """H-009 §B's central identity, asserted rather than assumed.

    If this ever stops holding, the label is comparing the forward window
    against something that is not the forward window, and no other test in
    this file would notice.
    """
    df = generate_ohlcv(n_bars=300, seed=11)
    horizon = 24

    rv = RealizedVol(window=horizon).compute(df).to_numpy(dtype=np.float64)
    threshold = volatility_threshold(
        df, vol_window=horizon, threshold_window=SMALL_THRESHOLD
    ).to_numpy(dtype=np.float64)
    labels = volatility_label(
        df,
        horizon=horizon,
        vol_window=horizon,
        threshold_window=SMALL_THRESHOLD,
    ).to_numpy(dtype=np.float64)

    defined = np.flatnonzero(~np.isnan(labels))
    assert defined.size > 100
    expected = (rv[defined + horizon] > threshold[defined]).astype(np.float64)
    assert np.array_equal(labels[defined], expected)


def test_the_trailing_and_forward_windows_share_no_returns() -> None:
    """The disjointness claim in H-009 §B, checked on the indices.

    ``rv[T]`` is built from returns indexed ``T-w+1 .. T``; ``rv[T+w]`` from
    ``T+1 .. T+w``. A one-bar overlap would put a shared return on both sides
    of the comparison and manufacture correlation.
    """
    window = 24
    trailing = set(range(0 - window + 1, 0 + 1))
    forward = set(range(0 + 1, 0 + window + 1))

    assert trailing.isdisjoint(forward)
    assert max(trailing) + 1 == min(forward)


def test_an_exact_tie_resolves_to_zero() -> None:
    """Strict '>', stated because it is an asymmetry in the base rate."""
    # A perfectly periodic series makes every volatility estimate identical,
    # so forward volatility equals the trailing median exactly.
    closes = [100.0 + (2.0 if i % 2 else 0.0) for i in range(40)]

    labels = volatility_label(
        _frame(closes), horizon=4, vol_window=4, threshold_window=SMALL_THRESHOLD
    )

    defined = labels.dropna()
    assert len(defined) > 5
    assert (defined == 0.0).all(), "every tie must resolve to 0, not to 1"


def test_labels_are_binary() -> None:
    labels = volatility_label(
        generate_ohlcv(n_bars=500, seed=2),
        horizon=24,
        vol_window=24,
        threshold_window=SMALL_THRESHOLD,
    )

    assert set(np.unique(labels.dropna().to_numpy())) <= {0.0, 1.0}


def test_the_final_horizon_rows_are_null_not_imputed() -> None:
    labels = volatility_label(
        generate_ohlcv(n_bars=400, seed=1),
        horizon=24,
        vol_window=SMALL_VOL,
        threshold_window=SMALL_THRESHOLD,
    )

    assert labels.iloc[-24:].isna().all()


def test_rows_without_enough_trailing_history_are_null() -> None:
    """The threshold's own warmup, which is longer than any feature's."""
    labels = volatility_label(
        generate_ohlcv(n_bars=400, seed=1),
        horizon=24,
        vol_window=SMALL_VOL,
        threshold_window=SMALL_THRESHOLD,
    )

    # rv is defined from bar SMALL_VOL; the median needs SMALL_THRESHOLD of
    # them, so the first defined threshold sits at SMALL_VOL + SMALL_THRESHOLD - 1.
    first_defined = SMALL_VOL + SMALL_THRESHOLD - 1
    assert labels.iloc[:first_defined].isna().all()
    assert not np.isnan(labels.iloc[first_defined])


def test_rejects_non_positive_horizon_and_missing_close() -> None:
    with pytest.raises(ValueError, match="horizon must be positive"):
        volatility_label(_frame([1.0, 2.0]), horizon=0)
    with pytest.raises(ValueError, match="close"):
        volatility_label(generate_ohlcv(n_bars=50, seed=1).drop(columns=["close"]))


# ---------------------------------------------------------------------------
# Validity -- the label reads in both directions, so both must be gated
# ---------------------------------------------------------------------------


def test_a_forward_window_spanning_an_invalid_bar_makes_the_label_undefined() -> None:
    n = 60
    frame = pd.DataFrame(
        {
            "close": np.linspace(100.0, 160.0, n),
            "valid": np.ones(n, dtype=bool),
        }
    )
    frame.loc[40, "valid"] = False

    labels = volatility_label(
        frame, horizon=4, vol_window=SMALL_VOL, threshold_window=SMALL_THRESHOLD
    ).to_numpy()

    # The forward window is [T, T+4] inclusive, so bars 36..40 all touch it.
    for position in (36, 37, 38, 39, 40):
        assert np.isnan(labels[position]), f"bar {position} reads the invalid bar"


def test_a_backward_span_touching_an_invalid_bar_makes_the_label_undefined() -> None:
    """The gate that is easy to omit, because nothing about it is visible.

    The threshold at ``T`` reaches back ``threshold_window + vol_window`` bars.
    A median taken across a hole is not missing and not flagged -- it is a
    median over two sides of a gap and looks like every other value.
    """
    n = 80
    frame = pd.DataFrame(
        {
            "close": np.linspace(100.0, 180.0, n),
            "valid": np.ones(n, dtype=bool),
        }
    )
    frame.loc[30, "valid"] = False

    labels = volatility_label(
        frame, horizon=4, vol_window=SMALL_VOL, threshold_window=SMALL_THRESHOLD
    ).to_numpy()

    span = SMALL_THRESHOLD + SMALL_VOL
    # Backward span at T is [T - span + 1, T], so bars 30 .. 30 + span - 1
    # all read the hole.
    for position in range(30, 30 + span):
        assert np.isnan(labels[position]), f"bar {position} reads back over the hole"
    assert not np.isnan(labels[30 + span]), "the invalidation must not spread further"


def test_the_validity_gate_costs_nothing_when_every_bar_is_valid() -> None:
    """The negative control: a validity column that is all True changes nothing."""
    n = 120
    close = np.linspace(100.0, 220.0, n)
    without = volatility_label(
        pd.DataFrame({"close": close}),
        horizon=4,
        vol_window=SMALL_VOL,
        threshold_window=SMALL_THRESHOLD,
    ).to_numpy()
    with_valid = volatility_label(
        pd.DataFrame({"close": close, "valid": np.ones(n, dtype=bool)}),
        horizon=4,
        vol_window=SMALL_VOL,
        threshold_window=SMALL_THRESHOLD,
    ).to_numpy()

    assert np.array_equal(without, with_valid, equal_nan=True)


def test_the_evaluation_entry_point_refuses_a_frame_with_no_validity() -> None:
    with pytest.raises(ValueError, match="requires a 'valid' column"):
        volatility_labels_for_snapshot(pd.DataFrame({"close": np.arange(2000.0)}))


def test_the_label_module_is_not_in_the_feature_registry() -> None:
    """A label looks forward by design and must never be swept as a feature."""
    from tests.test_causality import FEATURE_REGISTRY

    assert all("vol_above_median" not in f.name for f in FEATURE_REGISTRY)


def test_the_tie_rate_and_base_rate_share_a_denominator() -> None:
    df = generate_ohlcv(n_bars=600, seed=5)
    labels = volatility_label(
        df, horizon=24, vol_window=24, threshold_window=SMALL_THRESHOLD
    )

    summary = summarize_volatility(
        labels, df, horizon=24, vol_window=24, threshold_window=SMALL_THRESHOLD
    )

    assert summary.n_total == 600
    assert summary.n_defined == int(labels.notna().sum())
    assert 0.0 <= summary.base_rate <= 1.0
    assert summary.backward_span_bars == SMALL_THRESHOLD + 24


# ---------------------------------------------------------------------------
# The threshold is causal -- swept by the real harness, not by a bespoke check
# ---------------------------------------------------------------------------


class _ThresholdAsFeature:
    """Adapter letting ``tests/causality.py`` sweep the threshold directly.

    The threshold is not a feature and must never be registered as one -- it
    is a component of a forward-looking label. But its causal claim is
    identical in kind to a feature's, so it is checked by the same harness
    rather than by a second implementation of the same idea written here.
    """

    def __init__(self, vol_window: int, threshold_window: int) -> None:
        self._vol_window = vol_window
        self._threshold_window = threshold_window

    @property
    def name(self) -> str:
        return f"vol_median_{self._threshold_window}"

    @property
    def version(self) -> int:
        return 1

    @property
    def lookback_bars(self) -> int:
        return self._threshold_window + self._vol_window

    @property
    def confirmation_lag_bars(self) -> int:
        return 0

    @property
    def session_relative(self) -> bool:
        return False

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return volatility_threshold(
            df,
            vol_window=self._vol_window,
            threshold_window=self._threshold_window,
        )


def test_the_threshold_survives_truncation_at_every_bar() -> None:
    """DATA_CONTRACT §1 on the threshold, at test-sized windows."""
    assert_causal(
        _ThresholdAsFeature(SMALL_VOL, SMALL_THRESHOLD),
        generate_ohlcv(n_bars=260, seed=7),
    )


def test_the_threshold_survives_truncation_at_the_registered_windows() -> None:
    """The same sweep at the values H-009 actually runs.

    Slower, and run anyway: a causal property verified only at toy windows is
    a property of the toy windows. The registered configuration is the one
    that produces a result.
    """
    assert_causal(
        _ThresholdAsFeature(DEFAULT_VOL_WINDOW, DEFAULT_THRESHOLD_WINDOW),
        generate_ohlcv(
            n_bars=DEFAULT_THRESHOLD_WINDOW + DEFAULT_VOL_WINDOW + 220, seed=8
        ),
    )


# ---------------------------------------------------------------------------
# The adversarial fixture -- EVALUATION.md §14
# ---------------------------------------------------------------------------


def _centred_median(
    values: np.ndarray,
    window: int,
) -> np.ndarray:
    """Deliberately non-causal: the window is centred on ``T``, not trailing.

    This is the mistake the check above exists to catch, and it is the one a
    reader would make by reaching for a symmetric smoother. It is written here
    and nowhere near ``src/``.
    """
    half = window // 2
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(half, n - half):
        chunk = values[i - half : i + half + 1]
        if np.isnan(chunk).any():
            continue
        out[i] = float(np.median(chunk))
    return out


class _CentredThresholdAsFeature(_ThresholdAsFeature):
    """The same adapter over a threshold that reads bars after ``T``."""

    def compute(self, df: pd.DataFrame) -> pd.Series:
        rv = RealizedVol(window=self._vol_window).compute(df).to_numpy(dtype=np.float64)
        return pd.Series(
            _centred_median(rv, self._threshold_window),
            index=df.index,
            name=self.name,
        )


def test_a_centred_threshold_is_rejected_by_the_same_check() -> None:
    """The fixture that makes the test above mean something.

    A gate that has never fired is indistinguishable from a gate that cannot
    (``REPRODUCIBILITY.md`` §10). If this ever stops raising, the passing
    causality test above is no longer evidence of anything.
    """
    with pytest.raises(CausalityError) as excinfo:
        assert_causal(
            _CentredThresholdAsFeature(SMALL_VOL, SMALL_THRESHOLD),
            generate_ohlcv(n_bars=260, seed=7),
        )

    assert "FAIL" in str(excinfo.value)
