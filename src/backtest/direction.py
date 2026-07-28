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

What is allowed to live here, and what is not
----------------------------------------------

**A source may live in ``src`` once a hypothesis registers it, and not before.**

- :class:`LogisticDirection` and :class:`RandomDirection` — H-003 §A and §C.
- :class:`AlwaysLong` — `EVALUATION.md` §2 rung 2, registered 2026-07-28 as
  **H-007**. It arrived here by that route: ``tests/backtest/test_rungs.py``
  refused it until the registration existed, which is what that test is for.
  It has no parameters, so registering it introduced no constant.

Rungs 3 and 4 are still absent, and their absence is still the point: rung 4
needs a fast/slow pair and rung 3 needs a sizing rule, and both are constants
nobody has registered. ``tests/backtest/test_rungs.py`` implements them against
this protocol from the test module, which demonstrates the extensibility
property without moving unregistered choices into the evaluation path.
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


@dataclass(frozen=True, slots=True)
class AlwaysLong:
    """`EVALUATION.md` §2 rung 2, registered as H-007.

    Gold has a secular uptrend across the evaluation window, so any long-biased
    system looks clever. H-003's signal went long 56.2% of the time against a
    control that is 50% long by construction, and **a long bias produces H-003's
    measured difference with zero directional skill**. This arm is the registered
    instrument for telling the two apart.

    It has no parameters. That is not a convenience — it is why registering it
    added nothing to the degrees of freedom, and why it can sit in ``src``
    alongside the H-003 sources rather than in a test module.
    """

    name: str = "always_long"
    decision_method: str = "always_long"

    def directions(
        self, frame: pd.DataFrame, decisions: npt.NDArray[np.int64]
    ) -> tuple[Direction, ...]:
        """Long, every time.

        Args:
            frame: Unused, and unused on purpose — a baseline that looked at
                prices would not be a baseline.
            decisions: Decision positions.

        Returns:
            One direction per decision.
        """
        del frame
        return tuple([Direction.LONG] * len(decisions))
