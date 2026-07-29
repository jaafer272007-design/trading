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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from risk.carry import (
    PortfolioCarry,
    PositionCarry,
    portfolio_carry,
    position_carry,
)
from risk.clock import RolloverClock
from risk.config import RiskConfig
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
)
from risk.swap import SwapDivergence, declared_swap, swap_divergence

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
    refusals: tuple[Refusal, ...]
    alerts: tuple[Alert, ...]

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

    Returns:
        The report, with alerts already raised but not yet delivered.
    """
    clock = (
        RolloverClock(terminal.server_utc_offset_hours)
        if terminal.server_utc_offset_hours is not None
        else None
    )

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

    swap = tuple(
        swap_divergence(
            symbol=name,
            declared=declared_by_symbol[name],
            measured_daily_points=portfolio.per_lot_per_day_points.get(name, {}),
            measured_tolerance=config.swap_divergence_tolerance,
        )
        for name in sorted(terms_by_symbol)
    )

    margin = margin_projection(account, portfolio.rate_per_day, now)
    daily = daily_loss_status(
        account, positions, deals, config.daily_loss_limit_pct, now, clock
    )
    concurrency = concurrency_status(positions, config.max_concurrent_positions)

    refusals: list[Refusal] = []
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
        now, terminal, carries, portfolio, swap, margin, daily, concurrency, config
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
        refusals=tuple(refusals),
        alerts=alerts,
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

    if margin.mode is None:
        raise_alert(
            AlertCode.REFUSAL,
            Severity.WARN,
            "stop-out projection",
            "NOT BEING ENFORCED - the broker's margin-call mode was not "
            "recognised, so the intervention levels have no known units",
            RefusalCode.MARGIN_MODE_UNSUPPORTED.value,
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
