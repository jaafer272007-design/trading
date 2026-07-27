"""Open review items, and the conditions they block.

A review item is a claim this project has made about the world that **has not
been checked against a source outside this project**. It is not a bug and not
a hypothesis. It is a declaration standing on internal evidence alone, with a
named person who has to go and look.

Why this is a module and not a paragraph
----------------------------------------

``REVIEW_ITEMS.md`` is the human-readable register and is where the reasoning
lives. This file exists because a blocking condition written only in prose is
a blocking condition nobody enforces. The register is loaded by tests, and the
things an open item forbids are refused in code.

The distinction being enforced
------------------------------

``scripts/report_session_eras.py`` re-derives the session eras from the feed
and exits non-zero if they stop agreeing. That is worth having, and it is
**not** a review. It establishes *still agrees with the feed* — the same feed
the declaration was derived from in the first place — and says nothing about
*agrees with reality*. A calendar derived from a feed and then validated
against that feed is circular, which is the argument ``calendar.py`` already
makes for the clock rule and which applies with equal force here.

Only a source outside this project closes a review item: the broker's own
session-hours announcements, an exchange's published schedule, a regulator's
notice. Another measurement of the same data is not one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final


class ReviewItemError(RuntimeError):
    """Something blocked by an open review item was attempted."""


@dataclass(frozen=True)
class ReviewItem:
    """One claim awaiting confirmation from outside this project."""

    ident: str
    title: str
    owner: str
    raised: date
    external_source_required: str
    """What would actually close it. Named specifically, because "review it"
    is not a condition anyone can tell they have met."""

    blocks: str
    """What may not happen while this is open, in one line."""

    closed: date | None = None
    closed_by: str = ""
    """The external source consulted, and what it said. Empty while open."""

    @property
    def is_open(self) -> bool:
        """Whether the item still blocks.

        Returns:
            True until a closing date and a cited source are both recorded.
        """
        return self.closed is None or not self.closed_by


#: Every open review item. Nothing is ever deleted from here — a closed item
#: keeps its entry with the date and the source that closed it, for the same
#: reason ``HYPOTHESES.md`` keeps rejected hypotheses: the record of what was
#: checked is what makes the conclusion worth anything later.
REVIEW_ITEMS: Final[tuple[ReviewItem, ...]] = (
    ReviewItem(
        ident="R-001",
        title="session.eras has not been reviewed against an external source",
        owner="jaafer272007-design",
        raised=date(2026, 7, 27),
        external_source_required=(
            "FxPro's own published session-hours announcements or client "
            "notices covering 2017-10 and 2022-10. Not the feed, and not "
            "another measurement of the feed."
        ),
        blocks=(
            "No session-relative feature may be registered. A feature that "
            "reads the session open, the session close, position within the "
            "session, or bars until the break is measuring different things "
            "on either side of 2017-10-07, and the era boundaries themselves "
            "rest on unreviewed evidence."
        ),
    ),
)


def open_items() -> tuple[ReviewItem, ...]:
    """The items still blocking.

    Returns:
        Open entries, in registration order.
    """
    return tuple(item for item in REVIEW_ITEMS if item.is_open)


def find(ident: str) -> ReviewItem:
    """Look up one item.

    Args:
        ident: Its identifier, e.g. ``"R-001"``.

    Returns:
        The entry.

    Raises:
        ReviewItemError: If no such item is registered.
    """
    for item in REVIEW_ITEMS:
        if item.ident == ident:
            return item
    raise ReviewItemError(
        f"no review item {ident!r}; have {[i.ident for i in REVIEW_ITEMS]}"
    )


def assert_not_blocked_by(ident: str, what: str) -> None:
    """Refuse an action an open review item forbids.

    Args:
        ident: The review item.
        what: What was attempted, for the message.

    Raises:
        ReviewItemError: If the item is open.
    """
    item = find(ident)
    if not item.is_open:
        return
    raise ReviewItemError(
        f"{what} is blocked by {item.ident} ({item.title}).\n"
        f"  blocks : {item.blocks}\n"
        f"  owner  : {item.owner}, raised {item.raised}\n"
        f"  closes : {item.external_source_required}\n"
        f"Re-running scripts/report_session_eras.py does not close this. It "
        f"checks that the declaration still agrees with the feed it was "
        f"derived from, which is circular, and says nothing about whether the "
        f"declaration is true."
    )
