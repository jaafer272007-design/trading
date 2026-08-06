"""Recover the sound fields from a carry log written under a bad server clock.

What this is for
----------------

`[MEASURED]` 2026-08-02, instrument defect #10: a stale tick produced a server
offset of ``-23.0``, and rows written while it was in force carry timing fields
that are wrong by 26 hours. :func:`risk.carry_log.parse_rows` **refuses such a
log outright**, and that refusal is correct — a file that needs a per-field
trust map is a file somebody will read wrongly.

But the refusal is about the *file*, not about every number in it. A carry-log
row holds two kinds of field:

**Read, and therefore sound.** ``at`` comes from this machine's clock, not the
server's. ``carry_paid`` is ``position.swap`` as the broker published it.
``price``, ``volume``, ``published_swap_long``, ``floating_pnl`` and ``equity``
are all read. **None of them passes through the server offset.**

**Derived, and therefore void.** ``opened_at``, ``days_open``, ``nights_held``,
and the server weekday the analysis reconstructs from ``server_offset_hours``.

So the structural measurement — increments, unit charges, the two coefficient
series, the power assessment, the verdict — is computable from a contaminated
log in full. The **only** casualty is the triple-swap weekday, which is
inferred from the multiplier and then *named* by the server weekday.

Why this is a separate script and not a flag on the analyser
------------------------------------------------------------

Because it must be a decision somebody makes, once, on purpose, leaving a new
file behind that says what happened to it. An analyser that quietly skipped bad
fields would be filtering, and filtering is a judgement made once, silently,
and inherited by every later reading. This drops the void fields rather than
the rows: **every row survives, with its provenance recorded and its timing
gone.** Nothing is corrected — a corrected timestamp would be a guess wearing a
measurement's clothes.

Usage::

    python scripts/rescue_carry_log.py carry.contaminated.jsonl carry.rescued.jsonl

The output is a valid carry log with ``server_offset_hours`` and
``server_offset_source`` set to null, which
:func:`risk.carry_log.row_is_untrustworthy` accepts — an absent offset is
already reported as an absent server weekday, and that is exactly what has
happened. Concatenate it ahead of a fresh log, in ``at`` order, to extend the
increment series backwards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from risk.clock import offset_is_plausible

#: Fields that pass through the server offset and are void when it is wrong.
#: Dropped rather than corrected: the true offset is not recoverable from the
#: row, and substituting a plausible one would replace a wrong number with a
#: guess that reads exactly like a measurement.
VOID_FIELDS: Final[tuple[str, ...]] = (
    "opened_at",
    "days_open",
    "nights_held",
    "server_offset_hours",
    "server_offset_source",
)

#: Fields the broker or this machine supplied directly. Every one survives.
SOUND_FIELDS: Final[tuple[str, ...]] = (
    "at",
    "ticket",
    "symbol",
    "direction",
    "volume",
    "carry_paid",
    "price",
    "published_swap_long",
    "published_swap_short",
    "floating_pnl",
    "equity",
    "currency",
)


def rescue_row(payload: dict[str, object]) -> tuple[dict[str, object], bool]:
    """Strip the offset-dependent fields from one row.

    Args:
        payload: The row as written.

    Returns:
        ``(rescued row, whether anything was dropped)``. The rescued row keeps
        every sound field it had, sets the two offset fields to ``None``, and
        records that it was rescued so the file cannot be mistaken for one
        written by a healthy run.
    """
    dropped = any(
        payload.get(field) is not None
        for field in VOID_FIELDS
        if field not in ("server_offset_hours", "server_offset_source")
    )
    out: dict[str, object] = {k: payload[k] for k in SOUND_FIELDS if k in payload}
    out["server_offset_hours"] = None
    out["server_offset_source"] = None
    out["rescued_from_offset"] = payload.get("server_offset_hours")
    return out, dropped


def main(argv: list[str] | None = None) -> int:
    """Rescue a contaminated carry log.

    Args:
        argv: Arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit code: ``0`` written, ``2`` unreadable, ``3`` refused.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Drop the server-clock-dependent fields from a carry log so the "
            "sound ones can be read. Rows are kept; fields are dropped. "
            "Nothing is corrected."
        )
    )
    parser.add_argument("source", type=Path, help="the contaminated log")
    parser.add_argument("destination", type=Path, help="where to write the rescue")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the destination if it already exists",
    )
    args = parser.parse_args(argv)

    if args.destination.exists() and not args.force:
        print(f"FATAL: {args.destination} exists. Pass --force to overwrite.")
        return 3
    try:
        lines = args.source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"FATAL: {exc}")
        return 2

    rescued: list[str] = []
    suspect_offsets: set[float] = set()
    timing_dropped = 0
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError as exc:
            print(f"FATAL: line {number} is not JSON: {exc}")
            return 2
        offset = payload.get("server_offset_hours")
        if isinstance(offset, int | float) and not offset_is_plausible(float(offset)):
            suspect_offsets.add(float(offset))
        row, dropped = rescue_row(payload)
        timing_dropped += int(dropped)
        rescued.append(json.dumps(row, sort_keys=True))

    if not rescued:
        print("FATAL: no rows to rescue.")
        return 2

    args.destination.write_text("\n".join(rescued) + "\n", encoding="utf-8")

    print(f"read     {args.source}")
    print(f"wrote    {args.destination}")
    print(f"rows     {len(rescued):,} in, {len(rescued):,} out - none was dropped")
    print(f"timing   stripped from {timing_dropped:,} row(s)")
    if suspect_offsets:
        print(f"offsets  {sorted(suspect_offsets)} were outside the plausible range")
    print()
    print("KEPT, because the broker or this machine supplied them directly:")
    print("  " + ", ".join(SOUND_FIELDS))
    print()
    print("DROPPED, because they were derived through the bad server offset:")
    print("  " + ", ".join(VOID_FIELDS))
    print()
    print("What this costs the analysis: the TRIPLE-SWAP WEEKDAY, and nothing")
    print("else. Increments, unit charges, both coefficient series, the power")
    print("assessment and the verdict all read fields that never touched the")
    print("offset. The multiplier is still inferred from the increments; only")
    print("the weekday it lands on is now unnameable.")
    print()
    print("Nothing here was corrected. A repaired timestamp would be a guess")
    print("that reads exactly like a measurement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
