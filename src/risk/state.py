"""What the adapter reads from MT5, as plain frozen values.

Every field here corresponds to something the terminal publishes. The types
are deliberately plain — ``datetime``, ``float``, ``int``, ``str`` and nothing
else — so that the whole arithmetic core is importable and constructible on a
machine that has never seen MetaTrader, which is the only way it can be tested
at all. The adapter under ``scripts/risk_monitor.py`` is the single place that
knows the ``MetaTrader5`` module exists.

Signs and units, stated once
----------------------------

Two conventions cause every sign error in this area, so both are pinned here
and converted at the boundary rather than carried through the code:

``swap``
    MT5 reports accumulated financing on a position with the **broker's**
    sign: **negative means the account was charged**. Every function in this
    package works in *charge* terms instead, where **positive means money
    left the account**. :func:`carry_paid` is the one conversion.

``swap_long`` / ``swap_short``
    Same convention on the symbol's published rate, and in units chosen by
    ``swap_mode`` rather than fixed. :mod:`risk.swap` normalises both to a
    charge in **points per lot per night**, and refuses when the mode does not
    permit that conversion.

Prices are in the symbol's own units. Anything called ``_points`` is in
multiples of ``SymbolTerms.point``. Anything called ``_currency``, or any bare
money quantity, is in the **account's deposit currency**, which is also the
currency ``trade_tick_value`` is denominated in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

#: Reported by the adapter when it could measure the server clock against true
#: UTC from a fresh tick, when it fell back to a value it cached from an
#: earlier measurement, and when a human supplied one on the command line.
OFFSET_MEASURED: Final = "measured"
OFFSET_CACHED: Final = "cached"
OFFSET_EXPLICIT: Final = "explicit"
OFFSET_UNAVAILABLE: Final = "unavailable"


class PositionDirection(StrEnum):
    """Which way a position faces.

    An enum rather than MT5's ``POSITION_TYPE_BUY``/``SELL`` integers: the
    integers are 0 and 1, and 0 is exactly the value a bug produces.
    """

    LONG = "long"
    SHORT = "short"


def _require_utc(value: datetime, field: str) -> None:
    """Refuse a naive timestamp.

    A naive datetime here would be silently interpreted as the local clock of
    whatever machine the monitor happens to run on, and every rollover count
    downstream would be wrong by the offset.

    Args:
        value: The timestamp to check.
        field: Field name, for the message.

    Raises:
        ValueError: If ``value`` carries no timezone.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field} must be timezone-aware UTC; a naive timestamp would be "
            f"read as local time and every rollover count derived from it "
            f"would be wrong by the machine's offset"
        )


@dataclass(frozen=True, slots=True)
class TerminalState:
    """The terminal itself, and whether its clock could be located.

    ``server_utc_offset_hours`` is not a constant and is not read from
    configuration. MT5 reports timestamps as the **server's** wall clock
    expressed as a Unix epoch, so the offset is measurable by comparing a
    fresh tick against true UTC — the same measurement ``scripts/mt5_probe.py``
    makes. It is ``None`` when no measurement was possible, and every
    quantity that depends on the server day is then refused rather than
    computed against a guessed offset.
    """

    connected: bool
    trade_allowed: bool
    build: int
    server_utc_offset_hours: float | None
    server_offset_source: str

    def __post_init__(self) -> None:
        """Check the offset and its provenance agree.

        Raises:
            ValueError: If the source label contradicts the value.
        """
        has_value = self.server_utc_offset_hours is not None
        claims_value = self.server_offset_source != OFFSET_UNAVAILABLE
        if has_value != claims_value:
            raise ValueError(
                f"server_utc_offset_hours={self.server_utc_offset_hours} "
                f"contradicts server_offset_source={self.server_offset_source!r}"
            )


@dataclass(frozen=True, slots=True)
class AccountState:
    """One reading of ``account_info()``.

    ``margin_so_call`` and ``margin_so_so`` are the broker's own margin-call
    and stop-out levels, and their **units depend on** ``margin_so_mode``:
    percent of margin when the mode is 0, deposit currency when it is 1. They
    are not assumed and not defaulted; :mod:`risk.margin` refuses any mode it
    does not recognise.
    """

    currency: str
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    margin_so_call: float
    margin_so_so: float
    margin_so_mode: int
    leverage: int
    is_demo: bool


@dataclass(frozen=True, slots=True)
class SymbolTerms:
    """One reading of ``symbol_info()`` for a traded symbol.

    The swap fields are carried raw, in whatever units ``swap_mode`` declares.
    Normalising them is :mod:`risk.swap`'s job and is allowed to fail.
    """

    name: str
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: float
    trade_contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    spread_points: float
    spread_is_floating: bool
    swap_mode: int
    swap_long: float
    swap_short: float
    swap_rollover_3days_weekday: int
    currency_base: str
    currency_profit: str
    currency_margin: str


@dataclass(frozen=True, slots=True)
class PositionState:
    """One open position, as ``positions_get()`` reports it.

    ``margin`` is not a field MT5 returns on a position. The adapter fills it
    from ``order_calc_margin`` — a pure calculation call that places nothing —
    and it stays ``None`` when that call is unavailable.
    """

    ticket: int
    symbol: str
    direction: PositionDirection
    volume: float
    price_open: float
    price_current: float
    opened_at: datetime
    stop_loss: float | None
    take_profit: float | None
    swap: float
    profit: float
    margin: float | None

    def __post_init__(self) -> None:
        """Refuse a position that cannot be reasoned about.

        Raises:
            ValueError: If the timestamp is naive, or volume or open price is
                not positive.
        """
        _require_utc(self.opened_at, "opened_at")
        if self.volume <= 0:
            raise ValueError(
                f"position {self.ticket}: volume must be positive, got {self.volume}"
            )
        if self.price_open <= 0:
            raise ValueError(
                f"position {self.ticket}: price_open must be positive, "
                f"got {self.price_open}"
            )

    @property
    def has_stop(self) -> bool:
        """Whether a stop loss is attached.

        MT5 reports an absent stop as ``0.0`` rather than as null, so the
        adapter maps zero to ``None`` and this property reads the mapped
        value. A position with no stop is the shape that produces an
        open-ended drawdown, which is why it is worth naming.

        Returns:
            True when a non-zero stop is set.
        """
        return self.stop_loss is not None


@dataclass(frozen=True, slots=True)
class DealState:
    """One closed deal from ``history_deals_get()``.

    Realised profit and loss on MT5 is not a single field. A closing deal
    carries ``profit``, and the costs of the round turn arrive separately as
    ``commission``, ``swap`` and ``fee`` — sometimes on the closing deal,
    sometimes on the opening one. :func:`realised` sums all four so that a
    day's realised result cannot be understated by looking at ``profit``
    alone, which is the natural mistake and always flatters the number.
    """

    ticket: int
    symbol: str
    profit: float
    commission: float
    swap: float
    fee: float
    closed_at: datetime

    def __post_init__(self) -> None:
        """Refuse a naive timestamp.

        Raises:
            ValueError: If ``closed_at`` carries no timezone.
        """
        _require_utc(self.closed_at, "closed_at")

    @property
    def realised(self) -> float:
        """Total effect of this deal on the balance, in account currency.

        Returns:
            ``profit + commission + swap + fee``, signed as MT5 signs them:
            negative is a loss.
        """
        return self.profit + self.commission + self.swap + self.fee


def value_per_point_per_lot(terms: SymbolTerms) -> float | None:
    """Account-currency value of a one-point move on one lot.

    Derived from the broker's own tick figures rather than from the contract
    size, because ``trade_tick_value`` is already denominated in the deposit
    currency and therefore already carries any conversion the broker applies.
    Computing it as ``contract_size x point`` instead would be correct only
    when the profit currency happens to be the deposit currency, and wrong
    silently when it is not.

    For gold at ``point = 0.01``, ``tick_size = 0.01``, ``tick_value = 1.0``
    this returns 1.0, which is the same number
    ``backtest.costs.POINT_VALUE_PER_LOT`` states. The agreement is a
    coincidence of this contract and is not relied on anywhere.

    Args:
        terms: Symbol terms as read from the terminal.

    Returns:
        Currency per point per lot, or ``None`` when the broker has not
        populated the fields the conversion needs.
    """
    if terms.point <= 0 or terms.trade_tick_size <= 0:
        return None
    if terms.trade_tick_value <= 0:
        return None
    return terms.trade_tick_value * (terms.point / terms.trade_tick_size)
