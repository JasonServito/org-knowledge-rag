"""Parts of `make ingest` that need no database: the releases check, a document from its chain
of files (a web page or a feature gate), and reading the redirect file (from a tiny local git
repo).

Expected values are typed by hand from config/corpus_manifest.yaml (release dates, strip lists)
and the contract's gate cases.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from orgknow.db.models import Release, VersionData
from orgknow.ingestion.blog import Entry, publication
from orgknow.ingestion.ingest import (
    Document,
    Summary,
    blog_document,
    document_from_chain,
    gate_document_from_chain,
    governance_document,
    is_gate_file,
    kep_chains,
    kep_document,
    kep_files_state,
    read_redirects,
    release_problems,
    without_duplicate_ids,
)
from orgknow.ingestion.manifest import (
    BlogGroup,
    DateGroup,
    ReleaseGroup,
    Snapshot,
    load_normalization,
    load_releases,
    load_scope,
)
from orgknow.ingestion.normalize import docs_state
from orgknow.ingestion.renames import build_chains, date_link_rules, gate_link_rules

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


# --- Feature gates (S05-T3) --------------------------------------------------------------------

GATES = "content/en/docs/reference/command-line-tools-reference/feature-gates/"
GATE_FIXTURES = ROOT / "tests/fixtures/website_s05/feature-gates"
LOCK = ROOT / "config" / "corpus_manifest.lock.yaml"


def _gate_group(*releases: int) -> ReleaseGroup:
    """The real feature-gate group of the full scope, cut to the given releases."""
    gates = next(
        group
        for group in load_scope(MANIFEST, LOCK, "full").release_groups
        if group.source_type == "feature_gate_reference"
    )
    snapshots = tuple(s for s in gates.snapshots if s.release in releases)
    return ReleaseGroup(gates.source_type, gates.repo, gates.paths, snapshots)


def _gate_documents(group: ReleaseGroup, listings: list[dict[str, bytes]]) -> list[Document]:
    """Chain the gate files with the gate rules (git finds no renames), then derive each gate."""
    types = {path: group.source_type for listing in listings for path in listing}
    chains = build_chains(listings, gate_link_rules(), lambda after, paths: [], types)
    strip, releases = load_normalization(MANIFEST), load_releases(MANIFEST)
    return [
        gate_document_from_chain(
            group,
            [
                None if p is None else (p, listing[p])
                for p, listing in zip(paths, listings, strict=True)
            ],
            strip,
            releases,
        )
        for paths in chains.paths
    ]


def _release_windows(document: Document) -> list[tuple[int, int | None]]:
    return [(v.valid_from_release, v.valid_until_release) for v in document.versions]


def _gate_file(title: str, former_titles: str = "") -> bytes:
    """A gate file shaped as the real ones; `former_titles` is a YAML list line, if any."""
    return (
        f"---\ntitle: {title}\n{former_titles}content_type: feature_gate\n_build:\n"
        "  list: never\n  render: false\n\nstages:\n  - stage: beta\n"
        f'    defaultValue: true\n    fromVersion: "1.33"\n---\nThe {title} gate.\n'
    ).encode()


def test_a_gate_whose_title_is_fixed_in_place_is_one_document() -> None:
    # ServiceAccountNodeAudienceRestriction.md had the title `ServiceAcccount…` (three c's) at
    # 1.33 and 1.34; 1.35 fixed it in the same file. Same path: one document, whose id keeps the
    # typo (ADR-002 D4: the first title), with the fixed title as its alias.
    path = GATES + "ServiceAccountNodeAudienceRestriction.md"
    typo = _gate_file("ServiceAcccountNodeAudienceRestriction")
    fixed = _gate_file("ServiceAccountNodeAudienceRestriction")

    documents = _gate_documents(
        _gate_group(33, 34, 35), [{path: typo}, {path: typo}, {path: fixed}]
    )

    assert [(d.canonical_id, d.source_type, d.aliases) for d in documents] == [
        (
            "gate:ServiceAcccountNodeAudienceRestriction",
            "feature_gate_reference",
            ["gate:ServiceAccountNodeAudienceRestriction"],
        )
    ]
    # The title is in the hash (never stripped), so the fix is a new version.
    assert _release_windows(documents[0]) == [(33, 34), (35, None)]


def test_a_gate_renamed_by_similarity_is_identified_by_its_first_title() -> None:
    # The real files: APIServingWithRoute at 1.32, APIServingWithRoutine at 1.33 (93% similar).
    old, new = GATES + "APIServingWithRoute.md", GATES + "APIServingWithRoutine.md"
    chain = [
        (old, (GATE_FIXTURES / "APIServingWithRoute" / "1.32.md").read_bytes()),
        (new, (GATE_FIXTURES / "APIServingWithRoutine" / "1.33.md").read_bytes()),
    ]

    document = gate_document_from_chain(
        _gate_group(32, 33), chain, load_normalization(MANIFEST), load_releases(MANIFEST)
    )

    assert document.canonical_id == "gate:APIServingWithRoute"
    assert document.aliases == ["gate:APIServingWithRoutine"]
    assert _release_windows(document) == [(32, 32), (33, None)]
    assert [v.source_path for v in document.versions] == [old, new]


def test_former_titles_are_not_aliases() -> None:
    # At 1.37, PodReadyToStartContainersCondition names PodHasNetworkCondition in former_titles,
    # and PodHasNetworkCondition keeps its own file: two documents, no alias, nothing linked.
    net, ready = (
        GATES + "PodHasNetworkCondition.md",
        GATES + "PodReadyToStartContainersCondition.md",
    )
    former = "former_titles:\n  - PodHasNetworkCondition\n"
    listings = [
        {net: _gate_file("PodHasNetworkCondition")},
        {
            net: _gate_file("PodHasNetworkCondition"),
            ready: _gate_file("PodReadyToStartContainersCondition", former),
        },
    ]

    documents = _gate_documents(_gate_group(36, 37), listings)

    assert [(d.canonical_id, d.aliases) for d in documents] == [
        ("gate:PodHasNetworkCondition", []),
        ("gate:PodReadyToStartContainersCondition", []),
    ]
    # Kept in the version's metadata, for later slices.
    assert documents[1].versions[0].metadata["former_titles"] == ["PodHasNetworkCondition"]


def test_a_gates_stages_and_removed_flag_are_in_its_metadata() -> None:
    raw = _gate_file("PodHasNetworkCondition").replace(b"---\nThe", b"removed: true\n---\nThe")

    document = gate_document_from_chain(
        _gate_group(37),
        [(GATES + "PodHasNetworkCondition.md", raw)],
        load_normalization(MANIFEST),
        load_releases(MANIFEST),
    )

    metadata = document.versions[0].metadata
    assert metadata["stages"] == [{"stage": "beta", "defaultValue": True, "fromVersion": "1.33"}]
    assert metadata["removed"] is True
    assert metadata["_build"] == {"list": "never", "render": False}  # stripped, still stored


def test_a_gate_file_without_a_title_fails() -> None:
    raw = b"---\ncontent_type: feature_gate\n---\nNo title.\n"

    with pytest.raises(ValueError, match="a feature gate needs a front-matter title"):
        gate_document_from_chain(
            _gate_group(37),
            [(GATES + "Untitled.md", raw)],
            load_normalization(MANIFEST),
            load_releases(MANIFEST),
        )


@pytest.mark.parametrize(
    ("path", "gate"),
    [
        # The two pages before 1.29: files the manifest names one by one.
        ("content/en/docs/reference/command-line-tools-reference/feature-gates.md", False),
        ("content/en/docs/reference/command-line-tools-reference/feature-gates-removed.md", False),
        # From 1.29, each page is its folder's index.md (a page bundle).
        (GATES + "index.md", False),
        (
            "content/en/docs/reference/command-line-tools-reference/feature-gates-removed/index.md",
            False,
        ),
        # Every other file in the folders is one gate.
        (GATES + "StrictIPCIDRValidation.md", True),
        (GATES + "pod-ready-to-start-containers.md", True),
    ],
)
def test_which_feature_gate_files_are_gates(path: str, gate: bool) -> None:
    assert is_gate_file(_gate_group(37), path) is gate


def test_a_docs_page_is_never_a_gate() -> None:
    assert not is_gate_file(RECORDS, "content/en/docs/setup/release/notes.md")


def _document(canonical_id: str, path: str) -> Document:
    version = VersionData(
        content_hash="a" * 64,
        source_path=path,
        snapshot_repo="website",
        snapshot_ref="main",
        snapshot_sha="0" * 40,
        valid_from_release=37,
        valid_from_date=datetime(2026, 8, 26, tzinfo=UTC),
    )
    return Document(canonical_id, "feature_gate_reference", [version], [])


def test_two_chains_with_one_id_are_an_error_never_a_merge() -> None:
    # Two gate files with one title at one release (0 on real data): two chains, one id.
    first = _document("gate:A", GATES + "A.md")
    second = _document("gate:A", GATES + "a-copy.md")
    other = _document("gate:B", GATES + "B.md")
    summary = Summary()

    kept = without_duplicate_ids([first, other, second], summary)

    assert kept == [other]
    assert summary.failures == [
        f"gate:A: 2 chains have this id, so none is stored (first files: {GATES}A.md, "
        f"{GATES}a-copy.md)"
    ]


# --- KEPs and governance docs (S05-T4) --------------------------------------------------------

# Enhancements `master` at the 1.20 and 1.21 release dates (config/corpus_manifest.lock.yaml).
AT_20 = Snapshot(20, "master", "2df83383d452cf5dd029de73e1963543dbf37998")
AT_21 = Snapshot(21, "master", "a500df8dc9597839caf8616ec4d03885274593f4")
KEPS = DateGroup("kep", "enhancements", ("keps/sig-auth/", "keps/sig-network/"), (AT_20, AT_21))
KEP_STRIP = load_normalization(MANIFEST)["kep_yaml"]
OLD_KEP = "keps/sig-auth/0014-dynamic-audit-configuration.md"


def test_kep_files_group_into_one_chain_per_kep() -> None:
    # Real paths: KEP-1669's folder was renamed (graceful-termination-... up to the 1.23 snapshot,
    # proxy-terminating-endpoints from 1.24); here the rename falls between two snapshots. The
    # old single-file KEP and sig-network's index exist at 1.20 only (spike §7 R).
    graceful = "keps/sig-network/1669-graceful-termination-local-external-traffic-policy/"
    proxy = "keps/sig-network/1669-proxy-terminating-endpoints/"
    files: dict[str, list[bytes | None]] = {
        graceful + "README.md": [b"r1", None],
        graceful + "kep.yaml": [b"k1", None],
        proxy + "README.md": [None, b"r2"],
        proxy + "kep.yaml": [None, b"k2"],
        OLD_KEP: [b"old", None],
        "keps/sig-network/README.md": [b"# SIG Network KEPs", None],
    }

    chains, skipped = kep_chains(files, KEPS.snapshots)

    # One chain per KEP, whatever its folder is called: the number is the id (ADR-002 D4).
    assert chains == {
        "kep:sig-auth/0014-dynamic-audit-configuration": [{OLD_KEP: b"old"}, {}],
        "kep:1669": [
            {graceful + "README.md": b"r1", graceful + "kep.yaml": b"k1"},
            {proxy + "README.md": b"r2", proxy + "kep.yaml": b"k2"},
        ],
    }
    assert skipped == ["1.20 keps/sig-network/README.md: an index of the SIG's KEPs, not a KEP"]


def test_a_kep_number_with_two_folders_at_one_snapshot_fails() -> None:
    # 0 on real data: 1669, 3257 and 4444 never have both folder names at one snapshot.
    both = {
        "keps/sig-auth/3257-trust-anchor-sets/README.md": b"# A",
        "keps/sig-auth/3257-trust-anchor-sets/kep.yaml": b"title: A\n",
        "keps/sig-auth/3257-cluster-trust-bundles/README.md": b"# B",
        "keps/sig-auth/3257-cluster-trust-bundles/kep.yaml": b"title: B\n",
    }

    with pytest.raises(ValueError, match="2 folders at one snapshot"):
        kep_files_state(both, KEP_STRIP, {"GA": "stable"})


def test_an_old_single_file_kep_is_a_document_of_its_own() -> None:
    raw = (
        ROOT / "tests/fixtures/kep_old/0014-dynamic-audit-configuration-excerpt-1.20.md"
    ).read_bytes()
    # Real merge times (`git log --first-parent -1 --format=%cI`): the last change before the
    # 1.20 snapshot, and its removal before 1.21 (it became the folder 600-dynamic-audit-...).
    written = datetime(2019, 7, 4, 15, 52, 37, tzinfo=UTC)  # 2019-07-04T08:52:37-07:00
    removed = datetime(2020, 12, 22, 14, 2, 28, tzinfo=UTC)  # 273591aa, 2020-12-22T06:02:28-08:00

    document = kep_document(
        KEPS,
        "kep:sig-auth/0014-dynamic-audit-configuration",
        [{OLD_KEP: raw}, {}],
        [written, removed],
        KEP_STRIP,
        {"GA": "stable"},
        load_releases(MANIFEST),
    )

    # S05-R2 decision 3: the id pinned in the contract; claims from the front matter. Its text
    # is from 2019: the date is kept, and the release window starts at 20 (decision 1).
    assert (document.canonical_id, document.source_type, document.aliases) == (
        "kep:sig-auth/0014-dynamic-audit-configuration",
        "kep",
        [],
    )
    (version,) = document.versions
    assert (version.claimed_status, version.claimed_stage) == ("implementable", None)
    assert (version.valid_from_date, version.valid_until_date) == (written, removed)
    assert (version.valid_from_release, version.valid_until_release) == (20, 20)
    assert (version.source_path, version.snapshot_sha) == (OLD_KEP, AT_20.sha)


RELENG = "release-engineering/"
VERSIONING, MOVED = RELENG + "versioning.md", RELENG + "reference/versioning.md"


def test_an_old_path_back_after_its_move_is_a_duplicate_id_error() -> None:
    # 0 on real data: versioning.md moves at 1.37 and a new versioning.md appears at head. Its
    # chain starts at the moved chain's first path, so both have one id: neither is stored.
    snapshots = (
        Snapshot(36, "master", "760d54e82b76a13d1e8423d9143028c8220dfdb2"),
        Snapshot(37, "master", "9ad626fddbec5fe4757dc9882b8b9815f37ae450"),
        Snapshot(None, "master", "49d129fa10676ef91d821c006494bfddd5d1fcd2"),
    )
    group = DateGroup("governance_doc", "sig-release", (RELENG,), snapshots)
    listings = [
        {VERSIONING: b"# Versioning\n"},
        {MOVED: b"# Versioning\n"},
        {MOVED: b"# Versioning\n", VERSIONING: b"# Back\n"},
    ]
    types = {VERSIONING: "governance_doc", MOVED: "governance_doc"}
    # The move is linked by git similarity in real data; here by a stand-in.
    chains = build_chains(
        listings,
        date_link_rules(),
        lambda after, paths: [(VERSIONING, MOVED)] if after == 1 else [],
        types,
    )
    hand_made = [
        [datetime(2026, 2, 13, tzinfo=UTC), None, None],
        [None, None, datetime(2026, 9, 1, tzinfo=UTC)],
    ]
    documents = [
        governance_document(
            group,
            [
                None if p is None else (p, listing[p])
                for p, listing in zip(paths, listings, strict=True)
            ],
            changed_at,
            load_releases(MANIFEST),
        )
        for paths, changed_at in zip(chains.paths, hand_made, strict=True)
    ]
    summary = Summary()

    assert without_duplicate_ids(documents, summary) == []
    assert summary.failures == [
        "sig-release:release-engineering/versioning.md: 2 chains have this id, so none is "
        "stored (first files: release-engineering/versioning.md, release-engineering/versioning.md)"
    ]


# --- Blog posts: the id is the URL at publication; later URLs are aliases (S05-T5) ------------

BLOG = ROOT / "tests" / "fixtures" / "blog"
POSTS = "content/en/blog/_posts/"
BLOG_GROUP = BlogGroup(
    "blog_post",
    "website",
    "main",
    "256a1f49419171f6c7fbdb1857146da1c63eb533",
    (POSTS,),
    datetime(2020, 12, 8, tzinfo=UTC),
    "/:section/:year/:month/:day/:slug/",
)


def _post_entries(history: list[tuple[str, str, str | None]]) -> list[Entry]:
    """(committer time as git prints it, path then, fixture under tests/fixtures/blog/)."""
    strip = load_normalization(MANIFEST)["blog_post"]
    return [
        Entry(
            datetime.fromisoformat(when).astimezone(UTC),
            "c" * 40,
            path,
            None if name is None else docs_state(path, (BLOG / name).read_bytes(), strip),
        )
        for when, path, name in history
    ]


def _blog_document(history: list[tuple[str, str, str | None]]) -> Document:
    entries = _post_entries(history)
    published = publication(entries)
    assert published is not None
    return blog_document(BLOG_GROUP, entries, published, load_releases(MANIFEST))


def test_a_blog_post_is_identified_by_its_url_at_publication() -> None:
    # Spike §5 I, post 5: published at 17:00 UTC as 11-12 (the run contract's pinned id); its
    # last version is dated 11-11, so that URL is an alias. Real commit times and excerpts.
    path = POSTS + "2025-11-12-ingress-nginx-retirement.md"
    document = _blog_document(
        [
            ("2025-11-12T07:49:40-08:00", path, "ingress-nginx-retirement/35d8dfc2-excerpt.md"),
            ("2025-11-12T09:17:42-08:00", path, "ingress-nginx-retirement/2b1598fc-excerpt.md"),
            ("2025-11-12T09:53:41-08:00", path, "ingress-nginx-retirement/fe122837-excerpt.md"),
            (
                "2026-02-21T17:01:37+05:30",
                POSTS + "2025/ingress-nginx-retirement.md",
                "ingress-nginx-retirement/fe122837-excerpt.md",
            ),
        ]
    )

    assert document.canonical_id == "web:/blog/2025/11/12/ingress-nginx-retirement/"
    assert document.aliases == ["web:/blog/2025/11/11/ingress-nginx-retirement/"]
    assert document.source_type == "blog_post"
    assert len(document.versions) == 3  # the year-folder move (R100) adds none


def test_a_blog_url_changed_by_a_rename_is_an_alias() -> None:
    # Spike §5 I, post 4: published as 09-23 (`date: draft`, so the bundle folder's date), then
    # renamed and dated 10-06 (website `_redirects.base` maps the old URL to the new one).
    folder = "headlamp-karpenter-plugin"
    document = _blog_document(
        [
            (
                "2025-10-05T09:54:57-07:00",
                POSTS + f"2025-09-23-{folder}/index.md",
                f"{folder}/e5c44148-excerpt.md",
            ),
            (
                "2025-10-06T18:23:12+01:00",
                POSTS + f"2025-10-06-{folder}/index.md",
                f"{folder}/5eaca101-excerpt.md",
            ),
        ]
    )

    assert document.canonical_id == (
        "web:/blog/2025/09/23/introducing-headlamp-plugin-for-karpenter/"
    )
    assert document.aliases == ["web:/blog/2025/10/06/introducing-headlamp-plugin-for-karpenter/"]


def test_a_front_matter_alias_equal_to_the_id_is_skipped() -> None:
    # Spike §5 I, post 6: published as 02-26, re-dated 05-15. The new version's `aliases` list
    # the old URL twice (with and without a slash): both are the id, so neither is an alias.
    path = POSTS + "2026/ccm-metric-route-sync-total.md"
    document = _blog_document(
        [
            ("2026-04-22T11:13:14-07:00", path, "ccm-metric-route-sync-total/02ab95c9-excerpt.md"),
            ("2026-05-16T00:18:30+05:30", path, "ccm-metric-route-sync-total/73f7fa85-excerpt.md"),
        ]
    )

    assert document.canonical_id == "web:/blog/2026/02/26/ccm-new-metric-route-sync-total/"
    assert document.aliases == ["web:/blog/2026/05/15/ccm-new-metric-route-sync-total/"]
