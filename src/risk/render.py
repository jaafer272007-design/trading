"""Rendering a report as text a person will actually read.

Kept apart from :mod:`risk.report` so that changing how a number is presented
cannot change the number. Everything here is formatting; nothing here computes.

Order is a decision, not a convention
-------------------------------------

Alerts come first because they are why the report is being read. **Refusals
come second, before any figure** — a reader has to know which guards are not
running before they start trusting the numbers underneath. The swap divergence
comes third because it is a finding about the registry rather than about the
account, and burying it under the account's own figures would be the same
mistake as calling it a diagnostic.
"""

from __future__ import annotations

import textwrap

from risk.carry import PositionCarry
from risk.limits import ConcurrencyStatus, DailyLossStatus
from risk.margin import MarginProjection
from risk.notify import Severity
from risk.refusal import Refusal
from risk.report import RiskReport
from risk.swap import SwapDivergence, SwapVerdict

WIDTH = 78


def _rule(char: str = "=") -> str:
    """A horizontal rule.

    Args:
        char: Character to repeat.

    Returns:
        One line.
    """
    return char * WIDTH


def _header(title: str) -> list[str]:
    """A section header.

    Args:
        title: Section title.

    Returns:
        Lines.
    """
    return ["", _rule(), title, _rule()]


def _wrap(text: str, indent: str = "      ", bullet: str = "") -> list[str]:
    """Wrap a sentence to the report width with a hanging indent.

    Detail text is the part of this report that is genuinely read, and a
    120-character line in an 80-column terminal is read as two lines with the
    wrap in the wrong place. Wrapping here rather than shortening the sentences
    keeps the reasons complete, which is what they are for.

    Args:
        text: The sentence.
        indent: Leading whitespace on every line.
        bullet: Marker on the first line only, e.g. ``"- "``.

    Returns:
        Wrapped lines.
    """
    return textwrap.wrap(
        text,
        width=WIDTH,
        initial_indent=indent + bullet,
        subsequent_indent=indent + " " * len(bullet),
    ) or [indent + bullet]


def _row(label: str, value: object) -> str:
    """An aligned label/value line.

    Args:
        label: Left-hand label.
        value: Right-hand value.

    Returns:
        One line.
    """
    return f"  {label:.<38} {value}"


def _money(value: float, currency: str) -> str:
    """Format a currency amount.

    Args:
        value: Amount.
        currency: Account currency code.

    Returns:
        Signed amount with the currency appended.
    """
    return f"{value:,.2f} {currency}"


def render(report: RiskReport) -> str:
    """Render a whole report.

    Args:
        report: The report.

    Returns:
        The report as text, without a trailing newline.
    """
    ccy = report.account.currency
    lines: list[str] = [
        _rule(),
        f"RISK AND COST LAYER - reading at "
        f"{report.generated_at.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        _rule(),
        "",
        "  This layer predicts nothing and places nothing. Every figure below",
        "  is arithmetic on account state the terminal already publishes.",
    ]

    lines += _render_alerts(report)
    lines += _render_refusals(report.refusals)
    lines += _render_swap(report.swap)
    lines += _render_account(report, ccy)
    lines += _render_positions(report, ccy)
    lines += _render_margin(report.margin, ccy)
    lines += _render_limits(report.daily_loss, report.concurrency, ccy)

    return "\n".join(lines)


def _render_alerts(report: RiskReport) -> list[str]:
    """Render the alert block.

    Args:
        report: The report.

    Returns:
        Lines.
    """
    if not report.alerts:
        return [*_header("ALERTS"), "  none"]
    worst = report.worst_severity
    lines = _header(f"ALERTS - {len(report.alerts)}, worst {worst}")
    for alert in report.alerts:
        lines.append(f"  [{alert.severity.value}] {alert.subject}")
        lines += _wrap(alert.detail)
    return lines


def _render_refusals(refusals: tuple[Refusal, ...]) -> list[str]:
    """Render the refusal block.

    Args:
        refusals: Every refusal in the reading.

    Returns:
        Lines.
    """
    if not refusals:
        return [
            *_header("REFUSED - quantities not computed"),
            "  none; every figure below was computed from a value the broker",
            "  published, with nothing defaulted",
        ]
    lines = _header(f"REFUSED - {len(refusals)} quantities not computed")
    lines.append("  Read these before the numbers. Each one is a figure that")
    lines.append("  does not exist, not a figure that is approximate.")
    lines.append("")
    for refusal in refusals:
        lines.append(f"  {refusal.code.value}  {refusal.subject}")
        lines += _wrap(refusal.reason)
    return lines


def _render_swap(divergences: tuple[SwapDivergence, ...]) -> list[str]:
    """Render the measured-versus-registered financing finding.

    Args:
        divergences: One per symbol.

    Returns:
        Lines.
    """
    if not divergences:
        return []
    bears = [d for d in divergences if d.bears_on_the_registry]
    title = "SWAP - broker vs the registered substitute"
    if bears:
        title += "   *** BEARS ON THE REGISTRY ***"
    lines = _header(title)

    for d in divergences:
        lines.append("")
        lines.append(f"  {d.symbol}   verdict: {d.verdict.value}")
        if d.mode is not None:
            suffix = " - PRICE-DEPENDENT" if d.mode_is_price_dependent else ""
            lines.append(_row("swap_mode", f"{d.mode.name}{suffix}"))
        if d.declared_long_points is not None:
            lines.append(
                _row(
                    "broker charge, long",
                    f"{d.declared_long_points:+.3f} points/lot/night",
                )
            )
        if d.declared_short_points is not None:
            lines.append(
                _row(
                    "broker charge, short",
                    f"{d.declared_short_points:+.3f} points/lot/night",
                )
            )
        for side, per_day in sorted(d.measured_daily_points.items()):
            lines.append(
                _row(
                    f"measured charge, {side}",
                    f"{per_day:+.3f} points/lot/calendar day",
                )
            )
        if d.comparisons:
            lines.append("")
            lines.append(
                "      side   source     registered   broker     ratio  "
                "exceeds   reg%/yr  brk%/yr"
            )
            lines.append("      " + "-" * 74)
            for c in d.comparisons:
                ratio = f"{c.ratio:.2f}x" if c.ratio is not None else "n/a"
                flag = "YES" if c.exceeds else "no"
                reg_pct = (
                    f"{c.registered_annual_pct:+.2f}"
                    if c.registered_annual_pct is not None
                    else "  -  "
                )
                brk_pct = (
                    f"{c.broker_annual_pct:+.2f}"
                    if c.broker_annual_pct is not None
                    else "  -  "
                )
                lines.append(
                    f"      {c.side:<6} {c.source:<9}  {c.registered_points:>9.1f}  "
                    f"{c.broker_points:>9.1f}  {ratio:>6}  {flag:<7}  "
                    f"{reg_pct:>7}  {brk_pct:>7}"
                )
            lines.append("      points per lot per calendar week; %/yr of one")
            lines.append("      lot's notional, the only basis a price-dependent")
            lines.append("      swap leaves invariant")
        for note in d.notes:
            lines += _wrap(note, bullet="- ")

    if any(d.verdict is SwapVerdict.UNAVAILABLE for d in divergences):
        lines.append("")
        lines.append(
            "  An UNAVAILABLE verdict is not agreement. It means the comparison"
        )
        lines.append("  could not be made and the registered figure is untested.")
    return lines


def _render_account(report: RiskReport, ccy: str) -> list[str]:
    """Render the account block.

    Args:
        report: The report.
        ccy: Account currency.

    Returns:
        Lines.
    """
    a = report.account
    t = report.terminal
    lines = _header("ACCOUNT")
    lines.append(_row("account type", "DEMO" if a.is_demo else "LIVE"))
    lines.append(_row("terminal connected", t.connected))
    lines.append(_row("trading allowed by terminal", t.trade_allowed))
    offset = (
        f"UTC{t.server_utc_offset_hours:+.2f}h ({t.server_offset_source})"
        if t.server_utc_offset_hours is not None
        else "UNAVAILABLE"
    )
    lines.append(_row("server clock", offset))
    lines.append(_row("balance", _money(a.balance, ccy)))
    lines.append(_row("equity", _money(a.equity, ccy)))
    lines.append(_row("margin in use", _money(a.margin, ccy)))
    lines.append(_row("free margin", _money(a.margin_free, ccy)))
    lines.append(_row("leverage", f"1:{a.leverage}"))
    return lines


def _render_positions(report: RiskReport, ccy: str) -> list[str]:
    """Render one block per open position.

    Args:
        report: The report.
        ccy: Account currency.

    Returns:
        Lines.
    """
    if not report.carries:
        return [*_header("POSITIONS"), "  none open"]

    lines = _header(f"POSITIONS - {len(report.carries)} open")
    for c in report.carries:
        lines += _render_one_position(c, ccy)

    p = report.portfolio
    lines.append("")
    lines.append("  Book")
    lines.append(_row("financing paid, all positions", _money(p.paid_total, ccy)))
    if p.rate_per_day is not None:
        lines.append(_row("financing per calendar day", _money(p.rate_per_day, ccy)))
    if p.rate_is_partial:
        lines += _wrap(
            "at least one position contributed no rate, so the book figure "
            "understates the real cost"
        )
    if p.days_until_carry_consumes_equity is not None:
        lines.append(
            _row(
                "days for financing alone to take equity",
                f"{p.days_until_carry_consumes_equity:,.0f}",
            )
        )
        if p.date_carry_consumes_equity is not None:
            lines.append(
                _row(
                    "  which is",
                    p.date_carry_consumes_equity.strftime("%Y-%m-%d"),
                )
            )
        lines.append("      price held constant; this is arithmetic, not a forecast")
    return lines


def _render_one_position(c: PositionCarry, ccy: str) -> list[str]:
    """Render a single position.

    Args:
        c: The position's financing report.
        ccy: Account currency.

    Returns:
        Lines.
    """
    lines = [
        "",
        f"  #{c.ticket}  {c.symbol}  {c.direction.value.upper()}  {c.volume} lots",
    ]
    lines.append(_row("opened", c.opened_at.strftime("%Y-%m-%d %H:%M:%S UTC")))
    lines.append(
        _row("open for", f"{c.hours_open:,.1f} hours ({c.days_open:,.2f} days)")
    )
    if c.nights_held is not None:
        lines.append(
            _row("server midnights crossed", f"{c.nights_held} (not a swap count)")
        )
    lines.append(_row("stop loss attached", "yes" if c.has_stop else "NO"))
    lines.append(_row("floating result", _money(c.floating_pnl, ccy)))
    label = "financing CREDITED" if c.carry_is_credit else "financing paid"
    lines.append(_row(label, _money(abs(c.carry_paid), ccy)))
    if c.carry_pct_of_equity is not None:
        lines.append(_row("  as a share of equity", f"{c.carry_pct_of_equity:,.3f}%"))
    if c.breakeven_points is not None:
        lines.append(
            _row(
                "move needed to cover financing",
                f"{c.breakeven_points:,.1f} points",
            )
        )
    if c.breakeven_price is not None and c.breakeven_pct is not None:
        lines.append(
            _row("  reaching", f"{c.breakeven_price:,.3f} ({c.breakeven_pct:+.3f}%)")
        )
    lines.append(_row("forward rate source", c.rate_source.value))
    if c.rate_declared_per_day is not None:
        lines.append(
            _row("  published rate", f"{_money(c.rate_declared_per_day, ccy)}/day")
        )
    if c.rate_measured_per_day is not None:
        lines.append(
            _row("  measured rate", f"{_money(c.rate_measured_per_day, ccy)}/day")
        )

    usable = [p for p in c.projections if p.breakeven_points is not None]
    if usable:
        lines.append("")
        lines.append(
            "      hold for   more financing   total financing   move to cover"
        )
        lines.append("      " + "-" * 62)
        for p in usable:
            lines.append(
                f"      {p.horizon_days:>5.0f}d   {p.additional:>14,.2f}   "
                f"{p.cumulative:>15,.2f}   "
                f"{p.breakeven_points or 0.0:>10,.0f} pts"
            )
        lines.append("      price held constant")

    for note in c.notes:
        lines += _wrap(note, bullet="- ")
    return lines


def _render_margin(margin: MarginProjection, ccy: str) -> list[str]:
    """Render the margin projection.

    Args:
        margin: The projection.
        ccy: Account currency.

    Returns:
        Lines.
    """
    lines = _header("MARGIN - distance to the broker's own intervention levels")
    if margin.margin_level_pct is not None:
        lines.append(_row("margin level", f"{margin.margin_level_pct:,.1f}%"))
    if margin.mode is not None:
        lines.append(_row("levels expressed in", margin.mode.name.lower()))
    for level in (margin.call, margin.stop_out):
        if level is None:
            continue
        lines.append("")
        lines.append(f"  {level.name}")
        lines.append(
            _row("  equity at that level", _money(level.threshold_equity, ccy))
        )
        lines.append(_row("  headroom", _money(level.headroom, ccy)))
        if level.already_breached:
            lines.append("      ALREADY AT OR PAST THIS LEVEL")
        elif level.days_to_reach is not None:
            lines.append(
                _row("  days at current financing", f"{level.days_to_reach:,.1f}")
            )
            if level.date_reached is not None:
                lines.append(
                    _row("  which is", level.date_reached.strftime("%Y-%m-%d"))
                )
        else:
            lines.append("      no financing rate, so no time axis")
    if margin.call is not None or margin.stop_out is not None:
        lines.append("")
        lines.append(
            "  Price is held constant. An adverse move makes every figure above"
        )
        lines.append("  sooner, never later. This is a bound, not a forecast.")
    return lines


def _render_limits(
    daily: DailyLossStatus | Refusal, concurrency: ConcurrencyStatus, ccy: str
) -> list[str]:
    """Render the daily loss and concurrency blocks.

    Args:
        daily: The day's status, or a refusal.
        concurrency: Position count status.
        ccy: Account currency.

    Returns:
        Lines.
    """
    lines = _header("LIMITS")
    if isinstance(daily, Refusal):
        lines.append("  daily loss limit: NOT BEING ENFORCED")
        lines += _wrap(daily.reason)
    else:
        lines.append("  Daily loss, measured over the server trading day")
        lines.append(
            _row(
                "  day",
                f"{daily.day_start.strftime('%Y-%m-%d %H:%M')} to "
                f"{daily.day_end.strftime('%H:%M')} UTC",
            )
        )
        lines.append(_row("  opening balance", _money(daily.opening_balance, ccy)))
        lines.append(
            _row(
                "  realised today",
                f"{_money(daily.realised, ccy)} ({daily.deals_counted} deals)",
            )
        )
        lines.append(_row("  floating now", _money(daily.floating, ccy)))
        lines.append(_row("  total", _money(daily.total, ccy)))
        lines.append(
            _row(
                "  limit",
                f"{daily.limit_pct:,.2f}% = {_money(daily.limit_currency, ccy)}",
            )
        )
        if daily.used_fraction_of_limit is not None:
            lines.append(
                _row("  used", f"{daily.used_fraction_of_limit:.0%} of the limit")
            )
        lines.append(_row("  breached", "YES" if daily.breached else "no"))
        if daily.carried_in_positions:
            lines += _wrap(
                f"{daily.carried_in_positions} position(s) were opened before "
                f"this day began, so this figure is drawdown from the opening "
                f"balance and includes loss inherited from earlier days - the "
                f"stricter of the two readings"
            )

    lines.append("")
    lines.append("  Concurrent positions")
    lines.append(
        _row(
            "  open / maximum",
            f"{concurrency.open_positions} / {concurrency.limit}",
        )
    )
    lines.append(_row("  breached", "YES" if concurrency.breached else "no"))
    for symbol, count in concurrency.by_symbol:
        lines.append(_row(f"  {symbol}", count))
    return lines


def render_one_line(report: RiskReport) -> str:
    """A single-line summary, for a status check or a log.

    Args:
        report: The report.

    Returns:
        One line.
    """
    worst = report.worst_severity
    status = worst.value if worst is not None else "OK"
    return (
        f"{report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}Z  {status:<8}  "
        f"equity {report.account.equity:,.2f} {report.account.currency}  "
        f"positions {report.concurrency.open_positions}  "
        f"alerts {len(report.alerts)}  refusals {len(report.refusals)}"
    )


def severity_exit_code(report: RiskReport) -> int:
    """Map the worst severity to a process exit code.

    Args:
        report: The report.

    Returns:
        0 when nothing was raised, 1 at WARN, 2 at CRITICAL. A one-shot check
        can then be used from a shell without parsing the output.
    """
    worst = report.worst_severity
    if worst is Severity.CRITICAL:
        return 2
    if worst is Severity.WARN:
        return 1
    return 0
