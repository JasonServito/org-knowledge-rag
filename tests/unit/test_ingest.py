"""Parts of `make ingest` that need no database: the releases check, a document from its chain
of files, and reading the redirect file (from a tiny local git repo).

Expected values are typed by hand from config/corpus_manifest.yaml (release dates, strip lists).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from orgknow.db.models import Release
from orgknow.ingestion.ingest import document_from_chain, read_redirects, release_problems
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


# --- Renames: a chain's ids and aliases (S05-T2) -----------------------------------------------

POLICY_PSP = "content/en/docs/concepts/policy/pod-security-policy.md"
SECURITY_PSP = "content/en/docs/concepts/security/pod-security-policy.md"
DOCS_22_23 = ReleaseGroup(
    "docs_page",
    "website",
    ("content/en/docs/concepts/",),
    (
        Snapshot(22, "release-1.22", "80b4524c3dbe710a20ecdec421804b459e8e0efb"),
        Snapshot(23, "release-1.23", "d93441c06f14d1e952f477021dded2be9ce410e5"),
    ),
)


def test_a_moved_page_is_identified_by_its_first_url() -> None:
    # The PSP page moved from concepts/policy/ to concepts/security/ at 1.23 (spike §4 E).
    chain = [
        (POLICY_PSP, b"---\ntitle: Pod Security Policies\n---\nPSPs are deprecated.\n"),
        (SECURITY_PSP, b"---\ntitle: Pod Security Policies\n---\nPSPs are removed in 1.25.\n"),
    ]

    document = document_from_chain(
        DOCS_22_23, chain, load_normalization(MANIFEST), load_releases(MANIFEST)
    )

    # ADR-002 D4: the canonical id is the first URL; the later URL is an alias.
    assert document.canonical_id == "web:/docs/concepts/policy/pod-security-policy/"
    assert document.aliases == ["web:/docs/concepts/security/pod-security-policy/"]
    assert [
        (v.valid_from_release, v.valid_until_release, v.source_path) for v in document.versions
    ] == [
        (22, 22, POLICY_PSP),
        (23, None, SECURITY_PSP),
    ]


def test_a_move_that_changes_only_stripped_keys_adds_no_version() -> None:
    # 1.36 -> 1.37: the deprecation policy moved, and its new front matter only adds `aliases`
    # (on the docs_page strip list). The open version keeps its old path and snapshot.
    old = "content/en/docs/reference/using-api/deprecation-policy.md"
    new = "content/en/docs/reference/deprecation-policy.md"
    body = b"title: Kubernetes Deprecation Policy\nweight: 40\n---\nThis document details it.\n"
    group = ReleaseGroup(
        "docs_page",
        "website",
        (old, new),
        (
            Snapshot(36, "release-1.36", "1de955ebabe7e17da1ebb4f582635491227f4157"),
            Snapshot(37, "main", "256a1f49419171f6c7fbdb1857146da1c63eb533"),
        ),
    )
    chain = [
        (old, b"---\n" + body),
        (new, b"---\naliases:\n  - /docs/reference/using-api/deprecation-policy/\n" + body),
    ]

    document = document_from_chain(
        group, chain, load_normalization(MANIFEST), load_releases(MANIFEST)
    )

    assert document.canonical_id == "web:/docs/reference/using-api/deprecation-policy/"
    # The front-matter alias is the document's own id, so only the new URL is an alias.
    assert document.aliases == ["web:/docs/reference/deprecation-policy/"]
    assert [(v.valid_from_release, v.valid_until_release) for v in document.versions] == [
        (36, None)
    ]
    assert (document.versions[0].source_path, document.versions[0].snapshot_ref) == (
        old,
        "release-1.36",
    )


# --- The redirect file (S05-T2) ----------------------------------------------------------------


def test_redirects_come_from_static_redirects_before_the_base_file(
    make_git_repo: Callable[[str], Any],
) -> None:
    # Up to 1.33 the site has static/_redirects; from 1.34 only static/_redirects.base (spike §4).
    repo = make_git_repo("website")
    both = repo.commit(
        {
            "static/_redirects": b"/docs/a/  /docs/from-redirects/ 301\n",
            "static/_redirects.base": b"/docs/a/  /docs/from-base/ 301\n",
        }
    )
    base_only = repo.commit({"static/_redirects": None})
    neither = repo.commit({"static/_redirects.base": None})

    def redirects_at(sha: str) -> dict[str, str]:
        return read_redirects(repo.path, Snapshot(34, "release-1.34", sha))

    assert redirects_at(both) == {"/docs/a/": "/docs/from-redirects/"}
    assert redirects_at(base_only) == {"/docs/a/": "/docs/from-base/"}
    assert redirects_at(neither) == {}
