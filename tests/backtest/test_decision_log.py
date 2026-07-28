"""Tests for the §7 decision log.

The schema-key test is the point of this file. ``REPRODUCIBILITY.md`` §7 says
every decision — backtest, paper or live — is stored *identically*, and the
value of that is entirely in the keys being the same. An omitted key and a
forgotten key look alike in a diff.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from backtest.costs import CostModel
from backtest.decision_log import (
    OUTCOME_HORIZONS,
    decision_record,
    write_decision_log,
)
from backtest.execution import Direction, RiskModel, Trade, simulate_position
from tests.backtest.bars import bars_from

#: Every key ``REPRODUCIBILITY.md`` §7 names, plus the two documented
#: extensions. Written out rather than derived from the code, so a key
#: disappearing from the writer fails here instead of silently changing the
#: schema.
SCHEMA_KEYS = {
    "decision_id",
    "run_id",
    "bar_timestamp_utc",
    "snapshot_sha256",
    "features",
    "agents",
    "evidence_graph",
    "n_eff",
    "pc1_variance_share",
    "confidence_adjusted",
    "devils_advocate",
    "final_decision",
    "decision_method",
    "costs_applied",
    "outcome",
    "execution",
}

FLAT = (200_000.0, 200_000.0, 200_000.0)
ENTRY_BAR = (200_100.0, 200_100.0, 200_100.0)


Pieces = tuple[pd.DatetimeIndex, npt.NDArray[np.float64], Trade | None]


@pytest.fixture
def pieces() -> Pieces:
    """A one-trade fixture: index, closes, and the trade itself."""
    bars = bars_from([FLAT, ENTRY_BAR, FLAT, FLAT, FLAT])
    trade = simulate_position(
        bars=bars,
        decision_index=0,
        direction=Direction.LONG,
        atr_points=1_000.0,
        risk=RiskModel(1.5, 1.5, 3, 100.0),
        model=CostModel(),
    )
    close = bars.open / 100.0
    return bars.index, close, trade


def _record(
    pieces: Pieces,
    *,
    decision_method: str = "logistic",
    confidence: float | None = 0.61,
    with_trade: bool = True,
    features: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Build a record from the fixture, with the overrides tests need."""
    index, close, trade = pieces
    return decision_record(
        run_id="run-1",
        snapshot_sha256="abc",
        index=index,
        close=close,
        decision_index=0,
        features={"log_return_24": 0.001} if features is None else features,
        feature_versions={"log_return_24": 1},
        decision_method=decision_method,
        confidence=confidence,
        trade=trade if with_trade else None,
    )


def test_a_record_carries_every_schema_key(
    pieces: Pieces,
) -> None:
    assert set(_record(pieces)) == SCHEMA_KEYS


def test_the_agent_fields_are_explicit_nulls_not_omissions(
    pieces: Pieces,
) -> None:
    record = _record(pieces)
    assert record["agents"] == []
    assert record["evidence_graph"] == {"nodes": [], "edges": []}
    assert record["n_eff"] is None
    assert record["pc1_variance_share"] is None
    assert record["devils_advocate"] is None


def test_the_control_arms_records_are_written_too(
    pieces: Pieces,
) -> None:
    record = _record(pieces, decision_method="random", confidence=None)
    assert record["decision_method"] == "random"
    assert record["confidence_adjusted"] is None
    assert record["final_decision"] == "long"


def test_a_declined_decision_logs_flat_with_no_execution(
    pieces: Pieces,
) -> None:
    record = _record(pieces, with_trade=False)
    assert record["final_decision"] == "flat"
    assert record["execution"] is None
    assert record["costs_applied"]["total_points"] == 0.0


def test_costs_applied_carries_every_component_the_engine_charged(
    pieces: Pieces,
) -> None:
    _, _, trade = pieces
    costs = _record(pieces)["costs_applied"]
    assert set(costs) == {
        "spread",
        "slippage",
        "latency_ms",
        "commission",
        "swap",
        "gap_through",
        "total_points",
    }
    assert trade is not None
    assert costs["total_points"] == pytest.approx(trade.cost_points)


def test_an_outcome_past_the_series_is_none_not_a_substituted_value(
    pieces: Pieces,
) -> None:
    outcome = _record(pieces)["outcome"]
    assert set(outcome) == {f"h{h}" for h in OUTCOME_HORIZONS}
    assert outcome["h1"] is not None
    assert outcome["h24"] is None


def test_the_decision_id_is_stable_across_runs_of_the_same_run(
    pieces: Pieces,
) -> None:
    assert _record(pieces)["decision_id"] == _record(pieces)["decision_id"]
    assert (
        _record(pieces)["decision_id"]
        != _record(pieces, decision_method="random")["decision_id"]
    )


def test_the_log_round_trips_through_jsonl(pieces: Pieces, tmp_path: Path) -> None:
    records = [_record(pieces), _record(pieces, decision_method="random")]
    path = write_decision_log(records, tmp_path / "log" / "decisions.jsonl")

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert [json.loads(line)["decision_method"] for line in lines] == [
        "logistic",
        "random",
    ]


def test_numpy_scalars_survive_serialisation(tmp_path: Path) -> None:
    # A record assembled from arrays carries numpy scalars, which `json`
    # refuses outright. Silently dropping them is not an option and neither is
    # a partially written log.
    record = {"value": np.float64(0.5), "count": np.int64(3), "flag": np.bool_(True)}
    path = write_decision_log([record], tmp_path / "decisions.jsonl")
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "value": 0.5,
        "count": 3,
        "flag": True,
    }


def test_something_genuinely_unserialisable_raises_rather_than_being_dropped(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="cannot serialise"):
        write_decision_log([{"bad": object()}], tmp_path / "decisions.jsonl")
