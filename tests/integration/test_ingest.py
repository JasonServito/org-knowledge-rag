"""Ingestion end to end on tiny git repos built from real corpus files, into the test database.

The website repo gets one commit per release 1.24 -> 1.37 holding the real pages of that
release (tests/fixtures/website_s04/<page>/<first release with these bytes>.md, copied from
kubernetes/website at the locked SHAs; CC BY 4.0). overview.md is deleted at 1.29, as in the
corpus. The enhancements repo replays KEP-2579's real commit times around its real kep.yaml files.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.documents import resolve_document
from orgknow.db.versions import list_versions
from orgknow.ingestion.ingest import Summary, ingest
from orgknow.ingestion.manifest import Scope, Snapshot, load_normalization, load_releases

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
RELEASES = load_releases(ROOT / "config" / "corpus_manifest.yaml")
STRIP = load_normalization(ROOT / "config" / "corpus_manifest.yaml")

SECURITY = "content/en/docs/concepts/security/"
PSP_PATH = SECURITY + "pod-security-policy.md"
PSA_PATH = SECURITY + "pod-security-admission.md"
OVERVIEW_PATH = SECURITY + "overview.md"
RBAC_PATH = "content/en/docs/reference/access-authn-authz/rbac.md"
PAGES = {
    PSP_PATH: "pod-security-policy",
    PSA_PATH: "pod-security-admission",
    OVERVIEW_PATH: "overview",
}
KEP_DIR = "keps/sig-auth/2579-psp-replacement/"

PSP = "web:/docs/concepts/security/pod-security-policy/"
PSA = "web:/docs/concepts/security/pod-security-admission/"
OVERVIEW = "web:/docs/concepts/security/overview/"
RBAC = "web:/docs/reference/access-authn-authz/rbac/"

# Release dates (config/corpus_manifest.yaml) at 00:00 UTC.
D24 = datetime(2022, 5, 3, tzinfo=UTC)
D25 = datetime(2022, 8, 23, tzinfo=UTC)
D26 = datetime(2022, 12, 8, tzinfo=UTC)
D27 = datetime(2023, 4, 11, tzinfo=UTC)
D28 = datetime(2023, 8, 15, tzinfo=UTC)
D29 = datetime(2023, 12, 13, tzinfo=UTC)
D30 = datetime(2024, 4, 17, tzinfo=UTC)


def _page_at(folder: str, minor: int) -> bytes:
    """The fixture holding the page's bytes at release 1.<minor>: the latest one at or before."""
    files = {
        int(p.stem.removeprefix("1.")): p for p in (FIXTURES / "website_s04" / folder).iterdir()
    }
    return files[max(m for m in files if m <= minor)].read_bytes()


def _website(make_git_repo: Callable[[str], Any]) -> tuple[Any, list[Snapshot]]:
    repo = make_git_repo("website")
    rbac = (FIXTURES / "website_s04" / "rbac" / "excerpt-1.37.md").read_bytes()
    snapshots = []
    for minor in range(24, 38):
        files: dict[str, bytes | None] = {RBAC_PATH: rbac}
        for path, folder in PAGES.items():
            if path != OVERVIEW_PATH or minor < 29:
                files[path] = _page_at(folder, minor)
        if minor == 29:
            files[OVERVIEW_PATH] = None  # removed at 1.29
        snapshots.append(Snapshot(minor, f"release-1.{minor}", repo.commit(files)))
    return repo, snapshots


def _enhancements(make_git_repo: Callable[[str], Any]) -> list[Snapshot]:
    repo = make_git_repo("enhancements")
    kep_yaml = FIXTURES / "kep_2579"
    readme, kep = f"{KEP_DIR}README.md", f"{KEP_DIR}kep.yaml"
    before = repo.commit({"README.md": b"# Enhancements\n"}, when="2021-04-01T00:00:00+00:00")
    # Real committer times of 18948fdb and 182464a6, then of 9f14627a and 313ad8b5.
    first = (kep_yaml / "1.22.kep.yaml").read_bytes()
    repo.commit({readme: b"# KEP-2579\n", kep: first}, when="2021-05-11T13:42:01-07:00")
    alpha = repo.commit({readme: b"# KEP-2579\nfix typo\n"}, when="2021-05-11T13:46:27-07:00")
    repo.commit({readme: b"# KEP-2579\nimplemented\n"}, when="2022-08-31T15:51:14-04:00")
    last = (kep_yaml / "1.26.kep.yaml").read_bytes()
    head = repo.commit({kep: last}, when="2022-09-22T10:28:05+02:00")
    return [
        Snapshot(21, "master", before),
        Snapshot(22, "master", alpha),
        Snapshot(None, "master", head),
    ]


def _scope(docs_snapshots: list[Snapshot], kep_snapshots: list[Snapshot]) -> Scope:
    docs_paths = (SECURITY, RBAC_PATH)
    keps = ((2579, KEP_DIR),)
    return Scope(
        "test",
        "website",
        docs_paths,
        tuple(docs_snapshots),
        "enhancements",
        keps,
        tuple(kep_snapshots),
    )


def _ingest(conn: Conn, tmp_path: Path, scope: Scope) -> Summary:
    return ingest(conn, scope, tmp_path, RELEASES, STRIP, {"GA": "stable"}, 512)


def _windows(conn: Conn, canonical_id: str) -> list[tuple[Any, ...]]:
    document_id = resolve_document(conn, canonical_id)
    assert document_id is not None
    return [
        (v.valid_from_release, v.valid_until_release, v.valid_from_date, v.valid_until_date)
        for v in list_versions(conn, document_id)
    ]


@pytest.fixture
def repos(make_git_repo: Callable[[str], Any]) -> tuple[Any, list[Snapshot], list[Snapshot]]:
    website, docs_snapshots = _website(make_git_repo)
    return website, docs_snapshots, _enhancements(make_git_repo)


def test_docs_windows_on_real_files(conn: Conn, tmp_path: Path, repos: Any) -> None:
    _, docs_snapshots, kep_snapshots = repos

    summary = _ingest(conn, tmp_path, _scope(docs_snapshots, kep_snapshots))

    assert summary.failures == []
    # Expected windows from git and the spike normalizer (S04-R1 sitting). Release windows are
    # inclusive; date bounds are release dates at 00:00Z, `until` exclusive.
    assert _windows(conn, PSP) == [(24, 24, D24, D25), (25, None, D25, None)]
    assert _windows(conn, PSA) == [
        (24, 24, D24, D25),
        (25, 25, D25, D26),
        (26, 27, D26, D28),
        (28, 29, D28, D30),
        (30, None, D30, None),
    ]
    # Raw bytes change at 1.25, 1.27 and 1.28; 1.27 -> 1.28 normalizes equal. Removed at 1.29.
    assert _windows(conn, OVERVIEW) == [
        (24, 24, D24, D25),
        (25, 26, D25, D27),
        (27, 28, D27, D29),
    ]
    psp_id = resolve_document(conn, PSP)
    assert psp_id is not None
    first = list_versions(conn, psp_id)[0]
    assert (first.source_path, first.snapshot_repo, first.snapshot_ref) == (
        PSP_PATH,
        "website",
        "release-1.24",
    )
    assert first.snapshot_sha == docs_snapshots[0].sha
    assert first.metadata["title"] == "Pod Security Policies"
    assert (first.claimed_status, first.claimed_stage) == (None, None)  # claims: KEPs only


def test_the_alias_resolves_to_the_rbac_page(conn: Conn, tmp_path: Path, repos: Any) -> None:
    _, docs_snapshots, kep_snapshots = repos

    _ingest(conn, tmp_path, _scope(docs_snapshots, kep_snapshots))

    # rbac.md front matter: `aliases: [/rbac/]`.
    assert resolve_document(conn, "web:/rbac/") == resolve_document(conn, RBAC)
    assert resolve_document(conn, RBAC) is not None


def test_kep_windows_from_git_commit_times(conn: Conn, tmp_path: Path, repos: Any) -> None:
    _, docs_snapshots, kep_snapshots = repos

    _ingest(conn, tmp_path, _scope(docs_snapshots, kep_snapshots))

    # Each version starts at the LAST commit before its snapshot, converted to UTC.
    alpha_from = datetime(2021, 5, 11, 20, 46, 27, tzinfo=UTC)
    stable_from = datetime(2022, 9, 22, 8, 28, 5, tzinfo=UTC)
    assert _windows(conn, "kep:2579") == [
        (21, 25, alpha_from, stable_from),
        (25, None, stable_from, None),
    ]
    kep_id = resolve_document(conn, "kep:2579")
    assert kep_id is not None
    versions = list_versions(conn, kep_id)
    assert [(v.claimed_status, v.claimed_stage) for v in versions] == [
        ("implementable", "alpha"),
        ("implemented", "stable"),
    ]
    assert versions[0].source_path == f"{KEP_DIR}README.md"
    assert versions[0].metadata["title"] == "PSP Replacement Policy"


def test_a_rerun_creates_nothing(conn: Conn, tmp_path: Path, repos: Any) -> None:
    _, docs_snapshots, kep_snapshots = repos
    scope = _scope(docs_snapshots, kep_snapshots)

    first = _ingest(conn, tmp_path, scope)
    rows_after_first = _version_rows(conn)
    second = _ingest(conn, tmp_path, scope)

    # PSP 2 + PSA 5 + overview 3 + RBAC 1 + KEP 2 = 13 versions in 5 documents (counted by hand).
    assert (first.new_documents, first.new_versions) == (5, 13)
    assert (second.new_documents, second.new_versions, second.closed_versions) == (0, 0, 0)
    assert second.unchanged_documents == 5
    assert second.failures == []
    assert _version_rows(conn) == rows_after_first


def _version_rows(conn: Conn) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT id, valid_until_release, valid_until_date FROM document_versions ORDER BY id"
    ).fetchall()


def test_a_new_release_closes_the_open_version_and_adds_the_next(
    conn: Conn, tmp_path: Path, repos: Any
) -> None:
    _, docs_snapshots, kep_snapshots = repos
    _ingest(conn, tmp_path, _scope(docs_snapshots[:6], kep_snapshots))  # 1.24 -> 1.29

    summary = _ingest(conn, tmp_path, _scope(docs_snapshots, kep_snapshots))  # 1.24 -> 1.37

    # Only PSA changed after 1.29: its [28, open] version closes at 1.30 and [30, open] starts.
    assert (summary.closed_versions, summary.new_versions, summary.unchanged_documents) == (1, 1, 4)
    assert _windows(conn, PSA)[-2:] == [(28, 29, D28, D30), (30, None, D30, None)]


def test_a_changed_history_is_reported_and_the_other_documents_still_ingest(
    conn: Conn, tmp_path: Path, repos: Any
) -> None:
    website, docs_snapshots, kep_snapshots = repos
    _ingest(conn, tmp_path, _scope(docs_snapshots, kep_snapshots))
    stored = _version_rows(conn)
    # The lock moves 1.24 to a commit with other content: the 1.37 pages, plus an edit to PSP.
    edited = website.commit({PSP_PATH: _page_at("pod-security-policy", 37) + b"\nAn edit.\n"})
    moved = [Snapshot(24, "release-1.24", edited), *docs_snapshots[1:]]

    summary = _ingest(conn, tmp_path, _scope(moved, kep_snapshots))

    # PSP and PSA now hold other text at 1.24, and overview.md is absent there.
    assert sorted(line.split(": ", 1)[0] for line in summary.failures) == [OVERVIEW, PSA, PSP]
    assert all(": history mismatch: " in line for line in summary.failures)
    assert summary.unchanged_documents == 2  # RBAC and the KEP
    assert _version_rows(conn) == stored  # the mismatched documents are untouched


def test_every_version_is_chunked_once(conn: Conn, tmp_path: Path, repos: Any) -> None:
    _, docs_snapshots, kep_snapshots = repos
    scope = _scope(docs_snapshots, kep_snapshots)

    first = _ingest(conn, tmp_path, scope)
    rows_after_first = _chunk_rows(conn)
    second = _ingest(conn, tmp_path, scope)

    assert first.new_chunks == len(rows_after_first) > 0
    unchunked = conn.execute(
        "SELECT count(*) FROM document_versions v "
        "WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_version_id = v.id)"
    ).fetchone()
    assert unchunked == (0,)  # all 13 versions
    assert second.new_chunks == 0
    assert second.failures == []
    assert _chunk_rows(conn) == rows_after_first


def _chunk_rows(conn: Conn) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT id, document_version_id, ordinal, heading_path, content_hash "
        "FROM chunks ORDER BY id"
    ).fetchall()


def test_kep_chunks_are_read_from_each_versions_readme(
    conn: Conn, tmp_path: Path, repos: Any
) -> None:
    _, docs_snapshots, kep_snapshots = repos

    _ingest(conn, tmp_path, _scope(docs_snapshots, kep_snapshots))

    texts = conn.execute(
        """
        SELECT c.text FROM chunks c
        JOIN document_versions v ON v.id = c.document_version_id
        JOIN documents d ON d.id = v.document_id
        WHERE d.canonical_id = 'kep:2579'
        ORDER BY v.valid_from_date, c.ordinal
        """
    ).fetchall()
    # The READMEs committed in _enhancements at each version's snapshot; the title is kep.yaml's.
    header = (
        "Source: kep\nTitle: KEP-2579: PSP Replacement Policy\nDocument: kep:2579\n"
        "Section: KEP-2579\n\n"
    )
    assert texts == [(header + "fix typo",), (header + "implemented",)]
