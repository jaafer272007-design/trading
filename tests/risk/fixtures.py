"""Builders for the account state the risk layer reads.

Values are shaped like a retail gold CFD account and are deliberately *not*
round: a fixture whose every number is 100 hides an arithmetic error that a
fixture with 2,437.50 in it surfaces immediately.

The default symbol charges **10 points a night on a long**, which is below the
registered substitute's 20 on the per-night basis and below it on the weekly
basis too. :func:`gold` takes overrides so that a test can move it either side
of the line and say which line it moved across.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from risk.state import (
    OFFSET_MEASURED,
    AccountState,
    DealState,
    PositionDirection,
    PositionState,
    SymbolTerms,
    TerminalState,
)

#: An arbitrary but fixed reading time. Every test that needs "now" uses this
#: one, so no test can pass because it happened to run on a Tuesday.
NOW: Final = datetime(2026, 7, 29, 14, 30, 0, tzinfo=UTC)

#: The broker server sits three hours ahead of UTC, which is where a European
#: MT5 server sits in summer. Chosen non-zero on purpose: an offset of zero
#: would let a bug that ignores the offset entirely pass every test.
SERVER_OFFSET_HOURS: Final = 3.0


def terminal(**overrides: Any) -> TerminalState:  # noqa: ANN401
    """A connected terminal with a measured server clock.

    Args:
        **overrides: Fields to replace.

    Returns:
        The terminal state.
    """
    fields: dict[str, Any] = {
        "connected": True,
        "trade_allowed": True,
        "build": 4620,
        "server_utc_offset_hours": SERVER_OFFSET_HOURS,
        "server_offset_source": OFFSET_MEASURED,
    }
    fields.update(overrides)
    return TerminalState(**fields)


def account(**overrides: Any) -> AccountState:  # noqa: ANN401
    """A demo account with one position's worth of margin in use.

    Args:
        **overrides: Fields to replace.

    Returns:
        The account state.
    """
    fields: dict[str, Any] = {
        "currency": "USD",
        "balance": 4_812.55,
        "equity": 4_637.20,
        "margin": 481.44,
        "margin_free": 4_155.76,
        "margin_level": 963.19,
        "margin_so_call": 100.0,
        "margin_so_so": 50.0,
        "margin_so_mode": 0,
        "leverage": 500,
        "is_demo": True,
    }
    fields.update(overrides)
    return AccountState(**fields)


def gold(**overrides: Any) -> SymbolTerms:  # noqa: ANN401
    """Gold as a retail broker publishes it.

    ``point``, ``trade_tick_size`` and ``trade_tick_value`` are set so that one
    point on one lot is worth exactly 1.00 in the deposit currency, which is
    what ``backtest.costs.POINT_VALUE_PER_LOT`` also comes to. The agreement
    makes the arithmetic in these tests checkable by hand; nothing in the code
    relies on it.

    Args:
        **overrides: Fields to replace.

    Returns:
        The symbol terms.
    """
    fields: dict[str, Any] = {
        "name": "XAUUSD",
        "digits": 2,
        "point": 0.01,
        "trade_tick_size": 0.01,
        "trade_tick_value": 1.0,
        "trade_contract_size": 100.0,
        "volume_min": 0.01,
        "volume_max": 50.0,
        "volume_step": 0.01,
        "spread_points": 32.0,
        "spread_is_floating": True,
        "swap_mode": 1,
        "swap_long": -10.0,
        "swap_short": 2.0,
        "swap_rollover_3days_weekday": 3,
        "currency_base": "XAU",
        "currency_profit": "USD",
        "currency_margin": "USD",
    }
    fields.update(overrides)
    return SymbolTerms(**fields)


def position(**overrides: Any) -> PositionState:  # noqa: ANN401
    """A long gold position opened two days before :data:`NOW`.

    Opened 2026-07-27, a Monday, and read on the Wednesday: exactly two
    calendar days. Its ``swap`` of ``-2.00`` over two days is 1.00 a day, which
    is what the default symbol's published rate comes to on 0.10 lots -- 10
    points per lot per night at 1.00 a point, a tenth of a lot. The two routes
    therefore agree by construction, and a test that wants them to disagree
    moves one of them and says which.

    Args:
        **overrides: Fields to replace.

    Returns:
        The position state.
    """
    fields: dict[str, Any] = {
        "ticket": 3_118_442,
        "symbol": "XAUUSD",
        "direction": PositionDirection.LONG,
        "volume": 0.10,
        "price_open": 2_411.35,
        "price_current": 2_398.80,
        "opened_at": datetime(2026, 7, 27, 14, 30, 0, tzinfo=UTC),
        "stop_loss": 2_380.00,
        "take_profit": None,
        "swap": -2.0,
        "profit": -125.50,
        "margin": 481.44,
    }
    fields.update(overrides)
    return PositionState(**fields)


def deal(**overrides: Any) -> DealState:  # noqa: ANN401
    """One closed deal inside the current server day.

    Args:
        **overrides: Fields to replace.

    Returns:
        The deal state.
    """
    fields: dict[str, Any] = {
        "ticket": 9_004_771,
        "symbol": "XAUUSD",
        "profit": -84.20,
        "commission": -1.40,
        "swap": -3.00,
        "fee": 0.0,
        "closed_at": datetime(2026, 7, 29, 9, 15, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return DealState(**fields)
