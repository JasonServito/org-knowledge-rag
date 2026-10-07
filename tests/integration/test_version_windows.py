"""Both edges of each window, on two real documents.

Release windows are inclusive `[from, until]`; date windows are half-open `[from, until)`.
"""

from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.documents import add_alias, create_document, resolve_document
from orgknow.db.models import NewVersion, Version
from orgknow.db.versions import close_version, insert_version, version_at_time, versions_at_release

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

# Typed by hand: 40 lowercase hex characters, and one 64-character content hash per version.
SHA = "0123456789abcdef0123456789abcdef01234567"
HASH_1 = "1111111111111111111111111111111111111111111111111111111111111111"
HASH_2 = "2222222222222222222222222222222222222222222222222222222222222222"
HASH_3 = "3333333333333333333333333333333333333333333333333333333333333333"
HASH_4 = "4444444444444444444444444444444444444444444444444444444444444444"
HASH_5 = "5555555555555555555555555555555555555555555555555555555555555555"

# --- The Pod Security Policy page --------------------------------------------------------------
# From the corpus trace in the S03-R1 sitting: its content changes at 1.20, 1.21, 1.23, 1.24 and
# 1.25, and it moves at 1.23 (redirect in static/_redirects). The first URL is its canonical id.
PSP = "web:/docs/concepts/policy/pod-security-policy/"
PSP_ALIAS = "web:/docs/concepts/security/pod-security-policy/"
POLICY_PATH = "content/en/docs/concepts/policy/pod-security-policy.md"
SECURITY_PATH = "content/en/docs/concepts/security/pod-security-policy.md"

# Release dates (config/corpus_manifest.yaml) at 00:00 UTC.
D20 = datetime(2020, 12, 8, tzinfo=UTC)
D21 = datetime(2021, 4, 8, tzinfo=UTC)
D23 = datetime(2021, 12, 7, tzinfo=UTC)
D24 = datetime(2022, 5, 3, tzinfo=UTC)
D25 = datetime(2022, 8, 23, tzinfo=UTC)


def _psp_version(
    document_id: int, from_release: int, from_date: datetime, source_path: str, content_hash: str
) -> NewVersion:
    return NewVersion(
        document_id=document_id,
        content_hash=content_hash,
        source_path=source_path,
        snapshot_repo="website",
        snapshot_ref=f"release-1.{from_release}",
        snapshot_sha=SHA,
        valid_from_release=from_release,
        valid_from_date=from_date,
    )


@pytest.fixture
def psp(conn: Conn) -> tuple[int, list[int]]:
    """The PSP page's document id and its 5 version ids, oldest first.

    Release windows [20,20], [21,22], [23,23], [24,24], [25, open], built by close-then-insert.
    """
    document_id = create_document(conn, PSP, "docs_page")
    add_alias(conn, document_id, PSP_ALIAS)

    v1 = insert_version(conn, _psp_version(document_id, 20, D20, POLICY_PATH, HASH_1))
    close_version(conn, v1, 20, D21)
    v2 = insert_version(conn, _psp_version(document_id, 21, D21, POLICY_PATH, HASH_2))
    close_version(conn, v2, 22, D23)
    v3 = insert_version(conn, _psp_version(document_id, 23, D23, SECURITY_PATH, HASH_3))
    close_version(conn, v3, 23, D24)
    v4 = insert_version(conn, _psp_version(document_id, 24, D24, SECURITY_PATH, HASH_4))
    close_version(conn, v4, 24, D25)
    v5 = insert_version(conn, _psp_version(document_id, 25, D25, SECURITY_PATH, HASH_5))
    return document_id, [v1, v2, v3, v4, v5]


def test_psp_alias_and_canonical_id_resolve_to_one_document(
    conn: Conn, psp: tuple[int, list[int]]
) -> None:
    document_id, _ = psp

    assert resolve_document(conn, PSP) == document_id
    assert resolve_document(conn, PSP_ALIAS) == document_id
    assert resolve_document(conn, "web:/docs/concepts/policy/no-such-page/") is None


def test_psp_release_22_is_v2_only(conn: Conn, psp: tuple[int, list[int]]) -> None:
    # 22 is v2's inclusive `until`.
    document_id, ids = psp

    assert [v.id for v in versions_at_release(conn, document_id, 22)] == [ids[1]]


def test_psp_release_23_is_v3_only(conn: Conn, psp: tuple[int, list[int]]) -> None:
    # 23 is v3's `from`, one past v2's `until`.
    document_id, ids = psp

    assert [v.id for v in versions_at_release(conn, document_id, 23)] == [ids[2]]


def test_psp_on_the_1_23_release_date_is_v3(conn: Conn, psp: tuple[int, list[int]]) -> None:
    # v2's `until` and v3's `from` are both 1.23's release date: it belongs to v3.
    document_id, ids = psp

    found = version_at_time(conn, document_id, D23)

    assert found == Version(
        id=ids[2],
        document_id=document_id,
        content_hash=HASH_3,
        source_path=SECURITY_PATH,
        snapshot_repo="website",
        snapshot_ref="release-1.23",
        snapshot_sha=SHA,
        valid_from_release=23,
        valid_until_release=23,
        valid_from_date=D23,
        valid_until_date=D24,
    )


def test_psp_one_microsecond_before_1_23_is_v2(conn: Conn, psp: tuple[int, list[int]]) -> None:
    document_id, ids = psp
    just_before = datetime(2021, 12, 6, 23, 59, 59, 999999, tzinfo=UTC)

    found = version_at_time(conn, document_id, just_before)

    assert found is not None
    assert found.id == ids[1]


# --- The v1.30 release blog post ---------------------------------------------------------------
# Two edits 5 minutes apart on 2024-04-19 (website `main` merges 78f7ce0 and 8774faf), at their
# committer times in UTC (`TZ=UTC git log --date=iso-strict-local`). Both fall in release 1.30's
# cycle.
POST = "web:/blog/2024/04/17/kubernetes-v1-30-release/"
POST_PATH = "content/en/blog/_posts/2024-04-17-kubernetes-1.30.md"
EDIT_1 = datetime(2024, 4, 19, 20, 56, 34, tzinfo=UTC)
EDIT_2 = datetime(2024, 4, 19, 21, 1, 40, tzinfo=UTC)


def _post_version(document_id: int, from_date: datetime, content_hash: str) -> NewVersion:
    return NewVersion(
        document_id=document_id,
        content_hash=content_hash,
        source_path=POST_PATH,
        snapshot_repo="website",
        snapshot_ref="main",
        snapshot_sha=SHA,
        valid_from_release=30,
        valid_from_date=from_date,
    )


@pytest.fixture
def post(conn: Conn) -> tuple[int, list[int]]:
    """The post's document id and its 2 version ids: [30, 30] then [30, open]."""
    document_id = create_document(conn, POST, "blog_post")
    v1 = insert_version(conn, _post_version(document_id, EDIT_1, HASH_1))
    close_version(conn, v1, 30, EDIT_2)
    v2 = insert_version(conn, _post_version(document_id, EDIT_2, HASH_2))
    return document_id, [v1, v2]


def test_blog_post_edit_time_starts_the_new_version(
    conn: Conn, post: tuple[int, list[int]]
) -> None:
    document_id, ids = post

    between = version_at_time(conn, document_id, datetime(2024, 4, 19, 20, 58, tzinfo=UTC))
    at_edit = version_at_time(conn, document_id, EDIT_2)

    assert between is not None
    assert between.id == ids[0]
    assert at_edit is not None
    assert at_edit.id == ids[1]


def test_blog_post_versions_share_release_30(conn: Conn, post: tuple[int, list[int]]) -> None:
    document_id, ids = post

    assert [v.id for v in versions_at_release(conn, document_id, 30)] == ids
