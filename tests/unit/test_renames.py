"""Renames (ADR-002 D4): redirect parsing, the link rules of web pages and gate files, and the
chain builder.

Paths, titles and redirect lines are the real ones of the moves in spike §4 E and G and of the
gate cases in the S05-R1 plan. Page and gate contents are hand-written: the link rules read
only paths, URLs, front-matter `aliases`, `title` and `former_titles`. Expected chains and links
are written by hand from the plan's link rules.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from orgknow.ingestion.renames import (
    Chains,
    Link,
    build_chains,
    date_link_rules,
    gate_link_rules,
    parse_redirects,
    web_link_rules,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"

DOCS = "content/en/docs/"
NET = DOCS + "concepts/services-networking/"
SECURITY = DOCS + "concepts/security/"


def page(title: str, aliases: Sequence[str] = ()) -> bytes:
    """A page with front matter, and `aliases` when given."""
    lines = ["---", f"title: {title}"]
    if aliases:
        lines += ["aliases:", *(f"- {alias}" for alias in aliases)]
    return ("\n".join([*lines, "---", f"About {title}.", ""])).encode()


class FakeSimilarity:
    """git similarity without git: returns the given renames among the paths it's asked about,
    and records every call."""

    def __init__(self, renames: Mapping[int, Sequence[tuple[str, str]]] | None = None) -> None:
        self.renames = renames or {}
        self.calls: list[tuple[int, list[str]]] = []

    def __call__(self, after: int, paths: Sequence[str]) -> list[tuple[str, str]]:
        self.calls.append((after, list(paths)))
        return [(a, b) for a, b in self.renames.get(after, []) if a in paths and b in paths]


def chains_of(
    listings: Sequence[Mapping[str, bytes]],
    redirects: Sequence[Mapping[str, str]] | None = None,
    similar: FakeSimilarity | None = None,
    source_types: Mapping[str, str] | None = None,
) -> Chains:
    """Build chains with the web-page rules. Every file is a docs page unless typed otherwise."""
    every_path = {path for listing in listings for path in listing}
    types = {path: "docs_page" for path in every_path} | dict(source_types or {})
    return build_chains(
        listings,
        web_link_rules(redirects or [{} for _ in listings]),
        similar or FakeSimilarity(),
        types,
    )


# --- Redirect parsing --------------------------------------------------------------------------


def test_the_real_release_redirects_parse_to_normalized_urls() -> None:
    # Lines 495-498 of static/_redirects at 1.21: `<from> <to> <status>`, columns padded.
    text = (FIXTURES / "website_s05" / "redirects" / "excerpt-1.21.txt").read_text()

    assert parse_redirects(text) == {
        "/docs/setup/release/notes/": "/releases/notes/",
        "/docs/setup/release/": "/releases/",
        "/docs/setup/version-skew-policy/": "/releases/version-skew-policy/",
        "/docs/setup/release/version-skew-policy/": "/releases/version-skew-policy/",
    }


def test_comments_wildcards_and_placeholders_are_skipped() -> None:
    text = "\n".join(
        [
            "# set server-side redirects in this file",
            "/docs/admin/resourcequota/*     /docs/concepts/policy/resource-quotas/ 301",
            "/pt/*         /pt-br/:splat  302!",
            "/docs/:lang/old/     /docs/new/ 301",
            "",
            "/docs/only-one-field/",
            "/docs/kept/     /docs/target/ 301",
        ]
    )

    assert parse_redirects(text) == {"/docs/kept/": "/docs/target/"}


def test_the_first_rule_for_a_source_wins() -> None:
    # Netlify applies the first matching rule. The second source differs only in case.
    text = "/docs/Moved/  /docs/first/ 301\n/docs/moved/  /docs/second/ 301\n"

    assert parse_redirects(text) == {"/docs/moved/": "/docs/first/"}


def test_urls_are_normalized() -> None:
    text = "\n".join(
        [
            "/docs/a     https://kubernetes.io/docs/Target/#some-section 301",
            "/docs/b/?x=1     /docs/c?y=2#z 301",
            "/docs/d/     http://kubernetes.io/docs/e 301",
            # Another host keeps its host: it can never be the URL of a page in scope.
            "/docs/f/     https://v1-15.docs.kubernetes.io/docs/f/ 301",
        ]
    )

    assert parse_redirects(text) == {
        "/docs/a/": "/docs/target/",
        "/docs/b/": "/docs/c/",
        "/docs/d/": "/docs/e/",
        "/docs/f/": "https://v1-15.docs.kubernetes.io/docs/f/",
    }


# --- One rule per signal -------------------------------------------------------------------------

OLD_RELEASE = DOCS + "setup/release/"
NEW_RELEASE = "content/en/releases/"


def test_a_redirect_links_the_moved_release_records() -> None:
    # 1.20 -> 1.21: three release records moved to releases/, which also gained 4 new pages.
    # git pairs notes and _index below 50% (spike §4 G); it pairs version skew at 96% (spike §4
    # E), but the redirect file at 1.21 links all three first, so similarity is never asked.
    before = {
        OLD_RELEASE + "_index.md": page("Release notes and version skew"),
        OLD_RELEASE + "notes.md": page("v1.20 Release Notes"),
        OLD_RELEASE + "version-skew-policy.md": page("Kubernetes version and version skew"),
    }
    added = ["download.md", "patch-releases.md", "release-managers.md", "release.md"]
    after = {
        NEW_RELEASE + "_index.md": page("Releases"),
        NEW_RELEASE + "notes.md": page("Notes"),
        NEW_RELEASE + "version-skew-policy.md": page("Version Skew Policy"),
        **{NEW_RELEASE + name: page(name) for name in added},
    }
    text = (FIXTURES / "website_s05" / "redirects" / "excerpt-1.21.txt").read_text()
    similar = FakeSimilarity()

    chains = chains_of([before, after], [{}, parse_redirects(text)], similar)

    assert chains.links == [
        Link(1, OLD_RELEASE + "_index.md", NEW_RELEASE + "_index.md", "redirect"),
        Link(1, OLD_RELEASE + "notes.md", NEW_RELEASE + "notes.md", "redirect"),
        Link(
            1,
            OLD_RELEASE + "version-skew-policy.md",
            NEW_RELEASE + "version-skew-policy.md",
            "redirect",
        ),
    ]
    assert chains.paths == [
        [OLD_RELEASE + "_index.md", NEW_RELEASE + "_index.md"],
        [OLD_RELEASE + "notes.md", NEW_RELEASE + "notes.md"],
        [OLD_RELEASE + "version-skew-policy.md", NEW_RELEASE + "version-skew-policy.md"],
        *([None, NEW_RELEASE + name] for name in added),
    ]
    assert (chains.deleted, chains.added) == ([], [(1, NEW_RELEASE + name) for name in added])
    assert similar.calls == []  # no gone file left unlinked: git is never asked


def test_an_alias_links_the_moved_deprecation_policy() -> None:
    # 1.36 -> 1.37: no redirect; the new page's front matter lists the old URL (spike §4 E).
    old = DOCS + "reference/using-api/deprecation-policy.md"
    new = DOCS + "reference/deprecation-policy.md"
    title = "Kubernetes Deprecation Policy"
    listings = [
        {old: page(title)},
        {new: page(title, aliases=["/docs/reference/using-api/deprecation-policy/"])},
    ]

    chains = chains_of(listings)

    assert chains.links == [Link(1, old, new, "alias")]
    assert chains.paths == [[old, new]]


def test_similarity_links_a_move_no_declared_signal_names() -> None:
    # Real data also has a redirect for this move (static/_redirects at 1.27, line 98), and none
    # of the 6 real moves links by similarity. Here the chain builder gets only the similarity
    # signal: no redirect file, no aliases.
    old, new = NET + "topology-aware-hints.md", NET + "topology-aware-routing.md"
    similar = FakeSimilarity({1: [(old, new)]})  # git: 59% (spike §4 E)

    chains = chains_of([{old: page("Topology Aware Hints")}, {new: page("Routing")}], None, similar)

    assert chains.links == [Link(1, old, new, "similarity")]
    assert chains.paths == [[old, new]]
    assert similar.calls == [(1, [old, new])]


def test_same_url_links_a_move_into_a_page_bundle() -> None:
    # A page bundle's index.md is served at its folder's URL: the URL doesn't change.
    old, new = DOCS + "reference/gates.md", DOCS + "reference/gates/index.md"

    chains = chains_of([{old: page("Gates")}, {new: page("Gates")}])

    assert chains.links == [Link(1, old, new, "same URL")]
    assert chains.paths == [[old, new]]


def test_the_first_rule_that_links_wins_and_similarity_reads_only_what_is_left() -> None:
    old_psp, new_psp = DOCS + "concepts/policy/pod-security-policy.md", SECURITY + "psp.md"
    gone, new = NET + "a.md", NET + "b.md"
    # git would pair the PSP page with b.md; the redirect has already linked it.
    similar = FakeSimilarity({1: [(old_psp, new), (gone, new)]})
    redirects = {"/docs/concepts/policy/pod-security-policy/": "/docs/concepts/security/psp/"}
    listings = [
        {old_psp: page("PSP"), gone: page("A")},
        {new_psp: page("PSP"), new: page("B")},
    ]

    chains = chains_of(listings, [{}, redirects], similar)

    assert chains.links == [
        Link(1, old_psp, new_psp, "redirect"),
        Link(1, gone, new, "similarity"),
    ]
    assert similar.calls == [(1, [gone, new])]


# --- Refused links and unmatched files -----------------------------------------------------------


def test_a_redirect_to_a_page_that_existed_at_r_links_nothing() -> None:
    # 1.28 -> 1.29: overview.md is deleted and redirected to the section index, which existed at
    # 1.28 (real line 204 of static/_redirects at 1.29). cloud-native-security.md is new; git
    # scores the two under 10% (spike §4 G). A removal, not a rename.
    overview, index = SECURITY + "overview.md", SECURITY + "_index.md"
    cloud_native = SECURITY + "cloud-native-security.md"
    redirects = parse_redirects("/docs/concepts/security/overview/ /docs/concepts/security/ 301\n")
    similar = FakeSimilarity()
    listings = [
        {index: page("Security"), overview: page("Overview of Cloud Native Security")},
        {index: page("Security"), cloud_native: page("Cloud Native Security and Kubernetes")},
    ]

    chains = chains_of(listings, [{}, redirects], similar)

    assert chains.links == []
    assert chains.paths == [[index, index], [overview, None], [None, cloud_native]]
    assert (chains.deleted, chains.added) == ([(1, overview)], [(1, cloud_native)])
    assert similar.calls == [(1, [overview, cloud_native])]


def test_a_redirect_to_an_out_of_scope_page_closes_the_chain() -> None:
    # 1.20 -> 1.21: the page moved to tasks/network/, outside the manifest (spike §4 G).
    gone = NET + "add-entries-to-pod-etc-hosts-with-host-aliases.md"
    new = NET + "service-traffic-policy.md"
    redirects = {
        "/docs/concepts/services-networking/add-entries-to-pod-etc-hosts-with-host-aliases/": (
            "/docs/tasks/network/customize-hosts-file-for-pods/"
        )
    }

    chains = chains_of(
        [{gone: page("Host aliases")}, {new: page("Traffic policy")}], [{}, redirects]
    )

    assert chains.links == []
    assert chains.paths == [[gone, None], [None, new]]
    assert (chains.deleted, chains.added) == ([(1, gone)], [(1, new)])


def test_a_page_moved_in_from_out_of_scope_is_a_new_chain() -> None:
    # 1.24 -> 1.25: the old URL's page was outside the manifest (spike §4 G).
    new = DOCS + "reference/networking/ports-and-protocols.md"
    kept = NET + "service.md"
    redirects = {
        "/docs/reference/ports-and-protocols/": "/docs/reference/networking/ports-and-protocols/"
    }

    chains = chains_of(
        [{kept: page("Service")}, {kept: page("Service"), new: page("Ports and Protocols")}],
        [{}, redirects],
    )

    assert chains.links == []
    assert chains.paths == [[kept, kept], [None, new]]
    assert (chains.deleted, chains.added) == ([], [(1, new)])


def test_a_gone_file_claimed_by_two_new_files_is_a_conflict() -> None:
    gone, first, second = NET + "old.md", NET + "first.md", NET + "second.md"
    alias = ["/docs/concepts/services-networking/old/"]
    # git would pick one of them; a file in a conflict is never linked by a later rule.
    similar = FakeSimilarity({1: [(gone, first)]})
    listings = [
        {gone: page("Old")},
        {first: page("First", aliases=alias), second: page("Second", aliases=alias)},
    ]

    chains = chains_of(listings, None, similar)

    assert chains.links == []
    assert chains.conflicts == [Link(1, gone, first, "alias"), Link(1, gone, second, "alias")]
    assert chains.paths == [[gone, None], [None, first], [None, second]]
    assert similar.calls == []


def test_two_gone_files_claiming_one_new_file_are_a_conflict() -> None:
    first, second, new = NET + "first.md", NET + "second.md", NET + "new.md"
    redirects = {
        "/docs/concepts/services-networking/first/": "/docs/concepts/services-networking/new/",
        "/docs/concepts/services-networking/second/": "/docs/concepts/services-networking/new/",
    }

    chains = chains_of(
        [{first: page("First"), second: page("Second")}, {new: page("New")}], [{}, redirects]
    )

    assert chains.links == []
    assert chains.conflicts == [Link(1, first, new, "redirect"), Link(1, second, new, "redirect")]
    assert chains.paths == [[first, None], [second, None], [None, new]]


def test_a_link_between_two_source_types_is_refused() -> None:
    gone, new = NET + "notes.md", NEW_RELEASE + "notes.md"
    redirects = {"/docs/concepts/services-networking/notes/": "/releases/notes/"}

    chains = chains_of(
        [{gone: page("Notes")}, {new: page("Notes")}],
        [{}, redirects],
        source_types={new: "release_record"},
    )

    assert chains.links == []
    assert chains.crossings == [Link(1, gone, new, "redirect")]
    assert chains.paths == [[gone, None], [None, new]]


# --- Chains over many releases -------------------------------------------------------------------


def test_a_page_moved_twice_is_one_chain() -> None:
    a, b, c = NET + "a.md", NET + "b.md", NET + "c.md"
    redirects = [
        {},
        {"/docs/concepts/services-networking/a/": "/docs/concepts/services-networking/b/"},
        {"/docs/concepts/services-networking/b/": "/docs/concepts/services-networking/c/"},
    ]

    chains = chains_of([{a: page("A")}, {b: page("A")}, {c: page("A")}], redirects)

    assert chains.paths == [[a, b, c]]
    assert [link.rule for link in chains.links] == ["redirect", "redirect"]


def test_a_path_back_after_a_gap_continues_its_chain() -> None:
    # As before renames: one path, one document, with no version where the file is absent.
    path = NET + "page.md"

    chains = chains_of([{path: page("Page")}, {}, {path: page("Page")}])

    assert chains.paths == [[path, None, path]]
    assert (chains.deleted, chains.added) == ([(1, path)], [(2, path)])


# --- Gate files (S05-T3) ---------------------------------------------------------------------

GATES = "content/en/docs/reference/command-line-tools-reference/feature-gates/"


def gate(title: str, former_titles: Sequence[str] = (), stage: str = "alpha") -> bytes:
    """A gate file: front matter as the real ones (title, former_titles, stages), one body line."""
    lines = ["---", f"title: {title}"]
    if former_titles:
        lines += ["former_titles:", *(f"  - {name}" for name in former_titles)]
    lines += ["content_type: feature_gate", "stages:", f"  - stage: {stage}"]
    return ("\n".join([*lines, "---", f"The {title} gate.", ""])).encode()


def gate_chains_of(
    listings: Sequence[Mapping[str, bytes]], similar: FakeSimilarity | None = None
) -> Chains:
    """Build chains with the gate rules; every file is a feature gate."""
    every_path = {path for listing in listings for path in listing}
    types = {path: "feature_gate_reference" for path in every_path}
    return build_chains(listings, gate_link_rules(), similar or FakeSimilarity(), types)


def test_the_1_32_file_renames_link_by_title() -> None:
    # 1.31 -> 1.32: the gate files were renamed from kebab case to the gate name (spike §4 E).
    # PodReadyToStartContainersCondition also names PodHasNetworkCondition in former_titles;
    # same title is the earlier rule, so each gate links to its own new file.
    ready, net = "PodReadyToStartContainersCondition", "PodHasNetworkCondition"
    old_ready, new_ready = GATES + "pod-ready-to-start-containers.md", GATES + f"{ready}.md"
    old_net, new_net = GATES + "pod-has-network-condition.md", GATES + f"{net}.md"
    similar = FakeSimilarity()
    listings = [
        {old_ready: gate(ready, [net]), old_net: gate(net)},
        # The file changed in the same release, as 51 of the 345 renamed gate files did at 1.32.
        {new_ready: gate(ready, [net], stage="beta"), new_net: gate(net)},
    ]

    chains = gate_chains_of(listings, similar)

    assert chains.links == [
        Link(1, old_net, new_net, "same title"),
        Link(1, old_ready, new_ready, "same title"),
    ]
    assert chains.paths == [[old_net, new_net], [old_ready, new_ready]]
    assert (chains.deleted, chains.added, chains.conflicts) == ([], [], [])
    assert similar.calls == []  # every gone file linked: git is never asked


def test_former_titles_link_a_gate_whose_old_file_is_gone() -> None:
    old, new = GATES + "OldName.md", GATES + "NewName.md"
    similar = FakeSimilarity()

    chains = gate_chains_of([{old: gate("OldName")}, {new: gate("NewName", ["OldName"])}], similar)

    assert chains.links == [Link(1, old, new, "former title")]
    assert chains.paths == [[old, new]]
    assert similar.calls == []


def test_former_titles_naming_a_gate_that_keeps_its_file_links_nothing() -> None:
    # 1.37's PodReadyToStartContainersCondition names PodHasNetworkCondition, which keeps its own
    # file (and its own stages) in every release: it is never gone, so nothing links.
    net = GATES + "PodHasNetworkCondition.md"
    ready = GATES + "PodReadyToStartContainersCondition.md"
    listings = [
        {net: gate("PodHasNetworkCondition")},
        {
            net: gate("PodHasNetworkCondition"),
            ready: gate("PodReadyToStartContainersCondition", ["PodHasNetworkCondition"]),
        },
    ]

    chains = gate_chains_of(listings)

    assert (chains.links, chains.conflicts) == ([], [])
    assert chains.paths == [[net, net], [None, ready]]
    assert chains.added == [(1, ready)]


def test_a_renamed_title_is_found_by_similarity() -> None:
    # 1.32 -> 1.33: APIServingWithRoute -> APIServingWithRoutine; git scores the pair 93% (spike
    # §4 E). Neither the title nor former_titles names the old gate.
    old, new = GATES + "APIServingWithRoute.md", GATES + "APIServingWithRoutine.md"
    other = GATES + "ServiceAccountNodeAudienceRestriction.md"
    similar = FakeSimilarity({1: [(old, new)]})
    listings = [
        {old: gate("APIServingWithRoute")},
        {new: gate("APIServingWithRoutine"), other: gate("ServiceAcccountNodeAudienceRestriction")},
    ]

    chains = gate_chains_of(listings, similar)

    assert chains.links == [Link(1, old, new, "similarity")]
    assert chains.paths == [[old, new], [None, other]]
    assert similar.calls == [(1, [old, new, other])]


def test_a_title_fixed_in_place_keeps_its_chain() -> None:
    # 1.34 -> 1.35: the typo in the title was fixed in the same file. Same path is the first
    # rule: the file is neither gone nor new, so no other rule is asked.
    path = GATES + "ServiceAccountNodeAudienceRestriction.md"
    similar = FakeSimilarity()
    listings = [
        {path: gate("ServiceAcccountNodeAudienceRestriction")},
        {path: gate("ServiceAcccountNodeAudienceRestriction")},
        {path: gate("ServiceAccountNodeAudienceRestriction")},
    ]

    chains = gate_chains_of(listings, similar)

    assert chains.paths == [[path, path, path]]
    assert (chains.links, chains.deleted, chains.added) == ([], [], [])
    assert similar.calls == []


def test_two_new_gates_with_the_gone_gates_title_are_a_conflict() -> None:
    gone, first, second = GATES + "a.md", GATES + "B.md", GATES + "C.md"

    chains = gate_chains_of([{gone: gate("A")}, {first: gate("A"), second: gate("A")}])

    assert chains.links == []
    assert chains.conflicts == [
        Link(1, gone, first, "same title"),
        Link(1, gone, second, "same title"),
    ]
    assert chains.paths == [[gone, None], [None, first], [None, second]]


# --- Governance docs: date snapshots (S05-T4, S05-R2 decision 2) ------------------------------

RELENG = "release-engineering/"


def date_chains_of(
    listings: Sequence[Mapping[str, bytes]], similar: FakeSimilarity | None = None
) -> Chains:
    """Build chains with the date-snapshot rules; every file is a governance doc."""
    every_path = {path for listing in listings for path in listing}
    types = {path: "governance_doc" for path in every_path}
    return build_chains(listings, date_link_rules(), similar or FakeSimilarity(), types)


def test_governance_files_link_by_same_path_then_similarity() -> None:
    # sig-release PR #2984, between the 1.36 and 1.37 snapshots (git -M50%, in the design review):
    # versioning.md moved into reference/ (98%), handbooks/go.md became go-updates.md (66%),
    # platforms/guide.md was deleted and handbooks/release-manager.md added. README.md stayed.
    # go-updates.md was edited again before `head`. Contents are stand-ins: only paths matter.
    readme, guide = RELENG + "README.md", RELENG + "platforms/guide.md"
    versioning, moved = RELENG + "versioning.md", RELENG + "reference/versioning.md"
    go, go_updates = RELENG + "handbooks/go.md", RELENG + "handbooks/go-updates.md"
    manager = RELENG + "handbooks/release-manager.md"
    at_36 = {readme: b"r", guide: b"p", versioning: b"v", go: b"g"}
    at_37 = {readme: b"r", moved: b"v", go_updates: b"g2", manager: b"m"}
    at_head = {**at_37, go_updates: b"g3"}
    similar = FakeSimilarity({1: [(versioning, moved), (go, go_updates)]})

    chains = date_chains_of([at_36, at_37, at_head], similar)

    # A path at both snapshots stays in its chain, and no declared rule runs: governance docs
    # have no URL, redirect or front matter. Similarity is asked only about the files left.
    assert chains.paths == [
        [readme, readme, readme],
        [go, go_updates, go_updates],
        [guide, None, None],
        [versioning, moved, moved],
        [None, manager, manager],
    ]
    assert [(link.after, link.gone, link.new, link.rule) for link in chains.links] == [
        (1, go, go_updates, "similarity"),
        (1, versioning, moved, "similarity"),
    ]
    assert similar.calls == [(1, [go, guide, versioning, go_updates, manager, moved])]
    assert (chains.deleted, chains.added) == ([(1, guide)], [(1, manager)])


def test_an_old_path_back_after_its_move_starts_a_new_chain() -> None:
    # 0 on real data: versioning.md moves at 1.37 and comes back at head. The new file isn't
    # linked to anything, so it starts a chain whose first path is the moved chain's first path:
    # ingestion then refuses both as one id held by two chains, never a silent merge.
    versioning, moved = RELENG + "versioning.md", RELENG + "reference/versioning.md"
    similar = FakeSimilarity({1: [(versioning, moved)]})

    chains = date_chains_of(
        [{versioning: b"v"}, {moved: b"v"}, {moved: b"v", versioning: b"back"}], similar
    )

    assert chains.paths == [[versioning, moved, moved], [None, None, versioning]]
