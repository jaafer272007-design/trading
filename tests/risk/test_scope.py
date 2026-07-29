"""The boundary around this layer, asserted rather than intended.

``RETROSPECTIVE-2.md`` §1.2 records the transferable lesson from this project:
**a rule that is not a test is a rule you are relying on luck to follow.**
``REPRODUCIBILITY.md`` §8 was the one rule that stayed prose, and it was the
one rule that was not obeyed -- broken by an ordinary ``.gitignore`` edit that
nobody thought about.

Four statements about this layer are exactly the kind that decay into prose:

1. It **joins no pipeline** -- nothing in the research path depends on it.
2. It **never trades** -- ``order_send`` appears nowhere in this repository.
3. Its **core never imports MetaTrader5**, which is what makes it testable on a
   machine that does not have a terminal.
4. It **makes no market claim**, so it carries no hypothesis ID.

Each is a build failure here instead.
"""

import ast
from pathlib import Path
from typing import Final

REPO: Final = Path(__file__).resolve().parents[2]
SRC: Final = REPO / "src"

#: Every package in the research path. ``risk`` is deliberately absent: this is
#: the set that must not depend on it.
RESEARCH_PACKAGES: Final = (
    "backtest",
    "data",
    "evaluation",
    "features",
    "labels",
    "metrics",
    "models",
)

#: Directories whose Python is this project's own. ``.venv`` and ``.claude``
#: hold third-party code that these assertions say nothing about.
OWN_CODE_ROOTS: Final = ("src", "tests", "scripts")


def _own_python_files() -> list[Path]:
    files: list[Path] = []
    for root in OWN_CODE_ROOTS:
        files.extend(sorted((REPO / root).rglob("*.py")))
    return files


def _called_names(path: Path) -> set[str]:
    """Every name this file could be calling, from its syntax tree.

    Parsed rather than grepped, for the same reason as
    :func:`_imported_modules`: this file's own package docstring names
    ``order_send`` in order to say that it is absent, and a text search cannot
    tell that sentence apart from a call.

    Args:
        path: The file.

    Returns:
        Bare names and attribute names appearing in call position, plus every
        attribute accessed at all -- so ``mt5.order_send`` counts even when it
        is bound to a variable before being called.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Name):
            found.add(node.id)
    return found


def _imported_modules(path: Path) -> set[str]:
    """Top-level module names imported by a file, from its syntax tree.

    Parsed rather than grepped: a string containing the word ``import`` is not
    an import, and a test that cannot tell the difference reports findings
    about itself.

    Args:
        path: The file.

    Returns:
        Top-level names, so ``risk.carry`` contributes ``risk``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


# --------------------------------------------------------------------------
# 1. It joins no pipeline
# --------------------------------------------------------------------------


def test_nothing_in_the_research_path_imports_the_risk_layer() -> None:
    offenders = [
        path.relative_to(REPO)
        for package in RESEARCH_PACKAGES
        for path in sorted((SRC / package).rglob("*.py"))
        if "risk" in _imported_modules(path)
    ]
    assert offenders == [], (
        f"the risk layer joins no pipeline, but {offenders} import it; "
        f"the dependency runs one way only"
    )


def test_the_risk_layer_depends_on_the_research_path_only_for_the_comparison() -> None:
    # It imports the registered swap constants in order to compare against
    # them, and nothing else. A second research import would mean this layer
    # had started to be part of something.
    allowed = {"backtest"}
    used: set[str] = set()
    for path in sorted((SRC / "risk").rglob("*.py")):
        used |= _imported_modules(path) & set(RESEARCH_PACKAGES)
    assert used <= allowed, (
        f"the risk layer imports {sorted(used - allowed)} from the research "
        f"path; the only permitted dependency is the registered swap constant "
        f"it exists to compare against"
    )


def test_the_only_thing_taken_from_the_cost_model_is_the_registered_swap() -> None:
    source = (SRC / "risk" / "swap.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "backtest.costs":
            imported.update(alias.name for alias in node.names)
    assert imported == {
        "SWAP_LONG_POINTS_PER_LOT_PER_NIGHT",
        "SWAP_SHORT_POINTS_PER_LOT_PER_NIGHT",
    }


# --------------------------------------------------------------------------
# 2. It never trades
# --------------------------------------------------------------------------


#: Every MT5 entry point that changes state on the broker or the terminal.
#: Written out so that adding one has to be a deliberate act against a named
#: list rather than an import nobody reads. ``order_calc_margin`` and
#: ``order_check`` are absent because they compute and do not send.
MT5_STATE_CHANGING_CALLS: Final = (
    "order_send",
    "market_book_add",
    "market_book_release",
)


def test_no_state_changing_mt5_call_appears_anywhere_in_this_repository() -> None:
    # RESEARCH.md Sec 2: an autonomous system that trades unsupervised capital
    # is explicitly not what is being built. The read-only property of this
    # layer is worth exactly as much as the guarantee that nothing anywhere
    # can place an order, so the assertion is repository-wide rather than
    # scoped to src/risk.
    forbidden = set(MT5_STATE_CHANGING_CALLS)
    offenders = {
        str(path.relative_to(REPO)): sorted(_called_names(path) & forbidden)
        for path in _own_python_files()
        if path != Path(__file__) and _called_names(path) & forbidden
    }
    assert offenders == {}, (
        f"{offenders}; nothing in this repository may place, modify or close "
        f"an order, or take a position in the order book"
    )


def test_the_guard_reads_code_and_not_prose() -> None:
    # The package docstring names order_send in order to say it is absent. A
    # text search would report that sentence as a violation, and a guard that
    # fires on its own documentation gets deleted rather than fixed.
    package = SRC / "risk" / "__init__.py"
    assert "order_send" in package.read_text(encoding="utf-8")
    assert "order_send" not in _called_names(package)


# --------------------------------------------------------------------------
# 3. The core never imports MetaTrader5
# --------------------------------------------------------------------------


def test_the_arithmetic_core_never_imports_metatrader() -> None:
    offenders = [
        path.relative_to(REPO)
        for path in sorted((SRC / "risk").rglob("*.py"))
        if "MetaTrader5" in _imported_modules(path)
    ]
    assert offenders == [], (
        f"{offenders} import MetaTrader5; the core must stay constructible on "
        f"a machine that has no terminal, which is the only way it can be "
        f"tested at all"
    )


def test_the_core_reads_no_clock_of_its_own() -> None:
    # Every function takes the reading time as a parameter. A hidden
    # datetime.now would make the throttle untestable and the whole report
    # non-reproducible from its inputs.
    offenders = [
        path.relative_to(REPO)
        for path in sorted((SRC / "risk").rglob("*.py"))
        if "datetime.now(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# --------------------------------------------------------------------------
# 4. It makes no market claim
# --------------------------------------------------------------------------


def test_the_risk_layer_carries_no_hypothesis_id() -> None:
    # A hypothesis ID here would mean this layer had drawn on N_claims, which
    # would change the Benjamini-Hochberg denominator for every registered
    # result. It makes no claim about markets and must never take a draw.
    offenders = [
        path.relative_to(REPO)
        for path in sorted((SRC / "risk").rglob("*.py"))
        if "hypothesis_id" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_the_package_docstring_states_the_scope_it_is_held_to() -> None:
    text = (SRC / "risk" / "__init__.py").read_text(encoding="utf-8")
    assert "joins no pipeline" in text
    assert "makes no claim about markets" in text
