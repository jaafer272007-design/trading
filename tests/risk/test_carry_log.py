"""Reading a week of carry-log rows, before there is a week to read.

``EVALUATION.md`` §5: a gate that has never fired is indistinguishable from one
that cannot fire. This instrument's most important output is
``UNDETERMINED``, so most of this file is about making that branch fire — on a
flat week, on a monotone week, on a week too short, and on a size too small.

The synthetic weeks are built from the two hypotheses directly: one where the
charge is ``k x price`` and one where it is a constant that steps once. If the
instrument cannot tell those apart when handed them, it will not tell anything
apart when handed a real log.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from risk.carry_log import (
    CHARGE_RESOLUTION,
    MIN_RESOLVED_NIGHTS,
    POWER_MARGIN,
    SEPARATION_FACTOR,
    CarryRow,
    StructureVerdict,
    analyse,
    nightly_charges,
    parse_rows,
)

START = datetime(2026, 8, 2, 21, 0, tzinfo=UTC)
OFFSET = 3.0
VOLUME = 0.10

#: 67.9 a night on one lot is 6.79 on a tenth. The synthetic weeks are built
#: around that so the numbers match what a real FxPro log should show.
NIGHTLY_AT_TENTH_LOT = 6.79
BASE_PRICE = 2_400.0


def _week(
    prices: list[float], *, price_dependent: bool, step_after: int | None = None
) -> list[CarryRow]:
    """Build a week of readings under one of the two hypotheses.

    Args:
        prices: One price per charging event.
        price_dependent: True to charge ``k x price``; False for a constant.
        step_after: For the fixed-rate case, the night after which the rate
            steps up by 3%. ``None`` for no step.

    Returns:
        Readings, one before the first charge and one per charge.
    """
    k = NIGHTLY_AT_TENTH_LOT / BASE_PRICE
    rows = [
        CarryRow(
            at=START,
            ticket=7,
            carry_paid=0.0,
            price=prices[0],
            volume=VOLUME,
            server_offset_hours=OFFSET,
        )
    ]
    cumulative = 0.0
    for index, price in enumerate(prices):
        if price_dependent:
            charge = k * price
        else:
            charge = NIGHTLY_AT_TENTH_LOT
            if step_after is not None and index > step_after:
                charge *= 1.03
        cumulative += round(charge, 2)
        rows.append(
            CarryRow(
                at=START + timedelta(days=index + 1),
                ticket=7,
                carry_paid=round(cumulative, 2),
                price=price,
                volume=VOLUME,
                server_offset_hours=OFFSET,
            )
        )
    return rows


#: A week that reverses twice with a 2% range -- the median real week.
LIVELY = [2_400.0, 2_424.0, 2_410.0, 2_436.0, 2_418.0, 2_430.0]
#: A week that never changes direction. Range is fine, shape is not.
MONOTONE = [2_400.0, 2_410.0, 2_420.0, 2_430.0, 2_440.0, 2_450.0]
#: A week that barely moves. Shape is fine, range is not.
FLAT = [2_400.0, 2_400.4, 2_400.0, 2_400.5, 2_400.1, 2_400.3]


# --------------------------------------------------------------------------
# Reconstructing the charging events
# --------------------------------------------------------------------------


def test_increments_are_recovered_from_a_cumulative_field() -> None:
    nights = nightly_charges(_week(LIVELY, price_dependent=False))
    assert len(nights) == len(LIVELY)
    assert all(
        n.increment == pytest.approx(NIGHTLY_AT_TENTH_LOT, abs=0.01) for n in nights
    )


def test_readings_with_no_change_do_not_become_charging_events() -> None:
    # A 60-second monitor produces ~1,440 readings a day and one charge.
    rows = _week(LIVELY, price_dependent=False)
    padded = list(rows)
    for minute in range(1, 30):
        padded.append(
            CarryRow(
                at=START + timedelta(minutes=minute),
                ticket=7,
                carry_paid=0.0,
                price=BASE_PRICE,
                volume=VOLUME,
                server_offset_hours=OFFSET,
            )
        )
    assert len(nightly_charges(padded)) == len(nightly_charges(rows))


def test_the_triple_swap_night_is_inferred_rather_than_assumed() -> None:
    rows = _week(LIVELY, price_dependent=False)
    # Triple the third charge, as a broker does on its 3-day weekday.
    bumped = list(rows)
    extra = 2 * NIGHTLY_AT_TENTH_LOT
    for i in range(3, len(bumped)):
        bumped[i] = CarryRow(
            at=bumped[i].at,
            ticket=7,
            carry_paid=round(bumped[i].carry_paid + extra, 2),
            price=bumped[i].price,
            volume=VOLUME,
            server_offset_hours=OFFSET,
        )
    nights = nightly_charges(bumped)
    assert [n.multiplier for n in nights] == [1, 1, 3, 1, 1, 1]
    # And the unit charge is restored, which is what the test statistic needs.
    assert all(
        n.unit_charge == pytest.approx(NIGHTLY_AT_TENTH_LOT, abs=0.02) for n in nights
    )


def test_the_server_weekday_is_recovered_from_the_recorded_offset() -> None:
    nights = nightly_charges(_week(LIVELY, price_dependent=False))
    # The first charge is observed at Monday 2026-08-03 21:00 UTC, which is
    # exactly Tuesday 00:00 on a UTC+3 server -- so it is the rollover INTO
    # Tuesday, weekday 1. Getting this wrong by one is precisely how a
    # triple-swap day gets attributed to the wrong weekday, so it is pinned.
    assert nights[0].server_weekday == 1
    assert [n.server_weekday for n in nights] == [1, 2, 3, 4, 5, 6]


# --------------------------------------------------------------------------
# The verdict, when the week has power
# --------------------------------------------------------------------------


def test_a_price_dependent_week_is_called_price_dependent() -> None:
    result = analyse(_week(LIVELY, price_dependent=True))
    assert result.power.has_power
    assert result.verdict is StructureVerdict.PRICE_DEPENDENT
    assert result.cv_charge_over_price is not None
    assert result.cv_unit_charge is not None
    assert result.cv_charge_over_price * SEPARATION_FACTOR < result.cv_unit_charge
    assert "moves WITH the gold price" in result.notes[0]


def test_a_fixed_rate_week_is_called_fixed_even_when_the_price_moves() -> None:
    result = analyse(_week(LIVELY, price_dependent=False))
    assert result.power.has_power
    assert result.verdict is StructureVerdict.FIXED_RATE
    assert "does NOT move with gold" in result.notes[0]


def test_a_fixed_rate_that_steps_once_is_not_mistaken_for_price_dependence() -> None:
    # The specific alternative the reversal requirement exists to exclude.
    result = analyse(_week(LIVELY, price_dependent=False, step_after=2))
    assert result.power.has_power
    assert result.verdict is not StructureVerdict.PRICE_DEPENDENT


# --------------------------------------------------------------------------
# UNDETERMINED, which is the output that matters most
# --------------------------------------------------------------------------


def test_a_flat_week_is_undetermined_rather_than_agreeing_with_fixed() -> None:
    # The user's question: if gold does not move, the test is uninformative.
    # It must say so, not report FIXED_RATE.
    result = analyse(_week(FLAT, price_dependent=True))
    assert not result.power.has_power
    assert result.verdict is StructureVerdict.UNDETERMINED
    assert any("could not have been seen" in r for r in result.power.reasons)
    assert any("not evidence for either explanation" in n for n in result.notes)


def test_a_monotone_week_is_undetermined_however_far_the_price_travels() -> None:
    result = analyse(_week(MONOTONE, price_dependent=True))
    assert not result.power.has_power
    assert result.verdict is StructureVerdict.UNDETERMINED
    assert any("changed direction" in r for r in result.power.reasons)


def test_too_few_charging_events_is_undetermined() -> None:
    result = analyse(_week(LIVELY[:3], price_dependent=True))
    assert not result.power.has_power
    assert result.verdict is StructureVerdict.UNDETERMINED
    assert any("charging events resolved" in r for r in result.power.reasons)


def test_the_required_range_scales_inversely_with_position_size() -> None:
    # The fixed-rate week, so the mean unit charge is exactly the nightly
    # figure rather than that figure scaled by the week's mean price.
    tenth = analyse(_week(LIVELY, price_dependent=False)).power
    assert tenth.required_range_fraction is not None
    assert tenth.required_range_fraction == pytest.approx(
        POWER_MARGIN * CHARGE_RESOLUTION / NIGHTLY_AT_TENTH_LOT, rel=1e-3
    )
    # 0.44% at a tenth of a lot -- the figure the size recommendation rests on.
    assert tenth.required_range_fraction == pytest.approx(0.00442, abs=1e-4)


def test_a_hundredth_of_a_lot_needs_ten_times_the_price_movement() -> None:
    # 4.4%, which the snapshot says only 6% of weeks reach. This is why the
    # recommended size is 0.10 and not the broker minimum.
    small = [
        CarryRow(
            at=row.at,
            ticket=row.ticket,
            carry_paid=round(row.carry_paid / 10.0, 2),
            price=row.price,
            volume=0.01,
            server_offset_hours=row.server_offset_hours,
        )
        for row in _week(LIVELY, price_dependent=True)
    ]
    power = analyse(small).power
    assert power.required_range_fraction is not None
    assert power.required_range_fraction == pytest.approx(0.0442, abs=1e-3)
    assert power.price_range_fraction is not None
    assert power.price_range_fraction < power.required_range_fraction
    assert not power.has_power


# --------------------------------------------------------------------------
# What the week settles regardless of power
# --------------------------------------------------------------------------


def test_the_magnitude_is_settled_even_on_a_flat_week() -> None:
    result = analyse(_week(FLAT, price_dependent=True))
    assert result.verdict is StructureVerdict.UNDETERMINED
    assert result.charge_per_lot_per_night is not None
    assert result.charge_per_lot_per_night == pytest.approx(67.9, abs=0.5)
    assert any("settled with or without power" in n for n in result.notes)


def test_an_account_that_charges_nothing_says_so_and_names_the_ambiguity() -> None:
    rows = [
        CarryRow(
            at=START + timedelta(days=day),
            ticket=7,
            carry_paid=0.0,
            price=BASE_PRICE,
            volume=VOLUME,
            server_offset_hours=OFFSET,
        )
        for day in range(8)
    ]
    result = analyse(rows)
    assert not result.charges_swaps
    assert result.verdict is StructureVerdict.UNDETERMINED
    assert any("swap-free account" in n for n in result.notes)


# --------------------------------------------------------------------------
# Parsing, and refusing what is not a carry log
# --------------------------------------------------------------------------


def test_a_written_log_round_trips(tmp_path: object) -> None:
    line = (
        '{"at": "2026-08-02T21:00:00+00:00", "carry_paid": 6.79, "price": 2400.0, '
        '"server_offset_hours": 3.0, "ticket": 7, "volume": 0.1}'
    )
    rows = parse_rows([line, "", "  "])
    assert len(rows) == 1
    assert rows[0].ticket == 7
    assert rows[0].price == pytest.approx(2_400.0)


def test_a_log_without_a_price_still_parses_and_loses_only_the_structure_test() -> None:
    line = (
        '{"at": "2026-08-02T21:00:00+00:00", "carry_paid": 6.79, "price": null, '
        '"server_offset_hours": null, "ticket": 7, "volume": 0.1}'
    )
    rows = parse_rows([line])
    assert rows[0].price is None
    assert rows[0].server_offset_hours is None


def test_something_that_is_not_a_carry_log_is_refused() -> None:
    with pytest.raises(ValueError, match="not a carry-log record"):
        parse_rows(['{"hello": "world"}'])


def test_two_tickets_in_one_call_is_refused_rather_than_pooled() -> None:
    rows = _week(LIVELY, price_dependent=True)
    other = CarryRow(
        at=START,
        ticket=8,
        carry_paid=0.0,
        price=BASE_PRICE,
        volume=VOLUME,
        server_offset_hours=OFFSET,
    )
    with pytest.raises(ValueError, match="expected one ticket"):
        analyse([*rows, other])


def test_an_empty_log_is_refused() -> None:
    with pytest.raises(ValueError, match="no rows"):
        analyse([])


def test_the_thresholds_are_the_ones_written_before_the_data() -> None:
    # Restated as literals so that relaxing a threshold cannot also relax the
    # assertion. If the log arrives and the test does not fire, the correct
    # response is to report UNDETERMINED, not to move these.
    assert CHARGE_RESOLUTION == 0.01
    assert POWER_MARGIN == 3.0
    assert SEPARATION_FACTOR == 3.0
    assert MIN_RESOLVED_NIGHTS == 5


# --------------------------------------------------------------------------
# The published field: watched, reported, never acted on
# --------------------------------------------------------------------------


def _with_field(rows: list[CarryRow], values: list[float | None]) -> list[CarryRow]:
    """Attach a published swap_long to each row.

    Args:
        rows: Readings.
        values: One field value per row, or ``None`` for a row that predates
            the field being logged.

    Returns:
        New rows.
    """
    return [
        CarryRow(
            at=r.at,
            ticket=r.ticket,
            carry_paid=r.carry_paid,
            price=r.price,
            volume=r.volume,
            server_offset_hours=r.server_offset_hours,
            published_swap_long=v,
        )
        for r, v in zip(rows, values, strict=True)
    ]


def test_a_log_without_the_field_says_unknown_rather_than_stable() -> None:
    # Rows written before 2026-08-01 carry no field. Reading their silence as
    # "the rate held" would manufacture evidence for FIXED_RATE out of an
    # instrument that was not looking.
    result = analyse(_week(LIVELY, price_dependent=True))
    assert result.field.changed is None
    assert result.field.readings == 0
    note = next(n for n in result.notes if "published swap_long" in n)
    assert "not the same as the rate having held" in note


def test_a_field_that_never_moves_is_reported_with_its_coverage() -> None:
    rows = _week(LIVELY, price_dependent=False)
    result = analyse(_with_field(rows, [-67.9] * len(rows)))
    assert result.field.changed is False
    assert result.field.distinct == (-67.9,)
    assert result.field.spans_the_charges
    assert any("held at -67.9" in n for n in result.notes)


def test_a_re_quoted_field_is_named_as_a_step_not_as_price_dependence() -> None:
    rows = _week(MONOTONE, price_dependent=False, step_after=2)
    values: list[float | None] = [-67.9 if i <= 3 else -69.9 for i in range(len(rows))]
    result = analyse(_with_field(rows, values))
    assert result.field.changed is True
    assert result.field.distinct == (-67.9, -69.9)
    note = next(n for n in result.notes if "distinct values" in n)
    assert "FIXED_RATE with a step, not price-dependence" in note


def test_watching_the_field_changes_no_verdict() -> None:
    # The discriminator was added after data existed. It reports; it must not
    # decide, or the pre-committed test stops being pre-committed.
    rows = _week(LIVELY, price_dependent=True)
    bare = analyse(rows)
    watched = analyse(_with_field(rows, [-67.9] * len(rows)))
    assert watched.verdict is bare.verdict
    assert watched.power == bare.power
    assert watched.cv_unit_charge == bare.cv_unit_charge


def test_the_field_is_parsed_when_present_and_absent() -> None:
    with_field = '{"at": "2026-08-01T00:00:00+00:00", "ticket": 7, "carry_paid": 1.0, \
"price": 4000.0, "volume": 0.1, "server_offset_hours": 3.0, \
"published_swap_long": -67.9}'
    without = '{"at": "2026-08-01T00:01:00+00:00", "ticket": 7, "carry_paid": 1.0, \
"price": 4000.0, "volume": 0.1, "server_offset_hours": 3.0}'
    rows = parse_rows([with_field, without])
    assert rows[0].published_swap_long == pytest.approx(-67.9)
    assert rows[1].published_swap_long is None


# --------------------------------------------------------------------------
# The two-night window that was actually measured
# --------------------------------------------------------------------------


def test_two_monotone_nights_are_undetermined_and_say_which_conditions_failed() -> None:
    # `[MEASURED]` 2026-08-01: two charging events, a monotone price path.
    # The magnitude comes out; the structure does not, and the reasons are the
    # night count and the absence of reversals -- not the price being flat.
    rows = _week([4_083.82, 4_058.09], price_dependent=False)
    result = analyse(rows)

    assert result.verdict is StructureVerdict.UNDETERMINED
    assert not result.power.has_power
    assert result.power.resolved_nights == 2
    assert any("only 2 charging events" in r for r in result.power.reasons)
    assert any("changed direction 0 times" in r for r in result.power.reasons)
    # The range condition is the one that PASSED, and it is worth pinning
    # separately: the window failed on shape, not on resolution.
    assert result.power.price_range_fraction is not None
    assert result.power.required_range_fraction is not None
    assert result.power.price_range_fraction > result.power.required_range_fraction
    assert not any("posting resolution" in r for r in result.power.reasons)
    # And the magnitude is settled regardless.
    assert result.charge_per_lot_per_night == pytest.approx(67.9)


# --------------------------------------------------------------------------
# A log with a contaminated row is refused, not filtered
# --------------------------------------------------------------------------


def _line(**overrides: object) -> str:
    payload: dict[str, object] = {
        "at": "2026-08-02T02:00:00+00:00",
        "ticket": 7,
        "carry_paid": 13.58,
        "price": 4_042.0,
        "volume": 0.1,
        "server_offset_hours": 3.0,
        "server_offset_source": "measured",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_a_sound_row_parses() -> None:
    rows = parse_rows([_line()])
    assert rows[0].server_offset_source == "measured"


def test_a_row_written_under_an_impossible_offset_refuses_the_whole_log() -> None:
    # `[MEASURED]` 2026-08-02: row 1 of the live log carried -23.0.
    with pytest.raises(ValueError, match="row 1 of this log cannot be trusted"):
        parse_rows([_line(server_offset_hours=-23.0), _line()])


def test_the_refusal_says_why_it_does_not_simply_drop_the_row() -> None:
    # Filtering is a judgement made once, silently, and inherited by every
    # later reading of the file. Refusing forces it to be made deliberately.
    with pytest.raises(ValueError, match="cannot be trusted") as exc:
        parse_rows([_line(server_offset_hours=-23.0)])
    assert "THE WHOLE LOG IS REFUSED rather than filtered" in str(exc.value)
    assert "Start a fresh log" in str(exc.value)


def test_a_row_written_on_a_cached_clock_refuses_the_log_too() -> None:
    with pytest.raises(ValueError, match="rather than a fresh measurement"):
        parse_rows([_line(server_offset_source="cached")])


def test_a_row_from_before_the_field_existed_is_judged_on_its_offset_alone() -> None:
    # Old rows carry no source. Judging them on the offset they recorded is
    # what makes the guard work on logs written before the guard did.
    payload = json.loads(_line())
    del payload["server_offset_source"]
    assert parse_rows([json.dumps(payload)])[0].server_offset_source is None

    payload["server_offset_hours"] = -23.0
    with pytest.raises(ValueError, match="outside the range of real UTC offsets"):
        parse_rows([json.dumps(payload)])


def test_a_row_with_no_offset_at_all_is_not_refused() -> None:
    # An absent offset is already reported as an absent server weekday. It is
    # not evidence of corruption, and refusing it would refuse every log
    # written on a terminal whose clock could not be located.
    payload = json.loads(_line())
    payload["server_offset_hours"] = None
    del payload["server_offset_source"]
    assert parse_rows([json.dumps(payload)])[0].server_offset_hours is None
