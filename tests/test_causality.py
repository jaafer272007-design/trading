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
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import features
from data.synthetic import generate_ohlcv
from features.atr import ATR
from features.atr_distance import AtrDistance
from features.base import Feature
from features.drawdown_from_max import DrawdownFromMax
from features.log_return import LogReturn
from features.range_position import RangePosition
from features.realized_vol import RealizedVol
from features.reversal import Reversal
from features.vol_scaled_return import VolScaledReturn
from features.volume_weighted_return import VolumeWeightedReturn
from tests.causality import DEFAULT_MIN_BARS_TESTED, assert_causal

SEEDS = (0, 1, 2)
"""Seeds swept. A result on one seed is a result about that seed."""

N_BARS = 700
"""Frame length for the whole-registry checks that are not the causal sweep.

The sweep itself sizes its frame per feature — see :func:`_sweep_frame`. One
global length has to satisfy the longest-lookback feature, which makes every
short-lookback feature pay for it: at 1,400 bars the sweep cost 161 s of a
223 s suite, against a Tier 1 budget of five minutes.
"""

FEATURE_REGISTRY: tuple[Feature, ...] = (
    ATR(period=14),
    LogReturn(window=24),
    RealizedVol(window=24),
    RangePosition(window=48),
    # H-012 §B — seven priors. `log_return_120` and `log_return_480` reuse the
    # LogReturn class at other windows and need no new module.
    LogReturn(window=120),
    LogReturn(window=480),
    VolScaledReturn(window=120),
    Reversal(window=4),
    AtrDistance(window=480, atr_period=14),
    DrawdownFromMax(window=480),
    VolumeWeightedReturn(window=24),
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


def test_a_feature_declaring_no_session_relativity_ignores_the_index() -> None:
    """Falsifies the declaration instead of trusting it.

    ``session_relative`` is a claim a feature makes about itself, and R-001
    turns that claim into a gate. A claim nobody can check is not worth
    gating on.

    The check: recompute on a frame whose index has been replaced with an
    arbitrary monotonic one — irregular spacing, a different timezone,
    different weekdays, no session structure of any kind — and require
    bit-identical output. A feature that reads the clock cannot survive that;
    one that only walks a positional window cannot notice it.

    This is not the causal test and does not replace it. Causality is about
    *which bars* a feature reads; this is about whether it reads anything
    other than bars at all.
    """
    frame = generate_ohlcv(n_bars=N_BARS, seed=0)
    scrambled = frame.copy()
    scrambled.index = pd.DatetimeIndex(
        pd.Timestamp("1999-01-04 03:17", tz="Australia/Eucla")
        + pd.to_timedelta(np.cumsum(np.arange(1, len(frame) + 1) % 7 + 1), unit="h")
    )

    for feature in FEATURE_REGISTRY:
        if feature.session_relative:
            continue
        original = feature.compute(frame).to_numpy()
        relabelled = feature.compute(scrambled).to_numpy()
        assert np.array_equal(original, relabelled, equal_nan=True), (
            f"{feature.name} declares session_relative=False but its output "
            f"changed when only the index changed. Either it reads the clock — "
            f"in which case the declaration is wrong and R-001 blocks it — or "
            f"it has an index-dependent bug."
        )


def test_no_feature_module_mentions_the_calendar() -> None:
    """A second, blunter angle on the same claim.

    The test above would miss a feature whose clock-reading happens to make no
    difference on this particular fixture. This one cannot be fooled that way,
    and is cheap: a feature that imports the calendar or reads an hour is
    session-relative whether or not a 600-bar sample shows it.
    """
    forbidden = ("data.calendar", "data.invariants", "ZoneInfo", "tz_convert")
    for path in sorted(Path(features.__path__[0]).glob("*.py")):
        if path.name == "base.py":
            continue
        body = path.read_text(encoding="utf-8")
        hits = [token for token in forbidden if token in body]
        assert not hits, (
            f"{path.name} references {hits}. A feature reaching for the "
            f"calendar is session-relative; declare it and read REVIEW_ITEMS.md "
            f"R-001 before registering it."
        )


def _sweep_frame(feature: Feature, seed: int) -> pd.DataFrame:
    """A frame exactly long enough for the full sweep width on this feature.

    ``DEFAULT_MIN_BARS_TESTED`` bars must be eligible, and a bar is eligible
    once the feature can produce a value there and the frame can supply the
    declared confirmation window. Sizing per feature keeps the sweep width at
    exactly that number for every feature — the guarantee is unchanged — while
    not making a 4-bar feature walk a frame sized for a 480-bar one.

    Args:
        feature: The feature about to be swept.
        seed: Synthetic data seed.

    Returns:
        The frame.
    """
    n_bars = (
        feature.lookback_bars
        - 1
        + DEFAULT_MIN_BARS_TESTED
        + feature.confirmation_lag_bars
    )
    return generate_ohlcv(n_bars=n_bars, seed=seed)


@pytest.mark.parametrize("seed", SEEDS)
def test_all_features_are_causal(seed: int) -> None:
    """DATA_CONTRACT §1. Failure trips K-2 — halt, do not work around."""
    for feature in FEATURE_REGISTRY:
        assert_causal(feature, _sweep_frame(feature, seed))


def test_the_sweep_frame_gives_every_feature_the_full_width() -> None:
    """The cost fix must not have narrowed the sweep. Asserted, not assumed."""
    for feature in FEATURE_REGISTRY:
        frame = _sweep_frame(feature, seed=0)
        first = max(feature.lookback_bars - 1, 0)
        last = len(frame) - 1 - feature.confirmation_lag_bars
        assert last - first + 1 == DEFAULT_MIN_BARS_TESTED, feature.name
