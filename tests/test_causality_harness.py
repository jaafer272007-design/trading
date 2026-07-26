"""Acceptance tests for the causal harness itself.

A harness that only ever passes is worthless — it would report a green
pipeline whether or not the pipeline leaked. These tests pin it from both
sides: it must pass a genuinely causal feature (ATR) and it must fail a
feature that peeks forward (``leaky_swing_high``).

The leaky fixture is the load-bearing test in this repository. If it ever
starts passing, the harness has stopped enforcing ``DATA_CONTRACT.md`` §1 and
every downstream causal result is void.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.atr import ATR
from tests.causality import (
    CausalityError,
    InsufficientHistoryError,
    assert_causal,
    check_causality,
)
from tests.fixtures.leaky_swing_high import LeakySwingHigh

MIN_SWEEP = 200


@pytest.fixture
def df() -> pd.DataFrame:
    return generate_ohlcv(n_bars=600, seed=42)


# ---------------------------------------------------------------------------
# The two required directions
# ---------------------------------------------------------------------------


def test_harness_passes_clean_atr_feature(df: pd.DataFrame) -> None:
    report = check_causality(ATR(period=14), df, min_bars_tested=MIN_SWEEP)

    assert report.passed, report.summary()
    assert report.violations == ()


def test_harness_fails_leaky_swing_high(df: pd.DataFrame) -> None:
    """The whole point. A forward-peeking feature must be caught."""
    report = check_causality(LeakySwingHigh(window=3), df, min_bars_tested=MIN_SWEEP)

    assert not report.passed
    assert report.violations, "leaky feature produced no violations"


def test_assert_causal_is_silent_for_atr(df: pd.DataFrame) -> None:
    assert_causal(ATR(period=14), df, min_bars_tested=MIN_SWEEP)


def test_assert_causal_raises_for_leaky_swing_high(df: pd.DataFrame) -> None:
    with pytest.raises(CausalityError, match="leaky_swing_high"):
        assert_causal(LeakySwingHigh(window=3), df, min_bars_tested=MIN_SWEEP)


# ---------------------------------------------------------------------------
# Sweep width — DATA_CONTRACT §1 enforcement is only as good as its coverage
# ---------------------------------------------------------------------------


def test_sweep_covers_at_least_the_requested_bars(df: pd.DataFrame) -> None:
    report = check_causality(ATR(period=14), df, min_bars_tested=MIN_SWEEP)

    assert report.bars_tested >= MIN_SWEEP


def test_harness_refuses_to_run_a_sweep_it_cannot_cover() -> None:
    """A short sweep must be an error, never a quiet pass.

    Silently testing 4 bars and reporting green is how a harness becomes
    decoration.
    """
    short = generate_ohlcv(n_bars=40, seed=1)

    with pytest.raises(InsufficientHistoryError):
        check_causality(ATR(period=14), short, min_bars_tested=MIN_SWEEP)


# ---------------------------------------------------------------------------
# confirmation_lag_bars is what is actually being enforced
# ---------------------------------------------------------------------------


def test_same_computation_passes_when_its_lag_is_declared_honestly(
    df: pd.DataFrame,
) -> None:
    """Identical arithmetic, honest declaration — the harness must accept it.

    ``LeakySwingHigh`` needs ``window`` bars of confirmation. Declaring that
    lag makes it a legitimate structural feature under ``DATA_CONTRACT.md``
    §2, which registers the n-bar fractal swing at lag ``n``. This is the
    control that proves the harness is enforcing the *declaration*, not merely
    disliking the computation.
    """
    honest = LeakySwingHigh(window=3, declared_lag=3)

    report = check_causality(honest, df, min_bars_tested=MIN_SWEEP)

    assert report.passed, report.summary()


def test_understating_the_lag_by_one_bar_is_still_caught(df: pd.DataFrame) -> None:
    """One bar is enough. DATA_CONTRACT §4 says so, and it is right."""
    understated = LeakySwingHigh(window=3, declared_lag=2)

    report = check_causality(understated, df, min_bars_tested=MIN_SWEEP)

    assert not report.passed


# ---------------------------------------------------------------------------
# Comparison semantics
# ---------------------------------------------------------------------------


class _ConstantFeature:
    """Emits a fixed series regardless of history length."""

    name = "constant"
    version = 1
    lookback_bars = 1
    confirmation_lag_bars = 0

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index, name=self.name)


class _NullsOnlyWhenTruncated:
    """Returns a value on long history and NaN on short history.

    This is the polite failure mode of a leaky feature: rather than returning
    a different number once it can see forward, it declines to answer until it
    can. That is still a leak — the value at ``T`` changed when future bars
    arrived — and the harness must treat it as one.
    """

    name = "nulls_when_truncated"
    version = 1
    lookback_bars = 1
    confirmation_lag_bars = 0

    def __init__(self, full_length: int) -> None:
        self._full_length = full_length

    def compute(self, df: pd.DataFrame) -> pd.Series:
        value = 1.0 if len(df) == self._full_length else np.nan
        return pd.Series(value, index=df.index, name=self.name)


def test_constant_feature_passes(df: pd.DataFrame) -> None:
    report = check_causality(_ConstantFeature(), df, min_bars_tested=MIN_SWEEP)

    assert report.passed, report.summary()


def test_nan_appearing_only_under_truncation_is_a_violation(
    df: pd.DataFrame,
) -> None:
    feature = _NullsOnlyWhenTruncated(full_length=len(df))

    report = check_causality(feature, df, min_bars_tested=MIN_SWEEP)

    assert not report.passed


def test_report_summary_names_the_feature_and_violation_count(
    df: pd.DataFrame,
) -> None:
    report = check_causality(LeakySwingHigh(window=3), df, min_bars_tested=MIN_SWEEP)

    summary = report.summary()

    assert "leaky_swing_high" in summary
    assert str(len(report.violations)) in summary


# ---------------------------------------------------------------------------
# Containment: the leaky fixture must never reach the pipeline
# ---------------------------------------------------------------------------


def test_leaky_fixture_is_not_reachable_from_src() -> None:
    """The negative fixture lives in tests/ and stays there."""
    src = Path(__file__).resolve().parent.parent / "src"
    offenders = [
        path
        for path in src.rglob("*.py")
        if "leaky_swing_high" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_leaky_fixture_module_does_not_live_under_src() -> None:
    src = Path(__file__).resolve().parent.parent / "src"

    assert list(src.rglob("leaky_swing_high.py")) == []
