"""Ingestion end to end on tiny git repos built from real corpus files, into the test database.

The website repo gets one commit per release 1.24 -> 1.37 holding the real pages of that
release (tests/fixtures/website_s04/<page>/<first release with these bytes>.md, copied from
kubernetes/website at the locked SHAs; CC BY 4.0). overview.md is deleted at 1.29, as in the
corpus. Every commit also holds an excerpt of the real 1.20 release notes, a release record that
only the re-run test's scope reads. The enhancements repo replays KEP-2579's real commit times
around its real kep.yaml files.
"""

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.documents import find_document, resolve_document
from orgknow.db.models import VersionData
from orgknow.db.versions import list_versions
from orgknow.ingestion.git_reader import Skip
from orgknow.ingestion.ingest import Document, ReleasesMismatch, Summary, ingest, store_document
from orgknow.ingestion.manifest import (
    BlogGroup,
    ChangelogGroup,
    DateGroup,
    ReleaseGroup,
    Scope,
    Snapshot,
    load_normalization,
    load_releases,
)

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
RELEASE = "content/en/docs/setup/release/"
NOTES_PATH = RELEASE + "notes.md"
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
    notes = (FIXTURES / "website_s05" / "release-notes" / "excerpt-1.20.md").read_bytes()
    snapshots = []
    for minor in range(24, 38):
        files: dict[str, bytes | None] = {RBAC_PATH: rbac, NOTES_PATH: notes}
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


def _scope(
    docs_snapshots: list[Snapshot], kep_snapshots: list[Snapshot], release_records: bool = False
) -> Scope:
    groups = [ReleaseGroup("docs_page", "website", (SECURITY, RBAC_PATH), tuple(docs_snapshots))]
    if release_records:
        groups.append(ReleaseGroup("release_record", "website", (RELEASE,), tuple(docs_snapshots)))
    keps = DateGroup("kep", "enhancements", (KEP_DIR,), tuple(kep_snapshots))
    return Scope("test", tuple(groups), (keps,))


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


def _releases(conn: Conn) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT minor, version, release_date, end_of_life_date FROM releases ORDER BY minor"
    ).fetchall()


def _row_counts(conn: Conn) -> tuple[Any, ...] | None:
    return conn.execute(
        """
        SELECT (SELECT count(*) FROM documents), (SELECT count(*) FROM document_aliases),
               (SELECT count(*) FROM document_versions), (SELECT count(*) FROM chunks),
               (SELECT count(*) FROM embeddings)
        """
    ).fetchone()


# Hand edits of the seeded 1.30 row (manifest: released 2024-04-17, end of life 2025-07-15).
@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        ("DELETE FROM releases WHERE minor = 30", "1.30 is missing"),
        (
            "UPDATE releases SET release_date = '2024-04-18' WHERE minor = 30",
            "1.30 differs (table: 2024-04-18 to 2025-07-15; manifest: 2024-04-17 to 2025-07-15)",
        ),
    ],
    ids=["deleted", "re-dated"],
)
def test_a_releases_table_unlike_the_manifest_stops_before_any_write(
    conn: Conn, tmp_path: Path, repos: Any, edit: str, problem: str
) -> None:
    _, docs_snapshots, kep_snapshots = repos
    conn.execute(edit)
    before = (_releases(conn), _row_counts(conn))

    with pytest.raises(ReleasesMismatch, match="run `make seed`") as raised:
        _ingest(conn, tmp_path, _scope(docs_snapshots, kep_snapshots))

    assert problem in str(raised.value)
    # Nothing written anywhere: the edited releases row is left as it was, and no rows appear.
    assert (_releases(conn), _row_counts(conn)) == before


def test_the_releases_check_runs_before_any_git_read(conn: Conn, tmp_path: Path) -> None:
    conn.execute("DELETE FROM releases WHERE minor = 30")
    scope = _scope([Snapshot(24, "release-1.24", "0" * 40)], [])

    # No repos under this cache dir: any git read would raise GitError instead.
    with pytest.raises(ReleasesMismatch, match=r"1\.30 is missing"):
        _ingest(conn, tmp_path / "no-repos", scope)


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
    scope = _scope(docs_snapshots, kep_snapshots, release_records=True)

    first = _ingest(conn, tmp_path, scope)
    rows_after_first = _version_rows(conn)
    counts_after_first = _row_counts(conn)
    second = _ingest(conn, tmp_path, scope)

    # PSP 2 + PSA 5 + overview 3 + RBAC 1 + release notes 1 + KEP 2 = 14 versions in 6 documents
    # (counted by hand).
    assert (first.new_documents, first.new_versions) == (6, 14)
    assert first.documents == {"docs_page": 4, "release_record": 1, "kep": 1}
    assert (second.new_documents, second.new_versions, second.closed_versions) == (0, 0, 0)
    assert (second.unchanged_documents, second.new_chunks) == (6, 0)
    assert second.failures == []
    assert _version_rows(conn) == rows_after_first
    # documents, aliases (/rbac/), versions, chunks, embeddings: nothing added by the re-run.
    assert counts_after_first is not None and counts_after_first[:3] == (6, 1, 14)
    assert _row_counts(conn) == counts_after_first


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


# --- R3 when an id is another document's alias (S05-T1, parked item 10b) ----------------------

D20 = datetime(2020, 12, 8, tzinfo=UTC)
D37 = datetime(2026, 8, 26, tzinfo=UTC)
MOVED = "web:/docs/reference/deprecation-policy/"
OLD_URL = "web:/docs/reference/using-api/deprecation-policy/"


def _version(path: str, ref: str, from_release: int, from_date: datetime) -> VersionData:
    return VersionData(
        content_hash=("a" if from_release == 37 else "b") * 64,
        source_path=path,
        snapshot_repo="website",
        snapshot_ref=ref,
        snapshot_sha="0" * 40,
        valid_from_release=from_release,
        valid_from_date=from_date,
    )


def test_an_id_that_is_another_documents_alias_gets_the_r3_error(conn: Conn) -> None:
    # The 1.37 deprecation-policy page lists its old URL in `aliases`; the old page is a separate
    # document until T2 links them. Hand-written versions, so the two histories differ.
    moved = Document(
        MOVED,
        "docs_page",
        [_version("content/en/docs/reference/deprecation-policy.md", "main", 37, D37)],
        [OLD_URL],
    )
    store_document(conn, moved, Summary())
    old = Document(
        OLD_URL,
        "docs_page",
        [
            _version(
                "content/en/docs/reference/using-api/deprecation-policy.md", "release-1.20", 20, D20
            )
        ],
        [],
    )

    # Not HistoryMismatch (not a ValueError): the old URL must not resolve to the moved page.
    with pytest.raises(ValueError) as raised:
        store_document(conn, old, Summary())

    assert str(raised.value) == f"{OLD_URL!r} is already an alias of another document"
    assert find_document(conn, OLD_URL) is None  # rolled back: nothing created
    assert resolve_document(conn, OLD_URL) == find_document(conn, MOVED)


# --- Renames (S05-T2) --------------------------------------------------------------------------

NEW_NOTES_PATH = "content/en/releases/notes.md"
NOTES = "web:/docs/setup/release/notes/"
D21 = datetime(2021, 4, 8, tzinfo=UTC)
D22 = datetime(2021, 8, 4, tzinfo=UTC)


def test_a_moved_release_record_stays_one_document(
    conn: Conn, tmp_path: Path, make_git_repo: Callable[[str], Any]
) -> None:
    # The real move of 1.21: the release notes page left setup/release/ for releases/, and
    # static/_redirects says so (real lines 495-498 at 1.21). git can't pair the two files: the
    # 1.20 page held the release notes, the 1.21 page points to the CHANGELOG (spike §4 G).
    repo = make_git_repo("website")
    fixtures = FIXTURES / "website_s05"
    redirects = (fixtures / "redirects" / "excerpt-1.21.txt").read_bytes()
    at_20 = repo.commit({NOTES_PATH: (fixtures / "release-notes" / "excerpt-1.20.md").read_bytes()})
    at_21 = repo.commit(
        {
            NOTES_PATH: None,
            NEW_NOTES_PATH: (fixtures / "release-notes" / "1.21.md").read_bytes(),
            "static/_redirects": redirects,
        }
    )
    at_22 = repo.commit({NEW_NOTES_PATH: (fixtures / "release-notes" / "1.22.md").read_bytes()})
    snapshots = (
        Snapshot(20, "release-1.20", at_20),
        Snapshot(21, "release-1.21", at_21),
        Snapshot(22, "release-1.22", at_22),
    )
    records = ReleaseGroup(
        "release_record", "website", ("content/en/releases/", RELEASE), snapshots
    )
    scope = Scope("test", (records,), ())

    summary = _ingest(conn, tmp_path, scope)

    assert summary.failures == []
    assert (summary.new_documents, summary.new_versions) == (1, 3)
    # The contract's release-notes windows: the 1.21 page is new text, and it changed at 1.22.
    assert _windows(conn, NOTES) == [
        (20, 20, D20, D21),
        (21, 21, D21, D22),
        (22, None, D22, None),
    ]
    document_id = find_document(conn, NOTES)
    assert document_id is not None
    assert [v.source_path for v in list_versions(conn, document_id)] == [
        NOTES_PATH,
        NEW_NOTES_PATH,
        NEW_NOTES_PATH,
    ]
    # The later URL is an alias of the document, not a document of its own.
    assert find_document(conn, "web:/releases/notes/") is None
    assert resolve_document(conn, "web:/releases/notes/") == document_id


# --- Feature gates (S05-T3) --------------------------------------------------------------------

REFERENCE = "content/en/docs/reference/command-line-tools-reference/"
GATES = REFERENCE + "feature-gates/"
GATE_FIXTURES = FIXTURES / "website_s05" / "feature-gates"
FEATURE_GATES_PAGE = "web:/docs/reference/command-line-tools-reference/feature-gates/"
TYPO = "gate:ServiceAcccountNodeAudienceRestriction"


def _gate(title: str, stage: str = "alpha", former_titles: str = "") -> bytes:
    """A hand-written gate file shaped as the real ones; `former_titles` is its YAML lines."""
    return (
        f"---\ntitle: {title}\n{former_titles}content_type: feature_gate\n_build:\n"
        f"  list: never\n  render: false\n\nstages:\n  - stage: {stage}\n"
        f'    defaultValue: false\n    fromVersion: "1.25"\n---\nThe {title} gate.\n'
    ).encode()


def _real_gate(name: str, minor: int) -> bytes:
    return (GATE_FIXTURES / name / f"1.{minor}.md").read_bytes()


def _feature_gates(make_git_repo: Callable[[str], Any]) -> Scope:
    """A website repo with one commit per release 1.28 -> 1.37 holding the contract's gate cases.
    The files git compares (APIServingWithRoute, PodInfoAPI and their partners) are the real
    ones; the others are hand-written with the real paths and titles."""
    repo = make_git_repo("website")
    page = b"---\ntitle: Feature Gates\nweight: 10\n---\n"
    net, ready = "PodHasNetworkCondition", "PodReadyToStartContainersCondition"
    former = "former_titles:\n  - PodHasNetworkCondition\n"
    typo = GATES + "ServiceAccountNodeAudienceRestriction.md"
    commits: dict[int, dict[str, bytes | None]] = {
        28: {REFERENCE + "feature-gates.md": page + b"| `PodSecurity` | `true` | GA |\n"},
        # The tables become one file per gate; the page becomes a bundle at the same URL.
        29: {
            REFERENCE + "feature-gates.md": None,
            GATES + "index.md": page + b"{{< feature-gate-list >}}\n",
            GATES + "pod-has-network-condition.md": _gate(net),
            GATES + "pod-ready-to-start-containers.md": _gate(ready, former_titles=former),
        },
        30: {},
        31: {},
        # Kebab case -> gate name; PodReadyToStartContainersCondition's stage changes too.
        32: {
            GATES + "pod-has-network-condition.md": None,
            GATES + "pod-ready-to-start-containers.md": None,
            GATES + f"{net}.md": _gate(net),
            GATES + f"{ready}.md": _gate(ready, "beta", former),
            GATES + "APIServingWithRoute.md": _real_gate("APIServingWithRoute", 32),
        },
        33: {
            GATES + "APIServingWithRoute.md": None,
            GATES + "APIServingWithRoutine.md": _real_gate("APIServingWithRoutine", 33),
            typo: _gate("ServiceAcccountNodeAudienceRestriction", "beta"),
        },
        34: {},
        35: {typo: _gate("ServiceAccountNodeAudienceRestriction", "beta")},  # fixed in place
        36: {GATES + "PodInfoAPI.md": _real_gate("PodInfoAPI", 36)},
        37: {
            GATES + "PodInfoAPI.md": None,
            GATES + "InPlacePodVerticalScalingMemoryBackedVolumes.md": _real_gate(
                "InPlacePodVerticalScalingMemoryBackedVolumes", 37
            ),
            GATES + "StrictIPCIDRValidation.md": _real_gate("StrictIPCIDRValidation", 37),
        },
    }
    snapshots = tuple(
        Snapshot(minor, f"release-1.{minor}", repo.commit(files))
        for minor, files in commits.items()
    )
    # The manifest's paths that this history holds: a path absent at every snapshot is an error
    # (S05-T8), and it has no removed-gates page.
    paths = (REFERENCE + "feature-gates.md", GATES)
    group = ReleaseGroup("feature_gate_reference", "website", paths, snapshots)
    return Scope("test", (group,), ())


def _release_windows(conn: Conn, canonical_id: str) -> list[tuple[int, int | None]]:
    document_id = find_document(conn, canonical_id)
    assert document_id is not None, canonical_id
    return [(v.valid_from_release, v.valid_until_release) for v in list_versions(conn, document_id)]


def _aliases(conn: Conn) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT a.alias, d.canonical_id FROM document_aliases a "
        "JOIN documents d ON d.id = a.document_id ORDER BY a.alias"
    ).fetchall()


def test_feature_gates_keep_one_document_per_gate(
    conn: Conn, tmp_path: Path, make_git_repo: Callable[[str], Any]
) -> None:
    scope = _feature_gates(make_git_repo)

    summary = _ingest(conn, tmp_path, scope)

    assert summary.failures == []
    # 1 page + 7 gates, counted by hand from the commits above.
    assert summary.documents == {"feature_gate_reference": 8}
    # The page and its bundle share a URL: one web document. No gate links to it.
    assert _release_windows(conn, FEATURE_GATES_PAGE) == [(28, 28), (29, None)]
    # The 1.32 renames are linked by title: no new document. The unchanged file keeps its first
    # path (a version is a change in content, not a move).
    assert _release_windows(conn, "gate:PodHasNetworkCondition") == [(29, None)]
    assert _release_windows(conn, "gate:PodReadyToStartContainersCondition") == [
        (29, 31),
        (32, None),
    ]
    # git pairs the real files at 93%: one gate, identified by its first title.
    assert _release_windows(conn, "gate:APIServingWithRoute") == [(32, 32), (33, None)]
    # The title fixed in place: same path, one document whose id keeps the typo.
    assert _release_windows(conn, TYPO) == [(33, 34), (35, None)]
    # git scores the real pair 40%, under 50%: two documents.
    assert _release_windows(conn, "gate:PodInfoAPI") == [(36, 36)]
    assert _release_windows(conn, "gate:InPlacePodVerticalScalingMemoryBackedVolumes") == [
        (37, None)
    ]
    # Later titles are aliases; former_titles are not (PodHasNetworkCondition is its own gate).
    assert _aliases(conn) == [
        ("gate:APIServingWithRoutine", "gate:APIServingWithRoute"),
        ("gate:ServiceAccountNodeAudienceRestriction", TYPO),
    ]


def test_a_gate_chunk_stored_from_jsonb_metadata_keeps_the_files_yaml_order(
    conn: Conn, tmp_path: Path, make_git_repo: Callable[[str], Any]
) -> None:
    scope = _feature_gates(make_git_repo)

    first = _ingest(conn, tmp_path, scope)
    second = _ingest(conn, tmp_path, scope)

    texts = conn.execute(
        "SELECT c.text FROM chunks c JOIN document_versions v ON v.id = c.document_version_id "
        "JOIN documents d ON d.id = v.document_id "
        "WHERE d.canonical_id = 'gate:StrictIPCIDRValidation'"
    ).fetchall()
    # The pinned format, typed by hand: the stored metadata is jsonb, which reorders keys
    # (stage, toVersion, fromVersion, defaultValue); the YAML keeps the file's order.
    assert len(texts) == 1
    assert texts[0][0].startswith(
        "Source: feature_gate_reference\n"
        "Title: StrictIPCIDRValidation\n"
        "Document: gate:StrictIPCIDRValidation\n"
        "\n"
        "stages:\n"
        "- stage: alpha\n"
        "  defaultValue: false\n"
        "  fromVersion: '1.33'\n"
        "  toVersion: '1.35'\n"
        "- stage: beta\n"
        "  defaultValue: true\n"
        "  fromVersion: '1.36'\n"
        "\n"
        "Use stricter validation for fields containing IP addresses and CIDR values.\n"
    )
    assert first.failures == second.failures == []
    assert (second.new_documents, second.new_versions, second.new_chunks) == (0, 0, 0)


# --- KEPs dated by merge time (S05-T4) ---------------------------------------------------------

SIG_AUTH, SIG_NETWORK = "keps/sig-auth/", "keps/sig-network/"
OLD_KEP_PATH = SIG_AUTH + "0014-dynamic-audit-configuration.md"
OLD_KEP = "kep:sig-auth/0014-dynamic-audit-configuration"


def _pull_request(
    repo: Any, name: str, commits: list[tuple[dict[str, bytes | None], str]], merged: str
) -> str:
    """Commit each change on a branch at its own time, then merge the branch into main at
    `merged`, as GitHub merges a pull request. Returns the merge commit's SHA."""
    repo.switch(name, create=True)
    for files, when in commits:
        repo.commit(files, when=when)
    repo.switch("main")
    return repo.merge(name, when=merged)


def _enhancements_with_merges(make_git_repo: Callable[[str], Any]) -> tuple[Any, list[Snapshot]]:
    """KEP-2579's real history as pull requests: each branch commit at its real committer time
    (S04's dates), each merge at master's real merge time (`git log --first-parent`, S05-R2
    sitting), with its real kep.yaml. The 1.20 snapshot also holds the real old single-file KEP
    0014 (removed by a real merge at 2020-12-22T14:02:28Z), sig-network's index, a symlink and an
    OWNERS file; KEP-2579's folder also gets images, which are ignored."""
    repo = make_git_repo("enhancements")
    kep_yaml = FIXTURES / "kep_2579"
    readme, kep = f"{KEP_DIR}README.md", f"{KEP_DIR}kep.yaml"
    old_kep = (
        FIXTURES / "kep_old" / "0014-dynamic-audit-configuration-excerpt-1.20.md"
    ).read_bytes()
    base = {
        OLD_KEP_PATH: old_kep,
        SIG_NETWORK + "README.md": b"# SIG Network KEPs\n",
        SIG_AUTH + "OWNERS": b"approvers:\n- sig-auth-leads\n",
    }
    (repo.path / "keps" / "sig-auth").mkdir(parents=True)
    os.symlink("0014-dynamic-audit-configuration.md", repo.path / SIG_AUTH / "link.md")
    at_20 = repo.commit(base, when="2019-07-04T08:52:37-07:00")
    at_21 = _pull_request(
        repo,
        "old-keps",
        [({OLD_KEP_PATH: None}, "2020-12-21T10:00:00-08:00")],
        "2020-12-22T06:02:28-08:00",
    )
    first = (kep_yaml / "1.22.kep.yaml").read_bytes()
    at_22 = _pull_request(
        repo,
        "kep-2579-alpha",
        [
            ({readme: b"# KEP-2579\n", kep: first}, "2021-05-11T13:42:01-07:00"),
            (
                {
                    readme: b"# KEP-2579\nfix typo\n",
                    f"{KEP_DIR}images/flow.md": b"# A diagram's source\n",
                    f"{KEP_DIR}flow.png": b"\x89PNG",
                },
                "2021-05-11T13:46:27-07:00",
            ),
        ],
        "2021-05-12T16:25:28+00:00",
    )
    at_23 = _pull_request(
        repo,
        "kep-2579-beta",
        [({kep: (kep_yaml / "1.23.kep.yaml").read_bytes()}, "2021-11-04T21:29:13-04:00")],
        "2021-11-11T16:46:07+00:00",
    )
    at_25 = _pull_request(
        repo,
        "kep-2579-ga",
        [({kep: (kep_yaml / "1.25.kep.yaml").read_bytes()}, "2022-06-01T17:05:45-07:00")],
        "2022-06-06T16:34:23+00:00",
    )
    at_26 = _pull_request(
        repo,
        "kep-2579-implemented",
        [({kep: (kep_yaml / "1.26.kep.yaml").read_bytes()}, "2022-09-22T10:28:05+02:00")],
        "2022-09-22T15:59:06+00:00",
    )
    # Hand-made: the KEP's folder leaves sig-auth (as 506, 2004 and 2030 left the 3 SIG folders).
    at_27 = _pull_request(
        repo,
        "move-kep-2579",
        [
            (
                {
                    readme: None,
                    kep: None,
                    f"{KEP_DIR}images/flow.md": None,
                    f"{KEP_DIR}flow.png": None,
                },
                "2023-01-09T12:00:00+00:00",
            )
        ],
        "2023-01-10T12:00:00+00:00",
    )
    shas = {20: at_20, 21: at_21, 22: at_22, 23: at_23, 25: at_25, 26: at_26, 27: at_27}
    return repo, [Snapshot(minor, "master", sha) for minor, sha in shas.items()]


def _kep_scope(snapshots: list[Snapshot]) -> Scope:
    keps = DateGroup("kep", "enhancements", (SIG_AUTH, SIG_NETWORK), tuple(snapshots))
    return Scope("test", (), (keps,))


def test_kep_versions_start_at_their_merge_times(
    conn: Conn, tmp_path: Path, make_git_repo: Callable[[str], Any]
) -> None:
    _, snapshots = _enhancements_with_merges(make_git_repo)
    scope = _kep_scope(snapshots[:-1])  # up to 1.26: the KEP is still in sig-auth

    first = _ingest(conn, tmp_path, scope)
    second = _ingest(conn, tmp_path, scope)

    assert first.failures == []
    # The contract's KEP-2579 windows [21,22] [22,24] [24,25] [25,-], each starting at its merge
    # (S05-R2 sitting), not at its branch's last commit (S04 stored 2021-05-11T20:46:27Z, ...).
    m1 = datetime(2021, 5, 12, 16, 25, 28, tzinfo=UTC)
    m2 = datetime(2021, 11, 11, 16, 46, 7, tzinfo=UTC)
    m3 = datetime(2022, 6, 6, 16, 34, 23, tzinfo=UTC)
    m4 = datetime(2022, 9, 22, 15, 59, 6, tzinfo=UTC)
    assert _windows(conn, "kep:2579") == [
        (21, 22, m1, m2),
        (22, 24, m2, m3),
        (24, 25, m3, m4),
        (25, None, m4, None),
    ]
    # The old single-file KEP: its own document (S05-R2 decision 3), from its 2019 commit on
    # main (the first snapshot's whole history) to its removal; release window from 20
    # (decision 1).
    assert _windows(conn, OLD_KEP) == [
        (
            20,
            20,
            datetime(2019, 7, 4, 15, 52, 37, tzinfo=UTC),
            datetime(2020, 12, 22, 14, 2, 28, tzinfo=UTC),
        )
    ]
    old_id = find_document(conn, OLD_KEP)
    assert old_id is not None
    assert list_versions(conn, old_id)[0].claimed_status == "implementable"
    # Skipped with a reason: the symlink (at every snapshot) and sig-network's index. The other
    # files in the KEP's folder (images/flow.md, flow.png) are ignored, not even skipped.
    assert first.skipped[:2] == [
        Skip(snapshots[0], "keps/sig-auth/OWNERS", "not a .md/.yaml file"),
        Skip(snapshots[0], "keps/sig-auth/link.md", "symlink"),
    ]
    index = Skip(
        snapshots[0], "keps/sig-network/README.md", "an index of the SIG's KEPs, not a KEP"
    )
    assert index in first.skipped
    assert not any("flow" in skip.path for skip in first.skipped)
    assert first.documents == {"kep": 2}
    # A re-run adds nothing.
    assert (second.new_documents, second.new_versions, second.closed_versions) == (0, 0, 0)
    assert (second.unchanged_documents, second.new_chunks, second.failures) == (2, 0, [])


def test_a_reingest_that_only_closes_a_version(
    conn: Conn, tmp_path: Path, make_git_repo: Callable[[str], Any]
) -> None:
    # E2 (S05-R2): the 1.27 snapshot only removes KEP-2579, so a re-ingest closes its open
    # version at the removal's merge time and inserts nothing.
    _, snapshots = _enhancements_with_merges(make_git_repo)
    _ingest(conn, tmp_path, _kep_scope(snapshots[:-1]))
    open_rows = _version_rows(conn)

    summary = _ingest(conn, tmp_path, _kep_scope(snapshots))

    assert summary.failures == []
    assert (summary.new_documents, summary.new_versions, summary.closed_versions) == (0, 0, 1)
    removed = datetime(2023, 1, 10, 12, tzinfo=UTC)
    m4 = datetime(2022, 9, 22, 15, 59, 6, tzinfo=UTC)
    assert _windows(conn, "kep:2579")[-1] == (25, 26, m4, removed)
    # Only that row changed: KEP-2579's open version, stored last (rows by id: id, release
    # `until`, date `until`). The old single-file KEP, stored first, was already closed.
    assert open_rows[-1][1:] == (None, None)
    assert _version_rows(conn) == [*open_rows[:-1], (open_rows[-1][0], 26, removed)]


# --- Governance docs: moves on date snapshots (S05-T4, S05-R2 decision 2) ---------------------

RELENG = "release-engineering/"
VERSIONING_PATH, MOVED_VERSIONING = RELENG + "versioning.md", RELENG + "reference/versioning.md"
BASEIMAGE_PATH, MOVED_BASEIMAGE = (
    RELENG + "baseimage-exception-list.md",
    RELENG + "reference/baseimage-exception-list.md",
)
VERSIONING = "sig-release:release-engineering/versioning.md"
BASEIMAGE = "sig-release:release-engineering/baseimage-exception-list.md"


def _sig_release(make_git_repo: Callable[[str], Any]) -> list[Snapshot]:
    """versioning.md's 4 real merge times (`git log --first-parent`, sig-release): PR #1493
    (2021-03-15), #2452 (2024-03-12), #2962 (2026-02-13), and #2984 (2026-05-28), which moved it
    into reference/ (98% similar) and moved baseimage-exception-list.md unchanged (R100). The
    1.36 and 1.37 versioning.md files are the real ones; the others are hand-written. After 1.37
    a hand-made merge edits the moved baseimage file."""
    repo = make_git_repo("sig-release")
    real = FIXTURES / "sig_release" / "versioning"
    at_20 = repo.commit({"README.md": b"# SIG Release\n"}, when="2020-11-02T00:00:00+00:00")
    baseimage = b"# Base Image Exception List\n\nImages that may differ from the base image.\n"
    at_21 = _pull_request(
        repo,
        "versioning",
        [
            (
                {
                    VERSIONING_PATH: b"# Kubernetes Release Versioning\n\nFirst text.\n",
                    BASEIMAGE_PATH: baseimage,
                },
                "2021-03-10T09:00:00-08:00",
            )
        ],
        "2021-03-15T14:24:34-07:00",
    )
    at_30 = _pull_request(
        repo,
        "patch-1",
        [
            (
                {VERSIONING_PATH: b"# Kubernetes Release Versioning\n\nSecond text.\n"},
                "2024-03-01T00:00:00+00:00",
            )
        ],
        "2024-03-12T00:23:49-07:00",
    )
    at_36 = _pull_request(
        repo,
        "outdated-content",
        [({VERSIONING_PATH: (real / "1.36.md").read_bytes()}, "2026-02-10T00:00:00+00:00")],
        "2026-02-13T20:58:00+05:30",
    )
    at_37 = _pull_request(
        repo,
        "fix-release-engineering-docs",
        [
            (
                {
                    VERSIONING_PATH: None,
                    MOVED_VERSIONING: (real / "1.37.md").read_bytes(),
                    BASEIMAGE_PATH: None,
                    MOVED_BASEIMAGE: baseimage,
                },
                "2026-05-20T00:00:00+00:00",
            )
        ],
        "2026-05-28T17:10:47+05:30",
    )
    head = _pull_request(
        repo,
        "baseimage-update",
        [({MOVED_BASEIMAGE: baseimage + b"\nOne more image.\n"}, "2026-08-31T00:00:00+00:00")],
        "2026-09-01T00:00:00+00:00",
    )
    shas = {20: at_20, 21: at_21, 30: at_30, 36: at_36, 37: at_37, None: head}
    return [Snapshot(minor, "master", sha) for minor, sha in shas.items()]


def test_a_moved_governance_doc_stays_one_document(
    conn: Conn, tmp_path: Path, make_git_repo: Callable[[str], Any]
) -> None:
    snapshots = _sig_release(make_git_repo)
    group = DateGroup("governance_doc", "sig-release", (RELENG,), tuple(snapshots))
    scope = Scope("test", (), (group,))

    first = _ingest(conn, tmp_path, scope)
    second = _ingest(conn, tmp_path, scope)

    assert first.failures == []
    assert first.documents == {"governance_doc": 2}
    # versioning.md: 4 versions at its 4 merge times; the 4th is PR #2984's move (S05-R2
    # devil's-advocate check: 2026-05-28T11:40:47Z). Windows by hand from the release dates.
    t1 = datetime(2021, 3, 15, 21, 24, 34, tzinfo=UTC)
    t2 = datetime(2024, 3, 12, 7, 23, 49, tzinfo=UTC)
    t3 = datetime(2026, 2, 13, 15, 28, 0, tzinfo=UTC)
    t4 = datetime(2026, 5, 28, 11, 40, 47, tzinfo=UTC)
    assert _windows(conn, VERSIONING) == [
        (20, 29, t1, t2),
        (29, 35, t2, t3),
        (35, 36, t3, t4),
        (36, None, t4, None),
    ]
    versioning_id = find_document(conn, VERSIONING)
    assert versioning_id is not None
    versions = list_versions(conn, versioning_id)
    assert [v.source_path for v in versions] == [VERSIONING_PATH] * 3 + [MOVED_VERSIONING]
    # S05-R2 decision 4: line 1 of the real file, kept as the version's title.
    assert versions[-1].metadata == {"title": "Kubernetes Release Versioning"}
    # baseimage: the R100 move adds no version, so the open one kept its old path and snapshot;
    # the chain then continues from 1.37 to head, where the moved file was edited.
    t5 = datetime(2026, 9, 1, tzinfo=UTC)
    assert _windows(conn, BASEIMAGE) == [(20, 37, t1, t5), (37, None, t5, None)]
    baseimage_id = find_document(conn, BASEIMAGE)
    assert baseimage_id is not None
    first_baseimage = list_versions(conn, baseimage_id)[0]
    assert (first_baseimage.source_path, first_baseimage.snapshot_sha) == (
        BASEIMAGE_PATH,
        snapshots[1].sha,
    )
    # The first path is the id; the later path is an alias (ADR-002 D4, amended in S05-R2).
    assert _aliases(conn) == [
        ("sig-release:release-engineering/reference/baseimage-exception-list.md", BASEIMAGE),
        ("sig-release:release-engineering/reference/versioning.md", VERSIONING),
    ]
    # A re-run adds nothing.
    assert (second.new_documents, second.new_versions, second.new_chunks) == (0, 0, 0)
    assert second.failures == []


# --- Blog posts: one first-parent log of the posts' folder (S05-T5) ---------------------------

BLOG = FIXTURES / "blog"
POSTS = "content/en/blog/_posts/"
INGRESS_PATH = POSTS + "2025-11-12-ingress-nginx-retirement.md"
VAP_PATH = POSTS + "2024-04-24-validating-admission-policy-ga/index.md"
INTERVIEW_PATH = POSTS + "2022-04-29-kubernetes-1.23-release-interview.md"
BAD_PATH = POSTS + "2026-01-05-broken-front-matter.md"
INGRESS = "web:/blog/2025/11/12/ingress-nginx-retirement/"
VAP = "web:/blog/2024/04/24/validating-admission-policy-ga/"
INTERVIEW = (
    "web:/blog/2022/04/29/frontiers-fsgroups-and-frogs-the-kubernetes-1.23-release-interview/"
)


def _website_blog(make_git_repo: Callable[[str], Any]) -> tuple[str, str]:
    """Real posts at their real first-parent commit times on website main: the 1.23 release
    interview, the VAP GA post (`------`; its first version through a pull request, merged at
    its real merge time), the ingress-nginx retirement post's 3 versions, then PR #53902's
    year-folder move (2026-02-21), which moves two posts unchanged and the interview to a file
    with no extension. Also: the real 1.11 interview (2018, out of scope), a hand-made draft
    (never published), and a hand-made post with broken front matter. Returns (the broken
    post's commit, head)."""
    repo = make_git_repo("website")
    sausage = (BLOG / "kubernetes-1-11-release-interview-excerpt.md").read_bytes()
    repo.commit({POSTS + "2018-07-16-sausage.md": sausage}, when="2018-07-16T09:00:00-07:00")
    interview = (BLOG / "kubernetes-1.23-release-interview" / "27d1959c-excerpt.md").read_bytes()
    repo.commit({INTERVIEW_PATH: interview}, when="2022-04-28T08:15:50-07:00")
    vap = BLOG / "validating-admission-policy-ga"
    _pull_request(
        repo,
        "vap-ga",
        [({VAP_PATH: (vap / "3a358ed2-excerpt.md").read_bytes()}, "2024-04-19T10:00:00-07:00")],
        "2024-04-20T14:11:16-07:00",
    )
    repo.commit({VAP_PATH: (vap / "2de4371a-excerpt.md").read_bytes()}, "2024-04-23T05:05:52-07:00")
    ingress = BLOG / "ingress-nginx-retirement"
    for name, when in [
        ("35d8dfc2", "2025-11-12T07:49:40-08:00"),
        ("2b1598fc", "2025-11-12T09:17:42-08:00"),
        ("fe122837", "2025-11-12T09:53:41-08:00"),
    ]:
        repo.commit({INGRESS_PATH: (ingress / f"{name}-excerpt.md").read_bytes()}, when)
    draft = b"---\ntitle: A draft\ndate: XXXX-XX-XX\ndraft: true\n---\n\nNot yet.\n"
    repo.commit({POSTS + "XXXX-XX-XX-draft.md": draft}, when="2025-12-01T00:00:00+00:00")
    bad = repo.commit(
        {BAD_PATH: b"---\ntitle: [unclosed\n---\n\nText.\n"}, when="2026-01-05T00:00:00+00:00"
    )
    head = repo.commit(
        {
            INGRESS_PATH: None,
            POSTS + "2025/ingress-nginx-retirement.md": (
                ingress / "fe122837-excerpt.md"
            ).read_bytes(),
            VAP_PATH: None,
            POSTS + "2024/validating-admission-policy-ga/index.md": (
                vap / "2de4371a-excerpt.md"
            ).read_bytes(),
            INTERVIEW_PATH: None,
            POSTS + "2022/kubernetes-1.23-release-interview": interview,
        },
        when="2026-02-21T17:01:37+05:30",
    )
    return bad, head


def _blog_scope(head: str) -> Scope:
    blog = BlogGroup(
        "blog_post",
        "website",
        "main",
        head,
        (POSTS,),
        datetime(2020, 12, 8, tzinfo=UTC),
        "/:section/:year/:month/:day/:slug/",
    )
    return Scope("test", (), (), blog)


def test_blog_posts_are_stored_from_publication_and_a_rerun_adds_nothing(
    conn: Conn,
    tmp_path: Path,
    make_git_repo: Callable[[str], Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad, head = _website_blog(make_git_repo)
    scope = _blog_scope(head)

    with caplog.at_level(logging.INFO):
        first = _ingest(conn, tmp_path, scope)
    second = _ingest(conn, tmp_path, scope)

    # The broken post is reported with its reason, every run, labelled with its commit's short
    # SHA (S05-T8); the others are stored.
    reason = "front matter is not valid YAML: while parsing a flow sequence"
    broken = f"{bad[:8]} {BAD_PATH}: {reason}"
    assert [line.split("\n")[0] for line in first.failures] == [broken]
    assert first.documents == {"blog_post": 3}
    # Out of scope, counted (not listed one by one): the 2018 post and the draft.
    assert (
        "blog: 6 posts; 3 in scope; 1 never published; 1 dated before 2020-12-08; 0 with no date"
        in caplog.text
    )
    # ingress: valid_from = max(merge, publication); 11-12 is the id, 11-11 an alias.
    published = datetime(2025, 11, 12, 17, tzinfo=UTC)
    t1 = datetime(2025, 11, 12, 17, 17, 42, tzinfo=UTC)
    t2 = datetime(2025, 11, 12, 17, 53, 41, tzinfo=UTC)
    assert _windows(conn, INGRESS) == [
        (34, 34, published, t1),
        (34, 34, t1, t2),
        (34, None, t2, None),
    ]
    assert _aliases(conn) == [("web:/blog/2025/11/11/ingress-nginx-retirement/", INGRESS)]
    # VAP GA: its pull request's text was superseded before its date, so only the 04-23 text
    # is stored, from the date; the year-folder move adds no version (R100).
    assert _windows(conn, VAP) == [(30, None, datetime(2024, 4, 24, tzinfo=UTC), None)]
    vap_id = find_document(conn, VAP)
    assert vap_id is not None
    assert [v.source_path for v in list_versions(conn, vap_id)] == [VAP_PATH]
    # The interview, moved to a file with no extension: its version closes at that merge.
    moved = datetime(2026, 2, 21, 11, 31, 37, tzinfo=UTC)
    assert _windows(conn, INTERVIEW) == [(23, 35, datetime(2022, 4, 29, tzinfo=UTC), moved)]
    # Chunked from the version's own file: the `------` front matter is not in the text.
    (vap_chunk,) = conn.execute(
        "SELECT c.text FROM chunks c JOIN document_versions v ON v.id = c.document_version_id "
        "WHERE v.document_id = %s ORDER BY c.ordinal LIMIT 1",
        (vap_id,),
    ).fetchone() or (None,)
    assert vap_chunk.startswith(
        "Source: blog_post\n"
        "Title: Kubernetes 1.30: Validating Admission Policy Is Generally Available\n"
        f"Document: {VAP}\n\n"
        "On behalf of the Kubernetes project"
    )
    # A re-run adds nothing.
    assert (second.new_documents, second.new_versions, second.closed_versions) == (0, 0, 0)
    assert (second.unchanged_documents, second.new_chunks) == (3, 0)
    assert [line.split("\n")[0] for line in second.failures] == [broken]


# --- CHANGELOGs (S05-T6) ---------------------------------------------------------------------

KUBERNETES = FIXTURES / "kubernetes"
CHANGELOG_22 = "CHANGELOG/CHANGELOG-1.22.md"
CHANGELOG_37 = "CHANGELOG/CHANGELOG-1.37.md"


def _kubernetes(make_git_repo: Callable[[str], Any]) -> str:
    """The kubernetes repo at its lock head, with the head's real committer time: two real
    CHANGELOG excerpts (1.22's v1.22.0-beta.1 section, whose stray fence is followed by
    v1.22.0-beta.0's downloads; 1.37's TOC and v1.37.1 section) and a CHANGELOG-1.38.md, which is
    out of range. Returns the head."""
    repo = make_git_repo("kubernetes")
    return repo.commit(
        {
            CHANGELOG_22: (KUBERNETES / "CHANGELOG-1.22-beta.1-excerpt.md").read_bytes(),
            CHANGELOG_37: (KUBERNETES / "CHANGELOG-1.37-excerpt.md").read_bytes(),
            "CHANGELOG/CHANGELOG-1.38.md": b"# v1.38.0-alpha.1\n\nOut of range.\n",
        },
        when="2026-09-30T03:30:57+02:00",
    )


def test_changelogs_speak_for_their_release_and_hold_no_download_rows(
    conn: Conn, tmp_path: Path, make_git_repo: Callable[[str], Any]
) -> None:
    head = _kubernetes(make_git_repo)
    files = ((22, CHANGELOG_22), (37, CHANGELOG_37))
    changelogs = ChangelogGroup(
        "release_record", "kubernetes", Snapshot(None, "master", head), files
    )
    scope = Scope("test", (), (), changelogs=changelogs)

    first = _ingest(conn, tmp_path, scope)
    second = _ingest(conn, tmp_path, scope)

    assert (first.failures, first.documents) == ([], {"release_record": 2})
    # [R, R] set at insert; from the head commit's committer time, open (decision 6).
    head_time = datetime(2026, 9, 30, 1, 30, 57, tzinfo=UTC)
    assert _windows(conn, "changelog:1.22") == [(22, 22, head_time, None)]
    assert _windows(conn, "changelog:1.37") == [(37, 37, head_time, None)]
    assert find_document(conn, "changelog:1.38") is None  # never listed, never read
    # No chunk holds a sha512 row (done when): the two files hold 68 (grep -c, by hand).
    counts = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE c.text ~ '[0-9a-f]{128}') FROM chunks c "
        "JOIN document_versions v ON v.id = c.document_version_id "
        "JOIN documents d ON d.id = v.document_id WHERE d.canonical_id LIKE 'changelog:%'"
    ).fetchone()
    assert counts is not None and counts[0] > 0 and counts[1] == 0
    (text,) = conn.execute(
        "SELECT c.text FROM chunks c JOIN document_versions v ON v.id = c.document_version_id "
        "JOIN documents d ON d.id = v.document_id "
        "WHERE d.canonical_id = 'changelog:1.37' AND c.ordinal = 0"
    ).fetchone() or (None,)
    assert text.startswith(
        "Source: release_record\nTitle: CHANGELOG-1.37\nDocument: changelog:1.37\n"
        "Section: v1.37.1 > Changes by Kind > Feature\n\n- Kubernetes is now built using Go"
    )
    # A re-run adds nothing.
    assert (second.new_documents, second.new_versions, second.closed_versions) == (0, 0, 0)
    assert (second.unchanged_documents, second.new_chunks, second.failures) == (2, 0, [])
