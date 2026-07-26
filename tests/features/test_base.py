"""Tests for the Feature protocol declared in DATA_CONTRACT.md §7."""

import pandas as pd

from features.base import Feature


class _Complete:
    """A minimal object declaring every member the protocol requires."""

    name = "complete"
    version = 1
    lookback_bars = 1
    confirmation_lag_bars = 0

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(0.0, index=df.index, name=self.name)


class _MissingConfirmationLag:
    """Declares everything except the confirmation lag."""

    name = "missing_lag"
    version = 1
    lookback_bars = 1

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(0.0, index=df.index, name=self.name)


class _MissingCompute:
    """Declares the metadata but has no compute method."""

    name = "missing_compute"
    version = 1
    lookback_bars = 1
    confirmation_lag_bars = 0


def test_complete_declaration_satisfies_protocol() -> None:
    assert isinstance(_Complete(), Feature)


def test_missing_confirmation_lag_does_not_satisfy_protocol() -> None:
    """An undeclared lag must not silently pass as zero.

    DATA_CONTRACT §2: 'Any feature not in this table is prohibited until it is
    added with a declared lag.' Defaulting the lag is how the order-block leak
    gets into a pipeline unnoticed.
    """
    assert not isinstance(_MissingConfirmationLag(), Feature)


def test_missing_compute_does_not_satisfy_protocol() -> None:
    assert not isinstance(_MissingCompute(), Feature)
