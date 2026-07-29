"""Refusals — the record of everything this layer declined to guess.

``CLAUDE.md`` Hard Rule 6 forbids silent imputation. In a research pipeline
that rule protects a result. Here it protects an account: a defaulted margin
level or an assumed swap convention produces a days-to-margin-call figure that
is confident, plausible and wrong, and the person reading it has no way to
tell.

So every quantity this layer cannot compute produces a :class:`Refusal` naming
what was missing and why it matters, the refusals travel with the report as a
first-class field, and the renderer prints them above the numbers rather than
below. A report with refusals in it is not a broken report — it is a report
that is telling you which of its numbers do not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RefusalCode(StrEnum):
    """Why a quantity was not computed."""

    #: ``symbol_info`` did not supply usable tick figures, so points cannot be
    #: converted to money at all.
    NO_POINT_VALUE = "NO_POINT_VALUE"
    #: ``swap_mode`` is one whose units cannot be converted to points per lot
    #: per night without an assumption this layer refuses to make.
    SWAP_MODE_UNSUPPORTED = "SWAP_MODE_UNSUPPORTED"
    #: The swap rate is quoted in a currency that is not the deposit currency,
    #: and converting it needs a rate this layer does not have.
    SWAP_CURRENCY_MISMATCH = "SWAP_CURRENCY_MISMATCH"
    #: ``margin_so_mode`` is not one of the two documented values.
    MARGIN_MODE_UNSUPPORTED = "MARGIN_MODE_UNSUPPORTED"
    #: No open position carries margin, so no margin level exists to project.
    NO_MARGIN_IN_USE = "NO_MARGIN_IN_USE"
    #: The server clock could not be located, so the server day and the
    #: rollover boundary are both unknown.
    NO_SERVER_CLOCK = "NO_SERVER_CLOCK"
    #: A position has not been open long enough for its measured financing
    #: rate to mean anything.
    CARRY_TOO_YOUNG = "CARRY_TOO_YOUNG"
    #: Neither a measured nor a modelled financing rate is available, so
    #: nothing can be projected forward.
    NO_CARRY_RATE = "NO_CARRY_RATE"
    #: Position sizing was asked for with an ATR that is zero or negative.
    NO_VOLATILITY = "NO_VOLATILITY"
    #: The computed size is below the broker's minimum tradeable volume.
    SIZE_BELOW_MINIMUM = "SIZE_BELOW_MINIMUM"
    #: ``volume_step`` is zero or negative, so no size can be rounded to it.
    NO_VOLUME_STEP = "NO_VOLUME_STEP"
    #: A position references a symbol whose terms were not supplied.
    SYMBOL_TERMS_MISSING = "SYMBOL_TERMS_MISSING"
    #: The terminal is not connected to the broker, so every reading is stale
    #: by an unknown amount.
    TERMINAL_DISCONNECTED = "TERMINAL_DISCONNECTED"


@dataclass(frozen=True, slots=True)
class Refusal:
    """One quantity that was not computed, and the reason.

    Attributes:
        code: Machine-readable cause.
        subject: What was being computed, in human terms — a ticket number, a
            symbol, or the name of the figure.
        reason: One sentence a person can act on. Not a stack trace and not a
            restatement of the code.
    """

    code: RefusalCode
    subject: str
    reason: str

    def __str__(self) -> str:
        """Render as one line.

        Returns:
            ``CODE  subject: reason``.
        """
        return f"{self.code.value}  {self.subject}: {self.reason}"
