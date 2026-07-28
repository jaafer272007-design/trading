"""Every hash in the registry must have a file behind it.

``REPRODUCIBILITY.md`` §8 requires run manifests to be "retained for the
project's full life", with a monthly cold-storage export and a quarterly
restore drill: "a reproducibility policy that is never exercised is not a
policy."

Until 2026-07-28 that rule was **prose**, ``runs/`` was in ``.gitignore``, and
nothing enforced it. Five run manifests were referenced by sha256 in
``HYPOTHESES.md`` and none of them was in git. One is now unrecoverable — see
:data:`KNOWN_LOST`.

Why this module exists at all
------------------------------

Every rule in this project that survived became a **build-failing test**: the
causal harness for `DATA_CONTRACT.md` §1, ``FEATURE_REGISTRY`` checked against
the filesystem, the capacity signature for `REPRODUCIBILITY.md` §6, the
session-relative refusal for R-001. Every rule that stayed prose was either
obeyed by luck or not obeyed at all, and §8 is the one that was not.

So this is the same shape as those: parse the declaration out of the registry,
check it against the filesystem, and fail the build when they disagree. A hash
whose file is gone proves only that a file once existed with those contents. It
cannot reproduce a number, and it must not read as though it could.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent.parent
REGISTRY: Final = REPO_ROOT / "HYPOTHESES.md"
RUNS: Final = REPO_ROOT / "runs"

_REFERENCE: Final = re.compile(
    r"`(runs/[0-9a-f-]{36}\.json)`,?\s*\n\s*sha256 `([0-9a-f]{64})`"
)
"""Matches a ``**Run manifest:**`` block, over the two lines it spans."""

KNOWN_LOST: Final = {
    "runs/dc0f40bc-422c-433f-8790-4567a0408843.json": (
        "H-009, the volatility claim. Executed 2026-07-28 at commit `ea4dc33` "
        "on a clean tree, in a session whose filesystem is gone. The manifest "
        "was never committed because `runs/` was gitignored, and the container "
        "that held it was reclaimed. UNRECOVERABLE: the run cannot be "
        "reproduced from its manifest, because there is no manifest to "
        "reproduce it from. What survives is the sha256 in H-009's entry, the "
        "result block, the code at `ea4dc33`, and the snapshot hash - which "
        "together are enough to re-run the hypothesis but NOT enough to verify "
        "that a re-run reproduces the original."
    ),
}
"""Manifests referenced by the registry whose files no longer exist.

Naming a gap makes it a record. Discovering it later does not. Each entry says
which run, what is unrecoverable, and what survives - so a reader is never left
inferring the extent of the loss from an absence.

Adding to this dictionary is not a way to silence the guard: every entry is
checked to be genuinely absent by
``tests/evaluation/test_archive.py::test_the_loss_record_does_not_rot``. An
entry for a file that exists fails the build just as loudly as a missing file
with no entry.
"""


@dataclass(frozen=True, slots=True)
class ManifestReference:
    """One ``**Run manifest:**`` reference parsed out of the registry."""

    path: str
    recorded_sha256: str

    @property
    def file(self) -> Path:
        """Absolute path the reference points at."""
        return REPO_ROOT / self.path

    @property
    def exists(self) -> bool:
        """Whether the referenced file is present."""
        return self.file.is_file()

    @property
    def is_known_lost(self) -> bool:
        """Whether this reference is a recorded, explained loss."""
        return self.path in KNOWN_LOST

    def actual_sha256(self) -> str | None:
        """Hash the file on disk.

        Returns:
            Hex digest, or ``None`` when the file is absent.
        """
        if not self.exists:
            return None
        return hashlib.sha256(self.file.read_bytes()).hexdigest()

    def verifies(self) -> bool:
        """Whether the file exists and matches its recorded hash."""
        return self.actual_sha256() == self.recorded_sha256


def manifest_references(registry: Path | None = None) -> tuple[ManifestReference, ...]:
    """Every manifest the registry references by path and hash.

    Args:
        registry: Registry file. Defaults to ``HYPOTHESES.md``.

    Returns:
        One reference per ``**Run manifest:**`` block, in file order.

    Raises:
        FileNotFoundError: If the registry is absent.
    """
    path = REGISTRY if registry is None else registry
    text = path.read_text(encoding="utf-8")
    return tuple(
        ManifestReference(path=m.group(1), recorded_sha256=m.group(2))
        for m in _REFERENCE.finditer(text)
    )
