"""Assembling one reading of the account into a report, and raising alerts.

Nothing here computes; every number comes from :mod:`risk.carry`,
:mod:`risk.margin`, :mod:`risk.limits` or :mod:`risk.swap`. This module decides
what a reading *means* — which conditions are worth interrupting someone for,
and at what severity — and it is deliberately separate from the arithmetic so
that changing a threshold cannot change a number.

Refusals are promoted, not swallowed
------------------------------------

Two refusals disable a guard outright: an unlocatable server clock takes the
daily loss limit with it, and an unrecognised margin-call mode takes the
stop-out projection with it. Both raise an alert of their own. A monitor that
silently stops checking something is worse than one that was never started,
because the first looks like it is working — and this whole layer exists
because a cost nobody was watching emptied an account.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from risk.carry import (
    PortfolioCarry,
    PositionCarry,
    portfolio_carry,
    position_carry,
)
from risk.clock import (
    MAX_PLAUSIBLE_UTC_OFFSET_HOURS,
    MIN_PLAUSIBLE_UTC_OFFSET_HOURS,
    RolloverClock,
    offset_is_plausible,
)
from risk.config import RiskConfig
from risk.continuity import ContinuityCheck, check_openings
from risk.limits import (
    ConcurrencyStatus,
    DailyLossStatus,
    concurrency_status,
    daily_loss_status,
)
from risk.margin import MarginProjection, margin_projection
from risk.notify import Alert, AlertCode, Notifier, Severity
from risk.refusal import Refusal, RefusalCode
from risk.state import (
    AccountState,
    DealState,
    PositionState,
    SymbolTerms,
    TerminalState,
    value_per_point_per_lot,
)
from risk.swap import (
    DeclaredSwap,
    SwapDivergence,
    SwapMode,
    declared_swap,
    swap_divergence,
)

#: Multiple of a WARN threshold at which the same condition becomes CRITICAL.
#: One number for every escalation so that the report has a single notion of
#: "much worse than the threshold" rather than a different one per alert.
ESCALATION_MULTIPLE: float = 3.0

#: Fraction of the daily loss limit at which the limit warns before it binds.
DAILY_LOSS_WARN_FRACTION: float = 0.75

#: Projected days to the broker's stop-out at which a warning becomes critical.
STOPOUT_CRITICAL_DAYS: float = 7.0

#: What the alert-raising helpers are handed: ``(code, severity, subject,
#: detail, key) -> None``. A named alias rather than an inline signature so
#: that the helpers below read as what they are, which is decision logic with
#: one output.
RaiseAlert = Callable[[AlertCode, Severity, str, str, str], None]


@dataclass(frozen=True, slots=True)
class RiskReport:
    """One complete reading of the account.

    Attributes:
        generated_at: When the reading was taken, timezone-aware UTC.
        terminal: The terminal's state at that moment.
        account: The account reading.
        carries: Financing report per open position.
        portfolio: Financing across the book.
        swap: Measured-versus-registered financing, one entry per symbol. A
            first-class field rather than a diagnostic: if the broker's real
            rate exceeds the registered substitute, that bears on every
            cost-dependent result in ``HYPOTHESES.md``.
        margin: Distance from the broker's intervention levels.
        daily_loss: The day's drawdown against the limit, or a refusal.
        concurrency: Open positions against the maximum.
        continuity: What comparing this reading against the last established.
        timing_refusal: Set when a position's ``opened_at`` moved between
            readings. **While this is set, every age-derived figure in the
            report is void** and the renderer prints the timing section as
            refused rather than printing numbers nobody should read.
        refusals: Every quantity this reading declined to guess.
        alerts: Conditions worth interrupting someone for.
    """

    generated_at: datetime
    terminal: TerminalState
    account: AccountState
    carries: tuple[PositionCarry, ...]
    portfolio: PortfolioCarry
    swap: tuple[SwapDivergence, ...]
    margin: MarginProjection
    daily_loss: DailyLossStatus | Refusal
    concurrency: ConcurrencyStatus
    continuity: ContinuityCheck
    timing_refusal: Refusal | None
    refusals: tuple[Refusal, ...]
    alerts: tuple[Alert, ...]

    @property
    def timing_is_trustworthy(self) -> bool:
        """Whether any figure derived from a position's age may be read.

        Returns:
            False when the continuity guard fired.
        """
        return self.timing_refusal is None

    @property
    def worst_severity(self) -> Severity | None:
        """The highest severity present.

        Returns:
            ``None`` when nothing was raised.
        """
        if not self.alerts:
            return None
        order = (Severity.CRITICAL, Severity.WARN, Severity.INFO)
        present = {a.severity for a in self.alerts}
        return next(s for s in order if s in present)


def build_report(
    now: datetime,
    terminal: TerminalState,
    account: AccountState,
    positions: tuple[PositionState, ...],
    deals: tuple[DealState, ...],
    terms_by_symbol: dict[str, SymbolTerms],
    config: RiskConfig,
    price_by_symbol: dict[str, float] | None = None,
    opening_baseline: Mapping[int, datetime] | None = None,
    previous_reading_at: datetime | None = None,
) -> RiskReport:
    """Turn one reading of the terminal into a report.

    Args:
        now: Reading time, timezone-aware UTC.
        terminal: Terminal state, carrying the measured server clock offset.
        account: Account reading.
        positions: Open positions.
        deals: Closed deals covering at least the current server day. Filtered
            to the day inside :func:`risk.limits.daily_loss_status`.
        terms_by_symbol: Symbol terms for every symbol in ``positions``, and
            for any other symbol whose swap should be compared.
        config: Operating limits.
        price_by_symbol: Current price per symbol, used only for the annualised
            basis of the swap comparison. Falls back to an open position's
            ``price_current`` when absent, and the annualised figures are simply
            omitted when neither is available.
        opening_baseline: First-seen ``opened_at`` per ticket from previous
            readings. Supplying it turns on the continuity guard, which is the
            one check that catches a server-clock error without knowing
            anything about clocks. See :mod:`risk.continuity`.
        previous_reading_at: When the previous reading was taken, so that a
            host clock that went backwards is caught too.

    Returns:
        The report, with alerts already raised but not yet delivered.
    """
    offset = terminal.server_utc_offset_hours
    offset_refusal: Refusal | None = None
    if offset is not None and not offset_is_plausible(offset):
        # Not a clock. Differencing a stale tick against now produces exactly
        # this, and treating it as an offset moves every age by the error.
        offset_refusal = Refusal(
            RefusalCode.OFFSET_IMPLAUSIBLE,
            "server clock",
            f"the server offset reads {offset:+.1f} hours, outside the "
            f"{MIN_PLAUSIBLE_UTC_OFFSET_HOURS:+.0f}..."
            f"{MAX_PLAUSIBLE_UTC_OFFSET_HOURS:+.0f} range of real UTC "
            f"offsets. No place on earth uses it, so this is a stale tick "
            f"differenced against now rather than a clock reading. Every "
            f"quantity needing the server day is refused",
        )
        offset = None
    clock = RolloverClock(offset) if offset is not None else None

    declared_by_symbol = {
        name: declared_swap(terms, account.currency)
        for name, terms in terms_by_symbol.items()
    }

    carries = tuple(
        position_carry(
            position=p,
            terms=terms_by_symbol.get(p.symbol),
            declared=declared_by_symbol.get(
                p.symbol,
                Refusal(
                    RefusalCode.SYMBOL_TERMS_MISSING,
                    p.symbol,
                    "no symbol_info was supplied for this symbol",
                ),
            ),
            now=now,
            equity=account.equity,
            clock=clock,
            horizons=config.carry_projection_days,
            minimum_days_for_measured_rate=config.minimum_days_for_measured_carry,
        )
        for p in positions
    )

    portfolio = portfolio_carry(
        carries, positions, terms_by_symbol, account.equity, now
    )

    prices = dict(price_by_symbol or {})
    for p in positions:
        prices.setdefault(p.symbol, p.price_current)

    swap = tuple(
        _divergence_for(
            name,
            terms_by_symbol[name],
            declared_by_symbol[name],
            portfolio,
            prices.get(name),
            config,
        )
        for name in sorted(terms_by_symbol)
    )

    margin = margin_projection(account, portfolio.rate_per_day, now)
    daily = daily_loss_status(
        account, positions, deals, config.daily_loss_limit_pct, now, clock
    )
    concurrency = concurrency_status(positions, config.max_concurrent_positions)

    continuity = check_openings(
        opening_baseline or {}, positions, previous_reading_at, now
    )
    timing_refusal = continuity.refusals[0] if continuity.refusals else None

    refusals: list[Refusal] = []
    if offset_refusal is not None:
        refusals.append(offset_refusal)
    refusals.extend(continuity.refusals)
    if not terminal.connected:
        refusals.append(
            Refusal(
                RefusalCode.TERMINAL_DISCONNECTED,
                "terminal",
                "the terminal is not connected to the broker, so every "
                "figure below is as stale as the last successful update and "
                "the staleness is not measurable from here",
            )
        )
    for c in carries:
        refusals.extend(c.refusals)
    refusals.extend(margin.refusals)
    if isinstance(daily, Refusal):
        refusals.append(daily)

    alerts = _raise_alerts(
        now,
        terminal,
        carries,
        portfolio,
        swap,
        margin,
        daily,
        concurrency,
        config,
        timing_refusal,
    )

    return RiskReport(
        generated_at=now,
        terminal=terminal,
        account=account,
        carries=carries,
        portfolio=portfolio,
        swap=swap,
        margin=margin,
        daily_loss=daily,
        concurrency=concurrency,
        continuity=continuity,
        timing_refusal=timing_refusal,
        refusals=tuple(refusals),
        alerts=alerts,
    )


def _divergence_for(
    name: str,
    terms: SymbolTerms,
    declared: DeclaredSwap | Refusal,
    portfolio: PortfolioCarry,
    price: float | None,
    config: RiskConfig,
) -> SwapDivergence:
    """Build one symbol's divergence finding, with the annualised basis.

    Args:
        name: Symbol.
        terms: Its terms as read from the terminal.
        declared: Result of :func:`risk.swap.declared_swap`.
        portfolio: Book financing, for the measured route.
        price: Current price, or ``None``.
        config: Operating limits.

    Returns:
        The finding.
    """
    per_point = value_per_point_per_lot(terms)
    notional = (
        terms.trade_contract_size * price
        if price is not None and price > 0 and terms.trade_contract_size > 0
        else None
    )
    try:
        mode: SwapMode | None = SwapMode(terms.swap_mode)
    except ValueError:
        mode = None
    return swap_divergence(
        symbol=name,
        declared=declared,
        measured_daily_points=portfolio.per_lot_per_day_points.get(name, {}),
        measured_tolerance=config.swap_divergence_tolerance,
        mode=mode,
        currency_per_point=per_point,
        notional_per_lot=notional,
        measured_nightly_points=portfolio.per_lot_per_night_points.get(name, {}),
        published_swap_long=terms.swap_long,
        published_swap_short=terms.swap_short,
    )


def _raise_alerts(
    now: datetime,
    terminal: TerminalState,
    carries: tuple[PositionCarry, ...],
    portfolio: PortfolioCarry,
    swap: tuple[SwapDivergence, ...],
    margin: MarginProjection,
    daily: DailyLossStatus | Refusal,
    concurrency: ConcurrencyStatus,
    config: RiskConfig,
    timing_refusal: Refusal | None = None,
) -> tuple[Alert, ...]:
    """Decide which conditions in a reading are worth raising.

    Args:
        now: Reading time.
        terminal: Terminal state.
        carries: Per-position financing.
        portfolio: Book financing.
        swap: Per-symbol divergence findings.
        margin: Margin projection.
        daily: Daily loss status or refusal.
        concurrency: Position count status.
        config: Operating limits.
        timing_refusal: Set when the continuity guard fired, in which case
            every age-derived alert is suppressed and replaced by one saying
            so.

    Returns:
        Alerts, most severe first, then by code.
    """
    out: list[Alert] = []

    def raise_alert(
        code: AlertCode, severity: Severity, subject: str, detail: str, key: str
    ) -> None:
        out.append(Alert(code, severity, subject, detail, now, key))

    if not terminal.connected:
        raise_alert(
            AlertCode.TERMINAL_DISCONNECTED,
            Severity.CRITICAL,
            "terminal",
            "not connected to the broker; every figure in this report is "
            "stale by an unknown amount and no limit below is being enforced "
            "against live state",
            "terminal",
        )

    if timing_refusal is not None:
        # CRITICAL rather than WARN, and louder than the alerts it replaces.
        # A wrong age is not a missing age: the time-in-trade tripwire would
        # have fired late or not at all, and this layer exists because of a
        # two-month hold nobody was timing.
        raise_alert(
            AlertCode.REFUSAL,
            Severity.CRITICAL,
            "position timing",
            f"NOT BEING ENFORCED - {timing_refusal.reason}",
            timing_refusal.code.value,
        )
    else:
        for c in carries:
            _position_alerts(c, config, raise_alert)

    if margin.stop_out is not None:
        _level_alerts(margin, config, raise_alert)

    if isinstance(daily, DailyLossStatus):
        _daily_alerts(daily, raise_alert)
    else:
        raise_alert(
            AlertCode.REFUSAL,
            Severity.WARN,
            "daily loss limit",
            f"NOT BEING ENFORCED - {daily.reason}",
            daily.code.value,
        )

    if margin.stop_out is None:
        # Read the reason off the projection rather than assuming one. The
        # projection is refused for several distinct causes -- an unrecognised
        # margin mode, implausible leverage, no margin in use -- and an alert
        # that names the wrong one sends the reader to the wrong field.
        blocking = next(
            (
                r
                for r in margin.refusals
                if r.code
                in (
                    RefusalCode.MARGIN_MODE_UNSUPPORTED,
                    RefusalCode.LEVERAGE_IMPLAUSIBLE,
                )
            ),
            None,
        )
        if blocking is not None:
            raise_alert(
                AlertCode.REFUSAL,
                Severity.WARN,
                "stop-out projection",
                f"NOT BEING ENFORCED - {blocking.reason}",
                blocking.code.value,
            )

    if concurrency.breached:
        raise_alert(
            AlertCode.MAX_POSITIONS,
            Severity.WARN,
            "account",
            f"{concurrency.open_positions} positions open against a maximum "
            f"of {concurrency.limit}",
            "concurrency",
        )

    for divergence in swap:
        if divergence.bears_on_the_registry:
            raise_alert(
                AlertCode.SWAP_DIVERGENCE,
                Severity.CRITICAL,
                divergence.symbol,
                divergence.notes[0]
                if divergence.notes
                else "broker financing exceeds the registered substitute",
                divergence.symbol,
            )

    days_to_zero = portfolio.days_until_carry_consumes_equity
    book_rate = portfolio.rate_per_day
    if (
        days_to_zero is not None
        and book_rate is not None
        and days_to_zero <= config.margin_call_alert_days * ESCALATION_MULTIPLE
    ):
        raise_alert(
            AlertCode.CARRY_HEAVY,
            Severity.WARN,
            "account",
            f"at the current book financing rate of {book_rate:,.2f} a day, "
            f"financing alone consumes the whole of equity in "
            f"{days_to_zero:,.0f} days, price held constant",
            "portfolio",
        )

    rank = {Severity.CRITICAL: 0, Severity.WARN: 1, Severity.INFO: 2}
    return tuple(sorted(out, key=lambda a: (rank[a.severity], a.code.value, a.key)))


def _position_alerts(
    carry: PositionCarry,
    config: RiskConfig,
    raise_alert: RaiseAlert,
) -> None:
    """Raise the per-position alerts.

    Args:
        carry: The position's financing report.
        config: Operating limits.
        raise_alert: The closure that records an alert.
    """
    key = str(carry.ticket)
    subject = f"{carry.symbol} {carry.direction.value} #{carry.ticket}"

    if carry.hours_open >= config.time_in_trade_alert_hours:
        critical = (
            carry.hours_open >= config.time_in_trade_alert_hours * ESCALATION_MULTIPLE
        )
        detail = (
            f"open {carry.hours_open:,.1f} hours "
            f"({carry.days_open:,.1f} days) against a "
            f"{config.time_in_trade_alert_hours:,.0f}-hour threshold; "
            f"financing paid so far {carry.carry_paid:,.2f}"
        )
        if carry.breakeven_points is not None:
            detail += (
                f", needing a {carry.breakeven_points:,.0f}-point move just to cover it"
            )
        raise_alert(
            AlertCode.TIME_IN_TRADE,
            Severity.CRITICAL if critical else Severity.WARN,
            subject,
            detail,
            key,
        )

    pct = carry.carry_pct_of_equity
    if pct is not None and pct >= config.carry_alert_pct_of_equity:
        critical = pct >= config.carry_alert_pct_of_equity * ESCALATION_MULTIPLE
        raise_alert(
            AlertCode.CARRY_HEAVY,
            Severity.CRITICAL if critical else Severity.WARN,
            subject,
            f"financing paid is {carry.carry_paid:,.2f}, {pct:,.2f}% of "
            f"equity, against a {config.carry_alert_pct_of_equity:,.2f}% "
            f"threshold",
            key,
        )

    if not carry.has_stop:
        raise_alert(
            AlertCode.NO_STOP_LOSS,
            Severity.WARN,
            subject,
            "no stop loss is attached, so this position has no arithmetic "
            "bound on what it can lose",
            key,
        )


def _level_alerts(
    margin: MarginProjection, config: RiskConfig, raise_alert: RaiseAlert
) -> None:
    """Raise the margin-level alerts.

    Args:
        margin: The margin projection.
        config: Operating limits.
        raise_alert: The closure that records an alert.
    """
    for level in (margin.call, margin.stop_out):
        if level is None:
            continue
        if level.already_breached:
            raise_alert(
                AlertCode.MARGIN_BREACHED,
                Severity.CRITICAL,
                "account",
                f"equity {margin.equity:,.2f} is at or below the broker's "
                f"{level.name} level of {level.threshold_equity:,.2f}",
                level.name,
            )
        elif (
            level.days_to_reach is not None
            and level.days_to_reach <= config.margin_call_alert_days
        ):
            raise_alert(
                AlertCode.MARGIN_STOPOUT_NEAR,
                Severity.CRITICAL
                if level.days_to_reach <= STOPOUT_CRITICAL_DAYS
                else Severity.WARN,
                "account",
                f"financing alone reaches the broker's {level.name} level in "
                f"{level.days_to_reach:,.1f} days, price held constant; "
                f"headroom {level.headroom:,.2f} at "
                f"{level.daily_carry or 0.0:,.2f} a day",
                level.name,
            )


def _daily_alerts(daily: DailyLossStatus, raise_alert: RaiseAlert) -> None:
    """Raise the daily loss alerts.

    Args:
        daily: The day's status.
        raise_alert: The closure that records an alert.
    """
    used = daily.used_fraction_of_limit
    if used is None:
        return
    if daily.breached:
        raise_alert(
            AlertCode.DAILY_LOSS_LIMIT,
            Severity.CRITICAL,
            "account",
            f"drawdown from the day's opening balance is {daily.loss:,.2f}, "
            f"at or past the {daily.limit_pct:,.2f}% limit of "
            f"{daily.limit_currency:,.2f}",
            "daily",
        )
    elif used >= DAILY_LOSS_WARN_FRACTION:
        raise_alert(
            AlertCode.DAILY_LOSS_LIMIT,
            Severity.WARN,
            "account",
            f"drawdown from the day's opening balance is {daily.loss:,.2f}, "
            f"{used:.0%} of the {daily.limit_currency:,.2f} limit, with "
            f"{daily.remaining:,.2f} remaining",
            "daily",
        )


def deliver(report: RiskReport, notifier: Notifier) -> int:
    """Send every alert in a report to a channel.

    Args:
        report: The report.
        notifier: Where alerts go. Throttling, if any, is the notifier's.

    Returns:
        How many alerts were handed over. Not how many were delivered — a
        throttle may drop some, and it is the throttle's business how many.
    """
    for alert in report.alerts:
        notifier.emit(alert)
    return len(report.alerts)
