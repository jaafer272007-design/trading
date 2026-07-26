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
