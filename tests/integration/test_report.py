"""The ingestion report's reads (S05-T8) on a tiny hand-built database: the counts, the chunk id
range, and the fingerprint's records.

Expected counts are worked out by hand from the rows below. Release windows are inclusive; a
version is valid at R when its window contains R.
"""

import hashlib
from datetime import UTC, datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.chunks import add_chunks
from orgknow.db.documents import add_alias, create_document
from orgknow.db.models import (
    Counts,
    NewChunk,
    NewVersion,
    StoredAlias,
    StoredChunk,
    StoredDocument,
    StoredVersion,
)
from orgknow.db.report import chunk_id_range, counts_by_release, counts_by_source_type
from orgknow.db.versions import close_version, insert_version
from orgknow.ingestion.report import database_report, fingerprint

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

PAGE = "web:/docs/a/"
KEP = "kep:1"
SHA = "0123456789abcdef0123456789abcdef01234567"
# Release dates (config/corpus_manifest.yaml) at 00:00 UTC.
D20 = datetime(2020, 12, 8, tzinfo=UTC)
D21 = datetime(2021, 4, 8, tzinfo=UTC)
D22 = datetime(2021, 8, 4, tzinfo=UTC)
PLUS_TWO = timezone(timedelta(hours=2))


def _version(document_id: int, content_hash: str, release: int, at: datetime) -> NewVersion:
    return NewVersion(
        document_id=document_id,
        content_hash=content_hash,
        source_path="content/en/docs/a.md",
        snapshot_repo="website",
        snapshot_ref=f"release-1.{release}",
        snapshot_sha=SHA,
        valid_from_release=release,
        valid_from_date=at,
        metadata={"weight": 2, "title": "A"},
    )


def _tiny_database(conn: Conn) -> list[int]:
    """The page: [20,20] with texts x, y; then [21, open] with x, z; one alias. The KEP: [22,
    open] with w. Returns the chunk ids."""
    page = create_document(conn, PAGE, "docs_page")
    add_alias(conn, page, "web:/docs/old-a/")
    # Stored at +02:00: the database keeps the instant, and the report prints it in UTC.
    v1 = insert_version(conn, _version(page, "1" * 64, 20, D20.astimezone(PLUS_TWO)))
    close_version(conn, v1, 20, D21)
    v2 = insert_version(conn, _version(page, "2" * 64, 21, D21))
    kep = create_document(conn, KEP, "kep")
    v3 = insert_version(conn, _version(kep, "3" * 64, 22, D22))
    ids = add_chunks(conn, v1, [NewChunk(ordinal=0, heading_path=[], text="x")])
    ids += add_chunks(conn, v1, [NewChunk(ordinal=1, heading_path=["Y"], text="y")])
    ids += add_chunks(conn, v2, [NewChunk(ordinal=0, heading_path=[], text="x")])
    ids += add_chunks(conn, v2, [NewChunk(ordinal=1, heading_path=["Z"], text="z")])
    ids += add_chunks(conn, v3, [NewChunk(ordinal=0, heading_path=[], text="w")])
    return ids


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()  # R13's definition of a chunk's hash


def test_counts_per_source_type_and_per_release(conn: Conn) -> None:
    _tiny_database(conn)

    # 4 page chunks hold 3 texts (x twice); the total row comes last.
    assert counts_by_source_type(conn) == [
        Counts(source_type="docs_page", documents=1, versions=2, chunks=4, texts=3),
        Counts(source_type="kep", documents=1, versions=1, chunks=1, texts=1),
        Counts(documents=2, versions=3, chunks=5, texts=4),
    ]
    by_release = counts_by_release(conn)
    # 1.20: the page's first version; 1.21: its second; from 1.22 the KEP too.
    assert by_release[:7] == [
        Counts(release=20, source_type="docs_page", documents=1, versions=1, chunks=2, texts=2),
        Counts(release=20, documents=1, versions=1, chunks=2, texts=2),
        Counts(release=21, source_type="docs_page", documents=1, versions=1, chunks=2, texts=2),
        Counts(release=21, documents=1, versions=1, chunks=2, texts=2),
        Counts(release=22, source_type="docs_page", documents=1, versions=1, chunks=2, texts=2),
        Counts(release=22, source_type="kep", documents=1, versions=1, chunks=1, texts=1),
        Counts(release=22, documents=2, versions=2, chunks=3, texts=3),
    ]
    # 1.23 to 1.37 are as 1.22: 2 + 2 + 16 x 3 rows.
    assert len(by_release) == 52
    assert by_release[-1] == Counts(release=37, documents=2, versions=2, chunks=3, texts=3)


def test_the_fingerprint_reads_every_stored_value_except_generated_ids(conn: Conn) -> None:
    ids = _tiny_database(conn)
    # The same records, typed by hand: ids nowhere, the version dates in UTC.
    page_version = {
        "canonical_id": PAGE,
        "source_path": "content/en/docs/a.md",
        "snapshot_repo": "website",
        "snapshot_sha": SHA,
        "metadata": {"title": "A", "weight": 2},
    }
    by_hand = fingerprint(
        [
            StoredDocument(canonical_id=PAGE, source_type="docs_page"),
            StoredDocument(canonical_id=KEP, source_type="kep"),
        ],
        [StoredAlias(canonical_id=PAGE, alias="web:/docs/old-a/")],
        [
            StoredVersion(
                **page_version,
                content_hash="1" * 64,
                snapshot_ref="release-1.20",
                valid_from_release=20,
                valid_until_release=20,
                valid_from_date=D20,
                valid_until_date=D21,
            ),
            StoredVersion(
                **page_version,
                content_hash="2" * 64,
                snapshot_ref="release-1.21",
                valid_from_release=21,
                valid_from_date=D21,
            ),
            StoredVersion(
                **(page_version | {"canonical_id": KEP}),
                content_hash="3" * 64,
                snapshot_ref="release-1.22",
                valid_from_release=22,
                valid_from_date=D22,
            ),
        ],
        [
            StoredChunk(
                canonical_id=PAGE,
                valid_from_date=D20,
                ordinal=0,
                heading_path=[],
                content_hash=_sha256("x"),
            ),
            StoredChunk(
                canonical_id=PAGE,
                valid_from_date=D20,
                ordinal=1,
                heading_path=["Y"],
                content_hash=_sha256("y"),
            ),
            StoredChunk(
                canonical_id=PAGE,
                valid_from_date=D21,
                ordinal=0,
                heading_path=[],
                content_hash=_sha256("x"),
            ),
            StoredChunk(
                canonical_id=PAGE,
                valid_from_date=D21,
                ordinal=1,
                heading_path=["Z"],
                content_hash=_sha256("z"),
            ),
            StoredChunk(
                canonical_id=KEP,
                valid_from_date=D22,
                ordinal=0,
                heading_path=[],
                content_hash=_sha256("w"),
            ),
        ],
    )

    report = database_report(conn)

    assert report[-1] == f"Fingerprint: sha256:{by_hand}"
    assert f"Chunk ids: {min(ids)}\N{EN DASH}{max(ids)}" in report
    assert chunk_id_range(conn) == (min(ids), max(ids))
    assert "Aliases: 1" in report


def test_an_empty_database_reports_zeros_and_the_empty_fingerprint(conn: Conn) -> None:
    report = database_report(conn)

    # Columns: source_type (11 wide), documents (9), versions (8), chunks (6), texts (5).
    assert "  total                0         0       0      0" in report
    # Columns: release (7 wide), versions (8), chunks (6), texts (5); no source type columns.
    assert "  1.20            0       0      0" in report
    assert "Aliases: 0" in report
    assert "Chunk ids: none" in report
    # `printf '' | sha256sum`
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert report[-1] == f"Fingerprint: sha256:{empty}"
