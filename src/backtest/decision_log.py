"""The decision log — ``REPRODUCIBILITY.md`` §7, written for every arm.

    Every decision — backtest, paper, or live — is stored identically. This is
    the Evidence Graph as data.

H-003 §I requirement 4. The schema is agent-shaped because it was written for a
system with agents, and this path has none. The fields that describe an agent
panel are therefore emitted as explicit nulls and empty lists rather than
omitted: a reader diffing a backtest record against a later live record must see
the same keys, and an absent key is indistinguishable from a key someone forgot.

``decision_method`` carries ``logistic`` for the signal arm and ``random`` for
the control, both of which are §7 values. The control's records are written too.
A control whose decisions are not logged is a control nobody can audit.

Two documented extensions
-------------------------

``costs_applied`` in §7 names three keys — spread, slippage, latency_ms. This
writer emits those and adds the remaining components the §10 model actually
charges (commission, swap) plus the gap-through diagnostic. Dropping them to fit
the schema would make the logged cost disagree with the cost the engine
deducted, which is worse than an extension.

``execution`` is new, and holds the entry and exit the engine produced. §7 has
nowhere to put a fill, because it was written before there was one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from backtest.execution import Trade

#: Horizons whose realised outcome is recorded per §7's ``outcome`` block.
OUTCOME_HORIZONS: tuple[int, ...] = (1, 4, 24)


def _outcome(
    close: npt.NDArray[np.float64], position: int, horizon: int
) -> float | None:
    """Realised close-to-close return over one horizon.

    Args:
        close: Close prices.
        position: Decision bar.
        horizon: Bars ahead.

    Returns:
        The return, or ``None`` where the horizon runs past the series. Never a
        substituted value — ``DATA_CONTRACT.md`` §6.
    """
    end = position + horizon
    if end >= len(close):
        return None
    base = float(close[position])
    if base == 0.0:
        return None
    return float(close[end]) / base - 1.0


def decision_record(
    *,
    run_id: str,
    snapshot_sha256: str,
    index: pd.DatetimeIndex,
    close: npt.NDArray[np.float64],
    decision_index: int,
    features: Mapping[str, float],
    feature_versions: Mapping[str, int],
    decision_method: str,
    confidence: float | None,
    trade: Trade | None,
) -> dict[str, Any]:
    """Build one §7 record.

    Args:
        run_id: The run this decision belongs to.
        snapshot_sha256: Derived snapshot hash.
        index: Bar timestamps.
        close: Close prices, for the outcome block.
        decision_index: Bar the decision was taken on.
        features: Feature values at that bar.
        feature_versions: Declared version per feature.
        decision_method: ``logistic`` or ``random``.
        confidence: The combiner's probability, or ``None`` for a source that
            does not produce one.
        trade: The resulting position, or ``None`` if the source declined.

    Returns:
        A JSON-serialisable record.
    """
    stamp = index[decision_index]
    return {
        "decision_id": str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}/{decision_method}/{stamp}")
        ),
        "run_id": run_id,
        "bar_timestamp_utc": stamp.isoformat(),
        "snapshot_sha256": snapshot_sha256,
        "features": {
            name: {
                "value": float(value),
                "version": int(feature_versions.get(name, 1)),
                "computed_at": stamp.isoformat(),
            }
            for name, value in features.items()
        },
        # No agents on this path. Emitted as empty rather than omitted so a
        # later record with agents diffs cleanly against this one.
        "agents": [],
        "evidence_graph": {"nodes": [], "edges": []},
        "n_eff": None,
        "pc1_variance_share": None,
        "confidence_adjusted": confidence,
        "devils_advocate": None,
        "final_decision": "flat" if trade is None else trade.direction.value,
        "decision_method": decision_method,
        "costs_applied": _costs_block(trade),
        "execution": _execution_block(trade),
        "outcome": {
            f"h{h}": _outcome(close, decision_index, h) for h in OUTCOME_HORIZONS
        },
    }


def _costs_block(trade: Trade | None) -> dict[str, Any]:
    """§7's ``costs_applied``, extended to every component actually charged.

    Args:
        trade: The position, or ``None``.

    Returns:
        The block, all-zero for a declined decision.
    """
    if trade is None:
        return {
            "spread": 0.0,
            "slippage": 0.0,
            "latency_ms": 0.0,
            "commission": 0.0,
            "swap": 0.0,
            "gap_through": 0.0,
            "total_points": 0.0,
        }
    return {
        "spread": trade.spread_points,
        "slippage": trade.slippage_points,
        "latency_ms": trade.latency_points,
        "commission": trade.commission_points,
        "swap": trade.swap_points,
        "gap_through": trade.gap_through_points,
        "total_points": trade.cost_points,
    }


def _execution_block(trade: Trade | None) -> dict[str, Any] | None:
    """The fill, which §7 has no field for.

    Args:
        trade: The position, or ``None``.

    Returns:
        The block, or ``None`` for a declined decision.
    """
    if trade is None:
        return None
    return {
        "entry_timestamp_utc": trade.entry_timestamp.isoformat(),
        "exit_timestamp_utc": trade.exit_timestamp.isoformat(),
        "exit_reason": trade.exit_reason.value,
        "lots": trade.lots,
        "atr_points": trade.atr_points,
        "entry_mid_points": trade.entry_mid_points,
        "exit_mid_points": trade.exit_mid_points,
        "stop_points": trade.stop_points,
        "target_points": trade.target_points,
        "nights": trade.nights,
        "net_points": trade.net_points,
        "r_multiple": trade.r_multiple,
    }


def write_decision_log(records: Sequence[Mapping[str, Any]], path: Path) -> Path:
    """Write records as JSON Lines.

    One record per line so a log can be appended to as horizons close, and so a
    partial write leaves every complete record readable.

    Args:
        records: The records.
        path: Destination file; parent directories are created.

    Returns:
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, default=_encode) + "\n")
    return path


def _encode(value: object) -> object:
    """Serialise numpy scalars, which ``json`` refuses.

    Args:
        value: A value ``json`` could not encode.

    Returns:
        A JSON-safe equivalent.

    Raises:
        TypeError: If the value is genuinely not serialisable.
    """
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    raise TypeError(f"cannot serialise {type(value)!r} into the decision log")
