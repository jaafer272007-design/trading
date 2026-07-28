"""The archival guard — REPRODUCIBILITY.md §8, enforced rather than described.

``test_every_referenced_manifest_is_present_and_verifies`` is the load-bearing
test. It is the same filesystem-versus-declaration pattern as the feature
registry and the capacity signature: the registry declares a hash, the
filesystem either has a file matching it or the build fails.

§8 is the one rule in this project that stayed prose, and it is the one rule
that was not obeyed. That is the reason this file exists and the reason it is
written in this shape.
"""

import hashlib

import pytest

from evaluation.archive import (
    KNOWN_LOST,
    REGISTRY,
    RUNS,
    ManifestReference,
    manifest_references,
)

# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_the_registry_references_manifests_at_all() -> None:
    """A vacuous guard must not be able to report success."""
    references = manifest_references()

    assert len(references) >= 5, "the parser stopped matching; fix it, not this"


def test_every_referenced_manifest_is_present_and_verifies() -> None:
    """Every sha256 in the registry has a committed file behind it.

    If this fails, the fix is NOT to add the run to KNOWN_LOST. A manifest that
    exists but does not verify is a corrupted archive, and a manifest that is
    missing because nobody committed it is a process failure to fix at the
    source. KNOWN_LOST is for artefacts that are genuinely unrecoverable and it
    carries an explanation for each.
    """
    problems: list[str] = []
    for reference in manifest_references():
        if reference.is_known_lost:
            continue
        if not reference.exists:
            problems.append(f"{reference.path}: file absent, and not in KNOWN_LOST")
        elif not reference.verifies():
            problems.append(
                f"{reference.path}: recorded {reference.recorded_sha256}, "
                f"actual {reference.actual_sha256()}"
            )

    assert not problems, "\n".join(problems)


def test_the_loss_record_does_not_rot() -> None:
    """Every KNOWN_LOST entry must be genuinely lost, and genuinely referenced.

    An entry for a file that has since reappeared would silently exempt a
    manifest the guard should be checking. An entry for a path the registry
    never mentions is a record of nothing.
    """
    referenced = {r.path for r in manifest_references()}

    for path in KNOWN_LOST:
        assert path in referenced, f"{path} is in KNOWN_LOST but unreferenced"
        assert not (RUNS.parent / path).is_file(), (
            f"{path} is in KNOWN_LOST but the file exists. Remove the entry — "
            f"an exemption for a present file hides it from the guard."
        )


def test_every_loss_is_explained() -> None:
    """A gap named is a record; a gap listed is not."""
    for path, reason in KNOWN_LOST.items():
        assert len(reason) > 200, f"{path}: the explanation is too thin to be one"
        assert "UNRECOVERABLE" in reason or "recoverable" in reason.lower(), path


def test_runs_are_not_gitignored() -> None:
    """The cause, guarded at the cause.

    Re-ignoring ``runs/`` would make every future manifest vanish again while
    every test above kept passing on the files already committed.
    """
    ignore = (REGISTRY.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    offenders = [
        line
        for line in ignore
        if line.strip().rstrip("/") == "runs" and not line.strip().startswith("#")
    ]

    assert not offenders, (
        "runs/ is gitignored again. REPRODUCIBILITY.md §8 requires manifests "
        "retained for the project's life; a gitignored runs/ is how five of "
        "them ended up outside version control and one ended up unrecoverable."
    )


# ---------------------------------------------------------------------------
# The parser and the reference type
# ---------------------------------------------------------------------------


def test_the_parser_reads_both_lines_of_a_reference() -> None:
    """Path and hash are on separate lines. A one-line parser would find none."""
    for reference in manifest_references():
        assert reference.path.startswith("runs/")
        assert len(reference.recorded_sha256) == 64


def test_a_present_manifest_hashes_to_its_recorded_value() -> None:
    """At least one reference must actually verify, or the guard proves nothing."""
    verified = [r for r in manifest_references() if r.exists and r.verifies()]

    assert verified, "no referenced manifest verifies; the archive is empty"


def test_an_absent_file_reports_no_hash_rather_than_a_wrong_one() -> None:
    missing = ManifestReference(path="runs/nope.json", recorded_sha256="0" * 64)

    assert missing.actual_sha256() is None
    assert not missing.verifies()


def test_a_tampered_file_fails_verification() -> None:
    """Falsify the guard rather than trusting it.

    The check is only worth running if a changed byte breaks it.
    """
    present = next(r for r in manifest_references() if r.exists)
    tampered = present.file.read_bytes() + b" "

    assert hashlib.sha256(tampered).hexdigest() != present.recorded_sha256


def test_the_registry_is_where_it_is_expected() -> None:
    assert REGISTRY.name == "HYPOTHESES.md"
    assert REGISTRY.is_file()


@pytest.mark.parametrize("path", sorted(KNOWN_LOST))
def test_each_known_loss_names_what_survives(path: str) -> None:
    """A reader must not have to infer the extent of a loss from an absence."""
    assert "survives" in KNOWN_LOST[path]
