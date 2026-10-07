"""Pure parts of `make ingest`: the releases check, and a document from its chain of files.

Expected values are typed by hand from config/corpus_manifest.yaml (release dates, strip lists).
"""

from datetime import UTC, date, datetime
from pathlib import Path

from orgknow.db.models import Release
from orgknow.ingestion.ingest import document_from_chain, release_problems
from orgknow.ingestion.manifest import ReleaseGroup, Snapshot, load_normalization, load_releases

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "config" / "corpus_manifest.yaml"

R29 = Release(version="1.29", release_date=date(2023, 12, 13), end_of_life_date=date(2025, 2, 28))
R30 = Release(version="1.30", release_date=date(2024, 4, 17), end_of_life_date=date(2025, 7, 15))


def test_a_table_equal_to_the_manifest_has_no_problems() -> None:
    assert release_problems([R29, R30], [R29, R30]) == []


def test_extra_rows_in_the_table_are_not_a_problem() -> None:
    r19 = Release(
        version="1.19", release_date=date(2020, 8, 26), end_of_life_date=date(2021, 10, 28)
    )

    assert release_problems([R30], [r19, R29, R30]) == []


def test_a_release_missing_from_the_table_is_named() -> None:
    assert release_problems([R29, R30], [R29]) == ["1.30 is missing"]


def test_a_release_stored_with_another_date_is_named() -> None:
    redated = R30.model_copy(update={"release_date": date(2024, 4, 18)})

    assert release_problems([R29, R30], [R29, redated]) == [
        "1.30 differs (table: 2024-04-18 to 2025-07-15; manifest: 2024-04-17 to 2025-07-15)"
    ]


def test_an_end_of_life_date_is_compared_too() -> None:
    # A planned end of life that slipped in the manifest, while the table still has the old one.
    stale = R30.model_copy(update={"end_of_life_date": date(2025, 6, 1)})

    assert release_problems([R30], [stale]) == [
        "1.30 differs (table: 2024-04-17 to 2025-06-01; manifest: 2024-04-17 to 2025-07-15)"
    ]


# --- A document from its chain of files (S05-T1) -----------------------------------------------

NOTES_PATH = "content/en/docs/setup/release/notes.md"
# Real lines 1-18 of the 1.20 release notes; its front matter has a `card` block.
NOTES = (ROOT / "tests/fixtures/website_s05/release-notes/excerpt-1.20.md").read_bytes()
RECORDS = ReleaseGroup(
    "release_record",
    "website",
    ("content/en/docs/setup/release/",),
    (
        Snapshot(20, "release-1.20", "2886f437c434ab156f4306b67adedd162bb25c2d"),
        Snapshot(21, "release-1.21", "7ed77d72f3314a6b144448b473b94e7845973fdc"),
    ),
)
D20 = datetime(2020, 12, 8, tzinfo=UTC)  # 1.20's release date, 00:00 UTC
D21 = datetime(2021, 4, 8, tzinfo=UTC)


def _windows(chain_at_21: bytes) -> list[tuple[object, ...]]:
    document = document_from_chain(
        RECORDS,
        [(NOTES_PATH, NOTES), (NOTES_PATH, chain_at_21)],
        load_normalization(MANIFEST),
        load_releases(MANIFEST),
    )
    assert (document.canonical_id, document.source_type) == (
        "web:/docs/setup/release/notes/",
        "release_record",
    )
    return [
        (v.valid_from_release, v.valid_until_release, v.valid_from_date, v.valid_until_date)
        for v in document.versions
    ]


def test_a_release_record_card_change_is_not_a_new_version() -> None:
    card_edit = NOTES.replace(
        b"  name: release-notes\n  weight: 20\n", b"  name: release-notes\n  weight: 30\n"
    )
    assert card_edit != NOTES

    # `card` is on the release_record strip list (not on docs_page's), so the hash is unchanged.
    # The file is older than 1.20, but its first version starts at the scope's first release.
    assert _windows(card_edit) == [(20, None, D20, None)]


def test_a_release_record_body_change_is_a_new_version() -> None:
    body_edit = NOTES + b"\nA new paragraph.\n"

    assert _windows(body_edit) == [(20, 20, D20, D21), (21, None, D21, None)]
