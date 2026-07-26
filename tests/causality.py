"""The causal test harness — enforcement of ``DATA_CONTRACT.md`` §1.

    A feature computed at bar ``T`` may use only information that was
    observable at or before the close of bar ``T``.

The harness verifies that claim the only way it can be verified: by taking the
information away. For each bar ``T`` in a sweep, it recomputes the feature on
history truncated just after ``T`` and asserts the value at ``T`` is
bit-identical to the value the full-history computation produced there. A
feature that quietly consulted bar ``T+5`` cannot reproduce itself once bar
``T+5`` is gone.

Failure trips **K-2** (``EVALUATION.md`` §1): halt, fix, no further runs. This
module is deliberately unforgiving — there is no tolerance parameter, no
``rtol``, and no skip list, because every one of those is a place a leak could
hide.

What ``confirmation_lag_bars`` means here
-----------------------------------------

A feature declaring lag ``L`` is claiming its value at bar ``T`` becomes
knowable at the close of bar ``T + L``. The harness holds it to exactly that:
the value at ``T`` must be reproducible from ``df.iloc[: T + L + 1]``.

- ``L = 0`` is the strict §1 rule: the value at ``T`` must survive truncation
  at ``T``.
- ``L > 0`` grants precisely ``L`` bars of confirmation and not one more,
  matching the registry in ``DATA_CONTRACT.md`` §2 (n-bar fractal swing: ``n``;
  FVG: 2; order block: variable and explicit).

The harness therefore checks the *declaration*, not the computation. It cannot
tell you that a declared lag of 20 is dishonest for a feature that only needs
3 — that judgement belongs to review against the §2 registry, which is
normative. What the harness guarantees is that a feature never gets to use
more history than it declared.

Equality semantics
------------------

"Bit-identical" is meant literally:

- Two ``NaN`` values compare equal. Both mean "not computable", which is a
  legitimate and stable answer under ``DATA_CONTRACT.md`` §6.
- A ``NaN`` against a number is a **violation**, in either direction. This is
  the load-bearing case: a leaky feature that politely declines to answer
  until it can see forward has still changed its answer when future data
  arrived, and that is exactly the thing being tested for.
- Two numbers are compared as raw IEEE-754 float64 bit patterns, so ``0.0``
  and ``-0.0`` are *not* equal. A sign-of-zero flip means the arithmetic took
  a different path depending on how much history was present, which is a
  determinism defect worth surfacing even when it is numerically harmless
  (``REPRODUCIBILITY.md`` §1, Tier A).
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from features.base import Feature

DEFAULT_MIN_BARS_TESTED = 200
"""Minimum sweep width.

Chosen so a sweep spans enough bars that a leak has to be systematic to hide.
A handful of spot checks can pass on a feature that leaks only when a pattern
completes.
"""


class CausalityError(AssertionError):
    """Raised when a feature fails the causal test. Trips K-2."""


class InsufficientHistoryError(ValueError):
    """Raised when the frame cannot support the requested sweep width.

    Deliberately an error rather than a shrunken sweep: a harness that
    quietly tests four bars and reports success is worse than no harness,
    because it is believed.
    """


class FeatureOutputError(ValueError):
    """Raised when a feature returns a series that violates its own contract."""


@dataclass(frozen=True, slots=True)
class CausalViolation:
    """A single bar where truncation changed the answer."""

    bar_index: int
    timestamp: pd.Timestamp
    truncated_at: int
    full_history_value: float
    truncated_value: float

    def describe(self) -> str:
        """Render a one-line human-readable description."""
        return (
            f"bar {self.bar_index} ({self.timestamp.isoformat()}): "
            f"full-history={self.full_history_value!r} but "
            f"recomputed-on-{self.truncated_at}-bars={self.truncated_value!r}"
        )


@dataclass(frozen=True, slots=True)
class CausalReport:
    """Result of a causal sweep over one feature."""

    feature_name: str
    feature_version: int
    confirmation_lag_bars: int
    bars_tested: int
    first_bar_tested: int
    last_bar_tested: int
    violations: tuple[CausalViolation, ...]

    @property
    def passed(self) -> bool:
        """True when no bar changed under truncation."""
        return not self.violations

    def summary(self, max_examples: int = 5) -> str:
        """Render a report suitable for a CI log or an assertion message.

        Args:
            max_examples: Number of individual violations to show in full.

        Returns:
            A multi-line summary naming the feature, the sweep, and the
            violations.
        """
        verdict = "PASS" if self.passed else "FAIL — K-2"
        lines = [
            f"causal test {verdict}: {self.feature_name} "
            f"(v{self.feature_version}, "
            f"confirmation_lag_bars={self.confirmation_lag_bars})",
            f"  swept {self.bars_tested} bars "
            f"[{self.first_bar_tested}..{self.last_bar_tested}]",
            f"  violations: {len(self.violations)}",
        ]
        for violation in self.violations[:max_examples]:
            lines.append(f"    {violation.describe()}")
        remaining = len(self.violations) - max_examples
        if remaining > 0:
            lines.append(f"    ... and {remaining} more")
        return "\n".join(lines)


def _bitwise_equal(left: float, right: float) -> bool:
    """Compare two float64 values by bit pattern, treating NaN as equal to NaN.

    Args:
        left: First value.
        right: Second value.

    Returns:
        True when the values are indistinguishable at the bit level, or when
        both are NaN.
    """
    # Self-comparison is the NaN test: NaN is the only value unequal to itself.
    left_is_nan = left != left
    right_is_nan = right != right
    if left_is_nan or right_is_nan:
        return left_is_nan and right_is_nan
    return struct.pack("<d", left) == struct.pack("<d", right)


def _validate_output(
    result: pd.Series,
    frame: pd.DataFrame,
    feature: Feature,
) -> None:
    """Check that a feature's output obeys the shape contract.

    Args:
        result: The series the feature returned.
        frame: The frame it was computed on.
        feature: The feature under test.

    Raises:
        FeatureOutputError: If the series is misaligned or not float-typed.
    """
    if not isinstance(result, pd.Series):
        raise FeatureOutputError(
            f"{feature.name}.compute must return a pd.Series, "
            f"got {type(result).__name__}"
        )
    if len(result) != len(frame):
        raise FeatureOutputError(
            f"{feature.name}.compute returned {len(result)} values for "
            f"{len(frame)} bars; output must align to the input index"
        )
    if not result.index.equals(frame.index):
        raise FeatureOutputError(
            f"{feature.name}.compute returned a series whose index does not "
            f"match the input frame"
        )
    # A NumPy-backed float dtype specifically, not merely a float-like one.
    # Pandas' nullable Float64 stores missing values as pd.NA rather than a
    # NaN bit pattern, so it cannot be compared bitwise and does not carry the
    # NaN semantics the harness relies on to detect a polite leak.
    dtype = result.dtype
    if not isinstance(dtype, np.dtype) or not np.issubdtype(dtype, np.floating):
        raise FeatureOutputError(
            f"{feature.name}.compute must return a NumPy floating dtype so "
            f"that 'not computable' is representable as NaN "
            f"(DATA_CONTRACT.md §6); got {dtype}"
        )


def _sweep_bounds(
    feature: Feature,
    n_bars: int,
    min_bars_tested: int,
) -> tuple[int, int]:
    """Compute the inclusive range of bar indices eligible for testing.

    A bar ``T`` is eligible when the feature can produce a value there
    (``T >= lookback_bars - 1``) and when the frame is long enough to supply
    the declared confirmation window (``T + confirmation_lag_bars <=
    n_bars - 1``).

    Args:
        feature: The feature under test.
        n_bars: Length of the full frame.
        min_bars_tested: Required sweep width.

    Returns:
        The inclusive ``(first, last)`` bar indices to sweep.

    Raises:
        InsufficientHistoryError: If fewer than ``min_bars_tested`` bars are
            eligible.
    """
    first = max(feature.lookback_bars - 1, 0)
    last = n_bars - 1 - feature.confirmation_lag_bars
    eligible = last - first + 1

    if eligible < min_bars_tested:
        raise InsufficientHistoryError(
            f"{feature.name}: only {max(eligible, 0)} bars are eligible for "
            f"the causal sweep (frame has {n_bars} bars, "
            f"lookback_bars={feature.lookback_bars}, "
            f"confirmation_lag_bars={feature.confirmation_lag_bars}), "
            f"but {min_bars_tested} were requested. Supply a longer frame — "
            f"do not lower the sweep width."
        )
    return first, last


def check_causality(
    feature: Feature,
    df: pd.DataFrame,
    *,
    min_bars_tested: int = DEFAULT_MIN_BARS_TESTED,
) -> CausalReport:
    """Sweep a feature for temporal leakage and report every violation.

    For each eligible bar ``T``, recomputes ``feature`` on
    ``df.iloc[: T + confirmation_lag_bars + 1]`` and compares the value at
    ``T`` with the full-history value at ``T``.

    Args:
        feature: The feature under test.
        df: Full-history bar series.
        min_bars_tested: Minimum number of bars the sweep must cover.

    Returns:
        A :class:`CausalReport` listing every bar whose value changed.

    Raises:
        ValueError: If the feature declares a negative confirmation lag or a
            non-positive lookback.
        InsufficientHistoryError: If the frame is too short for the sweep.
        FeatureOutputError: If the feature returns a malformed series.
    """
    lag = feature.confirmation_lag_bars
    if lag < 0:
        raise ValueError(
            f"{feature.name}: confirmation_lag_bars must be non-negative, got {lag}"
        )
    if feature.lookback_bars < 1:
        raise ValueError(
            f"{feature.name}: lookback_bars must be at least 1, "
            f"got {feature.lookback_bars}"
        )

    first, last = _sweep_bounds(feature, len(df), min_bars_tested)

    full = feature.compute(df)
    _validate_output(full, df, feature)
    full_values = full.to_numpy(dtype=np.float64)

    violations: list[CausalViolation] = []
    for bar in range(first, last + 1):
        truncated_at = bar + lag + 1
        window = df.iloc[:truncated_at]
        recomputed = feature.compute(window)
        _validate_output(recomputed, window, feature)

        full_value = float(full_values[bar])
        truncated_value = float(recomputed.to_numpy(dtype=np.float64)[bar])

        if not _bitwise_equal(full_value, truncated_value):
            violations.append(
                CausalViolation(
                    bar_index=bar,
                    timestamp=df.index[bar],
                    truncated_at=truncated_at,
                    full_history_value=full_value,
                    truncated_value=truncated_value,
                )
            )

    return CausalReport(
        feature_name=feature.name,
        feature_version=feature.version,
        confirmation_lag_bars=lag,
        bars_tested=last - first + 1,
        first_bar_tested=first,
        last_bar_tested=last,
        violations=tuple(violations),
    )


def assert_causal(
    feature: Feature,
    df: pd.DataFrame,
    *,
    min_bars_tested: int = DEFAULT_MIN_BARS_TESTED,
) -> None:
    """Assert a feature is causal, raising with a full report if it is not.

    Args:
        feature: The feature under test.
        df: Full-history bar series.
        min_bars_tested: Minimum number of bars the sweep must cover.

    Raises:
        CausalityError: If any bar changed under truncation. Trips K-2.
    """
    report = check_causality(feature, df, min_bars_tested=min_bars_tested)
    if not report.passed:
        raise CausalityError(report.summary())


def assert_all_causal(
    features: Sequence[Feature],
    df: pd.DataFrame,
    *,
    min_bars_tested: int = DEFAULT_MIN_BARS_TESTED,
) -> None:
    """Assert every feature in ``features`` is causal.

    Reports all failing features together rather than stopping at the first,
    so a leakage audit needs one run rather than n.

    Args:
        features: Features under test.
        df: Full-history bar series.
        min_bars_tested: Minimum number of bars each sweep must cover.

    Raises:
        CausalityError: If any feature failed. Trips K-2.
    """
    failures = [
        report
        for report in (
            check_causality(feature, df, min_bars_tested=min_bars_tested)
            for feature in features
        )
        if not report.passed
    ]
    if failures:
        raise CausalityError("\n".join(report.summary() for report in failures))
