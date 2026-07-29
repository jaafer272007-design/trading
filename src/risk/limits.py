"""The two hard limits: loss in a day, and positions open at once.

Both are arithmetic on account state, and both are stated against a
denominator that has to be chosen deliberately.

The daily loss denominator
--------------------------

A 3% daily loss limit is 3% of *what*? Current equity is the wrong answer and
the tempting one: as the day's loss grows, equity falls, so the limit falls
with it, and the limit is never quite reached. The denominator here is the
**account balance at the start of the server trading day**, reconstructed as
``equity - realised today - floating now``. That is a fixed number for the
duration of the day, which is the only way a limit expressed as a percentage of
it can actually be hit.

Floating profit and loss counts. A limit that only counted closed trades would
have been silent through the entire two-month hold that this layer exists
because of.

What that measures, stated exactly
----------------------------------

Because the denominator is the opening *balance* and the numerator counts the
*whole* floating result, the quantity is **drawdown from the day's opening
balance**, not the change in equity during the day. For a position opened and
closed inside the day the two are identical. For a position carried in from
yesterday they are not: the loss it was already showing at midnight is counted
again today.

That is deliberate, and it is the stricter of the two readings. Separating them
would need each position's floating result *as at* the day boundary, and while
the price component of that is recoverable from history, the financing
component is not — MT5 publishes a position's accumulated swap only as it
stands now. Reconstructing it would mean modelling backwards through the very
rate this layer refuses to assume.

So the honest choice is the strict reading, named for what it is.
:attr:`DailyLossStatus.carried_in_positions` counts the positions that make the
two readings differ, so a reader can always see when the number includes
inherited loss. For an account whose failure mode is carrying a position for
two months, a limit that keeps counting that position is the right behaviour
rather than a defect in it.

The day boundary
----------------

The **server's** day, from :class:`risk.clock.RolloverClock`. Not UTC, not the
machine's local time. A limit measured over the wrong twenty-four hours mixes
two sessions and reports a number that never existed at any instant. When the
server clock is unavailable the limit is refused rather than measured over a
guessed day.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from risk.clock import RolloverClock
from risk.refusal import Refusal, RefusalCode
from risk.state import AccountState, DealState, PositionState


@dataclass(frozen=True, slots=True)
class DailyLossStatus:
    """The trading day's result against the configured limit.

    Attributes:
        day_start: Start of the server day, UTC.
        day_end: End of the server day, UTC.
        realised: Closed-trade result today, including commission, financing
            and fees. Negative is a loss.
        floating: Open-position result now, financing included. Negative is a
            loss.
        total: ``realised + floating``. Drawdown from the opening balance when
            negative; see the module docstring for what this does and does not
            mean.
        opening_balance: Account balance at the start of the server day,
            reconstructed.
        limit_pct: The configured limit.
        limit_currency: ``opening_balance x limit_pct / 100``.
        loss: The drawdown as a positive number, or zero when up on the day.
        used_fraction_of_limit: ``loss / limit_currency``.
        remaining: Currency of further loss before the limit is reached.
        breached: Whether the limit has been reached or passed.
        deals_counted: How many closed deals fell inside the day.
        carried_in_positions: Positions opened before this server day began.
            When this is non-zero the figure includes loss inherited from
            earlier days, and is stricter than a same-day-only reading.
    """

    day_start: datetime
    day_end: datetime
    realised: float
    floating: float
    total: float
    opening_balance: float
    limit_pct: float
    limit_currency: float
    loss: float
    used_fraction_of_limit: float | None
    remaining: float
    breached: bool
    deals_counted: int
    carried_in_positions: int


def daily_loss_status(
    account: AccountState,
    positions: tuple[PositionState, ...],
    deals: tuple[DealState, ...],
    limit_pct: float,
    now: datetime,
    clock: RolloverClock | None,
) -> DailyLossStatus | Refusal:
    """Measure the trading day's result against the limit.

    Args:
        account: The account reading.
        positions: Open positions, for the floating result.
        deals: Closed deals. Filtered to the server day here rather than by
            the caller, so that the day boundary is applied in exactly one
            place.
        limit_pct: The configured daily loss limit, as a percentage.
        now: Reading time, timezone-aware UTC.
        clock: The server clock, or ``None``.

    Returns:
        The status, or a :class:`Refusal` when the server day is unknown.
    """
    if clock is None:
        return Refusal(
            RefusalCode.NO_SERVER_CLOCK,
            "daily loss limit",
            "the server clock could not be located, so the trading day's "
            "boundaries are unknown; measuring the limit over a UTC day "
            "instead would mix two sessions and report a loss that was never "
            "the loss at any instant",
        )

    day_start, day_end = clock.server_day_bounds(now)
    today = [d for d in deals if day_start <= d.closed_at < day_end]
    realised = sum(d.realised for d in today)
    floating = sum(p.profit + p.swap for p in positions)
    total = realised + floating

    opening_balance = account.equity - total
    limit_currency = opening_balance * limit_pct / 100.0
    loss = max(0.0, -total)

    return DailyLossStatus(
        day_start=day_start,
        day_end=day_end,
        realised=realised,
        floating=floating,
        total=total,
        opening_balance=opening_balance,
        limit_pct=limit_pct,
        limit_currency=limit_currency,
        loss=loss,
        used_fraction_of_limit=(loss / limit_currency if limit_currency > 0 else None),
        remaining=max(0.0, limit_currency - loss),
        breached=limit_currency > 0 and loss >= limit_currency,
        deals_counted=len(today),
        carried_in_positions=sum(1 for p in positions if p.opened_at < day_start),
    )


@dataclass(frozen=True, slots=True)
class ConcurrencyStatus:
    """How many positions are open against the configured maximum.

    Counted per position rather than per symbol. Two lots of gold opened as
    two tickets are two positions here, because the thing being limited is the
    number of independent ways the account can be wrong at once, and a broker
    in hedging mode will happily let those two be in opposite directions.

    Attributes:
        open_positions: Total open tickets.
        limit: The configured maximum.
        breached: Whether the count is at or above the maximum.
        headroom: How many more may be opened before the limit binds.
        by_symbol: ``(symbol, count)`` pairs, sorted by symbol.
        by_direction: ``(direction, count)`` pairs.
    """

    open_positions: int
    limit: int
    breached: bool
    headroom: int
    by_symbol: tuple[tuple[str, int], ...]
    by_direction: tuple[tuple[str, int], ...]


def concurrency_status(
    positions: tuple[PositionState, ...], limit: int
) -> ConcurrencyStatus:
    """Count open positions against the maximum.

    Args:
        positions: Open positions.
        limit: The configured maximum.

    Returns:
        The status.
    """
    by_symbol = Counter(p.symbol for p in positions)
    by_direction = Counter(p.direction.value for p in positions)
    count = len(positions)
    return ConcurrencyStatus(
        open_positions=count,
        limit=limit,
        breached=count >= limit,
        headroom=max(0, limit - count),
        by_symbol=tuple(sorted(by_symbol.items())),
        by_direction=tuple(sorted(by_direction.items())),
    )
