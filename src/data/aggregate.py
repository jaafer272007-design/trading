"""The cross-timeframe proof: which hour a bar labelled ``t`` actually covers.

This is the only check in the project that rests on **no convention
assumption at all**, and it is the reason the M1 export exists.

The problem
-----------

MT5 hands over a bar stamped ``t`` and says nothing about what ``t`` means.
Two readings are self-consistent and produce identical-looking data:

=========  =====================================================
``LEFT``   ``t`` is the bar's **open**; it covers ``[t, t+3600)``
``RIGHT``  ``t`` is the bar's **close**; it covers ``(t-3600, t]``
=========  =====================================================

Every downstream question depends on which is true. A feature computed at
bar ``t`` under the wrong reading reads an hour of market that had not
happened yet — ``DATA_CONTRACT.md`` §4 calls a one-bar convention mismatch a
leak, and the data looks perfect either way. Documentation is not evidence:
``RESEARCH.md`` puts a vendor's description of its own product below a
measurement, and MT5's behaviour here is a widely-repeated belief rather than
something this project has observed on this feed.

Why the two timeframes settle it
--------------------------------

The H1 and M1 series come from the same tick stream and the same clock. So
whatever ``t`` means, it means the same thing in both, and the aggregation
relation must hold:

    the H1 bar at ``t``  ==  the aggregate of the M1 bars inside its hour

Under ``LEFT`` the constituent minutes are those stamped ``[t, t+3600)``.
Under ``RIGHT`` they are those stamped ``(t-3600, t]``. These are two almost
disjoint sets of minutes, so they aggregate to different bars, and only one of
them can equal the H1 bar that is actually there.

Nothing in this argument needs to know the server's timezone, its DST rule,
its session boundaries, or even that the epochs are seconds. The offsets
cancel. That is the whole point: every other convention check in this project
is conditional on the frozen calendar being right, and this one is not.

Deliberately built from primitives
----------------------------------

No pandas, no calendar, no timezone conversion — the proof that decides the
convention must not route through the machinery whose correctness depends on
the answer. Prices are read as exact scaled integers rather than floats, so
"equal" means equal and not equal-to-within-an-epsilon.

Reading the verdict
-------------------

:func:`decide` returns ``LEFT``, ``RIGHT``, or ``None``. ``None`` means the
evidence did not separate them, and it is a **halt**, not a tiebreak to be
resolved by picking the plausible one. The count that matters is
``decisive`` — bars where the two readings genuinely predict different
aggregates. A high match rate against a low decisive count proves nothing.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

HOUR_SECONDS: Final = 3600
MINUTE_SECONDS: Final = 60
MINUTES_PER_HOUR: Final = 60

#: Prices carry at most this many decimals on this symbol (``symbol_digits``
#: in the export metadata). Scaling by ``10**PRICE_DECIMALS`` makes every
#: comparison exact integer arithmetic. Asserted on load rather than trusted:
#: a symbol with more digits would silently lose precision here.
PRICE_DECIMALS: Final = 2
PRICE_SCALE: Final = 10**PRICE_DECIMALS

#: A verdict needs at least this many bars on which the two readings actually
#: disagree. Below it, a clean sweep is a statement about the sample size.
MIN_DECISIVE_BARS: Final = 200

#: And this share of them must fall the same way. Set at 1.0 deliberately:
#: the aggregation identity is arithmetic, not statistics. A single genuine
#: counterexample means the model of the feed is wrong somewhere, and
#: averaging it away is how a broken assumption survives.
REQUIRED_AGREEMENT: Final = 1.0


class AggregationError(RuntimeError):
    """The raw data cannot support the cross-timeframe proof."""


# ---------------------------------------------------------------------------
# Exact reading
# ---------------------------------------------------------------------------


class Bars(NamedTuple):
    """One raw timeframe, as exact integers.

    Prices are scaled by :data:`PRICE_SCALE`; comparisons between them are
    therefore exact, and no tolerance is ever needed or offered.
    """

    epoch: list[int]
    open: list[int]
    high: list[int]
    low: list[int]
    close: list[int]
    tick_volume: list[int]
    real_volume: list[int]

    def __len__(self) -> int:
        """Number of bars.

        Returns:
            Bar count.
        """
        return len(self.epoch)


def parse_price(text: str) -> int:
    """Read a decimal price string as an exact scaled integer.

    Args:
        text: The CSV field, e.g. ``"4815.3"``.

    Returns:
        The price times :data:`PRICE_SCALE`.

    Raises:
        AggregationError: If the value carries more decimals than the symbol
            declares, which would make the scaling lossy.
    """
    whole, _, frac = text.partition(".")
    if len(frac) > PRICE_DECIMALS:
        raise AggregationError(
            f"price {text!r} has {len(frac)} decimals but the symbol declares "
            f"{PRICE_DECIMALS}. Scaling would round, and this proof compares "
            f"prices for exact equality."
        )
    negative = whole.startswith("-")
    digits = f"{whole.lstrip('-') or '0'}{frac:<0{PRICE_DECIMALS}s}".replace(" ", "0")
    value = int(digits)
    return -value if negative else value


def load_bars(path: Path) -> Bars:
    """Read a raw MT5 export exactly.

    Args:
        path: A CSV written by ``scripts/mt5_export.py``.

    Returns:
        The bars, prices scaled to integers.

    Raises:
        AggregationError: If the header is not MT5's own, or the timestamps
            are not strictly increasing.
    """
    epoch: list[int] = []
    o: list[int] = []
    h: list[int] = []
    lo: list[int] = []
    c: list[int] = []
    tv: list[int] = []
    rv: list[int] = []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        expected = [
            "time",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread",
            "real_volume",
        ]
        if header != expected:
            raise AggregationError(f"{path.name}: header {header} != {expected}")
        for row in reader:
            epoch.append(int(row[0]))
            o.append(parse_price(row[1]))
            h.append(parse_price(row[2]))
            lo.append(parse_price(row[3]))
            c.append(parse_price(row[4]))
            tv.append(int(row[5]))
            rv.append(int(row[7]))

    for i in range(1, len(epoch)):
        if epoch[i] <= epoch[i - 1]:
            raise AggregationError(
                f"{path.name}: timestamps not strictly increasing at row {i + 1} "
                f"({epoch[i - 1]} -> {epoch[i]}). The proof indexes by time and "
                f"cannot run on an unordered series."
            )

    return Bars(epoch, o, h, lo, c, tv, rv)


# ---------------------------------------------------------------------------
# The two readings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """One candidate meaning for a bar's timestamp.

    The window is expressed in seconds relative to the H1 label, as a
    half-open interval over the **M1 labels** — which is consistent only
    because a reading applies to both timeframes at once. If ``t`` is an open
    time for the hour it is also an open time for the minute, so the minutes
    inside the hour are exactly those stamped in ``[t, t+3600)``.
    """

    name: str
    lo: int
    hi: int
    meaning: str

    def window(self, t: int) -> tuple[int, int]:
        """The half-open range of M1 labels this reading assigns to hour ``t``.

        Args:
            t: The H1 bar's label.

        Returns:
            ``(start_inclusive, end_exclusive)``.
        """
        return t + self.lo, t + self.hi


#: ``t`` is the bar's opening instant.
LEFT: Final = Reading(
    name="LEFT",
    lo=0,
    hi=HOUR_SECONDS,
    meaning="t is the bar's OPEN; the bar covers [t, t+3600)",
)

#: ``t`` is the bar's closing instant.
RIGHT: Final = Reading(
    name="RIGHT",
    lo=-HOUR_SECONDS + MINUTE_SECONDS,
    hi=MINUTE_SECONDS,
    meaning="t is the bar's CLOSE; the bar covers (t-3600, t]",
)

READINGS: Final = (LEFT, RIGHT)


class Aggregate(NamedTuple):
    """The bar implied by a set of M1 constituents.

    ``minutes`` rather than ``count``: a ``NamedTuple`` field named ``count``
    shadows ``tuple.count``, which mypy rejects and which would quietly break
    anything treating this as a plain tuple.
    """

    minutes: int
    open: int
    high: int
    low: int
    close: int
    tick_volume: int
    real_volume: int


def aggregate(m1: Bars, start: int, stop: int) -> Aggregate | None:
    """Roll M1 bars ``[start:stop)`` into the hour bar they imply.

    Args:
        m1: The minute series.
        start: First index, inclusive.
        stop: Last index, exclusive.

    Returns:
        The implied bar, or ``None`` if the range is empty.
    """
    if stop <= start:
        return None
    return Aggregate(
        minutes=stop - start,
        open=m1.open[start],
        high=max(m1.high[start:stop]),
        low=min(m1.low[start:stop]),
        close=m1.close[stop - 1],
        tick_volume=sum(m1.tick_volume[start:stop]),
        real_volume=sum(m1.real_volume[start:stop]),
    )


def _bisect_left(values: list[int], target: int) -> int:
    """Index of the first element ``>= target``.

    Args:
        values: Sorted, strictly increasing.
        target: Search key.

    Returns:
        Insertion point.
    """
    low, high = 0, len(values)
    while low < high:
        mid = (low + high) // 2
        if values[mid] < target:
            low = mid + 1
        else:
            high = mid
    return low


def constituents(m1: Bars, reading: Reading, t: int) -> Aggregate | None:
    """The hour bar that ``reading`` says the minutes around ``t`` add up to.

    The single place a reading is turned into a set of minutes, so the two
    readings cannot drift apart through a copy of this arithmetic.

    Args:
        m1: The minute series.
        reading: The candidate convention.
        t: The hourly label.

    Returns:
        The implied bar, or ``None`` if no minutes fall in the window.
    """
    lo, hi = reading.window(t)
    return aggregate(m1, _bisect_left(m1.epoch, lo), _bisect_left(m1.epoch, hi))


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mismatch:
    """One H1 bar that a reading failed to reproduce."""

    epoch: int
    reading: str
    constituents: int
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ReadingResult:
    """How one reading did across the overlap."""

    reading: str
    meaning: str
    tested: int
    empty: int
    ohlc_match: int
    field_match: dict[str, int]
    full_hour_tested: int
    full_hour_ohlc_match: int
    mismatches: tuple[Mismatch, ...]

    @property
    def ohlc_rate(self) -> float:
        """Share of tested bars reproduced exactly on OHLC.

        Returns:
            A rate in ``[0, 1]``; zero if nothing was tested.
        """
        return self.ohlc_match / self.tested if self.tested else 0.0


@dataclass(frozen=True)
class CrossTimeframeResult:
    """The full measurement, and the verdict that follows from it."""

    h1_bars: int
    m1_bars: int
    overlap_first: int
    overlap_last: int
    eligible: int
    decisive: int
    results: dict[str, ReadingResult]

    @property
    def verdict(self) -> str | None:
        """``LEFT``, ``RIGHT``, or ``None`` for undetermined.

        ``None`` is a halt. It means the measurement did not separate the two
        readings, and there is no defensible way to choose between them from
        this evidence — including choosing the one that matches the vendor
        documentation, which is what this proof exists to avoid relying on.

        Returns:
            The winning reading's name, or ``None``.
        """
        if self.decisive < MIN_DECISIVE_BARS:
            return None
        clean = [
            name
            for name, r in self.results.items()
            if r.tested and r.ohlc_rate >= REQUIRED_AGREEMENT
        ]
        return clean[0] if len(clean) == 1 else None


def compare_readings(
    h1: Bars, m1: Bars, readings: Iterable[Reading] = READINGS
) -> CrossTimeframeResult:
    """Test every candidate reading against the overlapping window.

    Eligibility is symmetric on purpose. An H1 bar is tested only if **both**
    candidate windows lie strictly inside the M1 export's span, so neither
    reading is penalised for the other's data simply running out. Scoring the
    readings on different bar sets would be the same class of error as choosing
    a metric after seeing which one wins.

    Args:
        h1: The hourly series.
        m1: The minute series.
        readings: Candidates to test.

    Returns:
        The measurement.

    Raises:
        AggregationError: If the two series do not overlap.
    """
    readings = tuple(readings)
    if not len(m1) or not len(h1):
        raise AggregationError("both timeframes must be non-empty")

    m1_first, m1_last = m1.epoch[0], m1.epoch[-1]
    # An H1 bar is eligible when every candidate window sits inside the M1
    # span. Widen by one hour on each side so LEFT and RIGHT are judged on
    # exactly the same bars.
    lo_bound = m1_first + HOUR_SECONDS
    hi_bound = m1_last - HOUR_SECONDS
    eligible_epochs = [t for t in h1.epoch if lo_bound <= t <= hi_bound]
    if not eligible_epochs:
        raise AggregationError(
            f"no H1 bar has a full hour of M1 coverage on both sides. "
            f"M1 spans {m1_first}..{m1_last}; H1 spans "
            f"{h1.epoch[0]}..{h1.epoch[-1]}. The proof needs an overlap."
        )

    h1_at = {t: i for i, t in enumerate(h1.epoch)}
    tallies: dict[str, ReadingResult] = {}
    per_bar: dict[str, dict[int, Aggregate | None]] = {r.name: {} for r in readings}
    fields = ("open", "high", "low", "close", "tick_volume", "real_volume")

    for reading in readings:
        tested = empty = ohlc_match = 0
        full_tested = full_match = 0
        field_match = dict.fromkeys(fields, 0)
        mismatches: list[Mismatch] = []

        for t in eligible_epochs:
            agg = constituents(m1, reading, t)
            per_bar[reading.name][t] = agg
            if agg is None:
                empty += 1
                continue

            tested += 1
            i = h1_at[t]
            actual = (
                h1.open[i],
                h1.high[i],
                h1.low[i],
                h1.close[i],
                h1.tick_volume[i],
                h1.real_volume[i],
            )
            implied = (
                agg.open,
                agg.high,
                agg.low,
                agg.close,
                agg.tick_volume,
                agg.real_volume,
            )
            bad = tuple(
                f for f, a, b in zip(fields, actual, implied, strict=True) if a != b
            )
            for f, a, b in zip(fields, actual, implied, strict=True):
                if a == b:
                    field_match[f] += 1

            ohlc_bad = tuple(f for f in bad if f in ("open", "high", "low", "close"))
            if not ohlc_bad:
                ohlc_match += 1
            elif len(mismatches) < 10:
                mismatches.append(
                    Mismatch(
                        epoch=t,
                        reading=reading.name,
                        constituents=agg.minutes,
                        fields=bad,
                    )
                )

            if agg.minutes == MINUTES_PER_HOUR:
                full_tested += 1
                if not ohlc_bad:
                    full_match += 1

        tallies[reading.name] = ReadingResult(
            reading=reading.name,
            meaning=reading.meaning,
            tested=tested,
            empty=empty,
            ohlc_match=ohlc_match,
            field_match=field_match,
            full_hour_tested=full_tested,
            full_hour_ohlc_match=full_match,
            mismatches=tuple(mismatches),
        )

    decisive = _count_decisive(eligible_epochs, per_bar, [r.name for r in readings])

    return CrossTimeframeResult(
        h1_bars=len(h1),
        m1_bars=len(m1),
        overlap_first=eligible_epochs[0],
        overlap_last=eligible_epochs[-1],
        eligible=len(eligible_epochs),
        decisive=decisive,
        results=tallies,
    )


def _count_decisive(
    epochs: list[int],
    per_bar: dict[str, dict[int, Aggregate | None]],
    names: list[str],
) -> int:
    """Count bars on which the readings predict genuinely different bars.

    The load-bearing statistic. A reading can only be *shown* wrong on a bar
    where it predicts something the other does not, and a sweep across bars
    that cannot separate them says nothing at all — the same reason a gate
    that has never fired is indistinguishable from one that cannot.

    Args:
        epochs: Eligible H1 labels.
        per_bar: Reading name to label to its implied aggregate.
        names: Reading names.

    Returns:
        How many eligible bars separate the readings.
    """
    count = 0
    for t in epochs:
        implied = [per_bar[n].get(t) for n in names]
        comparable = [
            None if a is None else (a.open, a.high, a.low, a.close) for a in implied
        ]
        if len({repr(c) for c in comparable}) > 1:
            count += 1
    return count


def decide(result: CrossTimeframeResult) -> str | None:
    """The verdict, as a function of the measurement alone.

    Args:
        result: Output of :func:`compare_readings`.

    Returns:
        ``"LEFT"``, ``"RIGHT"``, or ``None``.
    """
    return result.verdict


# ---------------------------------------------------------------------------
# Ruling out a third convention
# ---------------------------------------------------------------------------


def scan_offsets(
    h1: Bars,
    m1: Bars,
    step: int = MINUTE_SECONDS,
    span: int = 2 * HOUR_SECONDS,
    sample: int = 400,
) -> list[tuple[int, int, int]]:
    """Search every shift, not just the two named readings.

    ``compare_readings`` asks which of two candidates fits. That is the right
    question only if one of them is right. This asks the open version — for
    what shift ``k`` does the H1 bar at ``t`` equal the aggregate of the
    minutes in ``[t+k, t+k+3600)`` — so a convention nobody proposed shows up
    as a third peak instead of appearing as "neither reading fits".

    Args:
        h1: The hourly series.
        m1: The minute series.
        step: Shift granularity, seconds.
        span: Scan from ``-span`` to ``+span``.
        sample: How many eligible H1 bars to score per shift.

    Returns:
        ``(shift, matches, tested)`` per shift, best first.
    """
    m1_first, m1_last = m1.epoch[0], m1.epoch[-1]
    lo_bound = m1_first + span + HOUR_SECONDS
    hi_bound = m1_last - span - HOUR_SECONDS
    eligible = [t for t in h1.epoch if lo_bound <= t <= hi_bound]
    if len(eligible) > sample:
        stride = len(eligible) // sample
        eligible = eligible[::stride][:sample]

    h1_at = {t: i for i, t in enumerate(h1.epoch)}
    out: list[tuple[int, int, int]] = []
    for shift in range(-span, span + 1, step):
        matches = tested = 0
        for t in eligible:
            start = _bisect_left(m1.epoch, t + shift)
            stop = _bisect_left(m1.epoch, t + shift + HOUR_SECONDS)
            agg = aggregate(m1, start, stop)
            if agg is None:
                continue
            tested += 1
            i = h1_at[t]
            if (
                agg.open == h1.open[i]
                and agg.high == h1.high[i]
                and agg.low == h1.low[i]
                and agg.close == h1.close[i]
            ):
                matches += 1
        out.append((shift, matches, tested))
    out.sort(key=lambda row: (-row[1], abs(row[0])))
    return out
