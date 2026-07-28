"""The polynomial expansion, including the mandated causal test.

CLAUDE.md Hard Rule 1 admits no exception: the expansion ships with a
truncated-history equality test. A pointwise transform of same-row inputs
*cannot* move information across time — and "cannot" is the word every
instrument defect in ``EVALUATION.md`` §14 was fluent about before it was
caught, so the claim is swept by the real harness rather than argued.

The sweep runs through an adapter so the expansion is checked by
``tests/causality.py`` itself, not by a second implementation of the same idea
written here. `EVALUATION.md` §14 also requires the gate be shown to fire:
``test_a_forward_peeking_expansion_is_rejected`` is that adversarial fixture.
"""

import numpy as np
import pandas as pd
import pytest

from data.synthetic import generate_ohlcv
from features.log_return import LogReturn
from features.realized_vol import RealizedVol
from models.expansion import (
    n_polynomial_terms,
    polynomial_expand,
    polynomial_terms,
    term_names,
)
from tests.causality import CausalityError, assert_causal

# The registered H-011 ladder. Parameter count is terms + the intercept.
LADDER: tuple[tuple[str, int, bool, int], ...] = (
    ("C-0", 1, False, 4),
    ("C-1", 2, True, 7),
    ("C-2", 2, False, 10),
    ("C-3", 3, False, 20),
    ("C-4", 4, False, 35),
    ("C-5", 5, False, 56),
)


# ---------------------------------------------------------------------------
# The ladder is the one that was registered
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("rung", "degree", "diagonal", "parameters"), LADDER)
def test_each_rung_has_the_registered_parameter_count(
    rung: str, degree: int, diagonal: bool, parameters: int
) -> None:
    """H-011's ladder table, asserted against the code that produces it."""
    n_terms = n_polynomial_terms(3, degree, diagonal_only=diagonal)

    assert n_terms + 1 == parameters, rung


def test_degree_one_is_the_identity() -> None:
    """C-0 must be H-001's design untouched, or the comparison has no anchor."""
    x = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    np.testing.assert_array_equal(polynomial_expand(x, 1), x)


def test_expansion_matches_hand_computed_terms() -> None:
    x = np.array([[2.0, 3.0]])

    result = polynomial_expand(x, 2)

    # Order: degree 1 then degree 2, combinations_with_replacement within.
    expected = np.array([[2.0, 3.0, 4.0, 6.0, 9.0]])
    np.testing.assert_array_equal(result, expected)
    assert term_names(("a", "b"), 2) == ("a", "b", "a*a", "a*b", "b*b")


def test_diagonal_only_drops_every_cross_term() -> None:
    x = np.array([[2.0, 3.0]])

    result = polynomial_expand(x, 2, diagonal_only=True)

    np.testing.assert_array_equal(result, np.array([[2.0, 3.0, 4.0, 9.0]]))
    assert term_names(("a", "b"), 2, diagonal_only=True) == ("a", "b", "a*a", "b*b")


def test_term_order_is_canonical_and_stable() -> None:
    """A fitted coefficient must mean the same thing across runs."""
    assert polynomial_terms(3, 2) == polynomial_terms(3, 2)
    assert polynomial_terms(2, 3) == (
        (0,),
        (1,),
        (0, 0),
        (0, 1),
        (1, 1),
        (0, 0, 0),
        (0, 0, 1),
        (0, 1, 1),
        (1, 1, 1),
    )


def test_degrees_accumulate_rather_than_replace() -> None:
    """Every lower-degree term survives into a higher rung."""
    lower = set(polynomial_terms(3, 2))

    assert lower <= set(polynomial_terms(3, 3))


@pytest.mark.parametrize("bad", [0, -1])
def test_a_degree_below_one_is_refused(bad: int) -> None:
    with pytest.raises(ValueError, match="degree must be at least"):
        polynomial_terms(3, bad)


def test_an_empty_feature_set_is_refused() -> None:
    with pytest.raises(ValueError, match="n_features must be positive"):
        polynomial_terms(0, 2)


def test_a_one_dimensional_input_is_refused() -> None:
    with pytest.raises(ValueError, match="expected a 2-D design matrix"):
        polynomial_expand(np.zeros(5), 2)


# ---------------------------------------------------------------------------
# Pointwise, asserted bitwise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("rung", "degree", "diagonal", "parameters"), LADDER)
def test_expanding_a_truncated_matrix_equals_truncating_the_expansion(
    rung: str, degree: int, diagonal: bool, parameters: int
) -> None:
    """Row i of the output depends on row i of the input and nothing else.

    Bit-identical, not ``allclose``: a differing low bit would mean the
    arithmetic took a different path depending on how many rows were present.
    """
    rng = np.random.default_rng(11)
    x = rng.standard_normal((200, 3))

    full = polynomial_expand(x, degree, diagonal_only=diagonal)
    for cut in (1, 7, 63, 199):
        truncated = polynomial_expand(x[:cut], degree, diagonal_only=diagonal)
        np.testing.assert_array_equal(truncated, full[:cut], strict=True)


def test_row_order_does_not_change_any_row() -> None:
    """A pointwise transform commutes with permutation of the rows."""
    rng = np.random.default_rng(12)
    x = rng.standard_normal((50, 3))
    order = rng.permutation(50)

    np.testing.assert_array_equal(
        polynomial_expand(x[order], 3), polynomial_expand(x, 3)[order]
    )


# ---------------------------------------------------------------------------
# Swept by the real causal harness, through an adapter
# ---------------------------------------------------------------------------


class _ExpandedTermAsFeature:
    """Adapter exposing one expanded column to ``tests/causality.py``.

    The expansion is not a feature and must never be registered as one -- it
    is a transform of a design matrix. Its causal claim is identical in kind
    to a feature's, so the same harness sweeps it.

    The chosen term is a *cross* term of two different features. A pure power
    of a single feature would inherit that feature's causality trivially; a
    product of two is where a defect in the term-indexing could actually
    reorder or misalign columns.
    """

    def __init__(self, window: int, *, peek: bool = False) -> None:
        self._window = window
        self._peek = peek

    @property
    def name(self) -> str:
        return f"log_return_{self._window}*realized_vol_{self._window}"

    @property
    def version(self) -> int:
        return 1

    @property
    def lookback_bars(self) -> int:
        return self._window + 1

    @property
    def confirmation_lag_bars(self) -> int:
        return 0

    @property
    def session_relative(self) -> bool:
        return False

    def compute(self, df: pd.DataFrame) -> pd.Series:
        left = LogReturn(window=self._window).compute(df)
        right = RealizedVol(window=self._window).compute(df)
        if self._peek:
            # The adversarial fixture: one factor read from the next bar.
            right = right.shift(-1)

        design = np.column_stack(
            [left.to_numpy(dtype=np.float64), right.to_numpy(dtype=np.float64)]
        )
        expanded = polynomial_expand(np.nan_to_num(design, nan=np.nan), 2)
        cross = polynomial_terms(2, 2).index((0, 1))
        return pd.Series(expanded[:, cross], index=df.index, name=self.name)


def test_a_cross_term_survives_truncation_at_every_bar() -> None:
    """DATA_CONTRACT §1 on the expansion, swept by the real harness."""
    assert_causal(_ExpandedTermAsFeature(12), generate_ohlcv(n_bars=260, seed=7))


def test_the_cross_term_survives_at_the_registered_windows() -> None:
    """The same sweep at the window H-011 actually runs."""
    assert_causal(_ExpandedTermAsFeature(24), generate_ohlcv(n_bars=600, seed=9))


def test_a_forward_peeking_expansion_is_rejected() -> None:
    """EVALUATION.md §14: the gate must be shown to fire, not assumed to.

    Identical code path, one factor shifted back by a bar. If this passed, the
    two tests above would prove nothing.
    """
    with pytest.raises(CausalityError):
        assert_causal(
            _ExpandedTermAsFeature(12, peek=True), generate_ohlcv(n_bars=260, seed=7)
        )
