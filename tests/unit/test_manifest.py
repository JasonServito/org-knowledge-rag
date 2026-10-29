from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from orgknow.ingestion.manifest import (
    BlogGroup,
    DateGroup,
    ReleaseGroup,
    Scope,
    Snapshot,
    load_normalization,
    load_releases,
    load_repo_urls,
    load_scope,
)

REAL_MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"
REAL_LOCK = Path(__file__).parents[2] / "config" / "corpus_manifest.lock.yaml"

# Three real entries from the manifest. Each bad list below changes one thing.
R24 = '{version: "1.24", release_date: 2022-05-03, end_of_life: 2023-07-28}'
R25 = '{version: "1.25", release_date: 2022-08-23, end_of_life: 2023-10-28}'
R26 = '{version: "1.26", release_date: 2022-12-08, end_of_life: 2024-02-28}'


def _write_manifest(tmp_path: Path, entries: list[str], latest: str = "1.26") -> Path:
    lines = ["releases:", '  first: "1.24"', f'  latest: "{latest}"', "  list:"]
    lines += [f"    - {entry}" for entry in entries]
    path = tmp_path / "manifest.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_loads_the_real_manifest() -> None:
    releases = load_releases(REAL_MANIFEST)

    # Expected values read by hand from config/corpus_manifest.yaml in the S03-R1 design review.
    assert len(releases) == 18
    assert [r.minor for r in releases] == list(range(20, 38))
    by_version = {r.version: r for r in releases}
    assert by_version["1.24"].minor == 24
    assert by_version["1.24"].release_date == date(2022, 5, 3)
    assert by_version["1.24"].end_of_life_date == date(2023, 7, 28)
    assert by_version["1.34"].end_of_life_date == date(2026, 10, 27)


def test_loads_the_repo_urls_of_the_real_manifest() -> None:
    # Read by hand from config/corpus_manifest.yaml, `repos:` (S04-T6).
    assert load_repo_urls(REAL_MANIFEST) == {
        "website": "https://github.com/kubernetes/website",
        "kubernetes": "https://github.com/kubernetes/kubernetes",
        "enhancements": "https://github.com/kubernetes/enhancements",
        "community": "https://github.com/kubernetes/community",
        "sig-release": "https://github.com/kubernetes/sig-release",
    }


def test_accepts_a_good_small_list(tmp_path: Path) -> None:
    # The control for the tests below: without their one change, the list loads.
    releases = load_releases(_write_manifest(tmp_path, [R24, R25, R26]))

    assert [r.version for r in releases] == ["1.24", "1.25", "1.26"]


def test_rejects_a_missing_release(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"contiguous: 1\.26 follows 1\.24"):
        load_releases(_write_manifest(tmp_path, [R24, R26]))


def test_rejects_a_list_that_stops_before_latest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"releases\.latest \(1\.27\)"):
        load_releases(_write_manifest(tmp_path, [R24, R25, R26], latest="1.27"))


def test_rejects_release_dates_not_ascending(tmp_path: Path) -> None:
    r25_before_r24 = '{version: "1.25", release_date: 2022-04-01, end_of_life: 2023-10-28}'

    with pytest.raises(ValueError, match="strictly ascending"):
        load_releases(_write_manifest(tmp_path, [R24, r25_before_r24, R26]))


def test_rejects_end_of_life_before_release(tmp_path: Path) -> None:
    r25_eol_first = '{version: "1.25", release_date: 2022-08-23, end_of_life: 2022-08-01}'

    with pytest.raises(ValueError, match=r"1\.25: end of life"):
        load_releases(_write_manifest(tmp_path, [R24, r25_eol_first, R26]))


# Unquoted 1.25 is a YAML float, not the string "1.25".
@pytest.mark.parametrize("version", ['"1.25.0"', '"v1.25"', '"1.025"', "1.25"])
def test_rejects_a_version_not_shaped_1_n(tmp_path: Path, version: str) -> None:
    bad = f"{{version: {version}, release_date: 2022-08-23, end_of_life: 2023-10-28}}"

    with pytest.raises(ValidationError, match="version"):
        load_releases(_write_manifest(tmp_path, [R24, bad, R26]))


# --- Scopes and the lock (S04-R1 design review, pinned `scopes:` block) ---


def test_loads_the_s04_scope_at_the_locked_shas() -> None:
    scope = load_scope(REAL_MANIFEST, REAL_LOCK, "s04")

    # Expected values read by hand from config/corpus_manifest.yaml (sources.docs_page.sigs.auth,
    # sources.kep.traced) and config/corpus_manifest.lock.yaml.
    (docs,) = scope.release_groups
    assert (docs.source_type, docs.repo) == ("docs_page", "website")
    assert docs.paths == (
        "content/en/docs/concepts/security/",
        "content/en/docs/reference/access-authn-authz/",
        "content/en/docs/concepts/policy/pod-security-policy.md",
        "content/en/docs/tasks/configure-pod-container/enforce-standards-admission-controller.md",
        "content/en/docs/tasks/configure-pod-container/enforce-standards-namespace-labels.md",
        "content/en/docs/tasks/configure-pod-container/migrate-from-psp.md",
        "content/en/docs/setup/best-practices/enforcing-pod-security-standards.md",
    )
    # Every release 1.24 -> 1.37; the latest has no release branch, so it is `main`.
    assert [s.release for s in docs.snapshots] == list(range(24, 38))
    assert docs.snapshots[0] == Snapshot(
        24, "release-1.24", "98e2db7d9cc710554b486ad56274e362af03b438"
    )
    assert docs.snapshots[-1] == Snapshot(37, "main", "256a1f49419171f6c7fbdb1857146da1c63eb533")
    # The traced KEP only (sources.kep.traced), from master at each release date 1.20 -> 1.37,
    # then head.
    (keps,) = scope.date_groups
    assert (keps.source_type, keps.repo) == ("kep", "enhancements")
    assert keps.paths == ("keps/sig-auth/2579-psp-replacement/",)
    assert [s.release for s in keps.snapshots] == [*range(20, 38), None]
    assert keps.snapshots[0] == Snapshot(20, "master", "2df83383d452cf5dd029de73e1963543dbf37998")
    assert keps.snapshots[-1] == Snapshot(
        None, "master", "4be81e27aef5d252972fd02b5a9479a18982dfe5"
    )
    assert keps.snapshots[-1].label == "head"
    assert docs.snapshots[0].label == "1.24"
    assert scope.blog is None  # no blog in S04
    assert scope.changelogs is None  # no CHANGELOG in S04
    assert scope.github == ()  # no GitHub item in S04


def test_loads_the_full_scope_from_1_20() -> None:
    scope = load_scope(REAL_MANIFEST, REAL_LOCK, "full")

    # Expected values read by hand from config/corpus_manifest.yaml (sources.docs_page.sigs of
    # auth, network and release, in that order; the website entry of sources.release_record;
    # sources.feature_gate_reference) and config/corpus_manifest.lock.yaml (website_releases).
    docs, records, gates = scope.release_groups
    assert (docs.source_type, docs.repo) == ("docs_page", "website")
    assert docs.paths == (
        "content/en/docs/concepts/security/",
        "content/en/docs/reference/access-authn-authz/",
        "content/en/docs/concepts/policy/pod-security-policy.md",
        "content/en/docs/tasks/configure-pod-container/enforce-standards-admission-controller.md",
        "content/en/docs/tasks/configure-pod-container/enforce-standards-namespace-labels.md",
        "content/en/docs/tasks/configure-pod-container/migrate-from-psp.md",
        "content/en/docs/setup/best-practices/enforcing-pod-security-standards.md",
        "content/en/docs/concepts/services-networking/",
        "content/en/docs/reference/networking/",
        "content/en/docs/reference/using-api/deprecation-policy.md",
        "content/en/docs/reference/deprecation-policy.md",
    )
    # Every release 1.20 -> 1.37 (18 snapshots); 1.37 is `main` at the lock head.
    assert [s.release for s in docs.snapshots] == list(range(20, 38))
    assert docs.snapshots[0] == Snapshot(
        20, "release-1.20", "2886f437c434ab156f4306b67adedd162bb25c2d"
    )
    assert docs.snapshots[-1] == Snapshot(37, "main", "256a1f49419171f6c7fbdb1857146da1c63eb533")
    assert (records.source_type, records.repo) == ("release_record", "website")
    assert records.paths == (
        "content/en/releases/",
        "content/en/docs/setup/release/",
        "content/en/docs/reference/using-api/deprecation-guide.md",
    )
    assert records.snapshots == docs.snapshots
    assert (gates.source_type, gates.repo) == ("feature_gate_reference", "website")
    assert gates.paths == (
        "content/en/docs/reference/command-line-tools-reference/feature-gates.md",
        "content/en/docs/reference/command-line-tools-reference/feature-gates/",
        "content/en/docs/reference/command-line-tools-reference/feature-gates-removed.md",
        "content/en/docs/reference/command-line-tools-reference/feature-gates-removed/",
    )
    assert gates.snapshots == docs.snapshots
    # S05-T4: every KEP in sources.kep.sig_dirs, and both governance groups, each from its
    # repo's default branch at every release date, then head (lock: release_date_snapshots).
    keps, community, sig_release = scope.date_groups
    assert keps == DateGroup(
        "kep",
        "enhancements",
        ("keps/sig-release/", "keps/sig-auth/", "keps/sig-network/"),
        keps.snapshots,
    )
    assert (community.source_type, community.repo) == ("governance_doc", "community")
    assert community.paths == (
        "sig-release/README.md",
        "sig-release/charter.md",
        "sig-auth/README.md",
        "sig-auth/charter.md",
        "sig-network/README.md",
        "sig-network/charter.md",
        "contributors/devel/sig-release/",
    )
    assert (sig_release.source_type, sig_release.repo) == ("governance_doc", "sig-release")
    assert sig_release.paths == ("release-engineering/",)
    assert [s.release for s in sig_release.snapshots] == [*range(20, 38), None]
    assert community.snapshots[0] == Snapshot(
        20, "main", "ad91093a4a38e2655e55dcb1fac8ed04eeceae82"
    )
    assert sig_release.snapshots[-1] == Snapshot(
        None, "master", "49d129fa10676ef91d821c006494bfddd5d1fcd2"
    )
    # S05-T5: the blog, one first-parent log of sources.blog_post.paths on website main up to
    # the lock's website head; in scope from 1.20's release date (2020-12-08, 00:00 UTC); the
    # pinned permalink.
    assert scope.blog == BlogGroup(
        "blog_post",
        "website",
        "main",
        "256a1f49419171f6c7fbdb1857146da1c63eb533",
        ("content/en/blog/_posts/",),
        datetime(2020, 12, 8, tzinfo=UTC),
        "/:section/:year/:month/:day/:slug/",
    )
    # S05-T6: the CHANGELOGs (the kubernetes entry of sources.release_record), one file per
    # release 1.20 -> 1.37, all read at the kubernetes lock head: a snapshot of their own, not a
    # website release branch (deferred P2). CHANGELOG-1.38.md exists at the head, but 1.38 isn't a
    # manifest release, so it's never listed.
    changelogs = scope.changelogs
    assert changelogs is not None
    assert (changelogs.source_type, changelogs.repo) == ("release_record", "kubernetes")
    assert changelogs.snapshot == Snapshot(
        None, "master", "7c596ad7938d030a4cab3c1e55b16b7f61cf7ca5"
    )
    assert changelogs.files[0] == (20, "CHANGELOG/CHANGELOG-1.20.md")
    assert changelogs.files[-1] == (37, "CHANGELOG/CHANGELOG-1.37.md")
    assert [release for release, _ in changelogs.files] == list(range(20, 38))
    assert all(path == f"CHANGELOG/CHANGELOG-1.{r}.md" for r, path in changelogs.files)
    # S13-T1: `discussion: all` reads every decision chain's GitHub items (decision_chains).
    assert [item.key for item in scope.github] == [
        "sig-release/discussions/1290",
        "enhancements/issues/2572",
        "enhancements/pull/2567",
        "enhancements/issues/3015",
        "enhancements/pull/3010",
    ]


def test_changelogs_are_read_only_from_the_locked_default_branch(tmp_path: Path) -> None:
    # The lock holds only the default branch's head, so a CHANGELOG entry naming another branch
    # can't be read at the lock's SHA.
    text = REAL_MANIFEST.read_text(encoding="utf-8")
    old = "      branch: master\n"
    assert text.count(old) == 1
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(text.replace(old, "      branch: release-1.37\n"), encoding="utf-8")

    with pytest.raises(ValueError, match=r"kubernetes branch release-1\.37 is not the locked"):
        load_scope(manifest, REAL_LOCK, "full")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("blog_post: all", "blog_post: {from_release: '1.20'}", "blog_post must be `all`"),
        # Hugo never renders a draft, so the publication rules assume drafts are left out.
        ("exclude_drafts: true", "exclude_drafts: false", "exclude_drafts must be true"),
    ],
)
def test_the_blog_scope_is_all_posts_without_drafts(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    text = REAL_MANIFEST.read_text(encoding="utf-8")
    assert old in text
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(text.replace(old, new), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_scope(manifest, REAL_LOCK, "full")


def test_an_unknown_scope_is_refused() -> None:
    with pytest.raises(ValueError, match=r"unknown scope 's99'; the manifest has: s04, full"):
        load_scope(REAL_MANIFEST, REAL_LOCK, "s99")


SNAPSHOTS = (Snapshot(20, "release-1.20", "2886f437c434ab156f4306b67adedd162bb25c2d"),)
REFERENCE = "content/en/docs/reference/"
GUIDE = "content/en/docs/reference/using-api/deprecation-guide.md"


# Each pair of manifest paths matches at least one file in common.
@pytest.mark.parametrize(
    ("docs_path", "record_path"),
    [
        (REFERENCE, GUIDE),  # a folder holding the other group's file
        (GUIDE, "content/en/docs/reference/using-api/"),  # a file inside the other's folder
        (REFERENCE, "content/en/docs/reference/using-api/"),  # a folder inside a folder
        (GUIDE, GUIDE),  # the same file
    ],
)
def test_a_file_that_two_groups_would_read_is_refused(docs_path: str, record_path: str) -> None:
    docs = ReleaseGroup("docs_page", "website", (docs_path,), SNAPSHOTS)
    records = ReleaseGroup("release_record", "website", (record_path,), SNAPSHOTS)

    with pytest.raises(ValueError, match="match the same files") as raised:
        Scope("test", (docs, records), ())

    assert f"docs_page path {docs_path}" in str(raised.value)
    assert f"release_record path {record_path}" in str(raised.value)


def test_loads_the_strip_lists_lowercased() -> None:
    strip = load_normalization(REAL_MANIFEST)

    # From config/corpus_manifest.yaml, normalization.strip_front_matter (linkTitle lowercased).
    assert strip["docs_page"] == {
        "reviewers",
        "weight",
        "linktitle",
        "no_list",
        "simple_list",
        "hide_summary",
        "aliases",
    }
    assert strip["release_record"] == {
        "reviewers",
        "weight",
        "card",
        "linktitle",
        "notoc",
        "sitemap",
        "layout",
        "type",
    }
    assert strip["kep_yaml"] == {"reviewers", "approvers", "editor", "last-updated"}


def test_a_strip_list_with_a_never_strip_key_is_refused(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "normalization:\n"
        "  never_strip: [title, date]\n"
        "  strip_front_matter:\n"
        "    docs_page: [reviewers, Title]\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"never_strip keys: \['title'\]"):
        load_normalization(manifest)
