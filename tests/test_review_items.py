"""The open-review register, and that its two halves agree.

``REVIEW_ITEMS.md`` carries the reasoning; ``src/data/review.py`` carries the
identifiers and blocking conditions. Both are needed — the prose is where a
reader learns what would settle the question, and the module is what makes the
blocking condition something other than a suggestion.

Two copies of the same fact drift. These tests are what stops one being closed
while the other still says OPEN, which would be worse than having only the
prose: the code would silently stop blocking while the document still claimed
it did.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from data.review import (
    REVIEW_ITEMS,
    ReviewItemError,
    assert_not_blocked_by,
    find,
    open_items,
)

REGISTER = Path(__file__).resolve().parents[1] / "REVIEW_ITEMS.md"


def _document() -> str:
    """The prose register.

    Returns:
        Its text.
    """
    return REGISTER.read_text(encoding="utf-8")


def test_the_register_exists_and_is_not_empty() -> None:
    """A vacuous register must not be able to report success."""
    assert REGISTER.exists()
    assert REVIEW_ITEMS


def test_every_coded_item_has_a_section_in_the_document() -> None:
    """An item enforced in code but undocumented is a rule with no reason."""
    text = _document()
    for item in REVIEW_ITEMS:
        assert f"## {item.ident}" in text, item.ident


def test_every_documented_item_exists_in_code() -> None:
    """An item documented but not coded blocks nothing.

    This is the direction that fails silently. The document would say a
    condition is blocked, the code would not block it, and nobody would find
    out until something got through.
    """
    documented = set(re.findall(r"^## (R-\d{3})", _document(), flags=re.MULTILINE))
    coded = {item.ident for item in REVIEW_ITEMS}
    assert documented == coded, (documented - coded, coded - documented)


def test_the_documents_status_matches_the_codes() -> None:
    """OPEN in one and closed in the other is the drift this file exists for."""
    text = _document()
    for item in REVIEW_ITEMS:
        section = text.split(f"## {item.ident}", 1)[1].split("\n## ", 1)[0]
        says_open = "**Status:** OPEN" in section
        assert says_open == item.is_open, (
            f"{item.ident}: document says {'OPEN' if says_open else 'closed'}, "
            f"code says {'open' if item.is_open else 'closed'}"
        )


def test_an_item_cannot_be_closed_without_naming_the_source() -> None:
    """Closing means recording what was consulted, not just a date.

    A closing date with no source is indistinguishable from someone deciding
    the item had been open long enough.
    """
    for item in REVIEW_ITEMS:
        if item.closed is not None:
            assert item.closed_by, (
                f"{item.ident} has a closing date and no source. The source is "
                f"the whole content of a review; the date is bookkeeping."
            )


def test_every_item_names_what_would_close_it() -> None:
    """A condition nobody can tell they have met is not a condition."""
    for item in REVIEW_ITEMS:
        assert len(item.external_source_required) > 40, item.ident
        assert item.owner, item.ident
        assert item.blocks, item.ident


# ---------------------------------------------------------------------------
# The block can fire
# ---------------------------------------------------------------------------


def test_r001_is_open_and_blocks() -> None:
    """The item this register was created for."""
    item = find("R-001")
    assert item.is_open
    assert item in open_items()
    with pytest.raises(ReviewItemError, match="R-001"):
        assert_not_blocked_by("R-001", "registering a session-relative feature")


def test_the_block_says_re_deriving_is_not_reviewing() -> None:
    """The error carries the distinction, not just the refusal.

    Someone hitting this will reach for ``report_session_eras.py``, because it
    is the obvious thing and it is right there. The message has to say why
    that does not count, at the moment they are about to do it.
    """
    with pytest.raises(ReviewItemError) as caught:
        assert_not_blocked_by("R-001", "x")
    assert "circular" in str(caught.value)
    assert "report_session_eras" in str(caught.value)


def test_an_unknown_item_is_an_error_not_a_pass() -> None:
    """Guarding against a typo'd identifier silently blocking nothing."""
    with pytest.raises(ReviewItemError, match="no review item"):
        assert_not_blocked_by("R-999", "anything")


def test_a_closed_item_does_not_block() -> None:
    """The register must be able to release something, or it is a wall."""
    closed = replace(
        find("R-001"),
        closed=date(2026, 8, 1),
        closed_by="a source that does not exist, in a test",
    )
    assert not closed.is_open


def test_a_closing_date_alone_does_not_release_it() -> None:
    """The self-clearing rule, same shape as the raw-export awaiting flag."""
    dated_only = replace(find("R-001"), closed=date(2026, 8, 1))
    assert dated_only.is_open
