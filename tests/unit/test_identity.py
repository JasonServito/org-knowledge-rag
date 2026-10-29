"""Canonical ids (ADR-002 D4; the run plan's pinned formats)."""

import pytest

from orgknow.ingestion.identity import (
    alias_id,
    blog_canonical_id,
    changelog_canonical_id,
    docs_canonical_id,
    gate_canonical_id,
    governance_canonical_id,
    kep_canonical_id,
    kep_file_canonical_id,
)


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


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # A KEP folder's README.md and kep.yaml: the folder's number (ADR-002 D4).
        ("keps/sig-auth/2579-psp-replacement/README.md", "kep:2579"),
        ("keps/sig-auth/2579-psp-replacement/kep.yaml", "kep:2579"),
        # KEP-1669's two real folder names (never present together): one id.
        ("keps/sig-network/1669-proxy-terminating-endpoints/README.md", "kep:1669"),
        (
            "keps/sig-network/1669-graceful-termination-local-external-traffic-policy/kep.yaml",
            "kep:1669",
        ),
        # An old single-file KEP at 1.20 (S05-R2 decision 3, pinned): its path under keps/.
        (
            "keps/sig-auth/0014-dynamic-audit-configuration.md",
            "kep:sig-auth/0014-dynamic-audit-configuration",
        ),
        ("keps/sig-network/0007-pod-ready++.md", "kep:sig-network/0007-pod-ready++"),
    ],
)
def test_kep_file_canonical_id(path: str, expected: str) -> None:
    assert kep_file_canonical_id(path) == expected


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        # The SIG folder's index of its KEPs (spike §7 R).
        ("keps/sig-network/README.md", "an index of the SIG's KEPs"),
        ("keps/sig-auth/OWNERS", "not a KEP"),
        ("keps/sig-auth/5681-conditional-authorization/images/overview.md", "not a KEP"),
        ("keps/sig-auth/psp-replacement/README.md", "doesn't start with its number"),
    ],
)
def test_a_file_that_is_no_kep_has_no_kep_id(path: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        kep_file_canonical_id(path)


@pytest.mark.parametrize(
    ("repo", "path", "expected"),
    [
        # The run plan's pinned ids: the repo name, then the repo path (ADR-002 D4).
        (
            "sig-release",
            "release-engineering/versioning.md",
            "sig-release:release-engineering/versioning.md",
        ),
        ("community", "sig-auth/charter.md", "community:sig-auth/charter.md"),
    ],
)
def test_governance_canonical_id(repo: str, path: str, expected: str) -> None:
    assert governance_canonical_id(repo, path) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("StrictIPCIDRValidation", "gate:StrictIPCIDRValidation"),
        # As written: case kept, and a typo kept (the 1.33 title of a gate fixed at 1.35).
        ("ServiceAcccountNodeAudienceRestriction", "gate:ServiceAcccountNodeAudienceRestriction"),
        ("csiMigrationRBD", "gate:csiMigrationRBD"),
    ],
)
def test_gate_canonical_id(title: str, expected: str) -> None:
    assert gate_canonical_id(title) == expected


@pytest.mark.parametrize("title", [None, "", "  ", 123])
def test_a_gate_without_a_title_has_no_id(title: object) -> None:
    with pytest.raises(ValueError, match="a feature gate needs a front-matter title"):
        gate_canonical_id(title)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # The run plan's pinned blog id: `web:` + the URL at publication.
        (
            "/blog/2025/11/12/ingress-nginx-retirement/",
            "web:/blog/2025/11/12/ingress-nginx-retirement/",
        ),
        # Normalized like web URLs: lowercase, a trailing slash (a front-matter `url:` has
        # neither, e.g. the PodTopologySpread post's).
        (
            "/blog/2020/05/Introducing-PodTopologySpread",
            "web:/blog/2020/05/introducing-podtopologyspread/",
        ),
    ],
)
def test_blog_canonical_id(url: str, expected: str) -> None:
    assert blog_canonical_id(url) == expected


def test_a_relative_blog_url_has_no_id() -> None:
    with pytest.raises(ValueError, match="not a site path"):
        blog_canonical_id("blog/2020/05/x")


@pytest.mark.parametrize(("release", "expected"), [(20, "changelog:1.20"), (37, "changelog:1.37")])
def test_changelog_canonical_id(release: int, expected: str) -> None:
    # The run plan's pinned id: `changelog:1.R`, for CHANGELOG-1.R.md.
    assert changelog_canonical_id(release) == expected
