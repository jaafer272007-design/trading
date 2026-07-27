"""The raw-export guard: what is committed, and that it has not moved.

Two directions, both required. The registry is checked against the filesystem
so a registered export cannot be missing, and the filesystem is checked
against the registry so a file cannot appear without a reviewed hash. Same
pattern as ``FEATURE_REGISTRY`` and the frozen calendar.

Why the file-reading tests loop internally instead of parametrising
------------------------------------------------------------------

``LANDED`` is empty while the exports are in transit, and
``@pytest.mark.parametrize`` over an empty sequence makes pytest emit a
**skip**. A skipped test is the invisible gate this project keeps rediscovering
— it reads as a pass in every summary line that matters. Looping inside the
test body makes the vacuous case a genuine pass, and ``conftest.py``'s terminal
summary is what makes the absence loud instead.

The guard-can-fail tests below deliberately do *not* depend on ``LANDED``. They
synthesise their own files under ``tmp_path``, so the question "can this guard
actually reject anything?" is answered on every run, including runs where no
export has landed yet.
"""

import csv
import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from data.raw import (
    RAW_DIR,
    RAW_EXPORTS,
    RawExport,
    RawExportError,
    awaiting,
    find,
    sha256_file,
    verify,
    verify_all,
)

#: Exports whose bytes are here. Everything that reads a file is scoped to
#: these; the pending ones are covered by the registry tests instead.
LANDED = tuple(e for e in RAW_EXPORTS if not e.awaiting_upload)


def _stub(**overrides: object) -> RawExport:
    """A registry entry that names no real data, for exercising the guard.

    Its ``path`` resolves against whatever ``data.raw.RAW_DIR`` is at call
    time, so patching that to ``tmp_path`` puts the stub somewhere writable.

    Args:
        **overrides: Fields to change from the defaults.

    Returns:
        A ``RawExport`` naming a file no export ever produced.
    """
    fields: dict[str, object] = {
        "filename": "STUB-H4-20200101-20200102.csv",
        "timeframe": "H4",
        "sha256": "0" * 64,
        "rows": 1,
        "first_server_day": datetime(2020, 1, 1, tzinfo=UTC).date(),
        "last_server_day": datetime(2020, 1, 2, tzinfo=UTC).date(),
    }
    fields.update(overrides)
    return RawExport(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_every_registered_export_matches_its_recorded_hash() -> None:
    """The load-bearing test.

    If this fails, do NOT paste the new hash in. Establish whether the bytes
    changed in transit (line endings, a text-mode copy) or the broker revised
    history — those need opposite responses, and only one of them is a new
    export.
    """
    verify_all()


def test_every_registered_export_is_present_or_declared_pending() -> None:
    """A registry naming data we do not have makes results citing it void."""
    missing = [
        e.filename for e in RAW_EXPORTS if not e.path.exists() and not e.awaiting_upload
    ]
    assert not missing, (
        f"registered but absent from data/raw/: {missing}. Upload the export, "
        f"remove the entry, or mark it awaiting_upload — a registry that "
        f"silently overstates what the repository holds is worse than an "
        f"empty one."
    )


def test_a_landed_export_cannot_still_be_marked_awaiting() -> None:
    """The flag self-clears by failing, so it cannot rot."""
    stale = [e.filename for e in awaiting() if e.path.exists()]
    assert not stale, (
        f"present but still flagged awaiting_upload: {stale}. Set the flag to "
        f"False — leaving it set would let a genuinely missing export look "
        f"intentional forever."
    )


def test_nothing_may_be_ingested_from_a_pending_export() -> None:
    """States the consequence rather than leaving it to be inferred.

    Pending entries carry a pre-registered hash and no bytes. They are a
    promise about data, not data.
    """
    for export in awaiting():
        assert not export.path.exists(), export.filename


def test_every_file_in_raw_is_registered() -> None:
    """A CSV nobody registered has no reviewed hash and no provenance."""
    on_disk = {p.name for p in RAW_DIR.glob("*.csv")}
    registered = {e.filename for e in RAW_EXPORTS}
    assert not (on_disk - registered), (
        f"unregistered files in data/raw/: {sorted(on_disk - registered)}. "
        f"Add a RawExport entry with the hash transcribed from the export "
        f"run's own output."
    )


def test_registry_is_not_empty() -> None:
    """A vacuous sweep must not be able to report success."""
    assert RAW_EXPORTS


# ---------------------------------------------------------------------------
# The record is internally consistent
# ---------------------------------------------------------------------------


def test_hashes_are_well_formed_and_distinct() -> None:
    digests = [e.sha256 for e in RAW_EXPORTS]
    for digest in digests:
        assert len(digest) == 64, digest
        assert all(c in "0123456789abcdef" for c in digest), digest
    assert len(set(digests)) == len(digests), "two exports share a hash"


def test_timeframes_are_unique_and_findable() -> None:
    """``find`` returns one entry per timeframe; two would make it arbitrary."""
    timeframes = [e.timeframe for e in RAW_EXPORTS]
    assert len(set(timeframes)) == len(timeframes)
    for export in RAW_EXPORTS:
        assert find(export.timeframe) is export


def test_find_rejects_an_unregistered_timeframe() -> None:
    with pytest.raises(RawExportError, match="no raw export registered"):
        find("H4")


def test_spans_are_ordered() -> None:
    for export in RAW_EXPORTS:
        assert export.first_server_day <= export.last_server_day, export.filename


def test_filenames_agree_with_the_registered_span() -> None:
    """The name encodes the span. A copy-paste slip between the two is caught."""
    for export in RAW_EXPORTS:
        stem = export.filename.removesuffix(".csv")
        _, timeframe, first, last = stem.split("-")
        assert timeframe == export.timeframe, export.filename
        assert first == export.first_server_day.strftime("%Y%m%d"), export.filename
        assert last == export.last_server_day.strftime("%Y%m%d"), export.filename


# ---------------------------------------------------------------------------
# The file says what the registry says it says
# ---------------------------------------------------------------------------


def test_row_count_matches() -> None:
    """A truncated upload can still be a valid CSV. The count catches it."""
    for export in LANDED:
        with export.path.open(newline="", encoding="utf-8") as handle:
            rows = sum(1 for _ in csv.reader(handle)) - 1  # less the header
        assert rows == export.rows, (
            f"{export.filename}: {rows:,} data rows, registry says "
            f"{export.rows:,}. A partial transfer parses cleanly and is short."
        )


def test_columns_are_mt5s_own_untouched() -> None:
    """The exporter renames nothing. If this drifts, something interpreted."""
    for export in LANDED:
        with export.path.open(newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        assert header == [
            "time",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread",
            "real_volume",
        ], header


def test_span_matches_the_registered_dates() -> None:
    """``time`` is SERVER wall-clock as an epoch, so read it back as UTC.

    Reading it as local time would shift the boundary days by the runner's own
    offset — the export's first and last day are properties of the broker's
    clock, not of whichever machine happens to run the suite.
    """
    for export in LANDED:
        with export.path.open(newline="", encoding="utf-8") as handle:
            epochs = [int(row["time"]) for row in csv.DictReader(handle)]

        first = datetime.fromtimestamp(epochs[0], tz=UTC).date()
        last = datetime.fromtimestamp(epochs[-1], tz=UTC).date()
        assert first == export.first_server_day, f"{export.filename}: first {first}"
        assert last == export.last_server_day, f"{export.filename}: last {last}"


def test_timestamps_are_strictly_increasing() -> None:
    """De-duplicated and sorted at export. Reordering hides a feed defect."""
    for export in LANDED:
        with export.path.open(newline="", encoding="utf-8") as handle:
            epochs = [int(row["time"]) for row in csv.DictReader(handle)]
        bad = [i for i in range(1, len(epochs)) if epochs[i] <= epochs[i - 1]]
        assert not bad, f"{export.filename}: non-increasing at rows {bad[:5]}"


def test_line_endings_survived_transit() -> None:
    """CRLF here means git or a transport rewrote the file.

    Checked explicitly rather than left to the hash, because this is the one
    failure mode with an actionable fix (``.gitattributes``) rather than an
    investigation.
    """
    for export in LANDED:
        head = export.path.read_bytes()[:65_536]
        assert b"\r\n" not in head, (
            f"{export.filename} contains CRLF. The exporter writes LF only, so "
            f"something converted it — check `git check-attr text -- "
            f"{export.path}` and that .gitattributes marks data/raw/*.csv -text."
        )


def test_sidecars_are_present_and_agree() -> None:
    """The sidecar travels with the file; the registry is the independent copy."""
    for export in LANDED:
        assert export.sidecar.exists(), (
            f"{export.sidecar.name} missing. The sidecar is the exporting "
            f"machine's own account of the bytes and ships beside the CSV."
        )


# ---------------------------------------------------------------------------
# The guard can fail
#
# These run unconditionally. A guard that has never fired is indistinguishable
# from one that cannot fire, and the useful moment to know the difference is
# *before* the data arrives, not after it has been trusted.
# ---------------------------------------------------------------------------


def test_guard_rejects_an_absent_file() -> None:
    """No file, no awaiting flag: the registry overstates what we hold."""
    phantom = _stub(filename="NOT-A-REAL-EXPORT.csv")
    with pytest.raises(RawExportError, match="not present"):
        verify(phantom)


def test_guard_accepts_an_absent_file_that_is_declared_pending() -> None:
    """The one legitimate absence, and it has to be declared to be legitimate."""
    verify(_stub(filename="NOT-A-REAL-EXPORT.csv", awaiting_upload=True))


def test_guard_rejects_a_present_file_still_flagged_awaiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The self-clearing rule, exercised rather than asserted in prose."""
    monkeypatch.setattr("data.raw.RAW_DIR", tmp_path)
    entry = _stub(awaiting_upload=True)
    entry.path.write_bytes(b"time\n1\n")
    with pytest.raises(RawExportError, match="still says"):
        verify(entry)


def test_guard_rejects_a_wrong_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("data.raw.RAW_DIR", tmp_path)
    entry = _stub()
    entry.path.write_bytes(b"time\n1\n")
    with pytest.raises(RawExportError, match="does not match"):
        verify(entry)


def test_guard_rejects_a_sidecar_that_disagrees_with_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two independent records of the same bytes, disagreeing.

    The file matches the registry, so nothing is corrupt — but one of the two
    records was written about different bytes, and which one is unknown.
    """
    monkeypatch.setattr("data.raw.RAW_DIR", tmp_path)
    body = b"time\n1\n"
    digest = hashlib.sha256(body).hexdigest()
    entry = _stub(sha256=digest)
    entry.path.write_bytes(body)
    entry.sidecar.write_text(f"{'f' * 64} *{entry.filename}\n", encoding="utf-8")
    with pytest.raises(RawExportError, match="disagree"):
        verify(entry)


def test_guard_accepts_a_sidecar_that_agrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for the test above: same shape, correct sidecar."""
    monkeypatch.setattr("data.raw.RAW_DIR", tmp_path)
    body = b"time\n1\n"
    digest = hashlib.sha256(body).hexdigest()
    entry = _stub(sha256=digest)
    entry.path.write_bytes(body)
    entry.sidecar.write_text(f"{digest} *{entry.filename}\n", encoding="utf-8")
    verify(entry)


def test_one_appended_byte_moves_the_hash(tmp_path: Path) -> None:
    """The corruption this is built to catch is a byte, not a rewrite."""
    body = b"time,open\n1,1.0\n"
    original = tmp_path / "a.csv"
    original.write_bytes(body)
    before = sha256_file(original)

    with original.open("ab") as handle:
        handle.write(b"\n")
    assert sha256_file(original) != before, (
        "appending one byte did not move the hash; the guard cannot detect "
        "the corruption it exists to detect"
    )


def test_crlf_conversion_moves_the_hash(tmp_path: Path) -> None:
    """The specific failure ``.gitattributes`` prevents, shown to be detectable.

    This is the realistic one: nobody edits these files, but a checkout on a
    machine with ``core.autocrlf=true`` rewrites every line ending, and the
    result is a file that no human touched and that no longer verifies.
    """
    lf = tmp_path / "lf.csv"
    crlf = tmp_path / "crlf.csv"
    lf.write_bytes(b"time,open\n1,1.0\n2,2.0\n")
    crlf.write_bytes(lf.read_bytes().replace(b"\n", b"\r\n"))
    assert sha256_file(lf) != sha256_file(crlf)


def test_a_copied_export_still_verifies(tmp_path: Path) -> None:
    """Byte-mode copies are safe; the hash is only sensitive to real changes."""
    for export in LANDED[:1]:
        copied = tmp_path / export.filename
        shutil.copy(export.path, copied)
        assert sha256_file(copied) == export.sha256
