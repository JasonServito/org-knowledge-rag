"""Tests for the S02-T4a spike, spikes/renames.py.

Replace in S04/S05: rename and identity handling are rewritten in src/ with their own tests.
Delete this file then, together with the spike.
"""

import importlib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

SPIKES = Path(__file__).resolve().parents[2] / "spikes"


@pytest.fixture(scope="module")
def renames() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(SPIKES))  # renames.py imports its siblings fetch.py and measure.py
        yield importlib.import_module("renames")


def test_parse_name_status(renames: ModuleType) -> None:
    change = renames.Change
    out = "R081\0old/a.md\0new/a.md\0A\0x.md\0D\0y.md\0M\0z.md\0"
    assert renames.parse_name_status(out) == [
        change("R", 81, "old/a.md", "new/a.md"),
        change("A", None, None, "x.md"),
        change("D", None, "y.md", None),
        change("M", None, "z.md", "z.md"),
    ]
    # git log --format= -z separates commits with a newline before the next status.
    assert renames.parse_name_status("R100\0a\0b\0\nR099\0c\0d") == [
        change("R", 100, "a", "b"),
        change("R", 99, "c", "d"),
    ]


def test_page_url(renames: ModuleType) -> None:
    url = renames.page_url
    assert url("content/en/docs/concepts/security/rbac.md") == "/docs/concepts/security/rbac/"
    assert url("content/en/docs/reference/networking/_index.md") == "/docs/reference/networking/"
    assert url("content/en/blog/_posts/2026/a-post/index.md") == "/blog/_posts/2026/a-post/"
    assert url("content/en/releases/version-skew-policy.md") == "/releases/version-skew-policy/"
    assert (
        url("content/en/docs/A/APIListChunking.md") == "/docs/a/apilistchunking/"
    )  # Hugo lowercases


def test_parse_redirects(renames: ModuleType) -> None:
    text = "\n".join(
        [
            "# comment",
            "",
            "/docs/old/      /docs/new/   301",
            "/docs/no-slash  /docs/target 302",
            "/docs/old/      /docs/second-rule-loses/ 301",  # Netlify applies the first match
            "/docs/splat/*   /docs/x/:splat 301",  # wildcards and placeholders are skipped
            "/:lang/docs/y/  /:lang/docs/z/ 301",
            "/docs/abs/      https://kubernetes.io/docs/Abs-Target/#section 301",
        ]
    )
    assert renames.parse_redirects(text) == {
        "/docs/old/": "/docs/new/",
        "/docs/no-slash/": "/docs/target/",
        "/docs/abs/": "/docs/abs-target/",
    }


def test_aliases(renames: ModuleType) -> None:
    assert renames.aliases({"aliases": ["/docs/Old/", "/docs/older"]}) == {
        "/docs/old/",
        "/docs/older/",
    }
    assert renames.aliases({"aliases": "/docs/old/"}) == {"/docs/old/"}
    assert renames.aliases({"title": "T"}) == set()
    assert renames.aliases(None) == set()


def test_classify_delete(renames: ModuleType) -> None:
    redirects = {"/a/": "/in/", "/b/": "/out/", "/c/": "/old/", "/d/": "/gone/"}
    classify = renames.classify_delete
    kwargs = {"added_in_scope": {"/in/"}, "added_elsewhere": {"/out/"}, "existing": {"/old/"}}
    assert classify("/a/", redirects, **kwargs) == "missed rename"
    assert classify("/b/", redirects, **kwargs) == "moved out of scope"
    # Redirected to a page that wasn't added in this release: removed, not moved.
    assert classify("/c/", redirects, **kwargs) == "removed, redirected to an older page"
    assert classify("/d/", redirects, **kwargs) == "redirect target not found"
    assert classify("/e/", redirects, **kwargs) == "removed, no redirect"


def test_threshold_counts(renames: ModuleType) -> None:
    # (score, real?) per detected rename at the floor; a pair scored s is found at every t <= s.
    scored = [(100, True), (81, True), (59, True), (40, False), (12, False)]
    assert renames.threshold_counts(scored, (100, 60, 50, 10)) == [
        (100, 1, 1, 0),
        (60, 2, 2, 0),
        (50, 3, 3, 0),
        (10, 5, 3, 2),
    ]
