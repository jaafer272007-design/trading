"""Direction sources — the one thing an arm is allowed to be.

H-003 §I requirement 6. A rung of ``EVALUATION.md`` §2, and later an agent, must
be a **new direction source, not a new engine**. If adding rung 4 meant touching
the position lifecycle, the ladder would stop comparing like with like on the
day someone tightened a stop while implementing it, and nothing in the output
would say so.

The protocol is deliberately narrow: given the bar series and the decision
indices, return one :class:`~backtest.execution.Direction` per decision. It has
no access to the risk model, the cost model, or the fill logic, so a source
cannot change them.

Two sources live here — the two H-003 registers. The §2 rungs do not, and their
absence is the point: rung 4 needs a fast/slow pair, rung 3 needs a sizing rule,
and both are constants nobody has registered. Putting them in ``src`` would move
unregistered choices into the evaluation path. ``tests/backtest/test_rungs.py``
implements all three against this protocol, which is what demonstrates the
property without asserting the constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt
import pandas as pd

from backtest.execution import Direction


@runtime_checkable
class DirectionSource(Protocol):
    """Something that takes a view, and can do nothing else."""

    @property
    def name(self) -> str:
        """Stable identifier, used in reports and the decision log."""
        ...

    @property
    def decision_method(self) -> str:
        """``REPRODUCIBILITY.md`` §7 ``decision_method`` value."""
        ...

    def directions(
        self, frame: pd.DataFrame, decisions: npt.NDArray[np.int64]
    ) -> tuple[Direction, ...]:
        """One direction per decision, in decision order.

        Args:
            frame: The bar series the decisions index into.
            decisions: Bar positions where a decision is taken.

        Returns:
            A tuple the same length as ``decisions``.
        """
        ...


@dataclass(frozen=True, slots=True)
class LogisticDirection:
    """The signal under test — H-003 §A.

    Takes probabilities already produced by the walk-forward combiner rather
    than fitting anything itself. Fitting belongs to the evaluation pipeline,
    which knows about folds, purge and embargo; a direction source that fitted
    its own model could quietly train on the test window and this protocol would
    have no way to notice.

    ``p == 0.5`` exactly returns ``FLAT`` and no trade is taken, per §A. It is
    counted and reported rather than broken toward one side, because a tie rule
    that silently favours a direction is a base-rate asymmetry nobody declared.
    """

    probabilities: tuple[float, ...]
    name: str = "signal"
    decision_method: str = "logistic"

    def directions(
        self, frame: pd.DataFrame, decisions: npt.NDArray[np.int64]
    ) -> tuple[Direction, ...]:
        """Map probabilities to directions.

        Args:
            frame: Unused; the view is already computed.
            decisions: Decision positions, for the length check.

        Returns:
            One direction per decision.

        Raises:
            ValueError: If the probability count does not match the decisions.
        """
        del frame
        if len(self.probabilities) != len(decisions):
            raise ValueError(
                f"{len(self.probabilities)} probabilities for "
                f"{len(decisions)} decisions — a misalignment here silently "
                f"attaches one bar's view to another bar's trade"
            )
        return tuple(
            Direction.LONG
            if p > 0.5
            else (Direction.SHORT if p < 0.5 else Direction.FLAT)
            for p in self.probabilities
        )


@dataclass(frozen=True, slots=True)
class RandomDirection:
    """The control — H-003 §C.

    Same decision times, same risk management, direction from a coin. Draws from
    ``REPRODUCIBILITY.md`` §3's ``random_entry`` stream, which is deliberately
    **not** ``shuffled_labels``: sharing one would make this control's directions
    a deterministic function of H-001's permutations, correlating two nominally
    independent controls in a way nothing in either output would reveal.

    The draw depends on the seed and the decision count and on nothing else — in
    particular not on prices, so the control cannot accidentally acquire a view.
    """

    seed: int

    @property
    def name(self) -> str:
        """Identifier including the seed, since the arm is one of thirty."""
        return f"random_s{self.seed}"

    @property
    def decision_method(self) -> str:
        """``REPRODUCIBILITY.md`` §7 value."""
        return "random"

    def directions(
        self, frame: pd.DataFrame, decisions: npt.NDArray[np.int64]
    ) -> tuple[Direction, ...]:
        """Draw one direction per decision.

        Args:
            frame: Unused, and unused on purpose.
            decisions: Decision positions.

        Returns:
            One direction per decision.
        """
        del frame
        rng = np.random.default_rng(self.seed)
        draws = rng.integers(0, 2, size=len(decisions))
        return tuple(Direction.LONG if d == 1 else Direction.SHORT for d in draws)
