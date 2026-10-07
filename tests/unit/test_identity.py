"""Canonical ids (ADR-002 D4; the run contract's pinned formats)."""

import pytest

from orgknow.ingestion.identity import alias_id, docs_canonical_id, kep_canonical_id


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "content/en/docs/concepts/security/pod-security-policy.md",
            "web:/docs/concepts/security/pod-security-policy/",
        ),
        # _index.md (a section) and index.md (a page bundle) become their folder.
        ("content/en/docs/concepts/security/_index.md", "web:/docs/concepts/security/"),
        (
            "content/en/docs/concepts/security/some-bundle/index.md",
            "web:/docs/concepts/security/some-bundle/",
        ),
        # Hugo lowercases URLs.
        (
            "content/en/docs/reference/access-authn-authz/ABAC.md",
            "web:/docs/reference/access-authn-authz/abac/",
        ),
        # Release records outside docs/ (S05-R1, pinned canonical ids).
        ("content/en/releases/version-skew-policy.md", "web:/releases/version-skew-policy/"),
        ("content/en/releases/_index.md", "web:/releases/"),
    ],
)
def test_docs_canonical_id(path: str, expected: str) -> None:
    assert docs_canonical_id(path) == expected


@pytest.mark.parametrize(
    "path", ["content/fr/docs/page.md", "docs/page.md", "content/en/docs/image.svg"]
)
def test_a_path_outside_english_markdown_content_has_no_docs_id(path: str) -> None:
    with pytest.raises(ValueError, match="not an English docs page"):
        docs_canonical_id(path)


@pytest.mark.parametrize(
    ("alias", "expected"),
    [("/rbac/", "web:/rbac/"), ("/RBAC", "web:/rbac/"), ("/docs/old/page/", "web:/docs/old/page/")],
)
def test_alias_id(alias: str, expected: str) -> None:
    assert alias_id(alias) == expected


def test_a_relative_alias_is_refused() -> None:
    # Hugo resolves a relative alias against the page's section; S04 has none (only /rbac/).
    with pytest.raises(ValueError, match="relative alias"):
        alias_id("rbac")


def test_kep_canonical_id() -> None:
    assert kep_canonical_id(2579) == "kep:2579"
