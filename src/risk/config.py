"""The configured limits, and where each number came from.

Every default here is **provisional pending the probe**. They were chosen
before any figure had been read off a live terminal, and the acceptance step is
what confirms or moves them. Nothing in this module is registered, nothing here
is a hypothesis, and changing one of these numbers requires no procedure beyond
deciding to.

That is worth stating explicitly, because this repository's other constants are
the opposite: ``EVALUATION.md`` §1 is immutable, H-008's sweep values are fixed
before the run they govern, and changing a registered constant after seeing a
result is hypothesis laundering. **None of that applies here.** These are
operating limits on a live account, not parameters of a claim, and they are
meant to be tuned by the person whose account it is.

Where each default came from
----------------------------

``risk_per_trade_pct = 1.0``
    The conventional figure. It has no evidential status in this project and is
    not defended here.

``daily_loss_limit_pct = 3.0``
    Three losing trades at the full per-trade risk. The relationship between
    the two numbers is the point: at 1% and 3%, the day stops after three
    full-size losses rather than after an unbounded number of them.

``max_concurrent_positions = 2``
    Deliberately low. Concurrent positions in one instrument are not
    independent bets, and the account that prompted this layer had no cap at
    all.

``time_in_trade_alert_hours = 48.0``
    Deliberately aggressive. The account died on a two-month hold; 48 hours
    makes the alert fire long before that shape can form. It is not a claim
    that 48 hours is the right holding period for anything — it is a tripwire
    set far enough back that there is time to respond.

``stop_atr_multiple = 1.5``
    The centre of H-008's registered sweep. Reused here because it is a
    reasonable default and the number was already written down, **not** because
    this layer tests it. H-008 is registered, unrun, and its subject was
    withdrawn when H-007 failed; nothing this module does bears on it.

``carry_alert_pct_of_equity = 1.0``
    Financing paid on one position reaching 1% of equity is roughly one
    full-size trade's risk budget spent on holding rather than on being right.

``swap_divergence_tolerance = 0.10``
    Applies to the *measured* route only. The broker's published figure is
    compared exactly, because it carries no measurement noise; the measured
    figure absorbs triple-swap timing and partial days and needs an allowance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

#: Refuse a per-trade risk above this. Not a judgement about what a good risk
#: budget is -- a guard against a typo. ``10`` where ``1`` was meant is a
#: plausible keystroke and a ruinous configuration.
MAX_SANE_RISK_PCT: Final = 10.0


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Operating limits for the risk layer.

    Attributes:
        risk_per_trade_pct: Percentage of equity a single trade may lose.
        daily_loss_limit_pct: Percentage of the day's opening balance at which
            the day stops.
        max_concurrent_positions: Open tickets allowed at once.
        time_in_trade_alert_hours: Age at which an open position raises an
            alert.
        stop_atr_multiple: ``k`` in the ``k x ATR`` stop distance.
        carry_projection_days: Forward horizons for financing projections.
        carry_alert_pct_of_equity: Financing paid on one position, as a
            percentage of equity, at which it raises an alert.
        margin_call_alert_days: Projected days to the broker's stop-out at
            which it raises an alert.
        swap_divergence_tolerance: Fractional allowance on the measured swap
            comparison.
        minimum_days_for_measured_carry: How long a position must have been
            open before its own charge history is read as a rate.
        heartbeat_stale_seconds: Age at which the monitor's heartbeat is
            treated as dead, so that a status check refuses to report "all
            clear" from a process that is no longer running.
    """

    risk_per_trade_pct: float = 1.0
    daily_loss_limit_pct: float = 3.0
    max_concurrent_positions: int = 2
    time_in_trade_alert_hours: float = 48.0
    stop_atr_multiple: float = 1.5
    carry_projection_days: tuple[float, ...] = field(default=(7.0, 30.0, 60.0, 90.0))
    carry_alert_pct_of_equity: float = 1.0
    margin_call_alert_days: float = 30.0
    swap_divergence_tolerance: float = 0.10
    minimum_days_for_measured_carry: float = 1.0
    heartbeat_stale_seconds: float = 180.0

    def __post_init__(self) -> None:
        """Refuse a configuration that cannot mean what it says.

        Raises:
            ValueError: If any limit is out of range. Each message names the
                field and the bound, because a monitor that will not start is
                only useful if it says why.
        """
        if not 0 < self.risk_per_trade_pct <= MAX_SANE_RISK_PCT:
            raise ValueError(
                f"risk_per_trade_pct must be in (0, {MAX_SANE_RISK_PCT}], got "
                f"{self.risk_per_trade_pct}; a value above that is more often "
                f"a misplaced decimal point than an intention"
            )
        if not 0 < self.daily_loss_limit_pct <= 100.0:
            raise ValueError(
                f"daily_loss_limit_pct must be in (0, 100], got "
                f"{self.daily_loss_limit_pct}"
            )
        if self.max_concurrent_positions < 1:
            raise ValueError(
                f"max_concurrent_positions must be at least 1, got "
                f"{self.max_concurrent_positions}; zero would make every "
                f"reading a breach and the alert meaningless"
            )
        if self.time_in_trade_alert_hours <= 0:
            raise ValueError(
                f"time_in_trade_alert_hours must be positive, got "
                f"{self.time_in_trade_alert_hours}"
            )
        if self.stop_atr_multiple <= 0:
            raise ValueError(
                f"stop_atr_multiple must be positive, got {self.stop_atr_multiple}"
            )
        if not self.carry_projection_days:
            raise ValueError("carry_projection_days must not be empty")
        if any(d <= 0 for d in self.carry_projection_days):
            raise ValueError(
                f"every carry projection horizon must be positive, got "
                f"{self.carry_projection_days}"
            )
        if self.carry_alert_pct_of_equity <= 0:
            raise ValueError(
                f"carry_alert_pct_of_equity must be positive, got "
                f"{self.carry_alert_pct_of_equity}"
            )
        if self.margin_call_alert_days <= 0:
            raise ValueError(
                f"margin_call_alert_days must be positive, got "
                f"{self.margin_call_alert_days}"
            )
        if self.swap_divergence_tolerance < 0:
            raise ValueError(
                f"swap_divergence_tolerance must be non-negative, got "
                f"{self.swap_divergence_tolerance}"
            )
        if self.minimum_days_for_measured_carry <= 0:
            raise ValueError(
                f"minimum_days_for_measured_carry must be positive, got "
                f"{self.minimum_days_for_measured_carry}"
            )
        if self.heartbeat_stale_seconds <= 0:
            raise ValueError(
                f"heartbeat_stale_seconds must be positive, got "
                f"{self.heartbeat_stale_seconds}"
            )
