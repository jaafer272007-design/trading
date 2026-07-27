"""The pipeline-wide causal gate named in DATA_CONTRACT.md §1.

    ``tests/test_causality.py`` recomputes every feature on history truncated
    at ``T`` and asserts bit-identical equality with the full-history value at
    ``T``. Runs on every commit. No exceptions, no skips, no ``xfail``.

This module is that file. It is also CI Tier 1 step 3
(``REPRODUCIBILITY.md`` §6) — a hard gate. Failure trips **K-2** and the
backtest is not permitted to run, because its output would be meaningless.

The harness itself is tested separately in ``tests/test_causality_harness.py``,
which pins it against a deliberately leaky fixture. This module is the
registry sweep: it answers "is every shipped feature causal?", not "does the
harness work?".
"""

import pkgutil

import pytest

import features
from data.synthetic import generate_ohlcv
from features.atr import ATR
from features.base import Feature
from features.log_return import LogReturn
from features.range_position import RangePosition
from features.realized_vol import RealizedVol
from tests.causality import assert_all_causal

SEEDS = (0, 1, 2)
"""Seeds swept. A result on one seed is a result about that seed."""

N_BARS = 600

FEATURE_REGISTRY: tuple[Feature, ...] = (
    ATR(period=14),
    LogReturn(window=24),
    RealizedVol(window=24),
    RangePosition(window=48),
)
"""Every feature that ships.

Adding a feature to ``src/features/`` without adding it here is caught by
``test_every_feature_module_is_registered`` below — an unswept feature is an
unenforced contract.
"""


def test_registry_is_not_empty() -> None:
    """A vacuous sweep must not be able to report success."""
    assert FEATURE_REGISTRY


def test_every_feature_module_is_registered() -> None:
    """No feature may ship without entering the causal sweep.

    DATA_CONTRACT §1 admits no exceptions and no skips. The cheapest way for
    a leak to enter this project is a new feature module that nobody added to
    the registry, so the registry is checked against the filesystem rather
    than trusted.
    """
    shipped = {
        module.name
        for module in pkgutil.iter_modules(features.__path__)
        if module.name != "base"
    }
    registered = {
        feature.name.rsplit("_", 1)[0] if feature.name[-1].isdigit() else feature.name
        for feature in FEATURE_REGISTRY
    }

    assert shipped == registered, (
        f"feature modules not in FEATURE_REGISTRY: {sorted(shipped - registered)}; "
        f"registered but no module: {sorted(registered - shipped)}"
    )


def test_no_registered_feature_is_session_relative_while_r001_is_open() -> None:
    """``REVIEW_ITEMS.md`` R-001, enforced rather than described.

    This feed's session structure changes twice inside H-006's window — the
    daily break is absent between 2017-10-07 and 2022-10-20 — so a feature
    reading the session open, the session close, position within the session,
    or bars until the break is measuring a different quantity on either side
    of 2017-10-07. The boundary dates have not been checked against any source
    outside this project.

    Both of those are reasons to wait. Neither is visible once such a feature
    is in a design matrix, which is why this is a test and not a note.
    """
    from data.review import ReviewItemError, assert_not_blocked_by

    offenders = [f.name for f in FEATURE_REGISTRY if f.session_relative]
    if not offenders:
        return
    with pytest.raises(ReviewItemError):
        assert_not_blocked_by("R-001", f"registering {offenders}")
    pytest.fail(
        f"session-relative features registered while R-001 is open: {offenders}. "
        f"Close the review item against an external source first — re-running "
        f"scripts/report_session_eras.py does not close it."
    )


def test_every_feature_declares_session_relativity() -> None:
    """It cannot be inferred, so it must be declared.

    A feature indexing off the calendar's session hours and one that does not
    are the same shape from the outside. Without the declaration the guard
    above is a check on nothing.
    """
    for feature in FEATURE_REGISTRY:
        assert isinstance(feature.session_relative, bool), feature.name


@pytest.mark.parametrize("seed", SEEDS)
def test_all_features_are_causal(seed: int) -> None:
    """DATA_CONTRACT §1. Failure trips K-2 — halt, do not work around."""
    assert_all_causal(FEATURE_REGISTRY, generate_ohlcv(n_bars=N_BARS, seed=seed))
