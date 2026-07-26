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
from datetime import UTC, datetime, timedelta
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
# 2. Counts and observed bars-per-week
# --------------------------------------------------------------------------


def report_counts(mt5: Any, symbol: str, earliest_h1: datetime | None) -> Any:
    """Report total H1 bar count and bars actually observed per week.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        earliest_h1: Earliest H1 timestamp, from :func:`report_depth`.

    Returns:
        The full H1 rate array, or ``None``.
    """
    header("2. VOLUME — H1 bar count and observed bars per week")

    if earliest_h1 is None:
        print("  no H1 history — nothing to count")
        return None

    now = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, earliest_h1, now)
    if rates is None or len(rates) == 0:
        print("  H1 range request returned nothing")
        return None

    times = [to_naive(r["time"]) for r in rates]
    row("total H1 bars", f"{len(times):,}")
    row("first bar (server time)", fmt_time(times[0]))
    row("last bar (server time)", fmt_time(times[-1]))
    span_years = (times[-1] - times[0]).days / 365.25
    row("span", f"{span_years:.2f} years")

    per_week = Counter(t.isocalendar()[:2] for t in times)
    counts = sorted(per_week.values())
    if counts:
        median = counts[len(counts) // 2]
        full = [c for c in counts if c >= median * 0.9]
        print()
        row("weeks observed", len(counts))
        row("bars/week  median", median)
        row("bars/week  mean", f"{sum(counts) / len(counts):.1f}")
        row("bars/week  min", counts[0])
        row("bars/week  max", counts[-1])
        row("full weeks (>=90% of median)", len(full))
        note("Median is the honest figure — holidays drag the mean down.")
        print()
        row("=> decisions/year at H=24", f"{median * 52 / 24:.0f}")
        note("Non-overlapping decisions. K-6 needs >= 150 per evaluation window.")

    return rates


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


def report_gaps(rates: Any) -> None:
    """Classify gaps in the H1 series.

    ``DATA_CONTRACT.md`` §6 forbids silent imputation, which is only
    actionable if a missing bar can be distinguished from a closed market.
    Weekend and daily-break closures are expected and must not be filled;
    a hole inside an open session is a data defect and must be marked
    invalid. Conflating the two either buries real defects or floods the log
    with false alarms.

    The daily-break hour is derived from the data rather than assumed, on the
    same principle as the DST rule.

    Args:
        rates: Full H1 rate array, or ``None``.
    """
    header("5. GAPS — closures vs. missing bars inside an open session")

    if rates is None or len(rates) < 2:
        print("  insufficient H1 history for a gap census")
        return

    times = [to_naive(r["time"]) for r in rates]
    step = timedelta(hours=1)

    gaps: list[tuple[datetime, datetime, int]] = []
    for prev, nxt in pairwise(times):
        delta = nxt - prev
        if delta > step:
            gaps.append((prev, nxt, int(delta / step) - 1))

    if not gaps:
        print("  no gaps at all — every consecutive bar is exactly 1h apart")
        return

    single = [g for g in gaps if g[2] == 1]
    break_hour = None
    if single:
        break_hour = Counter(g[0].hour for g in single).most_common(1)[0][0]

    weekend = daily = holiday = suspicious = 0
    suspicious_list: list[tuple[datetime, datetime, int]] = []
    for start, end, missing in gaps:
        spans_saturday = any(
            (start.date() + timedelta(days=d)).weekday() == 5
            for d in range((end.date() - start.date()).days + 1)
        )
        if spans_saturday:
            weekend += 1
        elif missing == 1 and break_hour is not None and start.hour == break_hour:
            daily += 1
        elif missing >= HOLIDAY_MIN_MISSING_BARS:
            holiday += 1
        else:
            suspicious += 1
            suspicious_list.append((start, end, missing))

    row("total gaps", len(gaps))
    print()
    row("weekend closures", weekend)
    row(
        "daily session breaks",
        f"{daily}" + (f"  (break at server hour {break_hour:02d})" if daily else ""),
    )
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


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------


def report_verdict(depth: dict[str, datetime | None], rates: Any) -> None:
    """Summarise what the measured depth permits.

    Args:
        depth: Earliest timestamps by series.
        rates: Full H1 rate array, or ``None``.
    """
    header("VERDICT — what this history supports")

    now = datetime.now(UTC).replace(tzinfo=None)
    h1 = depth.get("H1")
    if h1 is None or rates is None or len(rates) == 0:
        print("  no H1 history — the data layer cannot be designed on this feed")
        return

    times = [to_naive(r["time"]) for r in rates]
    per_week = Counter(t.isocalendar()[:2] for t in times)
    counts = sorted(per_week.values())
    median_week = counts[len(counts) // 2] if counts else 0
    years = (now - h1).days / 365.25
    per_year = median_week * 52 / 24
    total = per_year * years

    row("history span", f"{years:.2f} years")
    row("decisions/year at H=24", f"{per_year:.0f}")
    row("total independent decisions", f"{total:.0f}")
    print()

    checks = [
        ("pooled walk-forward >= 150 (K-6)", total * 0.8 >= 150),
        ("each of 5 folds >= 150", total * 0.8 / 5 >= 150),
        ("sealed holdout (20%) >= 150", total * 0.2 >= 150),
        ("spans 2022 for the §11 regime split", h1.year < 2022),
    ]
    for label, ok in checks:
        row(label, "YES" if ok else "NO")

    print()
    if all(ok for _, ok in checks):
        note("Full protocol is runnable at H=24 on this feed.")
    else:
        note("At least one requirement fails. That is a FINDING, to be")
        note("reported — not a constraint to design around. The options are")
        note("consequential: deeper history, claims restricted to pooled")
        note("statistics only, or a finer bar interval — and the last changes")
        note("the label definition, which needs a hypothesis (RESEARCH §7).")


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

        rates = report_counts(mt5, symbol, depth.get("H1"))
        report_spread(mt5, symbol, depth.get("tick"))
        report_gaps(rates)
        report_offset(mt5, symbol, rates)
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
