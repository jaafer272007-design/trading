"""Days to margin call, at the current financing rate and a constant price.

The projection is one division, and everything difficult about it is in the
assumptions, so they are stated in full rather than buried.

**Price is held constant.** The figure answers "if the market does nothing at
all, how long does financing alone take to reach the broker's margin call?"
That is a bound, not a forecast, and it is the useful direction: an adverse
move makes it sooner, never later. Holding price constant also holds required
margin constant, since margin on a CFD moves with price, so the threshold and
the equity path are consistent with each other rather than mixing a moving
threshold with a static one.

**The threshold is the broker's, not a convention.** ``margin_so_call`` and
``margin_so_so`` come from ``account_info()``, and their units come from
``margin_so_mode``. Nothing here assumes 100%/50%, or any other pair of numbers
that a documentation page might suggest. An unrecognised mode is refused.

**Both levels are reported.** The margin call is a warning; the stop-out is
where positions are closed without being asked. An account that goes to zero
goes through the second one, so it is the number that matters and it is not
buried under the first.

Implausible leverage voids the projection entirely
--------------------------------------------------

`[MEASURED]` 2026-07-29, on the demo account the probe ran against:
``leverage = 1:2,000,000,000``. That is a demo artefact, and it does not merely
make the projection imprecise -- it makes it meaningless, by a mechanism worth
stating because it is not obvious from the formula.

Leverage does not appear anywhere in the arithmetic below. It does not have to.
Required margin is proportional to ``1 / leverage``, and in percent mode the
intervention threshold is ``margin x level / 100`` -- so at absurd leverage the
margin collapses toward zero, the threshold collapses with it, and the headroom
becomes the whole of equity. The projection then reports that financing needs
years to reach a stop-out that the account can in practice never hit, because
its margin regime is not one any real account has.

A number that is arithmetically correct and describes nothing is worse than a
refusal, so the projection is refused outside :data:`MIN_PLAUSIBLE_LEVERAGE` to
:data:`MAX_PLAUSIBLE_LEVERAGE`. Unlimited-leverage accounts fall outside that
range and are refused for the same reason rather than in spite of it: an account
with no margin requirement has no margin projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Final

from risk.refusal import Refusal, RefusalCode
from risk.state import AccountState

#: MT5's ``ENUM_ACCOUNT_STOPOUT_MODE``.
STOPOUT_MODE_PERCENT: Final = 0
STOPOUT_MODE_MONEY: Final = 1

#: The range of account leverage within which a margin projection describes
#: something. 1:1 is a fully funded account; 1:5000 is beyond the most
#: aggressive offshore retail offer seen in practice. These are bounds on
#: plausibility, not operating limits -- they are facts about what brokers
#: offer, so they live here rather than in :class:`risk.config.RiskConfig`,
#: and widening one is a claim about the market rather than a preference.
MIN_PLAUSIBLE_LEVERAGE: Final = 1
MAX_PLAUSIBLE_LEVERAGE: Final = 5_000


class StopoutMode(IntEnum):
    """How the broker expresses its margin-call and stop-out levels."""

    PERCENT = STOPOUT_MODE_PERCENT
    MONEY = STOPOUT_MODE_MONEY


@dataclass(frozen=True, slots=True)
class LevelProjection:
    """One of the broker's two intervention levels, and how far away it is.

    Attributes:
        name: ``"margin call"`` or ``"stop out"``.
        threshold_equity: Equity at which the level is reached, account
            currency.
        headroom: ``equity - threshold_equity``. Negative when already past
            it.
        already_breached: Whether the account is at or past the level now.
        daily_carry: Financing per calendar day used for the projection.
        days_to_reach: Headroom divided by daily financing. ``None`` when
            there is no financing rate, when financing is a net credit, or
            when the level is already breached.
        date_reached: That many days after the reading.
    """

    name: str
    threshold_equity: float
    headroom: float
    already_breached: bool
    daily_carry: float | None
    days_to_reach: float | None
    date_reached: datetime | None


@dataclass(frozen=True, slots=True)
class MarginProjection:
    """The account's distance from the broker's two intervention levels.

    Attributes:
        equity: Current equity.
        margin: Margin currently in use.
        margin_free: Free margin as the terminal reports it.
        margin_level_pct: ``equity / margin x 100``, or ``None`` when no
            margin is in use.
        mode: How the levels are expressed, or ``None`` when the mode was not
            recognised.
        call: The margin-call projection, or ``None``.
        stop_out: The stop-out projection, or ``None``.
        price_is_held_constant: Always true. Present as a field so that the
            assumption travels with the number into any serialised form,
            rather than living only in this docstring.
        refusals: Why a projection is missing, when one is.
    """

    equity: float
    margin: float
    margin_free: float
    margin_level_pct: float | None
    mode: StopoutMode | None
    call: LevelProjection | None
    stop_out: LevelProjection | None
    price_is_held_constant: bool
    refusals: tuple[Refusal, ...]


def _threshold_equity(level: float, mode: StopoutMode, margin: float) -> float:
    """Equity at which a stated level is reached.

    Args:
        level: The broker's figure, in the mode's units.
        mode: Percent of margin, or deposit currency.
        margin: Margin currently in use.

    Returns:
        Equity, in account currency.
    """
    if mode is StopoutMode.PERCENT:
        return margin * level / 100.0
    return level


def _project_level(
    name: str,
    level: float,
    mode: StopoutMode,
    account: AccountState,
    daily_carry: float | None,
    now: datetime,
) -> LevelProjection:
    """Project one intervention level.

    Args:
        name: Human name of the level.
        level: The broker's figure.
        mode: Units of that figure.
        account: The account reading.
        daily_carry: Financing per calendar day, positive meaning paid.
        now: Reading time.

    Returns:
        The projection.
    """
    threshold = _threshold_equity(level, mode, account.margin)
    headroom = account.equity - threshold
    breached = headroom <= 0

    days: float | None = None
    date: datetime | None = None
    if not breached and daily_carry is not None and daily_carry > 0:
        days = headroom / daily_carry
        date = now + timedelta(days=days)

    return LevelProjection(
        name=name,
        threshold_equity=threshold,
        headroom=headroom,
        already_breached=breached,
        daily_carry=daily_carry,
        days_to_reach=days,
        date_reached=date,
    )


def margin_projection(
    account: AccountState, daily_carry: float | None, now: datetime
) -> MarginProjection:
    """Project the account's distance from margin call and stop-out.

    Args:
        account: The account reading.
        daily_carry: Financing per calendar day across the book, positive
            meaning paid. ``None`` when no rate is available.
        now: Reading time, timezone-aware UTC.

    Returns:
        The projection, carrying a refusal for anything it could not compute.
    """
    refusals: list[Refusal] = []

    level_pct: float | None = None
    if account.margin > 0:
        level_pct = 100.0 * account.equity / account.margin
    else:
        refusals.append(
            Refusal(
                RefusalCode.NO_MARGIN_IN_USE,
                "margin projection",
                "no margin is in use, so there is no margin level and no "
                "intervention level to project toward",
            )
        )

    if not MIN_PLAUSIBLE_LEVERAGE <= account.leverage <= MAX_PLAUSIBLE_LEVERAGE:
        # Refused before the mode is even read: whatever the units, a threshold
        # proportional to a margin that is proportional to 1/leverage does not
        # describe this account. See the module docstring.
        refusals.append(
            Refusal(
                RefusalCode.LEVERAGE_IMPLAUSIBLE,
                "margin projection",
                f"leverage reads 1:{account.leverage:,}, outside the plausible "
                f"range 1:{MIN_PLAUSIBLE_LEVERAGE} to "
                f"1:{MAX_PLAUSIBLE_LEVERAGE:,}. Required margin is "
                f"proportional to 1/leverage and the intervention threshold is "
                f"proportional to margin, so at this leverage the threshold "
                f"collapses toward zero and the projection would report years "
                f"of headroom against a stop-out this account cannot reach. "
                f"That is a demo artefact, not a safe account",
            )
        )
        return MarginProjection(
            equity=account.equity,
            margin=account.margin,
            margin_free=account.margin_free,
            margin_level_pct=level_pct,
            mode=None,
            call=None,
            stop_out=None,
            price_is_held_constant=True,
            refusals=tuple(refusals),
        )

    try:
        mode: StopoutMode | None = StopoutMode(account.margin_so_mode)
    except ValueError:
        mode = None
        refusals.append(
            Refusal(
                RefusalCode.MARGIN_MODE_UNSUPPORTED,
                "margin projection",
                f"margin_so_mode={account.margin_so_mode} is not a documented "
                f"ENUM_ACCOUNT_STOPOUT_MODE value, so the units of "
                f"margin_so_call={account.margin_so_call} and "
                f"margin_so_so={account.margin_so_so} are unknown; guessing "
                f"percent would put the threshold out by orders of magnitude "
                f"if it is money",
            )
        )

    call: LevelProjection | None = None
    stop_out: LevelProjection | None = None
    if mode is not None and account.margin > 0:
        call = _project_level(
            "margin call", account.margin_so_call, mode, account, daily_carry, now
        )
        stop_out = _project_level(
            "stop out", account.margin_so_so, mode, account, daily_carry, now
        )
        if daily_carry is None:
            refusals.append(
                Refusal(
                    RefusalCode.NO_CARRY_RATE,
                    "margin projection",
                    "the levels below are located, but with no financing rate "
                    "there is no time axis and no days-to-reach figure",
                )
            )

    return MarginProjection(
        equity=account.equity,
        margin=account.margin,
        margin_free=account.margin_free,
        margin_level_pct=level_pct,
        mode=mode,
        call=call,
        stop_out=stop_out,
        price_is_held_constant=True,
        refusals=tuple(refusals),
    )
