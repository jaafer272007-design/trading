"""The cross-timeframe convention proof, and the demonstration it can fail.

Two halves, and the second is not optional.

The first half runs the proof on the real feed and pins the verdict. The
second half feeds it synthetic data built under the *other* reading and
requires it to say so. A proof that answers ``LEFT`` on every input — because
of a sign slip in the window arithmetic, say — would sail through the first
half and be worth nothing. Same reasoning as the raw-export guard: a check
that has never rejected anything is indistinguishable from one that cannot.

The abstention tests matter for the same reason in the other direction. The
project's rule is that an undetermined measurement halts rather than deferring
to the plausible answer, and ``None`` has to be reachable for that rule to
mean anything.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Final

import pytest

from data.aggregate import (
    HOUR_SECONDS,
    LEFT,
    MIN_DECISIVE_BARS,
    MINUTE_SECONDS,
    MINUTES_PER_HOUR,
    RIGHT,
    AggregationError,
    Bars,
    CrossTimeframeResult,
    Reading,
    aggregate,
    compare_readings,
    constituents,
    load_bars,
    parse_price,
    scan_offsets,
)
from data.raw import find

# ---------------------------------------------------------------------------
# The real feed
# ---------------------------------------------------------------------------


@functools.cache
def _real() -> tuple[Bars, Bars]:
    """Load both raw exports once for the whole module.

    Returns:
        ``(h1, m1)``.
    """
    return (
        load_bars(find("H1").path),
        load_bars(find("M1").path),
    )


@functools.cache
def _measured() -> CrossTimeframeResult:
    """Run the proof once.

    Returns:
        The measurement over the H1/M1 overlap.
    """
    h1, m1 = _real()
    return compare_readings(h1, m1)


def test_the_readings_were_actually_separable() -> None:
    """Read this before the verdict. Everything else is conditional on it.

    A reading can only be shown wrong on a bar where it predicts something
    different from its rival. A perfect score across bars that cannot tell
    them apart is a statement about the sample, not about the feed.
    """
    result = _measured()
    assert result.decisive >= MIN_DECISIVE_BARS, f"only {result.decisive} decisive bars"
    assert result.decisive == result.eligible, (
        "some eligible bars did not separate the readings; the verdict is "
        "based on a smaller sample than the headline count suggests"
    )


def test_both_readings_were_judged_on_the_same_bars() -> None:
    """Scoring rivals on different samples is choosing the metric post-hoc."""
    result = _measured()
    left = result.results["LEFT"]
    right = result.results["RIGHT"]
    total = result.eligible
    assert left.tested + left.empty == total
    assert right.tested + right.empty == total


def test_left_reproduces_every_eligible_bar_exactly() -> None:
    """Not a rate — every bar, every field, exact integers."""
    left = _measured().results["LEFT"]
    assert left.tested > 0
    assert left.ohlc_match == left.tested, left.mismatches[:3]
    for field, matched in left.field_match.items():
        assert matched == left.tested, (
            f"{field}: {matched}/{left.tested}. Volumes are corroboration "
            f"rather than proof, but a volume that does not sum means the two "
            f"timeframes are not the same tick stream and the argument fails."
        )


def test_right_reproduces_essentially_nothing() -> None:
    """The rival is not merely worse. It is wrong on every bar."""
    right = _measured().results["RIGHT"]
    assert right.tested > 0
    assert right.ohlc_match == 0, right.ohlc_match


def test_verdict_is_left() -> None:
    """``t`` is the bar's OPEN. The bar covers ``[t, t+3600)``.

    Pinned so a later change to the window arithmetic, the eligibility rule,
    or the raw data has to come past this line.
    """
    assert _measured().verdict == "LEFT"


def test_no_third_convention_fits() -> None:
    """The named readings are only the right question if one of them is right.

    The open version — for what shift does the aggregate match at all —
    must have exactly one peak, at zero. A second peak would mean the feed
    uses a convention nobody proposed, which ``compare_readings`` would have
    reported as "neither fits" rather than naming.
    """
    h1, m1 = _real()
    rows = scan_offsets(h1, m1, step=MINUTE_SECONDS, span=2 * HOUR_SECONDS, sample=200)
    best_shift, best_matches, tested = rows[0]
    assert best_shift == 0
    assert best_matches == tested

    runner_up = rows[1]
    assert runner_up[1] <= tested * 0.05, (
        f"shift {runner_up[0]}s also matches {runner_up[1]}/{tested} bars. Two "
        f"peaks means the aggregation relation does not identify the "
        f"convention here, and the verdict must not be read as settled."
    )


def test_the_scan_places_the_named_readings_where_they_belong() -> None:
    """Cheap check that the two descriptions agree with the scan's geometry."""
    assert LEFT.lo == 0
    assert RIGHT.lo == -HOUR_SECONDS + MINUTE_SECONDS


# ---------------------------------------------------------------------------
# The proof can return something other than LEFT
# ---------------------------------------------------------------------------


def _walk(n: int, start_epoch: int, step: int) -> Bars:
    """A deterministic minute series with enough movement to be decisive.

    No RNG: ``REPRODUCIBILITY.md`` wants a seeded generator or none at all,
    and a closed form is easier to reason about than either.

    Args:
        n: Bar count.
        start_epoch: First label.
        step: Seconds between labels.

    Returns:
        The series, prices already scaled.
    """
    epoch, o, h, low, c, tv, rv = [], [], [], [], [], [], []
    for k in range(n):
        base = 100_000 + (k * 37) % 211 + (k * 13) % 71
        epoch.append(start_epoch + step * k)
        o.append(base)
        h.append(base + 5 + k % 7)
        low.append(base - 3 - k % 5)
        c.append(base + 1 + k % 3)
        tv.append(100 + k % 29)
        rv.append(1000 + k % 41)
    return Bars(epoch, o, h, low, c, tv, rv)


def _h1_from(m1: Bars, reading: Reading, start: int, hours: int) -> Bars:
    """Build an hourly series that is true under ``reading`` by construction.

    Args:
        m1: The minute series.
        reading: The convention to build under.
        start: First hourly label.
        hours: How many hourly bars.

    Returns:
        The hourly series.
    """
    epoch, o, h, low, c, tv, rv = [], [], [], [], [], [], []
    for j in range(hours):
        t = start + HOUR_SECONDS * j
        agg = constituents(m1, reading, t)
        if agg is None:
            continue
        epoch.append(t)
        o.append(agg.open)
        h.append(agg.high)
        low.append(agg.low)
        c.append(agg.close)
        tv.append(agg.tick_volume)
        rv.append(agg.real_volume)
    return Bars(epoch, o, h, low, c, tv, rv)


#: Big enough that a synthetic case clears ``MIN_DECISIVE_BARS`` on its own
#: merits. Undersizing these is not a small mistake: every abstention test
#: below would then pass for the wrong reason — thin evidence rather than the
#: property it claims to demonstrate — and the suite would look green while
#: checking nothing.
SYNTH_HOURS: Final = 260
SYNTH_START: Final = 1_700_000_000


def _synthetic_minutes() -> Bars:
    """A minute series long enough to decide a synthetic case.

    Returns:
        ``SYNTH_HOURS`` hours of minutes, padded two hours either side so both
        candidate windows are in range at every hourly label.
    """
    return _walk(
        MINUTES_PER_HOUR * (SYNTH_HOURS + 4),
        SYNTH_START - 2 * HOUR_SECONDS,
        MINUTE_SECONDS,
    )


@pytest.mark.parametrize("truth", [LEFT, RIGHT], ids=lambda r: r.name)
def test_the_proof_recovers_whichever_convention_built_the_data(
    truth: Reading,
) -> None:
    """The load-bearing negative control.

    Data is generated under ``truth`` and the proof must name ``truth``. Run
    for both, so an implementation that always answers LEFT — a sign slip in
    the window arithmetic would do it — fails on the RIGHT case instead of
    quietly confirming the real-feed result.
    """
    m1 = _synthetic_minutes()
    h1 = _h1_from(m1, truth, SYNTH_START, SYNTH_HOURS)
    result = compare_readings(h1, m1)
    assert result.decisive >= MIN_DECISIVE_BARS, result.decisive
    assert result.verdict == truth.name, {
        n: (r.ohlc_match, r.tested) for n, r in result.results.items()
    }
    other = "RIGHT" if truth is LEFT else "LEFT"
    assert result.results[other].ohlc_match == 0


def test_the_proof_abstains_when_neither_reading_fits() -> None:
    """An unrecognised convention halts. It does not fall back to LEFT.

    The sample is deliberately over ``MIN_DECISIVE_BARS`` so the abstention is
    attributable to no reading fitting, and not to thin evidence. Those are
    different failures and this test is only about the first.
    """
    m1 = _synthetic_minutes()
    offset = Reading("HALF", 1800, 1800 + HOUR_SECONDS, "shifted half an hour")
    h1 = _h1_from(m1, offset, SYNTH_START, SYNTH_HOURS)
    result = compare_readings(h1, m1)
    assert result.decisive >= MIN_DECISIVE_BARS, result.decisive
    for name, r in result.results.items():
        assert r.ohlc_match == 0, (name, r.ohlc_match, r.tested)
    assert result.verdict is None


def test_the_proof_abstains_when_the_evidence_is_thin() -> None:
    """Too few decisive bars is undetermined, even with a perfect score.

    The complement of the test above: here a reading fits every single bar and
    the answer is still ``None``, because there were not enough bars for that
    to mean anything.
    """
    m1 = _walk(MINUTES_PER_HOUR * 6, SYNTH_START - 2 * HOUR_SECONDS, MINUTE_SECONDS)
    h1 = _h1_from(m1, LEFT, SYNTH_START, 2)
    result = compare_readings(h1, m1)
    left = result.results["LEFT"]
    assert left.tested > 0
    assert left.ohlc_match == left.tested, "the fit is perfect and still not enough"
    assert result.decisive < MIN_DECISIVE_BARS
    assert result.verdict is None


def test_the_proof_abstains_when_both_readings_fit() -> None:
    """Flat prices make the readings indistinguishable, so nothing is proved.

    The third way to fail: plenty of bars, a perfect score, and no information,
    because every window aggregates to the same bar. This is what ``decisive``
    is for, and it is why the headline number in any report of this proof is
    the decisive count rather than the match rate.
    """
    n = MINUTES_PER_HOUR * (SYNTH_HOURS + 4)
    flat = Bars(
        epoch=[SYNTH_START - 2 * HOUR_SECONDS + MINUTE_SECONDS * k for k in range(n)],
        open=[100_000] * n,
        high=[100_000] * n,
        low=[100_000] * n,
        close=[100_000] * n,
        tick_volume=[1] * n,
        real_volume=[1] * n,
    )
    h1 = _h1_from(flat, LEFT, SYNTH_START, SYNTH_HOURS)
    result = compare_readings(h1, flat)
    assert result.eligible >= MIN_DECISIVE_BARS, "sample size is not the confound here"
    # Both readings reproduce OHLC exactly; only the volumes could separate
    # them, and OHLC is what the verdict rests on.
    assert result.results["LEFT"].ohlc_match == result.results["LEFT"].tested
    assert result.results["RIGHT"].ohlc_match == result.results["RIGHT"].tested
    assert result.decisive == 0
    assert result.verdict is None


# ---------------------------------------------------------------------------
# The primitives
# ---------------------------------------------------------------------------


def test_parse_price_is_exact() -> None:
    assert parse_price("4815.3") == 481_530
    assert parse_price("4815.30") == 481_530
    assert parse_price("973") == 97_300
    assert parse_price("0.01") == 1
    assert parse_price("-1.5") == -150


def test_parse_price_refuses_to_round() -> None:
    """Silent rounding here would turn 'exactly equal' into 'close enough'."""
    with pytest.raises(AggregationError, match="decimals"):
        parse_price("4815.301")


def test_aggregate_is_selection_not_arithmetic() -> None:
    """Hand-checked. No averaging, no interpolation, no invented prices."""
    bars = Bars(
        epoch=[0, 60, 120],
        open=[10, 20, 30],
        high=[15, 25, 33],
        low=[8, 19, 28],
        close=[12, 24, 31],
        tick_volume=[1, 2, 3],
        real_volume=[10, 20, 30],
    )
    agg = aggregate(bars, 0, 3)
    assert agg is not None
    assert agg.open == 10  # first bar's open, not an average
    assert agg.close == 31  # last bar's close
    assert agg.high == 33
    assert agg.low == 8
    assert agg.tick_volume == 6
    assert agg.real_volume == 60
    assert agg.minutes == 3


def test_aggregate_of_nothing_is_none_not_a_zero_bar() -> None:
    """An empty window has no bar. Returning zeros would be imputation."""
    bars = Bars([0], [1], [1], [1], [1], [1], [1])
    assert aggregate(bars, 0, 0) is None


def test_load_rejects_an_unordered_series(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "time,open,high,low,close,tick_volume,spread,real_volume\n"
        "200,1,1,1,1,1,0,1\n"
        "100,1,1,1,1,1,0,1\n",
        encoding="utf-8",
    )
    with pytest.raises(AggregationError, match="strictly increasing"):
        load_bars(path)


def test_load_rejects_a_renamed_header(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "timestamp,open,high,low,close,tick_volume,spread,real_volume\n",
        encoding="utf-8",
    )
    with pytest.raises(AggregationError, match="header"):
        load_bars(path)
