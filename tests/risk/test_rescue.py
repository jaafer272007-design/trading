"""Recovering the sound fields from a log written under a bad server clock.

The claim this file exists to hold to account: **a contaminated carry log is
almost entirely salvageable, and the only casualty is the triple-swap
weekday.** That is a claim about which fields pass through the server offset,
and a claim about someone else's data flow with no test behind it is exactly
what instrument defect #8 was. So the last test here does not read the rescue
script at all -- it runs the real analyser over a rescued log and checks that
the verdict, the power assessment and the magnitude all still come out.
"""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from risk.carry_log import StructureVerdict, analyse, parse_rows

REPO: Final = Path(__file__).resolve().parents[2]

#: The offset the stale tick produced. `[MEASURED]` 2026-08-02.
BAD_OFFSET: Final = -23.0


def _load() -> ModuleType:
    """Import the rescue script by path.

    Returns:
        The loaded module.
    """
    path = REPO / "scripts" / "rescue_carry_log.py"
    spec = importlib.util.spec_from_file_location("rescue_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RESCUE: Final = _load()


def _contaminated(path: Path, *, nights: int = 6) -> None:
    """Write a log whose timing fields went through the bad offset.

    Args:
        path: Where to write it.
        nights: Charging events to include.
    """
    start = datetime(2026, 8, 2, 21, 0, tzinfo=UTC)
    prices = [4_090.0, 4_120.0, 4_100.0, 4_150.0, 4_130.0, 4_160.0][:nights]
    lines = []
    paid = 0.0
    for index, price in enumerate(prices):
        at = start + timedelta(days=index)
        paid = round(paid + 6.79, 2)
        lines.append(
            json.dumps(
                {
                    "at": at.isoformat(),
                    "ticket": 7,
                    "symbol": "GOLD",
                    "direction": "long",
                    "volume": 0.1,
                    "carry_paid": paid,
                    "price": price,
                    "published_swap_long": -67.9,
                    "published_swap_short": 27.0,
                    "floating_pnl": 120.0,
                    "equity": 5_000.0,
                    "currency": "USD",
                    # Everything below here went through the bad offset.
                    "opened_at": (at - timedelta(hours=26)).isoformat(),
                    "days_open": 1.1 + index,
                    "nights_held": index,
                    "server_offset_hours": BAD_OFFSET,
                    "server_offset_source": "cached",
                },
                sort_keys=True,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rows(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --------------------------------------------------------------------------
# The analyser refuses the original, which is the premise
# --------------------------------------------------------------------------


def test_the_contaminated_log_is_refused_before_any_rescue(tmp_path: Path) -> None:
    source = tmp_path / "carry.contaminated.jsonl"
    _contaminated(source)
    with pytest.raises(ValueError, match="cannot be trusted"):
        parse_rows(source.read_text(encoding="utf-8").splitlines())


# --------------------------------------------------------------------------
# Fields are dropped; rows are not
# --------------------------------------------------------------------------


def test_every_row_survives_because_this_is_not_filtering(tmp_path: Path) -> None:
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    assert RESCUE.main([str(source), str(out)]) == 0
    assert len(_rows(out)) == len(_rows(source))


def test_the_sound_fields_come_through_untouched(tmp_path: Path) -> None:
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    RESCUE.main([str(source), str(out)])
    before, after = _rows(source)[0], _rows(out)[0]
    for field in ("at", "ticket", "carry_paid", "price", "volume"):
        assert after[field] == before[field]
    # The one series that separates a re-quoted fixed rate from a
    # price-dependent one never touched the offset either.
    assert after["published_swap_long"] == pytest.approx(-67.9)


def test_the_void_fields_are_dropped_and_not_repaired(tmp_path: Path) -> None:
    # A corrected timestamp would be a guess that reads exactly like a
    # measurement. The true offset is not recoverable from the row.
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    RESCUE.main([str(source), str(out)])
    row = _rows(out)[0]
    assert "opened_at" not in row
    assert "days_open" not in row
    assert "nights_held" not in row
    assert row["server_offset_hours"] is None
    assert row["server_offset_source"] is None


def test_the_rescue_records_the_offset_it_was_rescued_from(tmp_path: Path) -> None:
    # So the file cannot be mistaken for one written by a healthy run.
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    RESCUE.main([str(source), str(out)])
    assert _rows(out)[0]["rescued_from_offset"] == pytest.approx(BAD_OFFSET)


def test_the_rescued_log_is_accepted_where_the_original_was_refused(
    tmp_path: Path,
) -> None:
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    RESCUE.main([str(source), str(out)])
    rows = parse_rows(out.read_text(encoding="utf-8").splitlines())
    assert len(rows) == 6


# --------------------------------------------------------------------------
# What the rescue actually costs the analysis
# --------------------------------------------------------------------------


def test_the_measurement_survives_the_rescue_in_full(tmp_path: Path) -> None:
    # The claim, checked against the real analyser rather than asserted.
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    RESCUE.main([str(source), str(out)])
    result = analyse(parse_rows(out.read_text(encoding="utf-8").splitlines()))

    # Six rows give FIVE increments: an increment needs a row on each side of
    # it, so N readings resolve N-1 charging events. That is also why the log
    # needs six readings to reach the five the structural test requires.
    assert result.power.resolved_nights == 5
    assert result.power.price_range_fraction is not None
    assert result.power.reversals >= 2
    assert result.charge_per_lot_per_night == pytest.approx(67.9)
    assert result.cv_unit_charge is not None
    assert result.cv_charge_over_price is not None
    assert result.charges_swaps
    # The field-stability channel survives too, which is the one that
    # discriminates a re-quoted fixed rate from a price-dependent one.
    assert result.field.changed is False
    assert result.field.distinct == (-67.9,)
    # And it reaches a verdict -- the strongest form of "the measurement
    # survives". The fixture is a fixed rate and the analyser says so.
    assert result.power.has_power
    assert result.verdict is StructureVerdict.FIXED_RATE


def test_the_only_casualty_is_the_triple_swap_weekday(tmp_path: Path) -> None:
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    RESCUE.main([str(source), str(out)])
    result = analyse(parse_rows(out.read_text(encoding="utf-8").splitlines()))
    assert all(n.server_weekday is None for n in result.nights)
    assert result.triple_swap_weekday is None


# --------------------------------------------------------------------------
# It refuses to do damage
# --------------------------------------------------------------------------


def test_it_will_not_overwrite_without_being_told_to(tmp_path: Path) -> None:
    source = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _contaminated(source)
    out.write_text("existing\n", encoding="utf-8")
    assert RESCUE.main([str(source), str(out)]) == 3
    assert out.read_text(encoding="utf-8") == "existing\n"
    assert RESCUE.main([str(source), str(out), "--force"]) == 0


def test_an_unreadable_source_fails_rather_than_writing_an_empty_log(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out.jsonl"
    assert RESCUE.main([str(tmp_path / "absent.jsonl"), str(out)]) == 2
    assert not out.exists()


def test_the_summary_names_what_was_kept_and_what_was_lost(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "in.jsonl"
    _contaminated(source)
    RESCUE.main([str(source), str(tmp_path / "out.jsonl")])
    printed = capsys.readouterr().out
    assert "TRIPLE-SWAP WEEKDAY, and nothing" in printed
    assert "Nothing here was corrected" in printed
    assert str(BAD_OFFSET) in printed
