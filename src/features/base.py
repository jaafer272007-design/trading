"""The Feature protocol.

Every feature in the pipeline implements :class:`Feature`. The protocol exists
to make the temporal claims in ``DATA_CONTRACT.md`` §7 *machine-checkable*
rather than documentary: a feature that does not declare its lookback and its
confirmation lag cannot be constructed, and therefore cannot be swept by the
causal harness in ``tests/causality.py``.

Relationship to the ``DATA_CONTRACT.md`` §7 declaration block
-------------------------------------------------------------

§7 specifies a full YAML block per feature. This protocol carries the subset
that the harness must be able to interrogate at runtime:

===========================  ====================================
``DATA_CONTRACT.md`` §7 key  Protocol member
===========================  ====================================
``name``                     :attr:`Feature.name`
``version``                  :attr:`Feature.version`
``lookback_bars``            :attr:`Feature.lookback_bars`
``confirmation_lag_bars``    :attr:`Feature.confirmation_lag_bars`
(the computation itself)     :meth:`Feature.compute`
===========================  ====================================

The remaining §7 keys (``inputs``, ``timezone``, ``returns``,
``null_semantics``, ``causal_test``, ``revision_risk``, ``notes``) are review
metadata, not harness inputs. They are not modelled here, and no code in this
module should be read as relaxing the §7 requirement to supply them.
"""

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class Feature(Protocol):
    """A deterministic, causally-bounded transformation of a bar series.

    Implementations must be pure: same frame in, bit-identical series out, no
    hidden state, no globals, no I/O (``CLAUDE.md`` Style).
    """

    @property
    def name(self) -> str:
        """Stable identifier, used as the output series name."""
        ...

    @property
    def version(self) -> int:
        """Declaration version.

        Increment whenever the computation changes. A value computed under
        version ``k`` is not comparable to one computed under version ``k+1``.
        """
        ...

    @property
    def lookback_bars(self) -> int:
        """Bars of history required before the first non-null value.

        This is a *warmup* quantity, not a temporal claim: it says the feature
        needs this many bars behind it, never that it may look ahead.
        """
        ...

    @property
    def confirmation_lag_bars(self) -> int:
        """Bars that must elapse after ``T`` before the value at ``T`` is knowable.

        This is the single most consequential number a feature declares, and
        the one the causal harness enforces. ``DATA_CONTRACT.md`` §2 fixes the
        value for every permitted feature; a feature absent from that registry
        is prohibited until it is added with a declared lag.

        A feature whose value at bar ``T`` is drawn retroactively once later
        bars confirm a pattern — an order block, an n-bar fractal swing — has
        a *positive* lag. Declaring ``0`` in that case is precisely the silent
        leak ``DATA_CONTRACT.md`` §2 warns about, and it will make a backtest
        look excellent.
        """
        ...

    @property
    def session_relative(self) -> bool:
        """Whether this feature reads where a bar sits inside its session.

        True for anything referencing the session open, the session close,
        position within the session, or bars remaining until the daily break.

        Declared rather than inferred, because it cannot be inferred: a
        feature that indexes off the calendar's session hours and one that
        does not are the same shape from the outside.

        It is load-bearing while ``R-001`` is open. This feed's session
        structure changes twice inside H-006's evaluation window — the daily
        break is absent between 2017-10-07 and 2022-10-20 — so a
        session-relative feature measures a different quantity on either side
        of that boundary, and the boundary dates themselves have not been
        checked against any source outside this project.
        ``tests/test_causality.py`` refuses a registry entry declaring ``True``
        until that review closes. See ``REVIEW_ITEMS.md``.
        """
        ...

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the feature over ``df``.

        Args:
            df: Bar series indexed by timezone-aware UTC open-time timestamps.

        Returns:
            A series aligned to ``df.index``, named :attr:`name`. Positions
            where the value is not computable hold ``NaN``. Values are never
            forward-filled, interpolated, or otherwise imputed
            (``DATA_CONTRACT.md`` §6).
        """
        ...
