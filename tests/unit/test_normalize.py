"""ADR-002 D2: what changes a content hash, and what doesn't."""

import hashlib
from pathlib import Path

import pytest

from orgknow.ingestion.normalize import (
    content_hash,
    docs_state,
    governance_state,
    kep_state,
    single_kep_state,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
# The manifest's docs_page and kep_yaml strip lists (config/corpus_manifest.yaml), lowercased.
DOCS_STRIP = frozenset(
    {"reviewers", "weight", "linktitle", "no_list", "simple_list", "hide_summary", "aliases"}
)
KEP_STRIP = frozenset({"reviewers", "approvers", "editor", "last-updated"})
SYNONYMS = {"GA": "stable"}
PATH = "content/en/docs/concepts/security/example.md"
README = "keps/sig-auth/2579-psp-replacement/README.md"

PAGE = b"""---
title: Example
reviewers:
- alice
content_type: concept
---

See [RBAC](/docs/reference/access-authn-authz/rbac/) for details.
"""


def _hash(text: bytes) -> str:
    return docs_state(PATH, text, DOCS_STRIP).content_hash


def test_hash_formula_is_pinned() -> None:
    # Expected value from coreutils, not from the code under test:
    #   printf '{"title": "T"}\nHello [docs] world' | sha256sum
    # Kept front matter as sorted JSON, a newline, then the body with link targets dropped and
    # whitespace collapsed. Changing the formula re-hashes every stored version.
    got = content_hash(
        {"title": "T", "Reviewers": ["a"]}, "Hello [docs](/docs/x/)   world\n", DOCS_STRIP
    )

    assert got == "52e8d0043ad352cca586ec0697228e4a718e60a2dca49828cc5ccc449da9c112"


def test_a_reviewer_only_change_keeps_the_hash() -> None:
    changed = PAGE.replace(b"- alice", b"- alice\n- bob")

    assert _hash(changed) == _hash(PAGE)


def test_strip_keys_match_case_insensitively() -> None:
    # Hugo reads front-matter keys case-insensitively, so `Reviewers` is the same key.
    changed = PAGE.replace(b"reviewers:\n- alice", b"Reviewers:\n- bob")

    assert _hash(changed) == _hash(PAGE)


def test_a_link_target_only_change_keeps_the_hash() -> None:
    inline = PAGE.replace(b"(/docs/reference/access-authn-authz/rbac/)", b"(/docs/rbac/)")
    definition_a = PAGE + b"\n[psa]: /docs/concepts/security/pod-security-admission/\n"
    definition_b = PAGE + b"\n[psa]: https://example.com/psa\n"

    assert _hash(inline) == _hash(PAGE)
    assert _hash(definition_a) == _hash(definition_b)


def test_a_whitespace_only_change_keeps_the_hash() -> None:
    changed = PAGE.replace(b"See [RBAC]", b"See\n\n   [RBAC]")

    assert _hash(changed) == _hash(PAGE)


def test_a_body_change_changes_the_hash() -> None:
    changed = PAGE.replace(b"for details", b"for the details")

    assert _hash(changed) != _hash(PAGE)


def test_a_kept_front_matter_change_changes_the_hash() -> None:
    changed = PAGE.replace(b"title: Example", b"title: Another example")

    assert _hash(changed) != _hash(PAGE)


def test_bom_crlf_and_leading_blank_lines_equal_plain_lf_input() -> None:
    windows = b"\xef\xbb\xbf" + PAGE.replace(b"\n", b"\r\n")
    leading_blank_lines = b"\n\n" + PAGE

    assert _hash(windows) == _hash(PAGE)
    assert _hash(leading_blank_lines) == _hash(PAGE)
    assert docs_state(PATH, windows, DOCS_STRIP).metadata["title"] == "Example"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (b"No front matter at all.\n", "no front matter"),
        (b"---\ntitle: [unclosed\n---\nBody\n", "not valid YAML"),
        (b"---\n- a list\n---\nBody\n", "not a mapping"),
        (b"---\ntitle: T\n---\n\xff\xfe broken bytes\n", "UTF-8"),
    ],
)
def test_an_unparseable_page_is_refused_with_a_reason(text: bytes, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        docs_state(PATH, text, DOCS_STRIP)


def test_metadata_keeps_stripped_keys_as_json() -> None:
    page = PAGE.replace(b"content_type: concept", b"content_type: concept\ndate: 2021-03-19")

    state = docs_state(PATH, page, DOCS_STRIP)

    # Stripped keys stay in metadata; a YAML date becomes a JSON string.
    assert state.metadata == {
        "title": "Example",
        "reviewers": ["alice"],
        "content_type": "concept",
        "date": "2021-03-19",
    }
    assert state.source_path == PATH
    assert state.claimed_status is None
    assert state.claimed_stage is None


def test_aliases_are_read_from_the_front_matter() -> None:
    page = (FIXTURES / "website_s04" / "rbac" / "excerpt-1.37.md").read_bytes()

    state = docs_state("content/en/docs/reference/access-authn-authz/rbac.md", page, DOCS_STRIP)

    assert state.aliases == ("/rbac/",)
    assert state.metadata["title"] == "Using RBAC Authorization"


# --- KEPs: README + kep.yaml hashed together ------------------------------------------------------


def _kep_yaml(release: str) -> bytes:
    return (FIXTURES / "kep_2579" / f"{release}.kep.yaml").read_bytes()


def test_a_kep_yaml_only_change_is_a_new_hash() -> None:
    # Real files: 1.25 -> 1.26 changed only kep.yaml (status implementable -> implemented).
    before = kep_state(README, b"# KEP-2579\n", _kep_yaml("1.25"), KEP_STRIP, SYNONYMS)
    after = kep_state(README, b"# KEP-2579\n", _kep_yaml("1.26"), KEP_STRIP, SYNONYMS)

    assert before is not None and after is not None
    assert before.content_hash != after.content_hash


def test_a_stripped_kep_yaml_key_keeps_the_hash() -> None:
    edited = _kep_yaml("1.26") + b"last-updated: 2022-09-22\n"

    plain = kep_state(README, b"# KEP-2579\n", _kep_yaml("1.26"), KEP_STRIP, SYNONYMS)
    stamped = kep_state(README, b"# KEP-2579\n", edited, KEP_STRIP, SYNONYMS)

    assert plain is not None and stamped is not None
    assert plain.content_hash == stamped.content_hash


def test_kep_claims_come_from_kep_yaml_and_metadata_keeps_it_all() -> None:
    state = kep_state(README, b"# KEP-2579\n", _kep_yaml("1.26"), KEP_STRIP, SYNONYMS)

    assert state is not None
    assert (state.claimed_status, state.claimed_stage) == ("implemented", "stable")
    assert state.source_path == README
    assert state.metadata["title"] == "PSP Replacement Policy"
    assert state.metadata["kep-number"] == 2579
    assert state.metadata["creation-date"] == "2021-03-19"
    assert state.metadata["approvers"][0] == "@deads2k"  # stripped from the hash, kept here


def test_ga_maps_to_stable_and_other_values_are_stored_as_written() -> None:
    kep_yaml = b"title: T\nstatus: Implemented\nstage: GA\n"

    state = kep_state(README, b"# T\n", kep_yaml, KEP_STRIP, SYNONYMS)

    assert state is not None
    assert (state.claimed_status, state.claimed_stage) == ("Implemented", "stable")


def test_only_the_first_yaml_document_of_kep_yaml_is_read() -> None:
    kep_yaml = b"title: T\nstage: beta\n---\nstage: [this second document is broken\n"

    state = kep_state(README, b"# T\n", kep_yaml, KEP_STRIP, SYNONYMS)

    assert state is not None
    assert state.claimed_stage == "beta"
    assert state.metadata == {"title": "T", "stage": "beta"}


def test_a_kep_needs_both_files() -> None:
    assert kep_state(README, None, None, KEP_STRIP, SYNONYMS) is None
    with pytest.raises(ValueError, match=r"kep\.yaml"):
        kep_state(README, b"# T\n", None, KEP_STRIP, SYNONYMS)
    with pytest.raises(ValueError, match="README"):
        kep_state(README, None, b"title: T\n", KEP_STRIP, SYNONYMS)


# --- Old single-file KEPs and governance docs (S05-T4) -----------------------------------------

OLD_KEP = "keps/sig-auth/0014-dynamic-audit-configuration.md"
# Real lines 1-61 of the old single-file KEP at the 1.20 snapshot: front matter, then the body.
OLD_KEP_RAW = (
    FIXTURES / "kep_old" / "0014-dynamic-audit-configuration-excerpt-1.20.md"
).read_bytes()


def test_an_old_single_file_kep_keeps_its_metadata_and_claims_in_front_matter() -> None:
    state = single_kep_state(OLD_KEP, OLD_KEP_RAW, KEP_STRIP, SYNONYMS)

    # Read by hand from the fixture's front matter (lines 2 and 20); it has no `stage` key.
    assert (state.claimed_status, state.claimed_stage) == ("implementable", None)
    assert state.source_path == OLD_KEP
    assert state.metadata["title"] == "Dynamic Audit Configuration"
    assert state.metadata["creation-date"] == "2018-05-18"
    assert state.metadata["reviewers"][0] == "@tallclair"  # stripped from the hash, kept here


def test_an_old_single_file_kep_is_hashed_with_the_kep_yaml_strip_list() -> None:
    reviewer_added = OLD_KEP_RAW.replace(b"reviewers:\n", b'reviewers:\n  - "@someone"\n')
    retitled = OLD_KEP_RAW.replace(b"# Dynamic Audit Control", b"# Dynamic Audit Control v2")
    assert reviewer_added != OLD_KEP_RAW and retitled != OLD_KEP_RAW

    def _hash(raw: bytes) -> str:
        return single_kep_state(OLD_KEP, raw, KEP_STRIP, SYNONYMS).content_hash

    assert _hash(reviewer_added) == _hash(OLD_KEP_RAW)
    assert _hash(retitled) != _hash(OLD_KEP_RAW)


def test_a_governance_doc_is_hashed_whole_and_its_metadata_holds_only_its_title() -> None:
    text = "# Release Engineering\n\nSee [the handbooks](handbooks/)  for   details.\n"

    state = governance_state("release-engineering/README.md", text, "Release Engineering")

    # No front matter: the hash is the empty JSON object, a newline, then the cleaned text
    # (link target dropped, whitespace collapsed), typed here by hand.
    cleaned = "# Release Engineering See [the handbooks] for details."
    assert state.content_hash == hashlib.sha256(("{}\n" + cleaned).encode()).hexdigest()
    assert state.metadata == {"title": "Release Engineering"}
    assert state.source_path == "release-engineering/README.md"
    assert (state.claimed_status, state.claimed_stage) == (None, None)
