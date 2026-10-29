"""Tests for the S02-T4b spike, spikes/blog_identity.py.

Replace in S04/S05: blog identity is rewritten in src/ with its own tests.
Delete this file then, together with the spike.
"""

import importlib
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

SPIKES = Path(__file__).resolve().parents[2] / "spikes"
PERMALINK = "/:section/:year/:month/:day/:slug/"  # website hugo.toml, unchanged since 1.20


@pytest.fixture(scope="module")
def blog() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(SPIKES))  # blog_identity.py imports its sibling spikes
        yield importlib.import_module("blog_identity")


def day(d: int, hour: int = 0) -> datetime:
    return datetime(2024, 1, d, hour, tzinfo=UTC)


PACIFIC = timezone(timedelta(hours=-8))


def test_front_time(blog: ModuleType) -> None:
    assert blog.front_time(date(2024, 1, 5)) == day(5)  # no offset: the site's timeZone, UTC
    assert blog.front_time("2024-01-05") == day(5)
    evening = blog.front_time(datetime(2024, 1, 4, 20, tzinfo=PACIFIC))
    assert evening == day(5, 4)  # the same instant as 04:00 UTC the next day...
    assert evening.day == 4  # ...but it keeps its own offset, as Hugo does
    assert blog.front_time("soon") is None
    assert blog.front_time(None) is None


def test_hugo_url_front_matter_date_and_slug(blog: ModuleType) -> None:
    meta = {"date": date(2022, 10, 20), "slug": "advanced-server-side-apply"}
    path = "content/en/blog/_posts/2022/advanced-server-side-apply.md"
    assert blog.hugo_url(meta, path, PERMALINK) == "/blog/2022/10/20/advanced-server-side-apply/"


def test_hugo_url_front_matter_url_wins(blog: ModuleType) -> None:
    meta = {"date": date(2019, 3, 7), "slug": "x", "url": "/:section/:year/:month/:slug/"}
    assert blog.hugo_url(meta, "_posts/2019/x.md", PERMALINK) == "/blog/2019/03/x/"
    literal = {"date": date(2020, 6, 1), "url": "/blog/2020/06/Better-Docs-UX"}
    assert blog.hugo_url(literal, "_posts/2020/y.md", PERMALINK) == "/blog/2020/06/better-docs-ux/"


def test_hugo_url_filename_gives_date_and_slug(blog: ModuleType) -> None:
    # Hugo's :filename date handler also sets the slug, when the front matter has none.
    path = "content/en/blog/_posts/2021-04-08-some-post.md"
    assert blog.hugo_url({}, path, PERMALINK) == "/blog/2021/04/08/some-post/"
    assert blog.hugo_url({"slug": "own"}, path, PERMALINK) == "/blog/2021/04/08/own/"
    bundle = "content/en/blog/_posts/2021-04-08-some-post/index.md"  # a bundle's name is its folder
    assert blog.hugo_url({}, bundle, PERMALINK) == "/blog/2021/04/08/some-post/"


def test_hugo_url_title_fallback(blog: ModuleType) -> None:
    # The date came from the front matter, so the filename's slug isn't used: the title is.
    meta = {"date": date(2021, 12, 7), "title": "Kubernetes 1.23: Interview with the Lead"}
    path = "content/en/blog/_posts/2021-12-07-not-used.md"
    expected = "/blog/2021/12/07/kubernetes-1.23-interview-with-the-lead/"
    assert blog.hugo_url(meta, path, PERMALINK) == expected


def test_hugo_url_uses_the_date_as_written(blog: ModuleType) -> None:
    meta = {"date": datetime(2024, 1, 4, 20, tzinfo=PACIFIC), "slug": "x"}  # 04:00 UTC on the 5th
    assert blog.hugo_url(meta, "_posts/2024/x.md", PERMALINK) == "/blog/2024/01/04/x/"
    assert blog.fm_id(meta) == ("2024-01-04", "x")


def test_hugo_url_needs_a_date(blog: ModuleType) -> None:
    assert blog.hugo_url({"slug": "x"}, "_posts/2021/x.md", PERMALINK) is None


def test_fm_id(blog: ModuleType) -> None:
    assert blog.fm_id({"date": date(2024, 1, 5), "slug": "s"}) == ("2024-01-05", "s")
    assert blog.fm_id({"title": "t"}) == (None, None)


@pytest.mark.parametrize(
    ("a", "b", "cause"),
    [
        (("2024-01-05", "s"), ("2024-01-09", "s"), "date"),
        (("2024-01-05", "s"), ("2024-01-05", "t"), "slug"),
        (("2024-01-05", "s"), ("2024-01-09", "t"), "date + slug"),
        ((None, "s"), ("2024-01-05", "s"), "date missing"),
        (("2024-01-05", None), ("2024-01-05", "s"), "slug missing"),
        ((None, "s"), ("2024-01-05", "t"), "date missing + slug"),
        ((None, None), ("2024-01-05", "s"), "date missing + slug missing"),
    ],
)
def test_change_cause(blog: ModuleType, a: tuple[str, str], b: tuple[str, str], cause: str) -> None:
    assert blog.change_cause(a, b) == cause


@pytest.mark.parametrize(
    ("live", "expected"),
    [
        ([(day(10), day(15))], day(15)),  # merged ahead of its date
        ([(day(20, 9), day(15))], day(20, 9)),  # merged after its date
        ([(day(10), None), (day(12), day(11))], day(12)),  # a draft, then undrafted
        ([(day(10), day(15)), (day(14), day(20))], day(20)),  # date moved before publication
        ([(day(10), day(15)), (day(12), None)], None),  # deleted (or drafted) before its date
    ],
)
def test_published_at(
    blog: ModuleType, live: list[tuple[datetime, datetime | None]], expected: datetime | None
) -> None:
    assert blog.published_at(live) == expected


def test_publish_time(blog: ModuleType) -> None:
    path = "content/en/blog/_posts/2024/x.md"
    assert blog.publish_time({"date": date(2024, 1, 15)}, path, day(10)) == day(15)
    assert blog.publish_time(
        {"publishdate": date(2024, 1, 20), "date": date(2024, 1, 15)}, path, day(10)
    ) == day(20)
    assert blog.publish_time({"date": date(2024, 1, 15), "draft": True}, path, day(10)) is None
    assert blog.publish_time({}, path, day(10)) == day(10)  # no date at all: rendered at once


def test_phases(blog: ModuleType) -> None:
    commits = [day(10), day(12), day(15), day(20)]
    assert blog.phases(commits, day(15)) == [
        "superseded before publication",
        "superseded before publication",
        "live at publication",
        "after publication",
    ]
    assert blog.phases(commits, day(14)) == [
        "superseded before publication",
        "live at publication",
        "after publication",
        "after publication",
    ]
    assert blog.phases(commits[:1], None) == ["never public"]


def test_timing(blog: ModuleType) -> None:
    assert blog.timing(day(14), day(15)) == "before publication"
    assert blog.timing(day(15), day(15)) == "before publication"  # the version that goes live
    assert blog.timing(day(16), day(15)) == "after publication"
    assert blog.timing(day(16), None) == "never published"


def test_blog_settings_both_layouts(blog: ModuleType) -> None:
    order = ["date", ":filename", "publishDate", "lastmod"]
    old = {"permalinks": {"blog": PERMALINK}, "frontmatter": {"date": order}}
    new = {"permalinks": {"page": {"blog": PERMALINK}}, "frontmatter": {"date": order}}
    assert blog.blog_settings(old) == blog.blog_settings(new) == (PERMALINK, tuple(order))


def test_coverage(blog: ModuleType) -> None:
    final, old = "/blog/2024/01/15/new/", "/blog/2024/01/10/old/"
    assert blog.coverage(old, final, {old}, {}) == "alias"
    assert blog.coverage(old, final, set(), {old: final}) == "redirect"
    assert blog.coverage(old, final, set(), {old: "/blog/"}) == "none"
    assert blog.coverage(old, final, set(), {}) == "none"


def test_first_public(blog: ModuleType) -> None:
    commits = [day(10), day(12), day(20)]
    assert blog.first_public(commits, day(15)) == 1  # the version committed on the 12th goes live
    assert blog.first_public(commits, None) == 3  # never published: no published commits


def test_d4_id(blog: ModuleType) -> None:
    assert blog.d4_id(("2024-01-05", "s")) == "blog:2024-01-05-s"
    assert blog.d4_id((None, "s")) is None


def test_rule_ids(blog: ModuleType) -> None:
    ids = [(None, "s"), ("2024-01-15", "s"), ("2024-01-16", "s")]  # draft, published, re-dated
    urls = [None, "/blog/2024/01/15/s/", "/blog/2024/01/16/s/"]
    published = {"blog:2024-01-15-s", "blog:2024-01-16-s"}
    assert (
        blog.rule_ids(ids, urls, 1)
        == {
            "D4": ({None, *published}, published),
            "A": ({"blog:2024-01-16-s"}, {"blog:2024-01-16-s"}),  # the latest id, applied backwards
            "B": (set(urls), set(urls[1:])),
        }
    )
    never = blog.rule_ids(ids, urls, 3)
    assert never["A"] == ({"blog:2024-01-16-s"}, set())
    assert never["B"] == (set(urls), set())


def test_a_drifts(blog: ModuleType) -> None:
    ids = [("2024-01-15", "s"), ("2024-01-16", "s")]
    assert blog.a_drifts(ids, 0)  # published as ...-15; the latest version says ...-16
    assert not blog.a_drifts(ids, 1)  # the re-dating came before publication
    assert not blog.a_drifts(ids, 2)  # never published


def test_old_urls(blog: ModuleType) -> None:
    assert blog.old_urls(["/x/", "/a/", "/b/"], 1) == ["/a/"]  # /x/ was before publication
    assert blog.old_urls(["/a/", "/b/", "/a/"], 0) == ["/b/"]  # back to /a/: only /b/ is old
    assert blog.old_urls(["/a/", "/a/"], 0) == []


def test_move_kind(blog: ModuleType) -> None:
    pr_merge = day(21)
    assert blog.move_kind(day(21), pr_merge, "after publication") == "PR #53902"
    assert blog.move_kind(day(5), pr_merge, "before publication") == "other, before publication"


def test_score(blog: ModuleType) -> None:
    ids: dict[str, tuple[set[str | None], set[str | None]]] = {
        "whole": ({"a"}, {"a"}),
        "split before publication": ({"b", "c"}, {"c"}),
        "split after publication": ({"d", "e"}, {"d", "e"}),
        "no id": ({None}, {None}),  # D4 for a post with no slug: never counts as whole
        "never published": ({"f"}, set()),  # left out of the published column
        "shares an id": ({"a"}, {"a"}),  # whole, but "a" is now shared by two posts
    }
    # every commit: whole, never published, shares an id; published: whole, split before, shares.
    assert blog.score("rule", ids, "no") == ["rule", 3, "3 of 5", 1, "no"]
