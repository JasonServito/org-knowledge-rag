"""Each rule in docs/domain-model.md ("Rules") broken on purpose, then the cases it must allow.

Every test writes through `conn`, so nothing is committed. An expected database error runs in
a nested `conn.transaction()` (a savepoint); the test checks the error class and the
constraint name from migrations 0002 and 0003. A code rule (R3, R10) raises ValueError instead.
"""

from datetime import UTC, date, datetime
from typing import Any

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import TupleRow

from orgknow.db.chunks import add_chunks, add_embedding
from orgknow.db.documents import add_alias, create_document, resolve_document
from orgknow.db.models import NewChunk, NewVersion, Release
from orgknow.db.releases import upsert_releases
from orgknow.db.versions import close_version, insert_version, version_at_time, versions_at_release

Conn = psycopg.Connection[TupleRow]

# Version rows reference releases, so every test here gets the manifest's releases.
pytestmark = pytest.mark.usefixtures("seeded_releases")

# Typed by hand: 64 and 40 lowercase hex characters.
HASH_A = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
HASH_B = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
SHA = "0123456789abcdef0123456789abcdef01234567"

# Release dates of 1.30-1.33 (config/corpus_manifest.yaml) at 00:00 UTC.
D30 = datetime(2024, 4, 17, tzinfo=UTC)
D31 = datetime(2024, 8, 13, tzinfo=UTC)
D32 = datetime(2024, 12, 11, tzinfo=UTC)
D33 = datetime(2025, 4, 23, tzinfo=UTC)


def _document(conn: Conn, canonical_id: str = "web:/test/page/") -> int:
    return create_document(conn, canonical_id, "docs_page")


def _version(document_id: int, **changes: Any) -> NewVersion:
    """A valid docs version, current since 1.30. `changes` overrides any field."""
    fields: dict[str, Any] = {
        "document_id": document_id,
        "content_hash": HASH_A,
        "source_path": "content/en/docs/test/page.md",
        "snapshot_repo": "website",
        "snapshot_ref": "release-1.30",
        "snapshot_sha": SHA,
        "valid_from_release": 30,
        "valid_from_date": D30,
    }
    return NewVersion(**(fields | changes))


# --- R1-R4: identity -------------------------------------------------------------------------


def test_r1_canonical_id_is_unique(conn: Conn) -> None:
    _document(conn)

    with pytest.raises(errors.UniqueViolation) as exc_info, conn.transaction():
        _document(conn)

    assert exc_info.value.diag.constraint_name == "documents_canonical_id_key"


def test_r2_canonical_id_needs_a_known_prefix(conn: Conn) -> None:
    # `docs:` was ADR-002's docs prefix before the S02 spike changed it to `web:`.
    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        create_document(conn, "docs:concepts/security/pod-security-policy", "docs_page")

    assert exc_info.value.diag.constraint_name == "documents_canonical_id_check"


def test_r2_alias_needs_a_known_prefix(conn: Conn) -> None:
    document_id = _document(conn)

    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        add_alias(conn, document_id, "docs:test/old-page")

    assert exc_info.value.diag.constraint_name == "document_aliases_alias_check"


def test_r3_alias_is_unique(conn: Conn) -> None:
    first = _document(conn, "web:/test/page-a/")
    second = _document(conn, "web:/test/page-b/")
    add_alias(conn, first, "web:/test/old-page/")

    with pytest.raises(errors.UniqueViolation) as exc_info, conn.transaction():
        add_alias(conn, second, "web:/test/old-page/")

    assert exc_info.value.diag.constraint_name == "document_aliases_pkey"
    assert resolve_document(conn, "web:/test/old-page/") == first


def test_r3_alias_cannot_equal_a_canonical_id(conn: Conn) -> None:
    first = _document(conn, "web:/test/page-a/")
    second = _document(conn, "web:/test/page-b/")

    with pytest.raises(ValueError, match="already a canonical_id"), conn.transaction():
        add_alias(conn, second, "web:/test/page-a/")

    assert resolve_document(conn, "web:/test/page-a/") == first


def test_r3_canonical_id_cannot_equal_an_alias(conn: Conn) -> None:
    first = _document(conn, "web:/test/page-a/")
    add_alias(conn, first, "web:/test/old-page/")

    with pytest.raises(ValueError, match="already an alias"), conn.transaction():
        _document(conn, "web:/test/old-page/")

    assert resolve_document(conn, "web:/test/old-page/") == first


def test_r4_source_type_must_be_known(conn: Conn) -> None:
    # `discussion` is an ADR-003 source type, but it arrives only with Phase 2.
    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        create_document(conn, "web:/test/page/", "discussion")

    assert exc_info.value.diag.constraint_name == "documents_source_type_check"


# --- R5-R11: versions and their windows ----------------------------------------------------------


def test_r5_date_window_cannot_be_empty(conn: Conn) -> None:
    document_id = _document(conn)

    # [D30, D30) contains no instant.
    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        insert_version(conn, _version(document_id, valid_until_release=30, valid_until_date=D30))

    assert exc_info.value.diag.constraint_name == "document_versions_date_window_check"


def test_r6_release_window_must_be_ordered(conn: Conn) -> None:
    document_id = _document(conn)

    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        insert_version(conn, _version(document_id, valid_from_release=31, valid_until_release=30))

    assert exc_info.value.diag.constraint_name == "document_versions_release_window_check"


@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        # 1.19 is before the manifest's first release; 1.99 is past its last.
        ({"valid_from_release": 19}, "document_versions_valid_from_release_fkey"),
        ({"valid_until_release": 99}, "document_versions_valid_until_release_fkey"),
    ],
)
def test_r6_release_bounds_must_be_real_releases(
    conn: Conn, changes: dict[str, int], constraint: str
) -> None:
    document_id = _document(conn)

    with pytest.raises(errors.ForeignKeyViolation) as exc_info, conn.transaction():
        insert_version(conn, _version(document_id, **changes))

    assert exc_info.value.diag.constraint_name == constraint


def test_r7_closed_date_window_needs_a_last_release(conn: Conn) -> None:
    document_id = _document(conn)

    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        insert_version(conn, _version(document_id, valid_until_date=D31))

    assert exc_info.value.diag.constraint_name == "document_versions_closed_window_check"


def test_r8_date_windows_cannot_overlap(conn: Conn) -> None:
    document_id = _document(conn)
    # [D30, D32), then [D31, D33): both closed, and the second starts inside the first.
    insert_version(conn, _version(document_id, valid_until_release=31, valid_until_date=D32))
    overlapping = _version(
        document_id,
        content_hash=HASH_B,
        valid_from_release=31,
        valid_from_date=D31,
        valid_until_release=32,
        valid_until_date=D33,
    )

    with pytest.raises(errors.ExclusionViolation) as exc_info, conn.transaction():
        insert_version(conn, overlapping)

    assert exc_info.value.diag.constraint_name == "document_versions_date_window_excl"


def test_r9_only_one_open_version(conn: Conn) -> None:
    # Also the wrong supersede order: the new version is inserted before the old one is closed.
    document_id = _document(conn)
    insert_version(conn, _version(document_id))
    newer = _version(document_id, content_hash=HASH_B, valid_from_release=31, valid_from_date=D31)

    with pytest.raises(errors.ExclusionViolation) as exc_info, conn.transaction():
        insert_version(conn, newer)

    assert exc_info.value.diag.constraint_name == "document_versions_date_window_excl"


def test_r10_cannot_close_a_closed_version(conn: Conn) -> None:
    document_id = _document(conn)
    version_id = insert_version(conn, _version(document_id))
    close_version(conn, version_id, 30, D31)

    with pytest.raises(ValueError, match="not open"), conn.transaction():
        close_version(conn, version_id, 31, D32)

    # The first close still stands.
    [version] = versions_at_release(conn, document_id, 30)
    assert (version.valid_until_release, version.valid_until_date) == (30, D31)


def test_r10_cannot_close_a_missing_version(conn: Conn) -> None:
    # Identity ids start at 1, so -1 never exists.
    with pytest.raises(ValueError, match="not open"), conn.transaction():
        close_version(conn, -1, 30, D31)


@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        # Each hash in the other's place: 40 hex is too short, 64 hex too long.
        ({"content_hash": SHA}, "document_versions_content_hash_check"),
        ({"snapshot_sha": HASH_A}, "document_versions_snapshot_sha_check"),
    ],
)
def test_r11_hashes_must_be_well_formed(
    conn: Conn, changes: dict[str, str], constraint: str
) -> None:
    document_id = _document(conn)

    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        insert_version(conn, _version(document_id, **changes))

    assert exc_info.value.diag.constraint_name == constraint


# --- R12-R14: chunks and embeddings -----------------------------------------------------------


def test_r12_chunk_ordinal_is_unique_in_its_version(conn: Conn) -> None:
    version_id = insert_version(conn, _version(_document(conn)))
    add_chunks(conn, version_id, [NewChunk(ordinal=0, heading_path=[], text="first")])

    with pytest.raises(errors.UniqueViolation) as exc_info, conn.transaction():
        add_chunks(conn, version_id, [NewChunk(ordinal=0, heading_path=[], text="second")])

    assert exc_info.value.diag.constraint_name == "chunks_document_version_id_ordinal_key"


def test_r13_chunk_hash_is_the_sha256_of_its_text(conn: Conn) -> None:
    version_id = insert_version(conn, _version(_document(conn)))

    [chunk_id] = add_chunks(
        conn, version_id, [NewChunk(ordinal=0, heading_path=["Overview"], text="abc")]
    )

    row = conn.execute("SELECT content_hash FROM chunks WHERE id = %s", (chunk_id,)).fetchone()
    # FIPS 180-2, appendix B.1: the SHA-256 of "abc".
    assert row == ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",)


def test_r14_one_vector_per_text_and_model(conn: Conn) -> None:
    # No chunk needed: vectors are keyed by text hash, with no foreign key (migration 0003).
    add_embedding(conn, HASH_A, "model-a", [0.5] * 1024)
    # Allowed: the same text under a second model (an ablation doesn't overwrite).
    add_embedding(conn, HASH_A, "model-b", [0.5] * 1024)

    with pytest.raises(errors.UniqueViolation) as exc_info, conn.transaction():
        add_embedding(conn, HASH_A, "model-a", [0.25] * 1024)

    assert exc_info.value.diag.constraint_name == "embeddings_pkey"


def test_r14_vector_has_exactly_1024_numbers(conn: Conn) -> None:
    with (
        pytest.raises(errors.DataException, match="expected 1024 dimensions") as exc_info,
        conn.transaction(),
    ):
        add_embedding(conn, HASH_A, "model-a", [0.5] * 1023)

    # Exactly DataException (SQLSTATE 22000), not one of its subclasses.
    assert exc_info.type is errors.DataException


def test_r14_hash_must_be_well_formed(conn: Conn) -> None:
    # 40 hex characters: a git SHA, not a SHA-256.
    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        add_embedding(conn, SHA, "model-a", [0.5] * 1024)

    assert exc_info.value.diag.constraint_name == "embeddings_content_hash_check"


# --- R15: releases -----------------------------------------------------------------------------


def test_r15_version_must_match_minor(conn: Conn) -> None:
    # Direct SQL: the Release model derives `minor` from `version`, so upsert_releases can't
    # send a mismatched pair.
    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        conn.execute(
            "INSERT INTO releases (minor, version, release_date, end_of_life_date) "
            "VALUES (99, '1.98', '2099-01-01', '2100-01-01')"
        )

    assert exc_info.value.diag.constraint_name == "releases_version_check"


def test_r15_end_of_life_after_release(conn: Conn) -> None:
    bad = Release(version="1.99", release_date=date(2099, 1, 1), end_of_life_date=date(2098, 12, 1))

    with pytest.raises(errors.CheckViolation) as exc_info, conn.transaction():
        upsert_releases(conn, [bad])

    assert exc_info.value.diag.constraint_name == "releases_end_of_life_date_check"


def test_r15_release_dates_are_unique(conn: Conn) -> None:
    # 2026-08-26 is 1.37's release date in the manifest.
    clash = Release(
        version="1.99", release_date=date(2026, 8, 26), end_of_life_date=date(2099, 1, 1)
    )

    with pytest.raises(errors.UniqueViolation) as exc_info, conn.transaction():
        upsert_releases(conn, [clash])

    assert exc_info.value.diag.constraint_name == "releases_release_date_key"


# --- Allowed cases (ADR-002 D2/D3) -------------------------------------------------------------


def test_allowed_close_then_insert_with_touching_windows(conn: Conn) -> None:
    # The right supersede order. The old window's `until` equals the new window's `from`.
    document_id = _document(conn)
    old = insert_version(conn, _version(document_id))
    close_version(conn, old, 30, D31)

    new = insert_version(
        conn, _version(document_id, content_hash=HASH_B, valid_from_release=31, valid_from_date=D31)
    )

    found = version_at_time(conn, document_id, D31)
    assert found is not None
    assert found.id == new


def test_allowed_gap_between_versions(conn: Conn) -> None:
    # The page is removed in 1.31 and re-added in 1.32.
    document_id = _document(conn)
    insert_version(conn, _version(document_id, valid_until_release=30, valid_until_date=D31))

    insert_version(conn, _version(document_id, valid_from_release=32, valid_from_date=D32))

    assert version_at_time(conn, document_id, datetime(2024, 10, 1, tzinfo=UTC)) is None
    assert versions_at_release(conn, document_id, 31) == []


def test_allowed_same_content_again(conn: Conn) -> None:
    # A -> B -> A: the third version repeats the first one's content, and is still a new version.
    document_id = _document(conn)
    insert_version(conn, _version(document_id, valid_until_release=30, valid_until_date=D31))
    insert_version(
        conn,
        _version(
            document_id,
            content_hash=HASH_B,
            valid_from_release=31,
            valid_from_date=D31,
            valid_until_release=31,
            valid_until_date=D32,
        ),
    )

    insert_version(conn, _version(document_id, valid_from_release=32, valid_from_date=D32))

    hashes = [versions_at_release(conn, document_id, r)[0].content_hash for r in (30, 31, 32)]
    assert hashes == [HASH_A, HASH_B, HASH_A]


def test_allowed_changelog_versions_share_one_release(conn: Conn) -> None:
    # CHANGELOG-1.30 always speaks for [30, 30]. A later edit gives a second version, dated by
    # the ingestion snapshot that first saw it (ADR-002 D1, D3).
    document_id = create_document(conn, "changelog:1.30", "release_record")
    common: dict[str, Any] = {
        "source_path": "CHANGELOG/CHANGELOG-1.30.md",
        "snapshot_repo": "kubernetes",
        "snapshot_ref": "master",
        "valid_from_release": 30,
        "valid_until_release": 30,
    }
    first = insert_version(
        conn, _version(document_id, **common, valid_from_date=datetime(2026, 9, 1, tzinfo=UTC))
    )
    close_version(conn, first, 30, datetime(2026, 10, 1, tzinfo=UTC))

    second = insert_version(
        conn,
        _version(
            document_id,
            **common,
            content_hash=HASH_B,
            valid_from_date=datetime(2026, 10, 1, tzinfo=UTC),
        ),
    )

    assert [v.id for v in versions_at_release(conn, document_id, 30)] == [first, second]


# --- Timezone-aware datetimes only (domain model, "Data-access functions") --------------------


def test_naive_datetimes_are_rejected(conn: Conn) -> None:
    # The model refuses them for insert_version (unit test); these two take a bare datetime.
    document_id = _document(conn)
    version_id = insert_version(conn, _version(document_id))

    with pytest.raises(ValueError, match="timezone-aware"):
        close_version(conn, version_id, 30, datetime(2024, 8, 13))
    with pytest.raises(ValueError, match="timezone-aware"):
        version_at_time(conn, document_id, datetime(2024, 8, 13))
