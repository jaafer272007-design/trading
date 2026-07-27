"""Pytest configuration.

Pins BLAS threading before NumPy is imported, per ``REPRODUCIBILITY.md`` §4:

    OS-level BLAS threading fixed (``OMP_NUM_THREADS=1``) — parallel float
    reduction ordering changes results in the last bits and will silently
    break bit-exactness tests.

This matters more here than almost anywhere else in the project. The causal
harness compares raw float64 bit patterns, so a last-bit difference caused by
a thread-count-dependent reduction order would be reported as a causal
violation — a false K-2 halt, chasing a leak that does not exist.

``conftest.py`` is imported before any test module, so setting the environment
here lands ahead of the NumPy import in the modules under test.
"""

import os

for _var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(_var, "1")


def pytest_terminal_summary(terminalreporter: object) -> None:
    """Report raw exports whose bytes have not arrived, on every run.

    ``src/data/raw.py`` lets a registered export be absent while it is still
    in transit from the Windows machine — the hash is pre-registered before
    the file lands, which is the useful property, but it means a green suite
    does not by itself mean the data is here.

    Reporting it in the summary is the whole point. The obvious alternative,
    parametrising the file-reading tests over an empty set, makes pytest emit
    a *skip*, and a skipped test is exactly the invisible gate this project
    keeps finding: it looks like a pass in every log that matters. This prints
    instead, unmissably, on green runs and red ones alike.
    """
    from data.raw import awaiting

    pending = awaiting()
    if not pending:
        return

    write = getattr(terminalreporter, "write_line", None)
    if write is None:  # pragma: no cover - defensive against a pytest change
        return
    write("")
    write("=" * 70)
    write(f"RAW DATA PENDING — {len(pending)} registered export(s) not yet in the repo")
    write("=" * 70)
    for export in pending:
        write(f"  {export.filename}")
        write(f"      hash pre-registered: {export.sha256}")
        write(f"      expected rows:       {export.rows:,}")
    write("")
    write("  These are a promise about data, not data. Nothing may be ingested")
    write("  from them, and no result may cite them, until the bytes land and")
    write("  the hash verifies. The suite is green because the repository is")
    write("  honest about not having them — not because it has them.")
    write("=" * 70)
