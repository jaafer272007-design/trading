"""The registry of raw broker exports, and the guard that pins them.

``data/raw/`` holds the irreplaceable bytes: exactly what MetaTrader handed
over, server timestamps untouched. These files are **committed**. Everything
downstream of them is not.

Why raw is committed and derived is not
---------------------------------------

``DATA_CONTRACT.md`` §8 makes a result void if its snapshot no longer exists.
That is a statement about *existence*, and the two stages differ in how they
can be made to exist again:

============  ====================================================  =========
stage         if it were lost                                        committed
============  ====================================================  =========
**raw**       Unrecoverable. A broker can revise history, prune it,
              or close the account. The bytes exist because we have
              them, and for no other reason.                         **yes**
**derived**   A pure function of raw + the frozen calendar + the
              code in ``src/data/``, all committed. Rebuild it and
              compare the manifest hash.                             no
============  ====================================================  =========

So committing the derived frame would store the same information twice. The
manifest's ``derived_sha256`` is what makes the rebuild checkable, and that
number lives in the run manifest rather than in a duplicated file.

Why the hashes are pinned *here* and not only in the sidecars
-------------------------------------------------------------

Each export ships a ``.sha256`` sidecar written on the Windows machine. That
sidecar travels with the file, and it is the file's own account of itself: if
the CSV is corrupted between the exporting machine and this repository, a
transport that mangles the CSV will just as happily mangle the sidecar, and
the pair stays internally consistent while being wrong.

The constants below are an *independent* record. They were transcribed from
the export run's terminal output, reviewed in a diff, and committed by hand.
A byte that changes in transit fails against them.

The realistic corruption is not exotic. A web upload, a copy through a text
editor, or a clone on a machine with ``core.autocrlf=true`` rewrites LF to
CRLF and shifts every byte after the first newline. ``.gitattributes`` marks
these paths ``-text`` to stop git doing it; this guard is what catches it if
something else does.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

RAW_DIR: Final = Path(__file__).resolve().parents[2] / "data" / "raw"


class RawExportError(RuntimeError):
    """A registered export is missing, altered, or disagrees with its record."""


@dataclass(frozen=True)
class RawExport:
    """One committed export, and everything needed to detect it changing."""

    filename: str
    timeframe: str
    sha256: str
    rows: int
    first_server_day: date
    last_server_day: date
    awaiting_upload: bool = False
    """The file is registered but has not landed in the repository yet.

    A real state, not a loophole. The exports are produced on a Windows
    machine this repository cannot reach, so the hash is committed *first* —
    pre-registering what the bytes must be, before they arrive, which is the
    same discipline ``HYPOTHESES.md`` applies to results.

    The flag cannot rot, because it self-clears by failing: once the file is
    present, leaving this ``True`` is itself an error (see :func:`verify`).
    The only reachable states are absent-and-awaited, or present-and-matching.
    """

    @property
    def path(self) -> Path:
        """Location on disk.

        Returns:
            Absolute path to the CSV.
        """
        return RAW_DIR / self.filename

    @property
    def sidecar(self) -> Path:
        """Location of the hash sidecar written beside it on Windows.

        Returns:
            Absolute path to the ``.sha256`` file.
        """
        return RAW_DIR / f"{self.filename}.sha256"


#: Every raw export that ships. Transcribed by hand from the export run's
#: output and reviewed in the diff that added it — that hand step is the whole
#: point, and pasting a hash from the sidecar to silence a failure defeats it.
#:
#: Adding an export here without adding the file is caught by
#: ``test_every_registered_export_is_present``; adding the file without
#: registering it is caught by ``test_every_file_in_raw_is_registered``.
RAW_EXPORTS: Final[tuple[RawExport, ...]] = (
    RawExport(
        filename="GOLD-H1-20080311-20260727.csv",
        timeframe="H1",
        sha256="519ecd24515495bdeb7fb1df2a3699a98ac0337be91af87fe0b218516eb4b775",
        rows=67_367,
        first_server_day=date(2008, 3, 11),
        last_server_day=date(2026, 7, 27),
        awaiting_upload=True,
    ),
    RawExport(
        filename="GOLD-M1-20260415-20260727.csv",
        timeframe="M1",
        sha256="c7470c3d3a6ed2d28fffc9aebf30817ae950c01c14d58c943ac469f20f3bded6",
        rows=100_213,
        first_server_day=date(2026, 4, 15),
        last_server_day=date(2026, 7, 27),
        awaiting_upload=True,
    ),
)


def sha256_file(path: Path) -> str:
    """Hash a file's bytes, streaming.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex SHA-256.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def read_sidecar(path: Path) -> str | None:
    """Read the hash out of a ``sha256sum``-format sidecar.

    Args:
        path: Sidecar file.

    Returns:
        The hex digest, or ``None`` if absent or unparseable.
    """
    if not path.exists():
        return None
    first = path.read_text(encoding="utf-8").strip().split()
    return first[0].lower() if first else None


def verify(export: RawExport) -> None:
    """Check one export against its registered record.

    Args:
        export: The registry entry.

    Raises:
        RawExportError: If the file is absent, its bytes do not match the
            registered hash, or the sidecar disagrees.
    """
    if not export.path.exists():
        if export.awaiting_upload:
            return
        raise RawExportError(
            f"{export.path} is registered in RAW_EXPORTS but not present.\n"
            f"Either upload the export, or remove the entry. A registry that "
            f"names data the repository does not have makes every result "
            f"citing it unreproducible (DATA_CONTRACT §8). If it is genuinely "
            f"still in transit, set awaiting_upload=True and say so."
        )

    if export.awaiting_upload:
        raise RawExportError(
            f"{export.filename} has landed, but its registry entry still says "
            f"awaiting_upload=True. Set it to False.\n"
            f"This is how the flag self-clears: an entry marked as awaited "
            f"while the file is present would let a permanently-absent export "
            f"look intentional, so the moment the data arrives the flag "
            f"becomes an error rather than a note."
        )

    live = sha256_file(export.path)
    if live != export.sha256:
        raise RawExportError(
            f"{export.filename} does not match its registered hash.\n"
            f"  registered: {export.sha256}\n"
            f"  on disk:    {live}\n"
            f"The most likely cause is line-ending conversion in transit or on "
            f"checkout, not a broker revision — check `git check-attr text -- "
            f"{export.path}` before concluding the data changed. If the broker "
            f"really did revise history, that is a NEW export under a new "
            f"name; §8 makes these files immutable."
        )

    sidecar = read_sidecar(export.sidecar)
    if sidecar is not None and sidecar != export.sha256:
        raise RawExportError(
            f"{export.filename}: the sidecar written on the exporting machine "
            f"says {sidecar}, the registry says {export.sha256}, and the file "
            f"itself matches the registry. Two independent records disagree; "
            f"do not proceed until it is understood which one is wrong."
        )


def verify_all() -> None:
    """Check every registered export.

    Raises:
        RawExportError: On the first failure.
    """
    for export in RAW_EXPORTS:
        verify(export)


def awaiting() -> tuple[RawExport, ...]:
    """Exports whose bytes have not arrived yet.

    Nothing may be ingested from these. Exposed so the state is reportable
    rather than something a reader has to notice.

    Returns:
        The pending entries.
    """
    return tuple(e for e in RAW_EXPORTS if e.awaiting_upload)


def find(timeframe: str) -> RawExport:
    """Look up the registered export for a timeframe.

    Args:
        timeframe: ``"H1"`` or ``"M1"``.

    Returns:
        The registry entry.

    Raises:
        RawExportError: If no export is registered for that timeframe.
    """
    for export in RAW_EXPORTS:
        if export.timeframe == timeframe:
            return export
    raise RawExportError(
        f"no raw export registered for timeframe {timeframe!r}; "
        f"have {sorted(e.timeframe for e in RAW_EXPORTS)}"
    )
