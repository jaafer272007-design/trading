"""Read a week of ``--carry-log`` rows and report what it settled.

All the judgement lives in :mod:`risk.carry_log`, which was written **before any
log existed** and whose thresholds are fixed there so they cannot be chosen
after seeing the data. This file is a command line and a printer.

Usage::

    python scripts/analyse_carry_log.py ~/.trading-risk/carry.jsonl

Runs anywhere. It needs no terminal, no credentials and no MetaTrader — the log
is a plain JSON-lines file, so the analysis happens wherever the file is.

Exit codes: ``0`` a verdict was reached, ``1`` the week was UNDETERMINED,
``2`` the log could not be read. UNDETERMINED is not an error and is not a
negative result; it means the week could not separate the two explanations, and
:attr:`risk.carry_log.PowerAssessment.reasons` says which condition failed.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from risk.carry_log import (
    CHARGE_RESOLUTION,
    MIN_REVERSALS,
    POWER_MARGIN,
    SEPARATION_FACTOR,
    CarryLogAnalysis,
    CarryRow,
    StructureVerdict,
    analyse,
    parse_rows,
)

WIDTH = 78


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
    print(f"  {label:.<42} {value}")


def report(result: CarryLogAnalysis) -> None:
    """Print one position's analysis.

    Args:
        result: The analysis.
    """
    header(f"TICKET {result.ticket} - verdict: {result.verdict.value}")

    print()
    print("  Charging events")
    print()
    print("      observed (UTC)        wkdy   x   increment    price   unit")
    print("      " + "-" * 62)
    for n in result.nights:
        weekday = "-" if n.server_weekday is None else str(n.server_weekday)
        price = "     -" if n.price is None else f"{n.price:,.2f}"
        print(
            f"      {n.observed_at.strftime('%Y-%m-%d %H:%M')}      {weekday:>3}   "
            f"{n.multiplier}   {n.increment:>9.2f}  {price:>9}  "
            f"{n.unit_charge:>6.3f}"
        )
    print("      wkdy is the SERVER weekday, 0 = Monday")

    print()
    print("  Power - checked before the verdict, not after")
    p = result.power
    row("charging events resolved", p.resolved_nights)
    row("mean single-night charge", f"{p.mean_unit_charge:,.4f}")
    if p.price_range_fraction is not None:
        row("price range over the week", f"{p.price_range_fraction:.4%}")
    if p.required_range_fraction is not None:
        row("range this charge size needed", f"{p.required_range_fraction:.4%}")
        row(
            "  which is",
            f"{POWER_MARGIN:.0f} x the {CHARGE_RESOLUTION:.2f} posting resolution",
        )
    row("price direction changes", f"{p.reversals} (need {MIN_REVERSALS})")
    row("HAS POWER", "yes" if p.has_power else "NO")
    for reason in p.reasons:
        print(f"      - {reason}")

    print()
    print("  The two series")
    row("CV of the unit charge", _fmt(result.cv_unit_charge))
    row("CV of unit charge / price", _fmt(result.cv_charge_over_price))
    row("separation needed", f"{SEPARATION_FACTOR:.0f}x")

    print()
    print("  The published field - reported, never acted on")
    f = result.field
    row("readings carrying swap_long", f"{f.readings:,}")
    row(
        "distinct values",
        "none recorded" if f.changed is None else ", ".join(str(v) for v in f.distinct),
    )
    row(
        "did the broker re-quote",
        "unknown - not logged" if f.changed is None else ("YES" if f.changed else "no"),
    )
    row("watched across every charge", "yes" if f.spans_the_charges else "no")

    print()
    print("  Settled regardless of power")
    row("charges swaps at all", "yes" if result.charges_swaps else "NO")
    if result.charge_per_lot_per_night is not None:
        row(
            "charge per lot per night",
            f"{result.charge_per_lot_per_night:,.4f}",
        )
    row(
        "triple-swap server weekday",
        "not observed"
        if result.triple_swap_weekday is None
        else result.triple_swap_weekday,
    )

    print()
    print("  Read these")
    for note in result.notes:
        print(f"      - {note}")


def _fmt(value: float | None) -> str:
    """Format an optional coefficient of variation.

    Args:
        value: The value.

    Returns:
        Six decimal places, or a dash.
    """
    return "-" if value is None else f"{value:.6f}"


def main(argv: list[str] | None = None) -> int:
    """Read a carry log and report on it.

    Args:
        argv: Arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Read a --carry-log file and report what the week settled. "
            "Thresholds are fixed in risk.carry_log and are not tunable here."
        )
    )
    parser.add_argument("path", type=Path, help="carry.jsonl written by the monitor")
    args = parser.parse_args(argv)

    try:
        rows = parse_rows(args.path.read_text(encoding="utf-8").splitlines())
    except (OSError, ValueError) as exc:
        print(f"FATAL: {exc}")
        return 2
    if not rows:
        print("FATAL: the log is empty. No position was open while the monitor ran.")
        return 2

    by_ticket: dict[int, list[CarryRow]] = defaultdict(list)
    for r in rows:
        by_ticket[r.ticket].append(r)

    header("CARRY LOG - what one week of readings settled")
    row("file", args.path)
    row("readings", f"{len(rows):,}")
    row("positions", len(by_ticket))
    print()
    print("  Thresholds were fixed in risk.carry_log before any log existed.")
    print("  UNDETERMINED is a real outcome, not a failure, and it is not")
    print("  evidence for the registered fixed-rate model.")

    verdicts = []
    for ticket in sorted(by_ticket):
        result = analyse(by_ticket[ticket])
        report(result)
        verdicts.append(result.verdict)

    return 0 if all(v is not StructureVerdict.UNDETERMINED for v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
