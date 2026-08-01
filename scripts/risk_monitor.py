"""MT5 adapter for the risk and cost layer — reads, computes, tells you.

.. important::

   **This script reads. It never trades.** Every MetaTrader call it makes is a
   query or a pure calculation: ``account_info``, ``positions_get``,
   ``symbol_info``, ``symbol_info_tick``, ``history_deals_get``,
   ``copy_rates_from_pos``, ``terminal_info``, and ``order_calc_margin``, which
   computes a margin requirement and sends nothing. ``order_send`` does not
   appear in this repository, and ``tests/risk/test_scope.py`` fails the build
   if it ever does.

   It writes two things and nothing else: a heartbeat file and, if configured,
   an alert log. Both live where you point them.

What it does
------------

Reads one snapshot of the account, hands it to :mod:`risk.report`, and reports:

- what each open position has been charged in financing, and what it will cost
  to keep holding it;
- how long each position has been open, against a threshold;
- how many days of financing alone stand between the account and the broker's
  own stop-out level;
- the day's drawdown against a limit, and the number of open positions against
  a cap;
- **whether this broker's real financing rate exceeds the one registered in
  ``backtest.costs``**, which is a finding about the research registry rather
  than about the account, and is printed above the account's own figures.

It also sizes a position on request, from a risk percentage and a measured ATR.

What it does not do
-------------------

It predicts nothing. It has no view on direction, no signal, and no opinion on
whether a trade is a good idea. Its days-to-stop-out figure is arithmetic under
an explicitly stated constant-price assumption, not a forecast. See
``src/risk/__init__.py`` for the scope this layer is held to.

Running it
----------

Windows, with a logged-in MT5 terminal. The ``MetaTrader5`` package ships only
``win_amd64`` wheels. Credentials are never read and never needed: the script
attaches to a terminal that is already logged in, and the account login is
masked in every line it prints.

::

    python scripts/risk_monitor.py --probe     # read everything once, print it all
    python scripts/risk_monitor.py --once      # one reading, rendered, then exit
    python scripts/risk_monitor.py             # monitor, every 60 seconds
    python scripts/risk_monitor.py --status    # is the monitor alive, and
                                               # what did it last see
    python scripts/risk_monitor.py --size      # size a position at the configured risk

``--probe`` is the acceptance step. It prints every field it read, the
provenance of every derived number, and every refusal, so that the adapter can
be checked against a terminal before anything depends on it. **Run it on a demo
account first**: until it has been read against a live terminal once, this
adapter is unverified.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from risk.config import RiskConfig
from risk.notify import (
    Alert,
    AlertCode,
    FileNotifier,
    MultiNotifier,
    Notifier,
    Severity,
    StreamNotifier,
    ThrottledNotifier,
)
from risk.refusal import Refusal
from risk.render import render, render_one_line, severity_exit_code
from risk.report import RiskReport, build_report, deliver
from risk.sizing import SizingResult, size_position
from risk.state import (
    OFFSET_CACHED,
    OFFSET_EXPLICIT,
    OFFSET_MEASURED,
    OFFSET_UNAVAILABLE,
    AccountState,
    DealState,
    PositionDirection,
    PositionState,
    SymbolTerms,
    TerminalState,
    value_per_point_per_lot,
)
from risk.swap import DeclaredSwap, declared_swap

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

#: Tried in order when no symbol is named. Same list as ``mt5_probe.py``, which
#: is the instrument that established which of them this broker uses.
CANDIDATE_SYMBOLS: Final[tuple[str, ...]] = (
    "XAUUSD",
    "GOLD",
    "XAUUSD.pro",
    "XAUUSD.raw",
    "XAUUSD_",
    "XAUUSDm",
    "GOLD.spot",
    "XAUUSDc",
)

DEFAULT_INTERVAL_SECONDS: Final = 60.0
DEFAULT_STATE_DIR: Final = Path.home() / ".trading-risk"
HEARTBEAT_NAME: Final = "heartbeat.json"
ALERTS_NAME: Final = "alerts.jsonl"
CARRY_LOG_NAME: Final = "carry.jsonl"
OFFSET_CACHE_NAME: Final = "server-offset.json"

#: How far a tick may be from a whole-hour offset before the measurement is
#: treated as staleness rather than as a clock reading. Every MT5 server offset
#: seen in practice is a whole number of hours, so a fractional residual means
#: the last tick is old and the market is closed.
OFFSET_STALENESS_MINUTES: Final = 5.0

#: Days of deal history to fetch. Two, so that the current server day is fully
#: covered whatever the offset, with the filtering done in
#: :func:`risk.limits.daily_loss_status` against the real boundary.
DEAL_HISTORY_DAYS: Final = 2

#: Bars used for the ATR that sizing is scaled to. Wilder's ATR is recursive,
#: so more history than the period is needed before the value settles.
ATR_PERIOD: Final = 14
ATR_BARS: Final = 300

#: How long the same standing condition is suppressed for before it is raised
#: again. An hour: long enough that a week-old position does not produce ten
#: thousand identical lines, short enough that a condition nobody acted on
#: comes back the same day.
THROTTLE_WINDOW: Final = timedelta(hours=1)

WIDTH: Final = 78


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
    print(f"  {label:.<40} {value}")


def note(text: str) -> None:
    """Print an indented note.

    Args:
        text: Note text.
    """
    print(f"      {text}")


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------


def require_mt5() -> Any:
    """Import and initialise MetaTrader5, failing with a useful message.

    Returns:
        The imported, initialised module.

    Raises:
        SystemExit: If the platform, the package, or the terminal is
            unavailable.
    """
    if platform.system() != "Windows":
        print("FATAL: this adapter must run on Windows.")
        print("  The MetaTrader5 package ships only win_amd64 wheels and")
        print(f"  declares Platform: Windows. Detected: {platform.system()}.")
        print()
        print("  Everything it computes lives in src/risk, which imports no")
        print("  MetaTrader5 and is tested on any platform. Only this reader")
        print("  is Windows-bound.")
        raise SystemExit(2)
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except ImportError:
        print("FATAL: MetaTrader5 is not installed.  Run:  pip install MetaTrader5")
        raise SystemExit(2) from None
    if not mt5.initialize():
        print(f"FATAL: could not attach to a running terminal: {mt5.last_error()}")
        print("  Start MetaTrader 5, log in, and try again. This script never")
        print("  supplies credentials and never asks for them.")
        raise SystemExit(2)
    return mt5


def resolve_symbol(mt5: Any, requested: str | None) -> str:
    """Find a usable symbol and select it in Market Watch.

    Args:
        mt5: The MetaTrader5 module.
        requested: Symbol from the command line, if any.

    Returns:
        The exact symbol string the broker uses.

    Raises:
        SystemExit: If no candidate resolves.
    """
    for name in (requested,) if requested else CANDIDATE_SYMBOLS:
        if name and mt5.symbol_info(name) is not None:
            mt5.symbol_select(name, True)
            return str(name)
    print("FATAL: could not resolve a symbol.")
    print(f"  Tried: {requested or ', '.join(CANDIDATE_SYMBOLS)}")
    print("  Re-run with:  python scripts/risk_monitor.py --symbol <SYMBOL>")
    raise SystemExit(2)


# --------------------------------------------------------------------------
# The server clock -- measured, cached, never guessed
# --------------------------------------------------------------------------


def measure_server_offset(mt5: Any, symbol: str) -> tuple[float | None, str]:
    """Measure the broker server's offset from UTC, from a fresh tick.

    MT5 reports timestamps as the server's wall clock expressed as a Unix
    epoch, so reading one as UTC and differencing against true UTC yields the
    offset. Valid only while the market is open: a stale tick measures its own
    staleness. Every server offset seen in practice is a whole number of hours,
    so a fractional residual is the staleness detector.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol to take a tick from.

    Returns:
        ``(offset_hours, reason)``. ``offset_hours`` is ``None`` when no usable
        measurement was possible, and ``reason`` says why in either case.
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or tick.time == 0:
        return None, "no tick available"
    server = datetime.fromtimestamp(tick.time, tz=UTC).replace(tzinfo=None)
    delta_hours = (server - datetime.now(UTC).replace(tzinfo=None)).total_seconds()
    delta_hours /= 3600.0
    whole = round(delta_hours)
    residual_minutes = abs(delta_hours - whole) * 60.0
    if residual_minutes > OFFSET_STALENESS_MINUTES:
        return None, (
            f"the last tick is {residual_minutes:.1f} minutes off a whole-hour "
            f"offset, so the market is probably closed and this would measure "
            f"tick staleness rather than the clock"
        )
    return float(whole), f"measured from a tick {residual_minutes:.1f} min off the hour"


def load_cached_offset(path: Path) -> tuple[float | None, str]:
    """Read a previously measured offset.

    Args:
        path: Cache file.

    Returns:
        ``(offset_hours, reason)``.
    """
    if not path.exists():
        return None, "no cached measurement exists"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return float(payload["utc_offset_hours"]), (
            f"cached from a measurement at {payload['measured_at']}"
        )
    except (OSError, ValueError, KeyError) as exc:
        return None, f"the cached measurement could not be read: {exc}"


def save_cached_offset(path: Path, offset: float, now: datetime) -> None:
    """Record a measured offset for use while the market is closed.

    Args:
        path: Cache file.
        offset: Measured offset in hours.
        now: When it was measured.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"utc_offset_hours": offset, "measured_at": now.isoformat()},
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def resolve_offset(
    mt5: Any,
    symbol: str,
    cache_path: Path,
    explicit: float | None,
    now: datetime,
) -> tuple[float | None, str, str]:
    """Settle on a server clock offset, preferring a fresh measurement.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol to measure from.
        cache_path: Where a measurement is cached.
        explicit: An offset supplied on the command line, if any.
        now: Reading time.

    Returns:
        ``(offset_hours, source, reason)``. ``offset_hours`` is ``None`` only
        when no route produced one, and every quantity that needs the server
        day is then refused rather than computed against a guess.
    """
    if explicit is not None:
        return explicit, OFFSET_EXPLICIT, "supplied on the command line"

    measured, reason = measure_server_offset(mt5, symbol)
    if measured is not None:
        save_cached_offset(cache_path, measured, now)
        return measured, OFFSET_MEASURED, reason

    cached, cache_reason = load_cached_offset(cache_path)
    if cached is not None:
        return cached, OFFSET_CACHED, f"{reason}; {cache_reason}"

    return None, OFFSET_UNAVAILABLE, f"{reason}; {cache_reason}"


# --------------------------------------------------------------------------
# Reading the terminal
# --------------------------------------------------------------------------


def read_terminal(
    mt5: Any,
    symbol: str,
    cache_path: Path,
    explicit_offset: float | None,
    now: datetime,
) -> tuple[TerminalState, str]:
    """Read terminal state and settle the server clock.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol to measure the clock from.
        cache_path: Offset cache.
        explicit_offset: Command-line override.
        now: Reading time.

    Returns:
        ``(state, clock_reason)``.
    """
    info = mt5.terminal_info()
    version = mt5.version()
    offset, source, reason = resolve_offset(
        mt5, symbol, cache_path, explicit_offset, now
    )
    return (
        TerminalState(
            connected=bool(info.connected) if info else False,
            trade_allowed=bool(info.trade_allowed) if info else False,
            build=int(version[1]) if version else 0,
            server_utc_offset_hours=offset,
            server_offset_source=source,
        ),
        reason,
    )


def read_account(mt5: Any) -> AccountState:
    """Read one snapshot of the account.

    Args:
        mt5: The MetaTrader5 module.

    Returns:
        The account state.

    Raises:
        SystemExit: If the terminal returns nothing.
    """
    info = mt5.account_info()
    if info is None:
        print(f"FATAL: account_info() returned nothing: {mt5.last_error()}")
        raise SystemExit(2)
    demo = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
    return AccountState(
        currency=str(info.currency),
        balance=float(info.balance),
        equity=float(info.equity),
        margin=float(info.margin),
        margin_free=float(info.margin_free),
        margin_level=float(info.margin_level),
        margin_so_call=float(info.margin_so_call),
        margin_so_so=float(info.margin_so_so),
        margin_so_mode=int(info.margin_so_mode),
        leverage=int(info.leverage),
        is_demo=int(info.trade_mode) == int(demo),
    )


def read_symbol(mt5: Any, name: str) -> SymbolTerms | None:
    """Read one symbol's terms.

    Args:
        mt5: The MetaTrader5 module.
        name: Symbol name.

    Returns:
        The terms, or ``None`` when the broker does not offer the symbol.
    """
    info = mt5.symbol_info(name)
    if info is None:
        return None
    return SymbolTerms(
        name=str(info.name),
        digits=int(info.digits),
        point=float(info.point),
        trade_tick_size=float(info.trade_tick_size),
        trade_tick_value=float(info.trade_tick_value),
        trade_contract_size=float(info.trade_contract_size),
        volume_min=float(info.volume_min),
        volume_max=float(info.volume_max),
        volume_step=float(info.volume_step),
        spread_points=float(info.spread),
        spread_is_floating=bool(info.spread_float),
        swap_mode=int(info.swap_mode),
        swap_long=float(info.swap_long),
        swap_short=float(info.swap_short),
        swap_rollover_3days_weekday=int(info.swap_rollover3days),
        currency_base=str(info.currency_base),
        currency_profit=str(info.currency_profit),
        currency_margin=str(info.currency_margin),
    )


def read_positions(mt5: Any, offset_hours: float | None) -> tuple[PositionState, ...]:
    """Read every open position.

    ``order_calc_margin`` is a pure calculation: it returns what a position of
    that size would require and sends nothing. It is the only route to a
    per-position margin figure, which MT5 does not put on the position itself.

    Args:
        mt5: The MetaTrader5 module.
        offset_hours: Measured server offset, for the timestamp conversion.

    Returns:
        The open positions. Empty when the account is flat.
    """
    raw = mt5.positions_get()
    if raw is None:
        return ()
    out: list[PositionState] = []
    for p in raw:
        is_long = int(p.type) == int(mt5.POSITION_TYPE_BUY)
        order_type = mt5.ORDER_TYPE_BUY if is_long else mt5.ORDER_TYPE_SELL
        margin = mt5.order_calc_margin(
            order_type, p.symbol, float(p.volume), float(p.price_open)
        )
        out.append(
            PositionState(
                ticket=int(p.ticket),
                symbol=str(p.symbol),
                direction=(
                    PositionDirection.LONG if is_long else PositionDirection.SHORT
                ),
                volume=float(p.volume),
                price_open=float(p.price_open),
                price_current=float(p.price_current),
                opened_at=server_epoch_to_utc(int(p.time), offset_hours),
                # MT5 uses 0.0 for "no level set" rather than a null. Mapping
                # it to None here is what makes `has_stop` mean what it says.
                stop_loss=float(p.sl) if float(p.sl) != 0.0 else None,
                take_profit=float(p.tp) if float(p.tp) != 0.0 else None,
                swap=float(p.swap),
                profit=float(p.profit),
                margin=float(margin) if margin is not None else None,
            )
        )
    return tuple(out)


def server_epoch_to_utc(epoch: int, offset_hours: float | None) -> datetime:
    """Convert an MT5 server-clock epoch to a true UTC instant.

    MT5 reports every timestamp as the **server's** wall clock expressed as a
    Unix epoch, so reading one with ``fromtimestamp(..., tz=UTC)`` yields the
    server's clock reading wearing a UTC label. Subtracting the measured offset
    is what turns it into the instant it actually was.

    Args:
        epoch: MT5 timestamp.
        offset_hours: Measured server offset, or ``None`` when it could not be
            measured.

    Returns:
        A timezone-aware UTC instant. With no offset the value is returned
        unshifted -- which is the server's reading, not UTC -- and the report
        says so: ``server_offset_source`` is ``unavailable``, and every
        quantity that depends on the server day is refused rather than
        computed against it.
    """
    naive = datetime.fromtimestamp(epoch, tz=UTC).replace(tzinfo=None)
    if offset_hours is not None:
        naive -= timedelta(hours=offset_hours)
    return naive.replace(tzinfo=UTC)


def read_deals(
    mt5: Any, now: datetime, offset_hours: float | None
) -> tuple[DealState, ...]:
    """Read closed deals covering at least the current server day.

    Args:
        mt5: The MetaTrader5 module.
        now: Reading time.
        offset_hours: Measured server offset, for the timestamp conversion.

    Returns:
        Deals in the window. Filtering to the server day happens in
        :func:`risk.limits.daily_loss_status`, against the real boundary.
    """
    start = now - timedelta(days=DEAL_HISTORY_DAYS)
    raw = mt5.history_deals_get(
        start.replace(tzinfo=None), (now + timedelta(days=1)).replace(tzinfo=None)
    )
    if raw is None:
        return ()
    out: list[DealState] = []
    for d in raw:
        # Entry deals carry no realised result; only exits and balance
        # operations move the balance, and summing entries too would
        # double-count the round turn.
        if int(d.entry) == int(getattr(mt5, "DEAL_ENTRY_IN", 0)):
            continue
        out.append(
            DealState(
                ticket=int(d.ticket),
                symbol=str(d.symbol),
                profit=float(d.profit),
                commission=float(d.commission),
                swap=float(d.swap),
                fee=float(d.fee),
                closed_at=server_epoch_to_utc(int(d.time), offset_hours),
            )
        )
    return tuple(out)


def read_atr_points(mt5: Any, terms: SymbolTerms) -> float | None:
    """Measure ATR on the H1 series, in points.

    Uses ``features.atr.ATR`` rather than a second implementation. That module
    is Wilder's ATR with a causal test asserting truncated-history equality;
    re-deriving it here would mean two definitions of one quantity, and the
    untested one would be the one live sizing depended on.

    Args:
        mt5: The MetaTrader5 module.
        terms: Symbol terms, for the point conversion.

    Returns:
        ATR in points, or ``None`` when there is not enough history or the
        value is not finite.
    """
    import numpy as np
    import pandas as pd

    from features.atr import ATR

    rates = mt5.copy_rates_from_pos(terms.name, mt5.TIMEFRAME_H1, 0, ATR_BARS)
    if rates is None or len(rates) < ATR_PERIOD + 1:
        return None
    frame = pd.DataFrame(
        {
            "high": [float(r["high"]) for r in rates],
            "low": [float(r["low"]) for r in rates],
            "close": [float(r["close"]) for r in rates],
        }
    )
    value = float(ATR(period=ATR_PERIOD).compute(frame).iloc[-1])
    if not np.isfinite(value) or value <= 0 or terms.point <= 0:
        return None
    return value / terms.point


def read_everything(
    mt5: Any,
    symbol: str,
    cache_path: Path,
    explicit_offset: float | None,
    now: datetime,
) -> tuple[
    TerminalState,
    AccountState,
    tuple[PositionState, ...],
    tuple[DealState, ...],
    dict[str, SymbolTerms],
    str,
]:
    """Take one complete reading of the terminal.

    Args:
        mt5: The MetaTrader5 module.
        symbol: The symbol to always include, whether or not it is held.
        cache_path: Offset cache.
        explicit_offset: Command-line override.
        now: Reading time.

    Returns:
        ``(terminal, account, positions, deals, terms_by_symbol, clock_reason)``.
    """
    terminal, clock_reason = read_terminal(
        mt5, symbol, cache_path, explicit_offset, now
    )
    offset = terminal.server_utc_offset_hours

    account = read_account(mt5)
    positions = read_positions(mt5, offset)
    deals = read_deals(mt5, now, offset)

    terms: dict[str, SymbolTerms] = {}
    for name in {symbol, *(p.symbol for p in positions)}:
        found = read_symbol(mt5, name)
        if found is not None:
            terms[name] = found
    return terminal, account, positions, deals, terms, clock_reason


def current_price(mt5: Any, symbol: str) -> float | None:
    """Read the current ask, for the annualised swap basis.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol.

    Returns:
        The ask, or ``None`` when no tick is available.
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or not tick.ask:
        return None
    return float(tick.ask)


def take_reading(
    mt5: Any,
    symbol: str,
    cache_path: Path,
    explicit_offset: float | None,
    config: RiskConfig,
) -> tuple[RiskReport, str, float | None]:
    """Read the terminal once and build a report from it.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol to always include.
        cache_path: Offset cache.
        explicit_offset: Command-line override.
        config: Operating limits.

    Returns:
        ``(report, clock_reason, price)``.
    """
    now = datetime.now(UTC)
    terminal, account, positions, deals, terms, clock_reason = read_everything(
        mt5, symbol, cache_path, explicit_offset, now
    )
    price = current_price(mt5, symbol)
    report = build_report(
        now=now,
        terminal=terminal,
        account=account,
        positions=positions,
        deals=deals,
        terms_by_symbol=terms,
        config=config,
        price_by_symbol={symbol: price} if price is not None else None,
    )
    return report, clock_reason, price


# --------------------------------------------------------------------------
# Heartbeat
# --------------------------------------------------------------------------


def append_carry_log(path: Path, report: RiskReport, price: float | None) -> None:
    """Append one row per open position per reading.

    This is the instrument the swap finding needs. ``position.swap`` accumulates,
    so a series of readings gives the **nightly increments**, and from those:

    - the effective per-night charge, which is what the declared route refuses
      to convert under a base-currency ``swap_mode``;
    - **which weekday carries the triple charge**, measured rather than read off
      ``swap_rollover3days``, because the increment on that day is three times
      its neighbours;
    - whether the charge is **price-dependent**, which is the structural claim.
      If it is, ``increment / price`` is constant while ``increment`` is not, and
      one week of rows shows which.

    The heartbeat holds only the latest reading, so without this the increments
    are unrecoverable and the measurement would have to be transcribed by hand.

    **The published field is logged alongside the charge**, unconverted. A rate
    that is proportional to price and a fixed rate the broker *re-quotes* as the
    price moves produce the same increments, and the only thing that tells them
    apart is whether ``swap_long`` itself moved. Rows written before 2026-08-01
    do not carry it; :mod:`risk.carry_log` treats it as optional for exactly
    that reason and says so rather than assuming it was stable.

    Args:
        path: File to append to.
        report: The reading just taken.
        price: Current price for the configured symbol, when known.
    """
    published = {d.symbol: d for d in report.swap}
    if not report.carries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for c in report.carries:
            handle.write(
                json.dumps(
                    {
                        "at": report.generated_at.isoformat(),
                        "ticket": c.ticket,
                        "symbol": c.symbol,
                        "direction": c.direction.value,
                        "volume": c.volume,
                        "opened_at": c.opened_at.isoformat(),
                        "days_open": round(c.days_open, 6),
                        "nights_held": c.nights_held,
                        # In charge terms: positive means the account paid.
                        "carry_paid": c.carry_paid,
                        "floating_pnl": c.floating_pnl,
                        "price": price,
                        # Raw, unconverted, whatever swap_mode says the units
                        # are. A change in this field over the week is what
                        # separates a re-quoted fixed rate from a price-
                        # dependent one.
                        "published_swap_long": (
                            published[c.symbol].published_swap_long
                            if c.symbol in published
                            else None
                        ),
                        "published_swap_short": (
                            published[c.symbol].published_swap_short
                            if c.symbol in published
                            else None
                        ),
                        # Recorded so the analysis can recover the SERVER
                        # weekday, which is what identifies the triple-swap
                        # day. Without it the multiplier is still inferable but
                        # the weekday it lands on is not.
                        "server_offset_hours": (
                            report.terminal.server_utc_offset_hours
                        ),
                        "equity": report.account.equity,
                        "currency": report.account.currency,
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def write_heartbeat(path: Path, report: RiskReport) -> None:
    """Record that the monitor completed a reading.

    Args:
        path: Heartbeat file.
        report: The reading just taken.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    worst = report.worst_severity
    path.write_text(
        json.dumps(
            {
                "at": report.generated_at.isoformat(),
                "summary": render_one_line(report),
                "worst_severity": worst.value if worst else None,
                "alerts": len(report.alerts),
                "refusals": len(report.refusals),
                "positions": report.concurrency.open_positions,
                "equity": report.account.equity,
                "currency": report.account.currency,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def report_status(path: Path, config: RiskConfig, now: datetime) -> int:
    """Report what the monitor last saw, refusing to say "all clear" if stale.

    The failure mode this guards against is the one that matters: a monitor
    that died at 3am and a status check that cheerfully reports the last thing
    it saw. Silence from a dead process is indistinguishable from silence from
    a quiet account, and only one of those is safe.

    Args:
        path: Heartbeat file.
        config: Operating limits, for the staleness threshold.
        now: Current time.

    Returns:
        Process exit code: 0 alive and quiet, 1 alive with warnings, 2 alive
        and critical or not alive at all.
    """
    header("MONITOR STATUS")
    if not path.exists():
        row("heartbeat", "ABSENT")
        note("No monitor has ever written to this path. Nothing is being")
        note("watched. This is NOT an all-clear.")
        return 2

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        beat_at = datetime.fromisoformat(str(payload["at"]))
    except (OSError, ValueError, KeyError) as exc:
        row("heartbeat", f"UNREADABLE - {exc}")
        note("This is NOT an all-clear.")
        return 2

    age = (now - beat_at).total_seconds()
    row("last reading", beat_at.isoformat())
    row("age", f"{age:,.0f} seconds")
    row("summary", payload.get("summary", ""))

    if age > config.heartbeat_stale_seconds:
        print()
        note(
            f"STALE: the last reading is older than "
            f"{config.heartbeat_stale_seconds:,.0f} seconds. The monitor is "
            f"not running,"
        )
        note("so nothing has been checked since then. This is NOT an")
        note("all-clear, whatever the summary above says.")
        return 2

    worst = payload.get("worst_severity")
    if worst == Severity.CRITICAL.value:
        return 2
    if worst == Severity.WARN.value:
        return 1
    return 0


# --------------------------------------------------------------------------
# Probe
# --------------------------------------------------------------------------


def run_probe(
    mt5: Any,
    symbol: str,
    cache_path: Path,
    explicit_offset: float | None,
    config: RiskConfig,
) -> int:
    """Print every field read and every number derived from it.

    This is the acceptance step. Nothing is summarised and nothing is hidden:
    if a figure below is wrong, the field it came from is on the same page.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol to read.
        cache_path: Offset cache.
        explicit_offset: Command-line override.
        config: Operating limits.

    Returns:
        Process exit code.
    """
    now = datetime.now(UTC)
    terminal, account, positions, deals, terms, clock_reason = read_everything(
        mt5, symbol, cache_path, explicit_offset, now
    )

    header("0. WHAT THIS IS")
    note("A read-only probe of one MT5 account. It predicts nothing, places")
    note("nothing, and writes nothing except an offset cache. Every number")
    note("below is arithmetic on a field the terminal published.")

    header("1. TERMINAL AND CLOCK")
    version = mt5.version()
    info = mt5.terminal_info()
    if version:
        row("terminal version / build", f"{version[0]} / {version[1]}")
    if info:
        row("terminal company", info.company)
        row("connected", info.connected)
        row("trade allowed by terminal", info.trade_allowed)
    row("server offset (hours from UTC)", terminal.server_utc_offset_hours)
    row("offset source", terminal.server_offset_source)
    note(clock_reason)
    if terminal.server_utc_offset_hours is None:
        note("WITHOUT THIS, the daily loss limit cannot be measured and is")
        note("refused rather than computed over a guessed day. Re-run during")
        note("market hours, or pass --server-utc-offset.")

    header("2. ACCOUNT")
    row("account type", "DEMO" if account.is_demo else "LIVE")
    row("login", "**** (masked)")
    row("currency", account.currency)
    row("balance", f"{account.balance:,.2f}")
    row("equity", f"{account.equity:,.2f}")
    row("margin", f"{account.margin:,.2f}")
    row("free margin", f"{account.margin_free:,.2f}")
    row("margin level", f"{account.margin_level:,.2f}%")
    row("margin_so_call (raw)", account.margin_so_call)
    row("margin_so_so (raw)", account.margin_so_so)
    row("margin_so_mode (raw)", account.margin_so_mode)
    note("The two levels above are in percent when the mode is 0 and in")
    note("deposit currency when it is 1. Nothing here assumes 100/50.")
    row("leverage", f"1:{account.leverage}")

    header("3. SYMBOL TERMS, AS PUBLISHED")
    for name, t in sorted(terms.items()):
        print()
        print(f"  {name}")
        for field in (
            "digits",
            "point",
            "trade_tick_size",
            "trade_tick_value",
            "trade_contract_size",
            "volume_min",
            "volume_max",
            "volume_step",
            "spread_points",
            "spread_is_floating",
            "swap_mode",
            "swap_long",
            "swap_short",
            "swap_rollover_3days_weekday",
            "currency_base",
            "currency_profit",
            "currency_margin",
        ):
            row(f"  {field}", getattr(t, field))
        per_point = value_per_point_per_lot(t)
        row("  => currency per point per lot", per_point)
        if per_point is None:
            note("REFUSED: the tick fields do not yield a conversion, so no")
            note("money figure for this symbol can be computed at all.")
        declared = declared_swap(t, account.currency)
        if isinstance(declared, DeclaredSwap):
            row("  => swap mode, named", declared.mode.name)
            row(
                "  => charge long (points/lot/night)",
                f"{declared.charge_long_points:+.4f}",
            )
            row(
                "  => charge short (points/lot/night)",
                f"{declared.charge_short_points:+.4f}",
            )
            note("Positive means the account pays. Negative means it is paid.")
        else:
            row("  => swap", "REFUSED")
            note(declared.reason)
        atr = read_atr_points(mt5, t)
        row("  => ATR(14) H1, in points", f"{atr:,.1f}" if atr else "unavailable")

    header("4. OPEN POSITIONS, AS PUBLISHED")
    if not positions:
        print("  none open")
    for p in positions:
        print()
        print(f"  #{p.ticket}  {p.symbol}  {p.direction.value}")
        row("  volume", p.volume)
        row("  price_open / price_current", f"{p.price_open} / {p.price_current}")
        row("  opened_at (converted to UTC)", p.opened_at.isoformat())
        row("  stop_loss", p.stop_loss if p.stop_loss is not None else "NONE SET")
        row("  take_profit", p.take_profit if p.take_profit is not None else "none")
        row("  swap (broker sign)", p.swap)
        row("  profit", p.profit)
        row("  margin (order_calc_margin)", p.margin)

    header("5. DEALS IN THE LAST TWO DAYS")
    row("deals fetched", len(deals))
    for d in deals[-10:]:
        print(
            f"      {d.closed_at.isoformat()}  {d.symbol:<10} "
            f"profit {d.profit:>10,.2f}  total {d.realised:>10,.2f}"
        )

    price = current_price(mt5, symbol)
    report = build_report(
        now=now,
        terminal=terminal,
        account=account,
        positions=positions,
        deals=deals,
        terms_by_symbol=terms,
        config=config,
        price_by_symbol={symbol: price} if price is not None else None,
    )

    header("6. THE REPORT THIS PRODUCES")
    print(render(report))

    header("7. SIZING, AT THE CONFIGURED RISK")
    _print_sizing(mt5, terms.get(symbol), account, config)

    header("8. WHAT TO CHECK BEFORE TRUSTING ANY OF THIS")
    note("1. The server offset above matches what the platform clock shows.")
    note("2. The swap charge figures match the broker's contract specification.")
    note("3. Every open position's opened_at matches the platform, in UTC.")
    note("4. The margin_so_* levels match what the broker states.")
    note("5. Every REFUSED line above is a figure that does not exist. If one")
    note("   surprises you, that is the finding, not a bug to work around.")
    return severity_exit_code(report)


def _print_sizing(
    mt5: Any,
    terms: SymbolTerms | None,
    account: AccountState,
    config: RiskConfig,
) -> None:
    """Print a size for the configured risk, or say why there is none.

    Args:
        mt5: The MetaTrader5 module.
        terms: Symbol terms, or ``None``.
        account: The account reading.
        config: Operating limits.
    """
    if terms is None:
        print("  no symbol terms; nothing to size")
        return
    atr = read_atr_points(mt5, terms)
    if atr is None:
        print("  ATR unavailable; nothing to size")
        return
    tick = mt5.symbol_info_tick(terms.name)
    reference = float(tick.ask) if tick is not None and tick.ask else None

    result = size_position(
        equity=account.equity,
        risk_pct=config.risk_per_trade_pct,
        atr_points=atr,
        terms=terms,
        stop_multiple=config.stop_atr_multiple,
        reference_price=reference,
    )
    if isinstance(result, Refusal):
        row("size", "REFUSED")
        note(result.reason)
        return
    _print_sizing_result(result, account, config)


def _print_sizing_result(
    result: SizingResult, account: AccountState, config: RiskConfig
) -> None:
    """Print one sizing result.

    Args:
        result: The size.
        account: The account reading, for the currency.
        config: Operating limits.
    """
    ccy = account.currency
    row("risk budget", f"{result.risk_budget:,.2f} {ccy}")
    row("  which is", f"{config.risk_per_trade_pct:,.2f}% of equity")
    row("ATR(14) H1", f"{result.atr_points:,.1f} points")
    row("stop distance", f"{result.stop_distance_points:,.1f} points")
    row("  which is", f"{result.stop_multiple} x ATR")
    row("spread (live quote)", f"{result.spread_points:,.1f} points")
    row("adverse excursion priced", f"{result.adverse_points:,.1f} points")
    row("=> SIZE", f"{result.lots} lots")
    row("   risk at that size", f"{result.risk_at_this_size:,.2f} {ccy}")
    if result.stop_price_long is not None:
        row("   stop for a long", f"{result.stop_price_long:,.3f}")
        row("   stop for a short", f"{result.stop_price_short:,.3f}")
    row(
        "   cost per extra point of spread",
        f"{result.risk_per_extra_spread_point:,.2f} {ccy}",
    )
    for line in result.notes:
        note(line)


# --------------------------------------------------------------------------
# Monitor
# --------------------------------------------------------------------------


def build_notifier(state_dir: Path, quiet: bool) -> Notifier:
    """Assemble the alert channel from the configured destinations.

    The channel is a configuration choice, not a rewrite: everything that
    raises an alert talks to :class:`risk.notify.Notifier`, and adding a phone
    or a webhook means adding one class here.

    Args:
        state_dir: Where the alert log lives.
        quiet: Suppress terminal output, leaving only the file.

    Returns:
        The channel, throttled.
    """
    channels: list[Notifier] = [FileNotifier(state_dir / ALERTS_NAME)]
    if not quiet:
        channels.insert(0, StreamNotifier(sys.stdout))
    return ThrottledNotifier(MultiNotifier(tuple(channels)), THROTTLE_WINDOW)


def run_monitor(
    mt5: Any,
    symbol: str,
    state_dir: Path,
    explicit_offset: float | None,
    config: RiskConfig,
    interval: float,
    quiet: bool,
) -> int:
    """Read the account on an interval until interrupted.

    A monitor rather than a script the user remembers to run, because the
    failure mode being addressed is not noticing. A two-month hold is invisible
    precisely because nobody goes looking for it.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol to always include.
        state_dir: Where the heartbeat and alert log live.
        explicit_offset: Command-line override.
        config: Operating limits.
        interval: Seconds between readings.
        quiet: Suppress terminal alert output.

    Returns:
        Process exit code.
    """
    notifier = build_notifier(state_dir, quiet)
    heartbeat = state_dir / HEARTBEAT_NAME
    cache = state_dir / OFFSET_CACHE_NAME

    print(f"risk monitor: reading {symbol} every {interval:,.0f} seconds")
    print(f"  heartbeat  {heartbeat}")
    print(f"  alert log  {state_dir / ALERTS_NAME}")
    print(f"  carry log  {state_dir / CARRY_LOG_NAME}")
    print("  read-only: this process never places, modifies or closes an order")
    print("  Ctrl-C to stop")
    print()

    while True:
        try:
            report, _, price = take_reading(mt5, symbol, cache, explicit_offset, config)
        except KeyboardInterrupt:
            print("\nstopped")
            return 0
        except Exception as exc:
            # A read that fails must be loud rather than fatal: the monitor's
            # whole value is that it is still running an hour from now.
            notifier.emit(
                Alert(
                    AlertCode.TERMINAL_DISCONNECTED,
                    Severity.CRITICAL,
                    "monitor",
                    f"a reading failed and was skipped: {exc!r}",
                    datetime.now(UTC),
                    "read-failure",
                )
            )
        else:
            deliver(report, notifier)
            write_heartbeat(heartbeat, report)
            append_carry_log(state_dir / CARRY_LOG_NAME, report, price)

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nstopped")
            return 0


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments, or ``None`` for ``sys.argv``.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Read-only risk and cost monitor for an MT5 account. "
            "Predicts nothing, places nothing."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--probe",
        action="store_true",
        help="read everything once and print every field and derived number",
    )
    mode.add_argument(
        "--once", action="store_true", help="one reading, rendered, then exit"
    )
    mode.add_argument(
        "--status",
        action="store_true",
        help="report what the monitor last saw, refusing to say all-clear if stale",
    )
    mode.add_argument(
        "--size", action="store_true", help="size a position at the configured risk"
    )
    parser.add_argument("--symbol", default=None, help="symbol to read")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=f"where the heartbeat and alert log live (default {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"seconds between readings (default {DEFAULT_INTERVAL_SECONDS:.0f})",
    )
    parser.add_argument(
        "--server-utc-offset",
        type=float,
        default=None,
        help=(
            "server clock offset in hours, when it cannot be measured "
            "because the market is closed"
        ),
    )
    parser.add_argument("--risk-pct", type=float, default=None)
    parser.add_argument("--daily-loss-pct", type=float, default=None)
    parser.add_argument("--max-positions", type=int, default=None)
    parser.add_argument("--time-alert-hours", type=float, default=None)
    parser.add_argument(
        "--quiet", action="store_true", help="alerts to the log file only"
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> RiskConfig:
    """Build the operating limits, defaults overridden by the command line.

    Args:
        args: Parsed arguments.

    Returns:
        The configuration.
    """
    defaults = RiskConfig()
    return RiskConfig(
        risk_per_trade_pct=(
            args.risk_pct if args.risk_pct is not None else defaults.risk_per_trade_pct
        ),
        daily_loss_limit_pct=(
            args.daily_loss_pct
            if args.daily_loss_pct is not None
            else defaults.daily_loss_limit_pct
        ),
        max_concurrent_positions=(
            args.max_positions
            if args.max_positions is not None
            else defaults.max_concurrent_positions
        ),
        time_in_trade_alert_hours=(
            args.time_alert_hours
            if args.time_alert_hours is not None
            else defaults.time_in_trade_alert_hours
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Run the adapter.

    Args:
        argv: Arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit code: 0 quiet, 1 warnings, 2 critical.
    """
    args = parse_args(argv)
    config = config_from_args(args)
    state_dir = Path(args.state_dir)

    # --status reads a file and needs no terminal, so it must not require one.
    if args.status:
        return report_status(state_dir / HEARTBEAT_NAME, config, datetime.now(UTC))

    mt5 = require_mt5()
    try:
        symbol = resolve_symbol(mt5, args.symbol)
        cache = state_dir / OFFSET_CACHE_NAME

        if args.probe:
            return run_probe(mt5, symbol, cache, args.server_utc_offset, config)

        if args.size:
            _, _, _, _, terms, _ = read_everything(
                mt5, symbol, cache, args.server_utc_offset, datetime.now(UTC)
            )
            header("SIZING")
            _print_sizing(mt5, terms.get(symbol), read_account(mt5), config)
            return 0

        if args.once:
            report, _ = take_reading(mt5, symbol, cache, args.server_utc_offset, config)
            print(render(report))
            return severity_exit_code(report)

        return run_monitor(
            mt5,
            symbol,
            state_dir,
            args.server_utc_offset,
            config,
            args.interval,
            args.quiet,
        )
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
