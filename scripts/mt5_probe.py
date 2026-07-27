"""MT5 history probe — a measurement instrument, not part of the pipeline.

.. important::

   **This script measures. It does not ingest, export, or transform anything,
   and it is not part of the evaluation path.**

   It writes nothing but its own stdout: no files into the repository, no
   files anywhere. It imports nothing from this repository, so it can be
   copied to a Windows machine and run on its own. Nothing it produces is a
   snapshot, and nothing it produces may be used as data — its entire output
   is a report for a human to read.

   One honest caveat about "writes nothing": requesting history causes the
   **MetaTrader 5 terminal** to download bars and ticks into its own cache,
   outside this repository. That is the terminal's behaviour, not this
   script's, and it is unavoidable for any measurement of what history
   exists. No other side effect occurs.

Why it exists
-------------

Three numbers decide the design of the data layer, and none of them can be
guessed from documentation:

1. the earliest available **H1** bar,
2. the earliest available **M1** bar,
3. the earliest available **tick with a real bid/ask spread**.

They determine whether ``EVALUATION.md`` §11's regime-shift test (fit
pre-2022, evaluate post-2022) is runnable at all, whether the sample-size
budget clears K-6 with room for walk-forward folds and a sealed holdout, and
whether the §10 cost model can be calibrated from observed spread or must be
bounded conservatively instead.

Everything else it reports — the timestamp offset, the gap census, the
symbol and server identity — exists because ``DATA_CONTRACT.md`` §4 calls a
one-bar convention mismatch a leak that is enough on its own, and because §6
forbids silent imputation, which requires knowing which absent bars are
market closures and which are real holes.

Requirements
------------

- Windows. The ``MetaTrader5`` PyPI package ships only ``win_amd64`` wheels
  and declares ``Platform: Windows``.
- A running MT5 terminal, logged in, with the symbol available.
- ``pip install MetaTrader5`` (it pulls in numpy, the only other import).

Usage::

    python mt5_probe.py               # tries common gold symbol names
    python mt5_probe.py XAUUSD.pro    # or name it explicitly

Credentials are never read, never printed, and never needed by this script —
it attaches to a terminal that is already logged in. The account login number
is deliberately masked in the output so the report can be pasted anywhere.
"""

from __future__ import annotations

import platform
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Any

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

CANDIDATE_SYMBOLS: tuple[str, ...] = (
    "XAUUSD",
    "GOLD",
    "XAUUSD.pro",
    "XAUUSD.raw",
    "XAUUSD_",
    "XAUUSDm",
    "GOLD.spot",
    "XAUUSDc",
)

SEARCH_START_YEAR = 1990
PROBE_WINDOW_DAYS = 30
TICK_PROBE_WINDOW_DAYS = 3
SUSPICIOUS_GAPS_TO_LIST = 15
HOLIDAY_MIN_MISSING_BARS = 20
BREAK_HOUR_MIN_SHARE = 0.02
SPREAD_SAMPLE_DAYS = (0, 90, 365, 730, 1095, 1460, 1825)

WIDTH = 78


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------


def header(title: str) -> None:
    """Print a section header.

    Args:
        title: Section title.
    """
    print()
    print("=" * WIDTH)
    print(title)
    print("=" * WIDTH)


def row(label: str, value: object) -> None:
    """Print an aligned label/value line.

    Args:
        label: Left-hand label.
        value: Right-hand value.
    """
    print(f"  {label:.<34} {value}")


def note(text: str) -> None:
    """Print an indented note line.

    Args:
        text: Note text.
    """
    print(f"      {text}")


def fmt_time(value: object) -> str:
    """Format a timestamp for the report.

    Args:
        value: A datetime, or something convertible.

    Returns:
        ISO-like string, or ``"n/a"``.
    """
    if value is None:
        return "n/a"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def to_naive(epoch: float) -> datetime:
    """Convert an MT5 epoch value to a naive datetime.

    MT5 timestamps are **server wall-clock time expressed as a Unix epoch**.
    Interpreting one as UTC therefore yields the server's clock reading, not
    true UTC — which is exactly what makes the offset measurable.

    Args:
        epoch: MT5 timestamp in seconds.

    Returns:
        Naive datetime carrying the server's wall-clock reading.
    """
    return datetime.fromtimestamp(epoch, tz=UTC).replace(tzinfo=None)


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------


def require_windows_mt5() -> Any:
    """Import MetaTrader5, failing with a useful message if impossible.

    Returns:
        The imported ``MetaTrader5`` module.

    Raises:
        SystemExit: If the platform or package is unavailable.
    """
    if platform.system() != "Windows":
        print("FATAL: this probe must run on Windows.")
        print("  The MetaTrader5 package ships only win_amd64 wheels and")
        print(f"  declares Platform: Windows. Detected: {platform.system()}.")
        raise SystemExit(2)
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except ImportError:
        print("FATAL: MetaTrader5 is not installed.")
        print("  Run:  pip install MetaTrader5")
        raise SystemExit(2) from None
    return mt5


def resolve_symbol(mt5: Any, requested: str | None) -> str:
    """Find a usable symbol and select it in Market Watch.

    Args:
        mt5: The MetaTrader5 module.
        requested: Symbol from the command line, if any.

    Returns:
        The exact symbol string the broker uses.

    Raises:
        SystemExit: If no candidate symbol resolves.
    """
    candidates = (requested,) if requested else CANDIDATE_SYMBOLS
    for name in candidates:
        if name and mt5.symbol_info(name) is not None:
            mt5.symbol_select(name, True)
            return name

    print("FATAL: could not resolve a gold symbol.")
    print(f"  Tried: {', '.join(c for c in candidates if c)}")
    all_symbols = mt5.symbols_get()
    if all_symbols:
        gold = [
            s.name
            for s in all_symbols
            if "XAU" in s.name.upper() or "GOLD" in s.name.upper()
        ]
        if gold:
            print("  Gold-like symbols this broker does offer:")
            for name in sorted(gold)[:40]:
                print(f"    {name}")
            print("  Re-run with:  python mt5_probe.py <SYMBOL>")
        else:
            print(f"  No gold-like symbol found among {len(all_symbols)} symbols.")
    raise SystemExit(2)


# --------------------------------------------------------------------------
# 3. Identity
# --------------------------------------------------------------------------


def report_identity(mt5: Any, symbol: str) -> None:
    """Report symbol, broker/server, and terminal build.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Resolved symbol string.
    """
    header("3. IDENTITY — symbol, broker/server, MT5 build")

    version = mt5.version()
    terminal = mt5.terminal_info()
    account = mt5.account_info()
    info = mt5.symbol_info(symbol)

    if version:
        row("MT5 terminal version", version[0])
        row("MT5 build", version[1])
        row("MT5 build date", version[2])
    if terminal:
        row("terminal name", terminal.name)
        row("terminal company", terminal.company)
        row("connected", terminal.connected)
    if account:
        # Login is masked deliberately: this report is meant to be pasted
        # around, and the account number has no bearing on any measurement.
        row("account server", account.server)
        row("account company", account.company)
        row("account login", "**** (masked)")
        row("account currency", account.currency)
        demo = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        row("account type", "DEMO" if account.trade_mode == demo else "LIVE/CONTEST")

    if info:
        row("symbol (exact string)", repr(info.name))
        row("symbol description", info.description)
        row("symbol path", info.path)
        row("digits", info.digits)
        row("point", info.point)
        row("tick size", info.trade_tick_size)
        row("contract size", info.trade_contract_size)
        row("current spread (points)", info.spread)
        row("spread is floating", bool(info.spread_float))
    note("Pin the exact symbol string in the data layer — DATA_CONTRACT §3.")


# --------------------------------------------------------------------------
# 1. Depth
# --------------------------------------------------------------------------


def earliest_bar(mt5: Any, symbol: str, timeframe: int, label: str) -> datetime | None:
    """Locate the earliest available bar by scanning whole years.

    Searched rather than assumed: MT5 downloads history on demand, so the
    only way to learn the depth is to ask.

    The window is a **whole calendar year**, and that matters. An earlier
    draft probed a 30-day window from each 1 January, which silently reported
    history starting 2019-04-08 as starting in 2020 — January was empty, so
    the whole year was skipped. Scanning the full year means the first
    non-empty year's first bar *is* the earliest bar, exactly, with no
    refinement step to get wrong.

    Only the first non-empty year is ever fetched in full; every earlier year
    returns nothing and costs almost nothing.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        timeframe: MT5 timeframe constant.
        label: Human label for progress output.

    Returns:
        Time of the earliest bar, or ``None`` if no history exists.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    print(f"  probing {label} depth", end="", flush=True)

    for year in range(SEARCH_START_YEAR, now.year + 1):
        print(".", end="", flush=True)
        rates = mt5.copy_rates_range(
            symbol, timeframe, datetime(year, 1, 1), datetime(year + 1, 1, 1)
        )
        if rates is not None and len(rates) > 0:
            print(" done")
            return to_naive(rates[0]["time"])

    print("  none found")
    return None


def earliest_tick(mt5: Any, symbol: str) -> datetime | None:
    """Locate the earliest available tick.

    Ticks cannot be scanned a year at a time — a single year of gold ticks is
    tens of millions of rows. ``copy_ticks_from`` with ``count=1`` asks for
    the first tick at or after a date, which is the same question at a
    fraction of the cost. A year-by-year fallback covers brokers whose
    terminal will not serve a request that far back in one call.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.

    Returns:
        Time of the earliest tick, or ``None``.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    print("  probing tick depth", end="", flush=True)

    def first_at_or_after(when: datetime) -> datetime | None:
        ticks = mt5.copy_ticks_from(symbol, when, 1, mt5.COPY_TICKS_INFO)
        if ticks is None or len(ticks) == 0:
            return None
        return to_naive(ticks[0]["time"])

    direct = first_at_or_after(datetime(SEARCH_START_YEAR, 1, 1))
    if direct is not None:
        print(" done")
        return direct

    for year in range(SEARCH_START_YEAR, now.year + 1):
        print(".", end="", flush=True)
        found = first_at_or_after(datetime(year, 1, 1))
        if found is not None:
            print(" done")
            return found

    print("  none found")
    return None


def report_depth(mt5: Any, symbol: str) -> dict[str, datetime | None]:
    """Report earliest available H1, M1, and tick timestamps.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.

    Returns:
        Mapping of series name to earliest timestamp.
    """
    header("1. DEPTH — earliest available history (the decisive numbers)")

    found = {
        "H1": earliest_bar(mt5, symbol, mt5.TIMEFRAME_H1, "H1"),
        "M1": earliest_bar(mt5, symbol, mt5.TIMEFRAME_M1, "M1"),
        "tick": earliest_tick(mt5, symbol),
    }

    print()
    now = datetime.now(UTC).replace(tzinfo=None)
    for name, when in found.items():
        if when is None:
            row(f"earliest {name}", "NONE AVAILABLE")
        else:
            years = (now - when).days / 365.25
            row(f"earliest {name}", f"{fmt_time(when)}   ({years:.2f} years)")
    return found


# --------------------------------------------------------------------------
# 2. Density — measured, never extrapolated
# --------------------------------------------------------------------------

DENSE_DAY_MIN_BARS = 20


def fetch_all_h1(mt5: Any, symbol: str, earliest_h1: datetime | None) -> Any:
    """Fetch the entire H1 series.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        earliest_h1: Earliest H1 timestamp.

    Returns:
        The full rate array, or ``None``.
    """
    if earliest_h1 is None:
        return None
    now = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, earliest_h1, now)
    if rates is None or len(rates) == 0:
        return None
    return rates


def report_density(rates: Any) -> None:
    """Report measured bar density per year, and the bars-per-day histogram.

    An earlier version of this probe reported "total independent decisions"
    as ``median_bars_per_week x 52 x span_years``. That is an extrapolation
    presented as a measurement, and on a feed whose early history is sparse it
    overstated the true count by 63%. Everything below is counted, and the two
    figures that remain estimates are labelled as such.

    Args:
        rates: Full H1 rate array, or ``None``.
    """
    header("2. DENSITY — measured bar counts (nothing here is extrapolated)")

    if rates is None or len(rates) == 0:
        print("  no H1 history — nothing to count")
        return

    times = [to_naive(r["time"]) for r in rates]
    row("total H1 bars [MEASURED]", f"{len(times):,}")
    row("first bar (server time)", fmt_time(times[0]))
    row("last bar (server time)", fmt_time(times[-1]))
    row("span", f"{(times[-1] - times[0]).days / 365.25:.2f} years")
    print()
    row("=> decisions at H=24 [MEASURED]", f"{len(times) // 24:,}")
    note("Total bars divided by 24. This is the real ceiling on")
    note("non-overlapping decisions. K-6 needs >= 150 per window.")

    # ---- per-year table -------------------------------------------------
    per_day: Counter[Any] = Counter(t.date() for t in times)
    per_year: Counter[int] = Counter(t.year for t in times)
    days_by_year: dict[int, list[int]] = {}
    for day, count in per_day.items():
        days_by_year.setdefault(day.year, []).append(count)

    print()
    print("  Bars per calendar year — all MEASURED")
    print()
    print("      year      bars    days   dense   dense%   med bars/day")
    print("      " + "-" * 58)
    for year in sorted(per_year):
        counts = days_by_year.get(year, [])
        dense = sum(1 for c in counts if c >= DENSE_DAY_MIN_BARS)
        pct = 100.0 * dense / len(counts) if counts else 0.0
        med = sorted(counts)[len(counts) // 2] if counts else 0
        print(
            f"      {year}   {per_year[year]:>7,}   {len(counts):>5}   "
            f"{dense:>5}   {pct:>5.1f}%   {med:>12}"
        )
    total_days = sum(len(v) for v in days_by_year.values())
    total_dense = sum(
        1 for v in days_by_year.values() for c in v if c >= DENSE_DAY_MIN_BARS
    )
    print("      " + "-" * 58)
    print(
        f"      TOTAL  {len(times):>7,}   {total_days:>5}   {total_dense:>5}   "
        f"{100.0 * total_dense / total_days if total_days else 0:>5.1f}%"
    )
    note(f"'dense' = a day carrying >= {DENSE_DAY_MIN_BARS} bars.")

    # ---- bars-per-day histogram ----------------------------------------
    print()
    print("  Bars-per-day histogram — the shape of the history")
    print()
    hist = Counter(per_day.values())
    print("      bars/day     days   share")
    print("      " + "-" * 34)
    for bars in sorted(hist):
        share = 100.0 * hist[bars] / total_days
        bar = "#" * int(share / 2)
        print(f"      {bars:>8}   {hist[bars]:>6}   {share:>5.1f}%  {bar}")
    note("A bimodal shape (a spike near 1 and another near 23-24) means")
    note("the feed is sparse early and dense later — one span, two datasets.")


def report_discrepancy(rates: Any, n_daily_breaks: int) -> None:
    """Reconcile the daily-break count against the full-week count.

    The previous run reported 1,078 daily session breaks and 535 full weeks.
    535 full weeks implies roughly 2,675 dense days, and if every dense day
    carried exactly one one-bar break there would be ~2,675 breaks. The two
    numbers disagree by a factor of about 2.5, and that gap is not
    interpretable from aggregates alone.

    This function tests the candidate explanations against the data rather
    than choosing between them by argument.

    Args:
        rates: Full H1 rate array, or ``None``.
        n_daily_breaks: Daily-break count from the gap census.
    """
    header("2b. DISCREPANCY — daily breaks vs full weeks, reconciled")

    if rates is None or len(rates) == 0:
        print("  no H1 history")
        return

    times = [to_naive(r["time"]) for r in rates]
    per_day: Counter[Any] = Counter(t.date() for t in times)
    dense_days = [d for d, c in per_day.items() if c >= DENSE_DAY_MIN_BARS]

    per_week = Counter(t.isocalendar()[:2] for t in times)
    week_counts = sorted(per_week.values())
    week_median = week_counts[len(week_counts) // 2] if week_counts else 0
    n_full_weeks = sum(1 for c in week_counts if c >= week_median * 0.9)

    row("daily breaks (gap census)", f"{n_daily_breaks:,}")
    row("bars/week median [MEASURED]", f"{week_median:,}")
    row("full weeks (>=90% median)", f"{n_full_weeks:,}")
    row("dense days [MEASURED]", f"{len(dense_days):,}")
    print()

    # Candidate 1: many dense days simply have no break at all (24 bars).
    full_24 = sum(1 for d in dense_days if per_day[d] == 24)
    with_23 = sum(1 for d in dense_days if per_day[d] == 23)
    other = len(dense_days) - full_24 - with_23
    print("  Dense days by bar count — the population the breaks come from")
    print()
    row("exactly 24 bars (no break)", f"{full_24:,}")
    row("exactly 23 bars (one break)", f"{with_23:,}")
    row("some other count", f"{other:,}")
    if full_24 > with_23:
        note("Most dense days carry a full 24 bars, so most days have no")
        note("session break at all. A break count far below the dense-day")
        note("count is then the expected result, not an anomaly.")
    else:
        note("Most dense days are short of 24 bars, so a break on nearly")
        note("every day is the expected result and a low break count is")
        note("the thing needing explanation.")

    # Candidate 2: the break hour moves, so breaks land at more than one hour.
    print()
    single_gap_hours: Counter[int] = Counter()
    step = timedelta(hours=1)
    for prev, nxt in pairwise(times):
        if nxt - prev == step * 2:
            single_gap_hours[prev.hour] += 1
    total_single = sum(single_gap_hours.values())
    if single_gap_hours:
        print("  Hour-of-day distribution of every 1-bar gap [MEASURED]:")
        ranked = sorted(single_gap_hours.items(), key=lambda kv: -kv[1])
        for hour, count in ranked[:6]:
            share = 100.0 * count / total_single
            print(f"      server hour {hour:02d}   {count:>6,}   {share:>5.1f}%")
        material = [
            (h, c) for h, c in ranked if c >= BREAK_HOUR_MIN_SHARE * total_single
        ]
        covered = sum(c for _, c in material)
        share = 100.0 * covered / total_single
        if len(material) == 1:
            note(f"A single hour carries {share:.1f}% of all 1-bar gaps, so the")
            note("break does not move. Anything at another hour is a candidate")
            note("defect rather than a session break.")
        else:
            hours_text = ", ".join(f"{h:02d}" for h, _ in material)
            missed = total_single - ranked[0][1]
            note(f"The break MOVES: hours {hours_text} each carry at least")
            note(f"{BREAK_HOUR_MIN_SHARE:.0%} of 1-bar gaps, {share:.1f}% together.")
            note("Keying the census on the modal hour alone would refile the")
            note(f"remaining {missed:,} breaks as in-session holes.")

    # Candidate 3: Friday breaks are absorbed into the weekend gap.
    print()
    fri_dense = sum(1 for d in dense_days if d.weekday() == 4)
    fri_short = sum(1 for d in dense_days if d.weekday() == 4 and per_day[d] < 24)
    row("dense Fridays", f"{fri_dense:,}")
    row("  of which short of 24 bars", f"{fri_short:,}")
    note("A Friday break falls at the weekly close and merges into the")
    note("weekend gap, so it is never counted as a separate 1-bar gap.")

    # The ledger. State the residual as a number rather than asserting that
    # the three effects above are sufficient.
    print()
    print("  Reconciliation [MEASURED]")
    print()
    row("dense days", f"{len(dense_days):,}")
    row("less: days with a full 24 bars", f"-{full_24:,}")
    row("= days that should show a break", f"{len(dense_days) - full_24:,}")
    row("less: dense Fridays short of 24", f"-{fri_short:,}")
    row("= expected 1-bar gaps", f"{len(dense_days) - full_24 - fri_short:,}")
    row("observed 1-bar gaps", f"{total_single:,}")
    residual = total_single - (len(dense_days) - full_24 - fri_short)
    row("RESIDUAL (observed - expected)", f"{residual:+,}")
    print()
    if residual == 0:
        note("The residual is zero: the three effects account for the count")
        note("exactly, and there is nothing left to explain.")
    else:
        note(f"A residual of {residual:+,} remains. It CANNOT be resolved from")
        note("bar timestamps alone — separating a broker holiday schedule")
        note("from a genuine hole needs the broker's own session calendar,")
        note("which MT5 does not expose through this API. Ingestion must")
        note("therefore treat these as unknown-cause and mark them invalid")
        note("under DATA_CONTRACT §6 rather than classify them.")


def report_spread_coverage(rates: Any) -> None:
    """Report what fraction of bars carry a non-zero spread value, per year.

    A zero may mean *unrecorded* rather than corrupt. "The field starts being
    populated in year X" is a statement about recording depth, and it is
    different from "the field is contaminated" — the previous run conflated
    them by reporting only a global min of 0.

    Args:
        rates: Full H1 rate array, or ``None``.
    """
    header("2c. SPREAD FIELD — recording depth by year")

    if rates is None or len(rates) == 0:
        print("  no H1 history")
        return

    by_year: dict[int, list[int]] = {}
    for r in rates:
        by_year.setdefault(to_naive(r["time"]).year, []).append(int(r["spread"]))

    print("      year      bars   non-zero   cover%    min    med    max")
    print("      " + "-" * 60)
    for year in sorted(by_year):
        values = by_year[year]
        nonzero = [v for v in values if v > 0]
        cover = 100.0 * len(nonzero) / len(values)
        med = sorted(nonzero)[len(nonzero) // 2] if nonzero else 0
        print(
            f"      {year}   {len(values):>7,}   {len(nonzero):>8,}   "
            f"{cover:>5.1f}%   {min(values):>4}   {med:>4}   {max(values):>4}"
        )
    print()
    note("Cover jumping from ~0% to ~100% in a given year means the broker")
    note("began recording the field then — that is recording depth, not")
    note("corruption. Cover that is high but patchy is a different problem.")
    note("Either way EVALUATION.md §10 forbids using this as a cost input:")
    note("it is the spread at bar-record time, not what you would have paid.")


# --------------------------------------------------------------------------
# 6. Server-time offset
# --------------------------------------------------------------------------


def report_offset(mt5: Any, symbol: str, rates: Any) -> None:
    """Measure the server-time offset from UTC, and look for DST transitions.

    The live offset is derived from the most recent tick: MT5 reports server
    wall-clock time as a Unix epoch, so interpreting it as UTC and comparing
    against true UTC yields the offset directly. This is only valid while the
    market is open — a stale tick measures staleness, not offset, and that
    case is detected and reported rather than silently returning a wrong
    number.

    Historical DST transitions cannot be derived from bar timestamps alone,
    because a server-time series looks identical either side of a shift. What
    *is* visible is the transition day itself: it carries one bar more or
    fewer than a normal day. Those dates are reported as candidates.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        rates: Full H1 rate array, or ``None``.
    """
    header("6. TIMESTAMPS — server-time offset from UTC (measured)")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None or tick.time == 0:
        print("  no tick available — cannot measure the live offset")
    else:
        server = to_naive(tick.time)
        utc_now = datetime.now(UTC).replace(tzinfo=None)
        delta_h = (server - utc_now).total_seconds() / 3600.0
        row("last tick (server clock)", fmt_time(server))
        row("now (true UTC)", fmt_time(utc_now))
        row("measured offset", f"UTC{delta_h:+.2f}h")
        row("nearest whole hour", f"UTC{round(delta_h):+d}")
        staleness = abs(delta_h - round(delta_h)) * 60
        if staleness > 5:
            print()
            note("WARNING: the last tick is more than 5 minutes off a whole")
            note("hour. The market is probably closed and this measures tick")
            note("staleness, not the offset. Re-run during market hours.")

    if rates is None or len(rates) == 0:
        return

    times = [to_naive(r["time"]) for r in rates]
    per_day = Counter(t.date() for t in times)
    # Interior weekdays only: Fri and Sun are partial by design, and Mon can
    # be truncated by the weekly open, so including them would bury the
    # one-bar DST signal in ordinary week-boundary noise.
    interior = {d: c for d, c in per_day.items() if d.weekday() in (1, 2, 3)}
    if not interior:
        return

    modal = Counter(interior.values()).most_common(1)[0][0]
    anomalies = sorted(d for d, c in interior.items() if abs(c - modal) == 1)

    print()
    row("modal bars on Tue/Wed/Thu", modal)
    row("days at modal +/- 1 bar", len(anomalies))
    note("Candidate DST transition days — a shift makes one day 23h or 25h.")
    note("This check is WEAK and finds nothing when transitions fall on a")
    note("Sunday, which is where both the US and EU rules put them. A count")
    note("of zero here is not evidence of a fixed clock. Section 6b is the")
    note("authoritative test; this one only catches a midweek shift.")
    if anomalies:
        by_year: dict[int, list[str]] = {}
        for day in anomalies:
            by_year.setdefault(day.year, []).append(day.isoformat())
        for year in sorted(by_year):
            shown = ", ".join(by_year[year][:6])
            more = len(by_year[year]) - 6
            print(f"      {year}: {shown}{f'  (+{more} more)' if more > 0 else ''}")
        note("Two per year in spring/autumn => the server observes DST.")
        note("Many scattered dates => these are data gaps, not DST.")


# --------------------------------------------------------------------------
# 6b. DST fingerprint
# --------------------------------------------------------------------------

WEEKEND_GAP_MIN_HOURS = 24
SUNDAY = 6  # date.weekday(): Monday is 0
# A bucket with fewer weeks than this cannot support a modal hour worth
# reading. The EU/US disagreement window supplies only ~4 weeks a year, so
# this is the binding constraint on the test and the reason it needs several
# dense years rather than one.
MIN_WEEKS_PER_BUCKET = 8


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the ``n``-th ``weekday`` of a month (1-based).

    Args:
        year: Calendar year.
        month: Calendar month.
        weekday: ``date.weekday()`` value, 0 = Monday.
        n: Which occurrence, 1-based.

    Returns:
        The date.
    """
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last ``weekday`` of a month.

    Args:
        year: Calendar year.
        month: Calendar month.
        weekday: ``date.weekday()`` value, 0 = Monday.

    Returns:
        The date.
    """
    day_after = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = day_after - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def us_is_summer(day: date) -> bool:
    """Whether New York is on daylight time (EDT) on ``day``.

    Second Sunday in March through the first Sunday in November. That rule
    has been in force since 2007; the test restricts itself to dense years,
    which begin well after that, so the pre-2007 rule is not implemented and
    must not be inferred from this function.

    Args:
        day: A calendar date.

    Returns:
        True if New York is on daylight time.
    """
    start = nth_weekday(day.year, 3, SUNDAY, 2)
    end = nth_weekday(day.year, 11, SUNDAY, 1)
    return start <= day < end


def eu_is_summer(day: date) -> bool:
    """Whether Europe is on summer time on ``day``.

    Last Sunday in March through the last Sunday in October, unchanged since
    1996 across the EU.

    Args:
        day: A calendar date.

    Returns:
        True if Europe is on summer time.
    """
    start = last_weekday(day.year, 3, SUNDAY)
    end = last_weekday(day.year, 10, SUNDAY)
    return start <= day < end


BOTH_WINTER = "both winter"
BOTH_SUMMER = "both summer"
MISMATCH = "US summer / EU winter"
IMPOSSIBLE = "US winter / EU summer"


def dst_bucket(day: date) -> str:
    """Classify a date by the joint US/EU daylight-saving state.

    Both transitions complete before the Sunday-evening New York session
    open (US at 02:00 local, EU at 01:00 UTC), so classifying by the open's
    own date needs no special case for transition weekends.

    Args:
        day: A calendar date.

    Returns:
        One of the four bucket constants.
    """
    us, eu = us_is_summer(day), eu_is_summer(day)
    if us and eu:
        return BOTH_SUMMER
    if not us and not eu:
        return BOTH_WINTER
    return MISMATCH if us else IMPOSSIBLE


def weekly_opens(rates: Any) -> list[datetime]:
    """Return the first bar of each trading week, in server time.

    Args:
        rates: Full H1 rate array.

    Returns:
        Server-time datetimes of weekly session opens.
    """
    times = [to_naive(r["time"]) for r in rates]
    opens: list[datetime] = []
    for prev, nxt in pairwise(times):
        if (nxt - prev) >= timedelta(hours=WEEKEND_GAP_MIN_HOURS):
            opens.append(nxt)
    return opens


def report_dst_fingerprint(rates: Any) -> None:
    """Determine whether the server clock is fixed, US-DST, or EU-DST.

    **Standing assumption, and the test is void without it:** the weekly
    session open is anchored to a fixed *local New York* time (Sunday 17:00
    ET), which is the spot FX and metals convention. The market's clock is
    the only reference available inside the bar timestamps — they are already
    in server time and carry no UTC anchor — so the whole method is a
    comparison of the server clock against the New York clock. If this broker
    sets its session boundaries on its own local calendar instead, the result
    below is meaningless rather than merely uncertain.

    Given that anchor, the three candidate server clocks are separable,
    because the US and EU transition on different dates:

    ===================  ==============  ==============  ==============
    server clock         both winter     both summer     US-only summer
    ===================  ==============  ==============  ==============
    fixed offset         hour H          hour H-1        hour H-1
    tracks US DST        hour H          hour H          hour H
    tracks EU DST        hour H          hour H          hour H-1
    ===================  ==============  ==============  ==============

    Two comparisons decide it. Both-winter versus both-summer separates a
    fixed clock from any DST clock. The US-only-summer window — the ~3 weeks
    between the second and last Sunday in March, plus the ~1 week between the
    last Sunday in October and the first Sunday in November — then separates
    the EU rule from the US rule. That window is the entire discriminating
    signal and it is only about four weeks a year, which is why the test
    needs several dense years and reports UNDETERMINED rather than guessing
    when it does not have them.

    Run on dense years only. An earlier modal-bar variant of this check
    reported a modal interior-weekday count of 1 and detected nothing — it
    was defeated by the sparse early history, which is absence of a working
    test rather than absence of DST.

    Args:
        rates: Full H1 rate array, or ``None``.
    """
    header("6b. DST FINGERPRINT — which rule does the server clock follow?")

    if rates is None or len(rates) == 0:
        print("  no H1 history")
        return

    times = [to_naive(r["time"]) for r in rates]
    per_day: Counter[Any] = Counter(t.date() for t in times)
    dense_years = {
        year
        for year in {t.year for t in times}
        if sum(
            1 for d, c in per_day.items() if d.year == year and c >= DENSE_DAY_MIN_BARS
        )
        >= 150
    }
    if not dense_years:
        print("  no year carries >= 150 dense days — cannot run the test")
        note("VERDICT: UNDETERMINED — no dense year to run it on.")
        return

    row("dense years used", ", ".join(str(y) for y in sorted(dense_years)))
    note("Sparse years are excluded: one bar a day has no session open to")
    note("locate, so including them would dilute the modal hour with noise.")

    opens = [o for o in weekly_opens(rates) if o.year in dense_years]
    if not opens:
        print("  no weekly opens found in dense years")
        note("VERDICT: UNDETERMINED — no weekly opens located.")
        return

    buckets: dict[str, Counter[int]] = {
        BOTH_WINTER: Counter(),
        BOTH_SUMMER: Counter(),
        MISMATCH: Counter(),
        IMPOSSIBLE: Counter(),
    }
    for opened in opens:
        buckets[dst_bucket(opened.date())][opened.hour] += 1

    print()
    row("weekly opens examined [MEASURED]", f"{len(opens):,}")
    print()
    print("  Weekly-open hour in SERVER time, by joint US/EU daylight state")
    print("  — every number below is MEASURED.")
    print()
    print("      US/EU state              weeks   modal hour   purity")
    print("      " + "-" * 58)

    modal: dict[str, int | None] = {}
    for name in (BOTH_WINTER, BOTH_SUMMER, MISMATCH, IMPOSSIBLE):
        counts = buckets[name]
        total = sum(counts.values())
        if total == 0:
            modal[name] = None
            print(f"      {name:<22} {total:>7}            —        —")
            continue
        hour, hits = counts.most_common(1)[0]
        modal[name] = hour
        purity = 100.0 * hits / total
        print(f"      {name:<22} {total:>7}     {hour:02d}:00 srv   {purity:>5.1f}%")
    print()
    note("'purity' is the share of that bucket's weeks landing on its modal")
    note("hour. Low purity means missing Sunday bars are displacing the")
    note("detected open, not that the clock is unstable.")

    if buckets[IMPOSSIBLE]:
        print()
        note(f"{sum(buckets[IMPOSSIBLE].values())} weeks fell in the")
        note("US-winter/EU-summer state, which the two calendars make")
        note("impossible. Treat the whole section as suspect if this is")
        note("more than a handful.")

    winter_hour, summer_hour = modal[BOTH_WINTER], modal[BOTH_SUMMER]
    mismatch_hour = modal[MISMATCH]
    n_mismatch = sum(buckets[MISMATCH].values())

    print()
    if winter_hour is None or summer_hour is None:
        verdict = "UNDETERMINED"
        detail = [
            "One of the two matched-season buckets is empty, so the first",
            "comparison cannot even be made. More history is needed.",
        ]
    elif winter_hour != summer_hour:
        verdict = "FIXED OFFSET (server clock does not observe DST)"
        detail = [
            f"The open moves from {winter_hour:02d}:00 in winter to "
            f"{summer_hour:02d}:00 in summer.",
            "New York moves and the server does not, so conversion to UTC",
            "uses one constant offset for the whole span — the offset that",
            "section 6 measures live is that constant.",
        ]
    elif n_mismatch < MIN_WEEKS_PER_BUCKET:
        verdict = "UNDETERMINED — DST yes, rule not separable"
        detail = [
            f"The open hour is constant at {winter_hour:02d}:00 across both",
            "matched seasons, so the server clock does track New York and is",
            "not a fixed offset.",
            f"But only {n_mismatch} weeks fall in the US-only-summer window,",
            f"below the {MIN_WEEKS_PER_BUCKET} needed to read a modal hour,",
            "so US rule and EU rule cannot be told apart from this history.",
        ]
    elif mismatch_hour != winter_hour:
        verdict = "TRACKS DST — EU RULE"
        detail = [
            f"Constant at {winter_hour:02d}:00 whenever both calendars agree,",
            f"and {mismatch_hour:02d}:00 in the weeks where New York has",
            "changed and Europe has not.",
            "That is exactly the European transition-date signature.",
            "Conversion to UTC needs two offsets and the EU switch dates.",
        ]
    else:
        verdict = "TRACKS DST — US RULE"
        detail = [
            f"Constant at {winter_hour:02d}:00 in every state, including the",
            f"{n_mismatch} weeks where New York changed and Europe had not.",
            "The server therefore switches on the American dates.",
            "Conversion to UTC needs two offsets and the US switch dates.",
        ]

    row("VERDICT", verdict)
    for line in detail:
        note(line)

    # The residual, and the one test that makes it interpretable. A missing
    # Sunday-evening bar can only push the *detected* open later than the
    # true one; nothing absent from the feed can make an open appear early.
    # So a late residual is a data gap and a holiday-shortened week, while an
    # early residual means the clock moved in a way this model does not
    # capture — and that invalidates the verdict rather than qualifying it.
    off_modal = [
        o
        for o in opens
        if modal[dst_bucket(o.date())] is not None
        and o.hour != modal[dst_bucket(o.date())]
    ]
    if off_modal:
        early = [o for o in off_modal if o.hour < (modal[dst_bucket(o.date())] or 0)]
        print()
        print(f"  Weekly opens away from their bucket's modal hour ({len(off_modal)}):")
        print("      date                  server hour   direction   US/EU state")
        print("      " + "-" * 66)
        for o in sorted(off_modal)[:20]:
            bucket = dst_bucket(o.date())
            hour = modal[bucket] or 0
            direction = "EARLY" if o.hour < hour else "late"
            print(
                f"      {fmt_time(o)}   {o.hour:02d}:00       {direction:<9}   {bucket}"
            )
        if len(off_modal) > 20:
            note(f"... and {len(off_modal) - 20} more")
        print()
        row("residual opening LATE", f"{len(off_modal) - len(early):,}")
        row("residual opening EARLY", f"{len(early):,}")
        if early:
            note("An EARLY open cannot be produced by a missing bar — absence")
            note("can only delay the first bar seen, never advance it. These")
            note("weeks mean the server clock moved in a way the three-rule")
            note("model does not describe. DO NOT USE the verdict above.")
        else:
            note("Every residual opens late, which is what a missing Sunday-")
            note("evening bar or a holiday-shortened week produces. None can")
            note("be a clock movement, so none contradicts the verdict.")

    print()
    note("Whatever this says, ingestion must FREEZE the derived rule as a")
    note("committed artifact and assert against it — a rule re-derived from")
    note("the data it validates can never detect that the broker changed it.")


# --------------------------------------------------------------------------
# 4. Spread availability
# --------------------------------------------------------------------------


def report_spread(mt5: Any, symbol: str, earliest_tick_at: datetime | None) -> None:
    """Report whether historical spread is recoverable, and from when.

    Two independent things are checked, because one of them is a trap. The
    ``spread`` field on bars looks like a historical spread series and
    generally is not — it is frequently zero or constant on backfilled
    history. The only genuine source is tick data carrying both bid and ask.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        earliest_tick_at: Earliest tick timestamp, or ``None``.
    """
    header("4. SPREAD — is historical spread recoverable at all?")

    info = mt5.symbol_info(symbol)
    point = info.point if info else 0.0

    print("  (a) the `spread` field on H1 bars")
    now = datetime.now(UTC).replace(tzinfo=None)
    rates = mt5.copy_rates_range(
        symbol, mt5.TIMEFRAME_H1, now - timedelta(days=365), now
    )
    if rates is None or len(rates) == 0:
        note("no recent H1 bars returned")
    else:
        values = [int(r["spread"]) for r in rates]
        distinct = sorted(set(values))
        row("bars sampled", f"{len(values):,}")
        row("distinct spread values", len(distinct))
        row("min / max (points)", f"{min(values)} / {max(values)}")
        if len(distinct) <= 1:
            note("Constant or zero => UNUSABLE as a historical spread series.")
        else:
            note("Varies. Still per-bar-recording, not what you would pay;")
            note("treat as indicative only, never as the cost model input.")

    print()
    print("  (b) tick data with genuine bid/ask")
    if earliest_tick_at is None:
        note("NO TICK HISTORY AT ALL — spread is not recoverable.")
        note("The §10 cost model must then be bounded, not calibrated:")
        note("  - floor from forward tick capture started now;")
        note("  - event multipliers from the calendar, not from spread data;")
        note("  - rely on §11's 1x-5x sweep and K-5's doubling test.")
        return

    row("earliest tick", fmt_time(earliest_tick_at))
    print()
    print("      date          ticks   bid&ask%   median sp.   p95 sp.")
    print("      " + "-" * 56)

    # Samples run most-recent first, so the *last* window that still shows
    # usable bid/ask is the oldest one — hence plain assignment rather than
    # first-wins, which would report today and say nothing.
    earliest_valid: datetime | None = None
    for days_back in SPREAD_SAMPLE_DAYS:
        # The window looks backward from the sample point. Anchoring it
        # forward would make the days_back=0 sample straddle the future and
        # return a handful of ticks.
        end_at = now - timedelta(days=days_back)
        start = end_at - timedelta(days=TICK_PROBE_WINDOW_DAYS)
        if end_at < earliest_tick_at:
            continue
        ticks = mt5.copy_ticks_range(symbol, start, end_at, mt5.COPY_TICKS_INFO)
        if ticks is None or len(ticks) == 0:
            print(f"      {start.date()}   {'(none)':>7}")
            continue

        spreads = [
            float(t["ask"]) - float(t["bid"])
            for t in ticks
            if float(t["bid"]) > 0.0 and float(t["ask"]) > 0.0
        ]
        pct = 100.0 * len(spreads) / len(ticks)
        if spreads:
            spreads.sort()
            median = spreads[len(spreads) // 2]
            p95 = spreads[int(len(spreads) * 0.95)]
            in_points = f"{median / point:>8.1f}" if point else f"{median:>8.5f}"
            p95_points = f"{p95 / point:>7.1f}" if point else f"{p95:>7.5f}"
            print(
                f"      {start.date()}   {len(ticks):>7,}   {pct:>7.1f}%   "
                f"{in_points}   {p95_points}"
            )
            if pct > 50.0:
                earliest_valid = start
        else:
            print(f"      {start.date()}   {len(ticks):>7,}   {pct:>7.1f}%   bid-only")

    print()
    if earliest_valid is None:
        note("No sampled window had usable bid/ask — treat spread as absent.")
    else:
        note(f"Usable bid/ask observed back to at least {earliest_valid.date()}.")
        unit = "points" if point else "price units"
        note(f"Spread columns are in {unit}. This is what §10 can calibrate")
        note("from; everything older than that date must be bounded instead.")


# --------------------------------------------------------------------------
# 5. Gap census
# --------------------------------------------------------------------------


def report_gaps(rates: Any) -> int:
    """Classify gaps in the H1 series, and return the daily-break count.

    ``DATA_CONTRACT.md`` §6 forbids silent imputation, which is only
    actionable if a missing bar can be distinguished from a closed market.
    Weekend and daily-break closures are expected and must not be filled;
    a hole inside an open session is a data defect and must be marked
    invalid. Conflating the two either buries real defects or floods the log
    with false alarms.

    The daily-break hour is derived from the data rather than assumed, on the
    same principle as the DST rule — and it is derived as a *set* of hours,
    not one. A server clock on the European rule puts the daily break at one
    server hour for most of the year and one hour earlier during the weeks
    when New York has changed over and Europe has not. Keying on the single
    modal hour therefore refiles every break in those weeks as an in-session
    hole: roughly a hundred and sixty false defects per decade, all of them
    landing in March and late October, which is precisely where a reader
    looking for a DST artefact would find them and mistake them for one.

    Args:
        rates: Full H1 rate array, or ``None``.

    Returns:
        Count of gaps classified as daily session breaks.
    """
    header("5. GAPS — closures vs. missing bars inside an open session")

    if rates is None or len(rates) < 2:
        print("  insufficient H1 history for a gap census")
        return 0

    times = [to_naive(r["time"]) for r in rates]
    step = timedelta(hours=1)

    gaps: list[tuple[datetime, datetime, int]] = []
    for prev, nxt in pairwise(times):
        delta = nxt - prev
        if delta > step:
            gaps.append((prev, nxt, int(delta / step) - 1))

    if not gaps:
        print("  no gaps at all — every consecutive bar is exactly 1h apart")
        return 0

    single = [g for g in gaps if g[2] == 1]
    single_by_hour: Counter[int] = Counter(g[0].hour for g in single)
    # Every hour holding at least this share of all one-bar gaps is a session
    # break, not a defect. The threshold is deliberately far below the ~6%
    # a DST-mismatch hour carries, and far above the share any scattered
    # data hole reaches.
    break_hours = {
        hour
        for hour, count in single_by_hour.items()
        if count >= BREAK_HOUR_MIN_SHARE * len(single)
    }

    weekend = daily = holiday = suspicious = 0
    suspicious_list: list[tuple[datetime, datetime, int]] = []
    for start, end, missing in gaps:
        spans_saturday = any(
            (start.date() + timedelta(days=d)).weekday() == 5
            for d in range((end.date() - start.date()).days + 1)
        )
        if spans_saturday:
            weekend += 1
        elif missing == 1 and start.hour in break_hours:
            daily += 1
        elif missing >= HOLIDAY_MIN_MISSING_BARS:
            holiday += 1
        else:
            suspicious += 1
            suspicious_list.append((start, end, missing))

    row("total gaps", len(gaps))
    print()
    row("weekend closures", weekend)
    hours_text = ", ".join(f"{h:02d}" for h in sorted(break_hours))
    row(
        "daily session breaks",
        f"{daily}" + (f"  (at server hour {hours_text})" if daily else ""),
    )
    if len(break_hours) > 1:
        note("More than one break hour. That is the DST signature, not a")
        note("defect — see section 6b. Classifying on the modal hour alone")
        note("would have reported the rest as in-session holes.")
    row(f"holiday-scale (>={HOLIDAY_MIN_MISSING_BARS} bars)", holiday)
    row("SUSPICIOUS (in-session holes)", suspicious)

    largest = max(gaps, key=lambda g: g[2])
    print()
    row("largest gap (bars missing)", largest[2])
    row("  from", fmt_time(largest[0]))
    row("  to", fmt_time(largest[1]))

    if suspicious_list:
        suspicious_list.sort(key=lambda g: g[2], reverse=True)
        print()
        print(f"  Largest in-session holes (top {SUSPICIOUS_GAPS_TO_LIST}):")
        print("      from                  to                    missing")
        print("      " + "-" * 56)
        for start, end, missing in suspicious_list[:SUSPICIOUS_GAPS_TO_LIST]:
            print(f"      {fmt_time(start)}   {fmt_time(end)}   {missing:>7}")
        print()
        note("These are candidate data defects. Under §6 they are marked")
        note("invalid and their decisions excluded — never forward-filled.")
    else:
        print()
        note("No unexplained in-session holes. Every gap is a market closure.")

    return daily


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------


def report_verdict(depth: dict[str, datetime | None], rates: Any) -> None:
    """Summarise what the measured history supports.

    Every count here is measured. The previous version multiplied a median
    weekly bar count by the span in years and printed the product as "total
    independent decisions" — an extrapolation presented as a measurement,
    which on this feed overstated the truth by 63% because the early history
    is sparse. The only estimate that remains is the per-year rate implied by
    the dense period, and it is labelled.

    Args:
        depth: Earliest timestamps by series.
        rates: Full H1 rate array, or ``None``.
    """
    header("VERDICT — what this history supports")

    h1 = depth.get("H1")
    if h1 is None or rates is None or len(rates) == 0:
        print("  no H1 history — the data layer cannot be designed on this feed")
        return

    times = [to_naive(r["time"]) for r in rates]
    per_day: Counter[Any] = Counter(t.date() for t in times)
    dense_days = [d for d, c in per_day.items() if c >= DENSE_DAY_MIN_BARS]
    dense_bars = sum(c for d, c in per_day.items() if c >= DENSE_DAY_MIN_BARS)

    total_decisions = len(times) // 24
    dense_decisions = dense_bars // 24

    row("total H1 bars [MEASURED]", f"{len(times):,}")
    row("bars on dense days [MEASURED]", f"{dense_bars:,}")
    row("dense days [MEASURED]", f"{len(dense_days):,}")
    print()
    row("decisions, all bars [MEASURED]", f"{total_decisions:,}")
    row("decisions, dense only [MEASURED]", f"{dense_decisions:,}")
    note("Both are counted, not extrapolated. The dense-only figure is the")
    note("conservative one: sparse stretches cannot support 24-bar labels.")

    if dense_days:
        span_dense = (max(dense_days) - min(dense_days)).days / 365.25
        if span_dense > 0:
            print()
            row(
                "dense-period span [MEASURED]",
                f"{span_dense:.2f} years ({min(dense_days)} to {max(dense_days)})",
            )
            row(
                "decisions/year over that span [ESTIMATE]",
                f"{dense_decisions / span_dense:.0f}",
            )
            note("Labelled an estimate: it divides a measured count by a")
            note("measured span and assumes the rate is uniform within it.")

    # Gates are evaluated on the conservative (dense-only) count.
    print()
    print("  Protocol requirements, against the DENSE-ONLY count:")
    checks = [
        ("pooled walk-forward >= 150 (K-6)", dense_decisions * 0.8 >= 150),
        ("each of 5 folds >= 150", dense_decisions * 0.8 / 5 >= 150),
        ("sealed holdout (20%) >= 150", dense_decisions * 0.2 >= 150),
    ]
    for label, ok in checks:
        row(label, "YES" if ok else "NO")

    pre_2022 = sum(1 for d in dense_days if d.year < 2022)
    post_2022 = sum(1 for d in dense_days if d.year >= 2022)
    row(
        "spans 2022 for the §11 regime split", "YES" if pre_2022 and post_2022 else "NO"
    )
    note(f"dense days pre-2022: {pre_2022:,}   post-2022: {post_2022:,}")
    note("Both sides need enough dense days to carry their own decisions —")
    note("a split that spans 2022 on paper but is sparse on one side cannot")
    note("support the regime-shift test that §11 calls the harshest stress.")

    print()
    if all(ok for _, ok in checks) and pre_2022 and post_2022:
        note("Full protocol is runnable at H=24 on the dense portion.")
    else:
        note("At least one requirement fails on the dense-only count. That is")
        note("a FINDING to be reported, not a constraint to design around.")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    """Run every probe and print the report.

    Returns:
        Process exit code.
    """
    mt5 = require_windows_mt5()

    print("=" * WIDTH)
    print("MT5 HISTORY PROBE — measurement only, nothing is written or ingested")
    print("=" * WIDTH)
    print(f"  run at (true UTC) ................ {datetime.now(UTC).isoformat()}")
    print(f"  python ........................... {sys.version.split()[0]}")
    print(f"  platform ......................... {platform.platform()}")

    if not mt5.initialize():
        print()
        print(f"FATAL: mt5.initialize() failed: {mt5.last_error()}")
        print("  Is the MT5 terminal running and logged in?")
        return 2

    try:
        symbol = resolve_symbol(mt5, sys.argv[1] if len(sys.argv) > 1 else None)
        report_identity(mt5, symbol)

        print()
        print("  (depth probing walks back year by year; this takes a minute)")
        depth = report_depth(mt5, symbol)

        rates = fetch_all_h1(mt5, symbol, depth.get("H1"))
        report_density(rates)
        report_spread_coverage(rates)
        report_spread(mt5, symbol, depth.get("tick"))
        daily_breaks = report_gaps(rates)
        report_discrepancy(rates, daily_breaks)
        report_offset(mt5, symbol, rates)
        report_dst_fingerprint(rates)
        report_verdict(depth, rates)

        print()
        print("=" * WIDTH)
        print("END OF REPORT — paste everything above this line")
        print("=" * WIDTH)
    finally:
        mt5.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
