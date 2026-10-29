"""Blog posts (ADR-002 D2-D4, S05-R2 decision 5): the Hugo URL, when a post is published, and
which of its versions are stored.

Histories are built by hand, most from real post excerpts and real commit times (website
`git log --first-parent`). Expected windows are worked out by hand from the manifest's release
dates (1.23 2021-12-07, 1.30 2024-04-17, 1.34 2025-08-27, 1.35 2025-12-17, 1.36 2026-04-22).
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from orgknow.ingestion.blog import (
    Entry,
    Publication,
    due_time,
    hugo_url,
    out_of_scope,
    page_date,
    post_versions,
    publication,
)
from orgknow.ingestion.manifest import SnapshotError, load_releases
from orgknow.ingestion.normalize import FileState, docs_state

ROOT = Path(__file__).parents[2]
RELEASES = load_releases(ROOT / "config" / "corpus_manifest.yaml")
BLOG = ROOT / "tests" / "fixtures" / "blog"
POSTS = "content/en/blog/_posts/"
PERMALINK = "/:section/:year/:month/:day/:slug/"  # the manifest's sources.blog_post.permalink
STRIP = frozenset({"layout", "math"})  # the manifest's blog_post strip list
SINCE = datetime(2020, 12, 8, tzinfo=UTC)  # 1.20's release date


def _utc(text: str) -> datetime:
    """A committer time as git prints it (`%cI`), in UTC."""
    return datetime.fromisoformat(text).astimezone(UTC)


def _state(path: str, raw: bytes) -> FileState:
    return docs_state(path, raw, STRIP)


def _fixture(name: str) -> bytes:
    return (BLOG / name).read_bytes()


def _post(front_matter: str, body: str = "Text.") -> bytes:
    return f"---\n{front_matter}\n---\n\n{body}\n".encode()


def _entry(when: str, path: str, raw: bytes | None, sha: str = "a" * 40) -> Entry:
    return Entry(_utc(when), sha, path, None if raw is None else _state(path, raw))


def _url(name: str, path: str) -> str | None:
    return hugo_url(_state(path, _fixture(name)).metadata, path, PERMALINK)


def _windows(entries: list[Entry]) -> list[tuple[Any, ...]]:
    published = publication(entries)
    assert published is not None
    return [
        (v.valid_from_release, v.valid_until_release, v.valid_from_date, v.valid_until_date)
        for v in post_versions("website", "main", entries, published, RELEASES)
    ]


# --- The URL (spike §5's hand checks) ----------------------------------------------------------


def test_the_title_gives_the_slug_when_there_is_none() -> None:
    # Spike §5 hand check: the post has no `slug` and no `url`; the site serves it here.
    url = _url(
        "kubernetes-1-11-release-interview-excerpt.md",
        POSTS + "2018/kubernetes-1-11-release-interview.md",
    )

    assert url == (
        "/blog/2018/07/16/"
        "how-the-sausage-is-made-the-kubernetes-1.11-release-interview-from-the-kubernetes-podcast/"
    )


@pytest.mark.parametrize(
    ("name", "path", "expected"),
    [
        # `+0000`: a string to PyYAML (no colon in the offset).
        (
            "kubernetes-1.28-blog-excerpt.md",
            "2023/kubernetes-1.28-blog.md",
            "/blog/2023/08/15/kubernetes-v1-28-release/",
        ),
        # `15:00:00-0800`: also a string to PyYAML (no colon in a negative offset).
        (
            "psp-historical-context-excerpt.md",
            "2022/psp-historical-context/index.md",
            "/blog/2022/08/23/podsecuritypolicy-the-historical-context/",
        ),
        # `2025-05-15T16:00:00-08:00` is 00:00 UTC on 05-16: the URL keeps the day as written,
        # as Hugo does (spike §5). The etcd 3.6 post.
        (
            "announcing-etcd-3-6-excerpt.md",
            "2025/announcing-etcd-3-6/index.md",
            "/blog/2025/05/15/announcing-etcd-3.6/",
        ),
        # Milliseconds.
        (
            "image-registry-change-excerpt.md",
            "2023/image-registry-change.md",
            "/blog/2023/03/10/image-registry-redirect/",
        ),
    ],
)
def test_the_date_comes_from_the_front_matter_as_written(
    name: str, path: str, expected: str
) -> None:
    assert _url(name, POSTS + path) == expected


def test_a_front_matter_url_replaces_the_permalink() -> None:
    # As written (Hugo's own case); the canonical id lowercases it.
    url = _url("introducing-podtopologyspread-excerpt.md", POSTS + "2020/x.md")

    assert url == "/blog/2020/05/Introducing-PodTopologySpread"


def test_a_front_matter_url_may_hold_tokens() -> None:
    url = _url("borg-predecessor-to-kubernetes-excerpt.md", POSTS + "2015/x.md")

    assert url == "/blog/2015/04/borg-predecessor-to-kubernetes/"


def test_an_unparseable_date_falls_back_to_the_filename_date() -> None:
    # The karpenter post's first version has `date: draft`; its bundle folder is dated 09-23.
    url = _url(
        "headlamp-karpenter-plugin/e5c44148-excerpt.md",
        POSTS + "2025-09-23-headlamp-karpenter-plugin/index.md",
    )

    assert url == "/blog/2025/09/23/introducing-headlamp-plugin-for-karpenter/"


def test_the_filename_slug_is_used_only_with_the_filename_date() -> None:
    path = POSTS + "2024-02-22-k8s-book-club/index.md"
    no_date = {"title": "A look into the Kubernetes Book Club"}
    dated = {**no_date, "date": "2024-02-23"}

    assert hugo_url(no_date, path, PERMALINK) == "/blog/2024/02/22/k8s-book-club/"
    assert hugo_url(dated, path, PERMALINK) == (
        "/blog/2024/02/23/a-look-into-the-kubernetes-book-club/"
    )


def test_no_date_at_all_gives_no_url() -> None:
    assert hugo_url({"title": "Draft"}, POSTS + "drafts/x.md", PERMALINK) is None


# --- Page date and due time ---------------------------------------------------------------------


def test_the_page_date_order_is_date_then_filename_then_publish_date_then_lastmod() -> None:
    # Hugo's front-matter date order in the site config (spike §5): date, :filename,
    # publishDate, lastmod. Keys are matched case-insensitively.
    path = POSTS + "2024-02-22-k8s-book-club.md"
    later = {"publishDate": "2024-03-01", "lastmod": "2024-03-02"}

    assert page_date({"Date": "2024-02-23", **later}, path) == (
        datetime(2024, 2, 23, tzinfo=UTC),
        None,
    )
    assert page_date(later, path) == (datetime(2024, 2, 22, tzinfo=UTC), "k8s-book-club")
    assert page_date(later, POSTS + "2024/k8s-book-club.md")[0] == datetime(2024, 3, 1, tzinfo=UTC)
    assert page_date({"lastmod": "2024-03-02"}, POSTS + "x.md")[0] == datetime(
        2024, 3, 2, tzinfo=UTC
    )


def test_due_time() -> None:
    path = POSTS + "2025/x.md"
    when = "2025-01-10T12:00:00+00:00"

    # publishDate first, then the page date, then the commit time.
    scheduled = _post("title: X\ndate: 2025-01-15\npublishDate: 2025-01-20")
    assert due_time(_entry(when, path, scheduled)) == datetime(2025, 1, 20, tzinfo=UTC)
    dated = _post("title: X\ndate: 2025-01-15T09:00:00-08:00")
    assert due_time(_entry(when, path, dated)) == datetime(2025, 1, 15, 17, tzinfo=UTC)
    assert due_time(_entry(when, path, _post("title: X"))) == _utc(when)
    # Never due: a draft, or a deleted file.
    assert due_time(_entry(when, path, _post("title: X\ndate: 2025-01-15\ndraft: true"))) is None
    assert due_time(_entry(when, path, None)) is None


# --- Publication and stored versions (ADR-002 D3) -----------------------------------------------


def test_a_version_merged_ahead_of_its_date_starts_at_its_date() -> None:
    # The ingress-nginx-retirement post's real history (spike §5 I, post 5): merged at 15:49 UTC
    # dated 17:00 UTC (12:00-05:00); re-dated at 17:17 to 18:30 UTC; re-dated at 17:53 to the
    # day before, which changed its URL.
    folder = "ingress-nginx-retirement/"
    path = POSTS + "2025-11-12-ingress-nginx-retirement.md"
    entries = [
        _entry("2025-11-12T07:49:40-08:00", path, _fixture(folder + "35d8dfc2-excerpt.md")),
        _entry("2025-11-12T09:17:42-08:00", path, _fixture(folder + "2b1598fc-excerpt.md")),
        _entry("2025-11-12T09:53:41-08:00", path, _fixture(folder + "fe122837-excerpt.md")),
    ]

    # Published when its date passed (17:00), before the next merge (17:17).
    assert publication(entries) == Publication(0, datetime(2025, 11, 12, 17, tzinfo=UTC))
    # valid_from = max(merge, publication) = 17:00, not the merge at 15:49:40; the later
    # versions start at their merges, as after publication a version starts at its commit.
    t1 = datetime(2025, 11, 12, 17, 17, 42, tzinfo=UTC)
    t2 = datetime(2025, 11, 12, 17, 53, 41, tzinfo=UTC)
    assert _windows(entries) == [
        (34, 34, datetime(2025, 11, 12, 17, tzinfo=UTC), t1),
        (34, 34, t1, t2),
        (34, None, t2, None),
    ]


def test_a_version_merged_after_its_date_starts_at_its_merge() -> None:
    # The ccm post: merged on 2026-04-22 (18:13:14 UTC) with a past date, 2026-02-26.
    path = POSTS + "2026/ccm-metric-route-sync-total.md"
    entries = [
        _entry(
            "2026-04-22T11:13:14-07:00",
            path,
            _fixture("ccm-metric-route-sync-total/02ab95c9-excerpt.md"),
        )
    ]

    merged = datetime(2026, 4, 22, 18, 13, 14, tzinfo=UTC)
    assert publication(entries) == Publication(0, merged)
    assert _windows(entries) == [(36, None, merged, None)]


def test_a_version_superseded_before_publication_is_not_stored() -> None:
    # The VAP GA post (`------`): added on 04-20 and edited on 04-23, dated 2024-04-24. The
    # 04-20 text was never public (ADR-002 D3), so only the 04-23 text is stored, from 04-24.
    folder = "validating-admission-policy-ga/"
    path = POSTS + "2024-04-24-validating-admission-policy-ga/index.md"
    entries = [
        _entry("2024-04-20T14:11:16-07:00", path, _fixture(folder + "3a358ed2-excerpt.md")),
        _entry(
            "2024-04-23T05:05:52-07:00", path, _fixture(folder + "2de4371a-excerpt.md"), "b" * 40
        ),
    ]
    assert entries[0].state != entries[1].state

    published = publication(entries)

    assert published == Publication(1, datetime(2024, 4, 24, tzinfo=UTC))
    versions = post_versions("website", "main", entries, published, RELEASES)
    assert [(v.valid_from_release, v.valid_from_date, v.valid_until_date) for v in versions] == [
        (30, datetime(2024, 4, 24, tzinfo=UTC), None)
    ]
    # Its snapshot is the commit that made it: website `main` at that commit, the path then.
    assert (versions[0].snapshot_repo, versions[0].snapshot_ref) == ("website", "main")
    assert (versions[0].snapshot_sha, versions[0].source_path) == ("b" * 40, path)


def test_a_deletion_after_publication_closes_the_open_version() -> None:
    # The 1.23 release interview's real commit times. PR #53902 moved it to a file with no
    # extension, which Hugo doesn't render: its `.md` is deleted at that merge (2026-02-21).
    path = POSTS + "2022-04-29-kubernetes-1.23-release-interview.md"
    first = _fixture("kubernetes-1.23-release-interview/27d1959c-excerpt.md")
    entries = [
        _entry("2022-04-28T08:15:50-07:00", path, first),
        _entry("2022-04-28T11:13:50-07:00", path, first + b"An edit before publication.\n"),
        _entry("2024-04-30T14:48:52-07:00", path, first + b"An edit after publication.\n"),
        _entry("2026-02-21T17:01:37+05:30", path, None),
    ]

    # Due on 04-29 (its date); the 04-28 edit superseded the first text before then.
    assert publication(entries) == Publication(1, datetime(2022, 4, 29, tzinfo=UTC))
    edited = datetime(2024, 4, 30, 21, 48, 52, tzinfo=UTC)
    deleted = datetime(2026, 2, 21, 11, 31, 37, tzinfo=UTC)
    assert _windows(entries) == [
        (23, 30, datetime(2022, 4, 29, tzinfo=UTC), edited),
        (30, 35, edited, deleted),
    ]


def test_a_draft_after_publication_closes_and_a_later_rendered_version_reopens() -> None:
    path = POSTS + "2025/x.md"
    text = "title: X\ndate: 2025-01-15"
    entries = [
        _entry("2025-01-16T00:00:00+00:00", path, _post(text)),
        _entry("2025-02-01T00:00:00+00:00", path, _post(text + "\ndraft: true")),
        _entry("2025-02-03T00:00:00+00:00", path, _post(text)),  # the same text again
    ]

    assert _windows(entries) == [
        (32, 32, datetime(2025, 1, 16, tzinfo=UTC), datetime(2025, 2, 1, tzinfo=UTC)),
        (32, None, datetime(2025, 2, 3, tzinfo=UTC), None),
    ]


def test_a_post_re_dated_into_the_future_keeps_its_first_publication() -> None:
    # A known approximation (S05-R2 plan): after publication a version starts at its
    # commit, even when its new date is later (Hugo would hide it until then).
    path = POSTS + "2025/x.md"
    entries = [
        _entry("2025-01-16T00:00:00+00:00", path, _post("title: X\ndate: 2025-01-15")),
        _entry("2025-02-01T00:00:00+00:00", path, _post("title: X\ndate: 2025-03-01")),
    ]

    assert publication(entries) == Publication(0, datetime(2025, 1, 16, tzinfo=UTC))
    assert _windows(entries) == [
        (32, 32, datetime(2025, 1, 16, tzinfo=UTC), datetime(2025, 2, 1, tzinfo=UTC)),
        (32, None, datetime(2025, 2, 1, tzinfo=UTC), None),
    ]


def test_a_post_never_rendered_is_never_published() -> None:
    path = POSTS + "2023-04-05-kubescape.md"
    # A draft throughout; and a post deleted before its date (the kubescape fragment, renamed
    # a week before its date to a file git doesn't pair with it: spike §5).
    drafts = [_entry("2025-01-16T00:00:00+00:00", path, _post("title: X\ndraft: true"))]
    fragment = [
        _entry("2023-03-20T00:00:00+00:00", path, _post("title: X\ndate: 2023-04-05")),
        _entry("2023-03-28T00:00:00+00:00", path, None),
    ]

    assert publication(drafts) is None
    assert publication(fragment) is None


def test_scope_is_the_page_date_at_publication_from_1_20() -> None:
    path = POSTS + "2020/x.md"
    when = "2020-12-10T00:00:00+00:00"

    assert out_of_scope(_entry(when, path, _post("title: X\ndate: 2020-12-08")), SINCE) is None
    assert out_of_scope(_entry(when, path, _post("title: X\ndate: 2020-12-07")), SINCE) == (
        "dated before"
    )
    # An instant: 23:00 at -08:00 is 07:00 UTC on 12-08.
    late = _post("title: X\ndate: 2020-12-07T23:00:00-08:00")
    assert out_of_scope(_entry(when, path, late), SINCE) is None
    # No page date at all: out of scope (it has no URL either), counted apart (S05-T8).
    assert out_of_scope(_entry(when, path, _post("title: X")), SINCE) == "no date"


def test_a_window_error_names_the_blog_commit_by_its_short_sha() -> None:
    # Hand-made: committer times on main can go backwards. The third commit is dated before the
    # second, so its version can't start after the one it replaces. The error names that
    # commit's short SHA, not "head" (S05-T8).
    path = POSTS + "2025/x.md"
    entries = [
        _entry("2025-01-01T00:00:00+00:00", path, _post("title: X\ndate: 2024-12-31"), "a" * 40),
        _entry("2025-01-03T00:00:00+00:00", path, _post("title: Y\ndate: 2024-12-31"), "b" * 40),
        _entry("2025-01-02T00:00:00+00:00", path, _post("title: Z\ndate: 2024-12-31"), "c" * 40),
    ]
    published = publication(entries)
    assert published is not None

    with pytest.raises(SnapshotError, match="not after the version it replaces") as error:
        post_versions("website", "main", entries, published, RELEASES)
    assert error.value.label == "cccccccc"
