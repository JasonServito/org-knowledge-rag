"""S13-T1: GitHub items as `discussion` documents (ADR-012 D3; the S13-R1 contract, "Pinned: T1").

- Rendering: the opening post, then `# Comments` with one `## @login · YYYY-MM-DD` per kept post
  in time order (`· reply`, `· review`); bots dropped by login; empty review bodies dropped;
  headings inside a post pushed below its heading (at most level 6); CRLF and CR become LF.
- The version: date-scoped from the last kept post (ADR-002 D3), pinned to its snapshot.
- The fetcher, on `httpx2.MockTransport`: REST lists paged over 2 pages, GraphQL comments and
  replies paged, diff-line comments never requested, the token sent as a bearer header.
- The hash pin: ingest reads only a cached snapshot whose sha256 the lock pins.

All JSON is synthetic and shaped like GitHub's API: no GitHub text is committed (ADR-001). Every
expected value is typed by hand from the contract's rules, never computed by the code under test.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from orgknow.ingestion.chunker import chunk_version
from orgknow.ingestion.github import (
    GithubSnapshotError,
    ItemSnapshot,
    Post,
    canonical_id,
    fetch_item,
    github_client,
    is_bot,
    item_metadata,
    item_version,
    kept_posts,
    last_post_time,
    read_snapshot,
    render,
    save_snapshots,
    snapshot_bytes,
    snapshot_path,
    snapshot_text,
    update_lock,
)
from orgknow.ingestion.manifest import GithubItem, GithubPin, load_github_items, load_releases

ROOT = Path(__file__).parents[2]
RELEASES = load_releases(ROOT / "config" / "corpus_manifest.yaml")
PR = GithubItem("enhancements", "pull", 9001)


def _post(kind: str, author: str, created_at: str, body: str) -> Post:
    return Post.model_validate(
        {"kind": kind, "author": author, "created_at": created_at, "body": body}
    )


def _pull_request() -> ItemSnapshot:
    """A merged PR: 4 human posts (2 by bob on one day, out of order), 3 bots, 1 empty review."""
    return ItemSnapshot.model_validate(
        {
            "kind": "pull",
            "number": 9001,
            "url": "https://github.com/kubernetes/enhancements/pull/9001",
            "title": "KEP-9001: a synthetic proposal",
            "author": "alice",
            "created_at": "2021-03-12T23:30:00Z",
            "closed_at": "2021-04-23T15:38:03Z",
            "merged_at": "2021-04-23T15:38:03Z",
            "merged_by": "k8s-ci-robot",
            "body": "Opening line\r\n\r\n# Why\r\nBecause.\r\n",
            "posts": [
                _post(
                    "comment",
                    "bob",
                    "2021-03-13T09:00:00Z",
                    "# Plan\r\nStep one\r\n\r\n##### Deep\r\nDetail\r\n\r\n```\r\n"
                    "# not a heading\r\n```\r\n",
                ),
                _post("comment", "k8s-ci-robot", "2021-03-13T09:05:00Z", "/assign"),
                _post("comment", "renovate[bot]", "2021-03-13T12:00:00Z", "bump"),
                _post("review", "carol", "2021-03-14T10:00:00Z", "LGTM with nits"),
                _post("review", "dave", "2021-03-14T11:00:00Z", "  \n"),
                _post("comment", "bob", "2021-03-13T08:00:00Z", "First\rsecond"),
                _post("comment", "fejta-bot", "2021-05-01T00:00:00Z", "stale"),
            ],
        }
    )


# The contract's rendering, typed by hand from _pull_request().
PULL_REQUEST_TEXT = """\
# Opening post · @alice · 2021-03-12

Opening line

## Why
Because.

# Comments

## @bob · 2021-03-13

First
second

## @bob · 2021-03-13

### Plan
Step one

###### Deep
Detail

```
# not a heading
```

## @carol · 2021-03-14 · review

LGTM with nits
"""


# --- Rendering -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("login", "expected"),
    [
        ("k8s-ci-robot", True),
        ("k8s-triage-robot", True),
        ("fejta-bot", True),
        ("dependabot[bot]", True),
        ("dims", False),
        ("robotics-fan", False),  # "robot" inside a login isn't the suffix
        ("bot", False),  # the suffix is "-bot", with its hyphen
    ],
)
def test_bots_are_logins_ending_in_robot_bot_or_bracket_bot(login: str, expected: bool) -> None:
    assert is_bot(login) is expected


def test_the_pinned_rendering_of_a_pull_request() -> None:
    assert render(_pull_request()) == PULL_REQUEST_TEXT


def test_kept_posts_drop_bots_and_empty_review_bodies_and_sort_by_time() -> None:
    kept = kept_posts(_pull_request())

    assert [(p.author, p.created_at.isoformat()) for p in kept] == [
        ("bob", "2021-03-13T08:00:00+00:00"),
        ("bob", "2021-03-13T09:00:00+00:00"),
        ("carol", "2021-03-14T10:00:00+00:00"),
    ]


def test_crlf_and_cr_become_lf() -> None:
    text = render(_pull_request())

    assert "\r" not in text
    assert "First\nsecond" in text


def test_a_discussion_renders_replies_in_time_order_with_their_suffix() -> None:
    discussion = ItemSnapshot.model_validate(
        {
            "kind": "discussions",
            "number": 12,
            "url": "https://github.com/kubernetes/sig-release/discussions/12",
            "title": "How often should we release?",
            "author": "erin",
            "created_at": "2020-10-14T20:00:00Z",
            "closed_at": None,
            "body": "Question?",
            "posts": [
                # The API's order: each comment, then its replies.
                _post("comment", "frank", "2020-10-14T21:00:00Z", "Three a year."),
                _post("reply", "erin", "2020-10-16T09:00:00Z", "Why three?"),
                _post("comment", "grace", "2020-10-15T08:00:00Z", "Four."),
                _post("reply", "k8s-triage-robot", "2021-01-01T00:00:00Z", "/lifecycle stale"),
            ],
        }
    )

    assert render(discussion) == (
        "# Opening post · @erin · 2020-10-14\n\n"
        "Question?\n\n"
        "# Comments\n\n"
        "## @frank · 2020-10-14\n\nThree a year.\n\n"
        "## @grace · 2020-10-15\n\nFour.\n\n"
        "## @erin · 2020-10-16 · reply\n\nWhy three?\n"
    )


def test_an_item_with_no_kept_post_has_no_comments_heading() -> None:
    issue = _pull_request().model_copy(update={"kind": "issues", "posts": [], "body": ""})

    assert render(issue) == "# Opening post · @alice · 2021-03-12\n\n\n"


def test_post_dates_are_utc_days() -> None:
    late = _pull_request().model_copy(
        update={"created_at": datetime.fromisoformat("2021-03-12T20:30:00-05:00"), "posts": []}
    )

    assert render(late).startswith("# Opening post · @alice · 2021-03-13\n")


def test_chunks_of_a_rendered_item_carry_each_posts_heading() -> None:
    chunks = chunk_version(
        "gh:enhancements/pull/9001",
        "discussion",
        item_metadata(_pull_request()),
        render(_pull_request()).encode(),
        512,
    )

    # A heading with no text of its own (`# Comments`, bob's second post) makes no chunk.
    assert [c.heading_path for c in chunks] == [
        ["Opening post · @alice · 2021-03-12"],
        ["Opening post · @alice · 2021-03-12", "Why"],
        ["Comments", "@bob · 2021-03-13"],
        ["Comments", "@bob · 2021-03-13", "Plan"],
        ["Comments", "@bob · 2021-03-13", "Plan", "Deep"],
        ["Comments", "@carol · 2021-03-14 · review"],
    ]
    assert chunks[0].text == (
        "Source: discussion\n"
        "Title: KEP-9001: a synthetic proposal\n"
        "Document: gh:enhancements/pull/9001\n"
        "Section: Opening post · @alice · 2021-03-12\n\n"
        "Opening line"
    )


# --- The document and its version ---------------------------------------------------------------


def test_the_metadata_holds_the_items_dates_and_a_prs_merge() -> None:
    assert item_metadata(_pull_request()) == {
        "kind": "pull",
        "number": 9001,
        "url": "https://github.com/kubernetes/enhancements/pull/9001",
        "title": "KEP-9001: a synthetic proposal",
        "author": "alice",
        "created_at": "2021-03-12T23:30:00Z",
        "closed_at": "2021-04-23T15:38:03Z",
        "merged_at": "2021-04-23T15:38:03Z",
        "merged_by": "k8s-ci-robot",
    }


def test_an_issues_metadata_has_no_merge_fields() -> None:
    issue = _pull_request().model_copy(
        update={"kind": "issues", "closed_at": None, "merged_at": None, "merged_by": None}
    )

    assert sorted(item_metadata(issue)) == [
        "author",
        "closed_at",
        "created_at",
        "kind",
        "number",
        "title",
        "url",
    ]


def test_the_id_and_the_cache_path() -> None:
    item = GithubItem("sig-release", "discussions", 1290)

    assert canonical_id(item) == "gh:sig-release/discussions/1290"
    assert snapshot_path(item) == "github/sig-release/discussions/1290.json"


def test_the_last_kept_post_dates_the_version_bots_after_it_dont() -> None:
    # carol's review; fejta-bot's 2021-05-01 comment is dropped, so it doesn't count.
    assert last_post_time(_pull_request()) == datetime(2021, 3, 14, 10, 0, tzinfo=UTC)


def test_a_version_is_date_scoped_from_the_last_kept_post_and_pinned_to_its_snapshot() -> None:
    sha256 = "ab" * 32
    pin = GithubPin(sha256=sha256, fetched_at="2026-10-13T12:00:00Z")

    version = item_version(PR, pin, _pull_request(), RELEASES)

    # 2021-03-14 is after 1.20's release (2020-12-08) and before 1.21's (2021-04-08).
    assert version.valid_from_release == 20
    assert version.valid_from_date == datetime(2021, 3, 14, 10, 0, tzinfo=UTC)
    assert (version.valid_until_release, version.valid_until_date) == (None, None)
    assert (version.claimed_status, version.claimed_stage) == (None, None)
    assert version.source_path == "github/enhancements/pull/9001.json"
    assert version.snapshot_repo == "enhancements"
    assert version.snapshot_ref == "2026-10-13T12:00:00Z"
    assert version.snapshot_sha == "ab" * 20  # the sha256's first 40 hex characters
    assert version.metadata == item_metadata(_pull_request())


def test_the_content_hash_ignores_dropped_posts() -> None:
    pin = GithubPin(sha256="ab" * 32, fetched_at="2026-10-13T12:00:00Z")
    snapshot = _pull_request()
    more_bots = snapshot.model_copy(
        update={
            "posts": [
                *snapshot.posts,
                _post("comment", "k8s-ci-robot", "2021-06-01T00:00:00Z", "x"),
            ]
        }
    )

    first = item_version(PR, pin, snapshot, RELEASES)
    second = item_version(PR, pin, more_bots, RELEASES)

    assert first.content_hash == second.content_hash


# --- The hash pin -------------------------------------------------------------------------------


def _cache_with(tmp_path: Path, snapshot: ItemSnapshot) -> tuple[Path, str]:
    raw = snapshot_bytes(snapshot)
    path = tmp_path / "github" / "enhancements" / "pull" / "9001.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    return tmp_path, hashlib.sha256(raw).hexdigest()


def test_a_snapshot_whose_hash_the_lock_pins_is_read(tmp_path: Path) -> None:
    cache_dir, sha256 = _cache_with(tmp_path, _pull_request())
    pin = GithubPin(sha256=sha256, fetched_at="2026-10-13T12:00:00Z")

    snapshot, got_pin = read_snapshot(cache_dir, GithubItem("enhancements", "pull", 9001, pin))

    assert snapshot == _pull_request()
    assert got_pin == pin


def test_a_snapshot_with_another_hash_stops_with_the_item_named(tmp_path: Path) -> None:
    cache_dir, sha256 = _cache_with(tmp_path, _pull_request())
    pin = GithubPin(sha256="0" * 64, fetched_at="2026-10-13T12:00:00Z")

    with pytest.raises(GithubSnapshotError) as error:
        read_snapshot(cache_dir, GithubItem("enhancements", "pull", 9001, pin))

    assert str(error.value) == (
        f"enhancements/pull/9001: the cached snapshot's sha256 is {sha256}, the lock pins "
        f"{'0' * 64}; run `make fetch-github`"
    )


def test_a_missing_snapshot_stops_with_the_item_named(tmp_path: Path) -> None:
    pin = GithubPin(sha256="0" * 64, fetched_at="2026-10-13T12:00:00Z")

    with pytest.raises(GithubSnapshotError) as error:
        read_snapshot(tmp_path, GithubItem("enhancements", "pull", 9001, pin))

    assert str(error.value) == (
        f"enhancements/pull/9001: no snapshot at "
        f"{tmp_path / 'github/enhancements/pull/9001.json'}; run `make fetch-github`"
    )


def test_an_item_the_lock_doesnt_pin_stops_with_the_item_named(tmp_path: Path) -> None:
    cache_dir, _ = _cache_with(tmp_path, _pull_request())

    with pytest.raises(GithubSnapshotError) as error:
        read_snapshot(cache_dir, GithubItem("enhancements", "pull", 9001))

    assert str(error.value) == (
        "enhancements/pull/9001: the lock pins no snapshot; run `make fetch-github`"
    )


def test_chunking_reads_the_snapshot_only_if_it_is_still_the_versions(tmp_path: Path) -> None:
    cache_dir, sha256 = _cache_with(tmp_path, _pull_request())
    path = cache_dir / "github/enhancements/pull/9001.json"

    assert snapshot_text(path, sha256[:40]) == PULL_REQUEST_TEXT.encode()
    with pytest.raises(ValueError, match="isn't the snapshot this version was stored from"):
        snapshot_text(path, "0" * 40)


# --- The fetcher (httpx2.MockTransport) ----------------------------------------------------------

API = "https://api.test"
TOKEN = SecretStr("test-token")


def _user(login: str) -> dict[str, Any]:
    return {"login": login, "type": "User", "id": 1}


def _rest(routes: dict[str, tuple[Any, str | None]], seen: list[httpx2.Request]) -> httpx2.Client:
    """A client whose transport answers each `path?query` in `routes` with (JSON, next URL)."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        target = request.url.raw_path.decode()
        if target not in routes:
            return httpx2.Response(404, json={"message": "Not Found"})
        body, next_url = routes[target]
        headers = {} if next_url is None else {"Link": f'<{next_url}>; rel="next"'}
        return httpx2.Response(200, json=body, headers=headers)

    return github_client(TOKEN, httpx2.MockTransport(handle))


def _comment(login: str, at: str, body: str) -> dict[str, Any]:
    return {
        "user": _user(login),
        "created_at": at,
        "body": body,
        "id": 5,
        "author_association": "MEMBER",
    }


def test_an_issues_comments_are_paged_over_2_pages() -> None:
    seen: list[httpx2.Request] = []
    base = "/repos/example/repo/issues/7"
    client = _rest(
        {
            base: (
                {
                    "html_url": "https://github.com/example/repo/issues/7",
                    "title": "Track a thing",
                    "user": _user("alice"),
                    "created_at": "2021-01-01T00:00:00Z",
                    "closed_at": None,
                    "body": "Tracking.",
                    "labels": [],
                },
                None,
            ),
            f"{base}/comments?per_page=100": (
                [
                    _comment("bob", "2021-01-02T00:00:00Z", "one"),
                    _comment("k8s-ci-robot", "2021-01-03T00:00:00Z", "two"),
                ],
                f"{API}{base}/comments?per_page=100&page=2",
            ),
            f"{base}/comments?per_page=100&page=2": (
                [_comment("carol", "2021-01-04T00:00:00Z", "three")],
                None,
            ),
        },
        seen,
    )

    snapshot = fetch_item(client, API, "example/repo", GithubItem("repo", "issues", 7))

    assert snapshot == ItemSnapshot.model_validate(
        {
            "kind": "issues",
            "number": 7,
            "url": "https://github.com/example/repo/issues/7",
            "title": "Track a thing",
            "author": "alice",
            "created_at": "2021-01-01T00:00:00Z",
            "closed_at": None,
            "body": "Tracking.",
            "posts": [
                # Bots are kept in the snapshot: rendering drops them.
                _post("comment", "bob", "2021-01-02T00:00:00Z", "one"),
                _post("comment", "k8s-ci-robot", "2021-01-03T00:00:00Z", "two"),
                _post("comment", "carol", "2021-01-04T00:00:00Z", "three"),
            ],
        }
    )
    assert all(r.headers["Authorization"] == "Bearer test-token" for r in seen)


def test_a_prs_reviews_are_paged_and_its_diff_line_comments_never_requested() -> None:
    seen: list[httpx2.Request] = []
    base = "/repos/example/repo"
    client = _rest(
        {
            f"{base}/pulls/8": (
                {
                    "html_url": "https://github.com/example/repo/pull/8",
                    "title": "Do the thing",
                    "user": _user("alice"),
                    "created_at": "2021-02-01T00:00:00Z",
                    "closed_at": "2021-02-10T00:00:00Z",
                    "merged_at": "2021-02-10T00:00:00Z",
                    "merged_by": _user("k8s-ci-robot"),
                    "body": None,  # a PR with no description
                },
                None,
            ),
            f"{base}/issues/8/comments?per_page=100": (
                [_comment("bob", "2021-02-02T00:00:00Z", "/lgtm")],
                None,
            ),
            f"{base}/pulls/8/reviews?per_page=100": (
                [
                    {
                        "user": _user("carol"),
                        "submitted_at": "2021-02-03T00:00:00Z",
                        "body": "",
                        "state": "APPROVED",
                    },
                    {
                        "user": _user("dave"),
                        "submitted_at": "2021-02-04T00:00:00Z",
                        "body": "Nice.",
                        "state": "COMMENTED",
                    },
                ],
                f"{API}{base}/pulls/8/reviews?per_page=100&page=2",
            ),
            f"{base}/pulls/8/reviews?per_page=100&page=2": (
                [
                    {
                        "user": _user("erin"),
                        "submitted_at": "2021-02-05T00:00:00Z",
                        "body": "Ship it",
                        "state": "APPROVED",
                    },
                    # A pending review has no submission time: it was never posted.
                    {
                        "user": _user("frank"),
                        "submitted_at": None,
                        "body": "draft",
                        "state": "PENDING",
                    },
                ],
                None,
            ),
        },
        seen,
    )

    snapshot = fetch_item(client, API, "example/repo", GithubItem("repo", "pull", 8))

    assert (snapshot.merged_at, snapshot.merged_by) == (
        datetime(2021, 2, 10, tzinfo=UTC),
        "k8s-ci-robot",
    )
    assert snapshot.body == ""
    assert [(p.kind, p.author, p.body) for p in snapshot.posts] == [
        ("comment", "bob", "/lgtm"),
        ("review", "carol", ""),
        ("review", "dave", "Nice."),
        ("review", "erin", "Ship it"),
    ]
    assert f"{base}/pulls/8/comments" not in [r.url.path for r in seen]
    assert [r.url.raw_path.decode() for r in seen] == [
        f"{base}/pulls/8",
        f"{base}/issues/8/comments?per_page=100",
        f"{base}/pulls/8/reviews?per_page=100",
        f"{base}/pulls/8/reviews?per_page=100&page=2",
    ]


def _connection(nodes: list[dict[str, Any]], end: str | None) -> dict[str, Any]:
    return {"pageInfo": {"hasNextPage": end is not None, "endCursor": end}, "nodes": nodes}


def _node(login: str | None, at: str, body: str, **more: Any) -> dict[str, Any]:
    author = None if login is None else {"login": login}
    return {"author": author, "createdAt": at, "body": body, **more}


def test_a_discussions_comments_and_replies_are_paged_over_graphql() -> None:
    seen: list[dict[str, Any]] = []
    discussion = {
        "title": "How often should we release?",
        "url": "https://github.com/example/repo/discussions/9",
        "createdAt": "2020-10-14T20:00:00Z",
        "closedAt": None,
        "body": "Question?",
        "author": {"login": "erin"},
    }
    comment_a = _node(
        "frank",
        "2020-10-14T21:00:00Z",
        "A",
        id="A",
        replies=_connection([_node("erin", "2020-10-15T00:00:00Z", "A.1")], "a1"),
    )
    # A deleted account has no author: GitHub shows it as "ghost".
    comment_b = _node(None, "2020-10-16T00:00:00Z", "B", id="B", replies=_connection([], None))
    pages = {
        None: {
            "repository": {"discussion": {**discussion, "comments": _connection([comment_a], "c1")}}
        },
        "c1": {
            "repository": {"discussion": {**discussion, "comments": _connection([comment_b], None)}}
        },
    }

    def handle(request: httpx2.Request) -> httpx2.Response:
        assert request.url == f"{API}/graphql"
        assert request.headers["Authorization"] == "Bearer test-token"
        payload = json.loads(request.content)
        variables = payload["variables"]
        seen.append(variables)
        if "id" in variables:  # the rest of a comment's replies
            assert (variables["id"], variables["after"]) == ("A", "a1")
            replies = _connection([_node("grace", "2020-10-15T01:00:00Z", "A.2")], None)
            return httpx2.Response(200, json={"data": {"node": {"replies": replies}}})
        assert (variables["owner"], variables["name"], variables["number"]) == (
            "example",
            "repo",
            9,
        )
        return httpx2.Response(200, json={"data": pages[variables["after"]]})

    client = github_client(TOKEN, httpx2.MockTransport(handle))

    snapshot = fetch_item(client, API, "example/repo", GithubItem("repo", "discussions", 9))

    assert (snapshot.title, snapshot.author, snapshot.closed_at) == (
        "How often should we release?",
        "erin",
        None,
    )
    assert [(p.kind, p.author, p.body) for p in snapshot.posts] == [
        ("comment", "frank", "A"),
        ("reply", "erin", "A.1"),
        ("reply", "grace", "A.2"),
        ("comment", "ghost", "B"),
    ]
    assert len(seen) == 3  # 2 pages of comments, 1 more page of A's replies


def test_a_graphql_error_is_raised() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"data": None, "errors": [{"message": "Bad credentials"}]})

    client = github_client(TOKEN, httpx2.MockTransport(handle))

    with pytest.raises(ValueError, match="Bad credentials"):
        fetch_item(client, API, "example/repo", GithubItem("repo", "discussions", 9))


# --- Saving snapshots and the lock --------------------------------------------------------------


def test_saving_writes_each_snapshot_and_keeps_the_fetch_time_of_an_unchanged_one(
    tmp_path: Path,
) -> None:
    raw = snapshot_bytes(_pull_request())
    sha256 = hashlib.sha256(raw).hexdigest()
    unchanged = GithubItem("enhancements", "pull", 9001, GithubPin(sha256, "2026-10-01T00:00:00Z"))
    changed = GithubItem("enhancements", "issues", 7, GithubPin("0" * 64, "2026-10-01T00:00:00Z"))
    new = GithubItem("sig-release", "discussions", 12)
    issue = _pull_request().model_copy(update={"kind": "issues", "number": 7})

    pins = save_snapshots(
        tmp_path, [unchanged, changed, new], [_pull_request(), issue, issue], "2026-10-13T12:00:00Z"
    )

    issue_sha = hashlib.sha256(snapshot_bytes(issue)).hexdigest()
    assert pins == {
        "enhancements/pull/9001": GithubPin(sha256, "2026-10-01T00:00:00Z"),
        "enhancements/issues/7": GithubPin(issue_sha, "2026-10-13T12:00:00Z"),
        "sig-release/discussions/12": GithubPin(issue_sha, "2026-10-13T12:00:00Z"),
    }
    assert (tmp_path / "github/enhancements/pull/9001.json").read_bytes() == raw


LOCK = """\
# Generated by spikes/fetch.py (S02-T2). Don't edit by hand; use --relock.
# The single record of corpus SHAs; see the S02-T2 notes in docs/slices/.
schema_version: 0
fetched_at: '2026-09-30T06:09:15Z'
repos:
  website:
    url: https://github.com/kubernetes/website
    default_branch: main
    head: 256a1f49419171f6c7fbdb1857146da1c63eb533
"""


def test_the_lock_gets_a_github_section_and_keeps_everything_else(tmp_path: Path) -> None:
    lock = tmp_path / "lock.yaml"
    lock.write_text(LOCK, encoding="utf-8")

    update_lock(lock, {"enhancements/pull/2567": GithubPin("ab" * 32, "2026-10-13T12:00:00Z")})

    assert lock.read_text(encoding="utf-8") == LOCK + (
        "github:\n"
        "  enhancements/pull/2567:\n"
        f"    sha256: {'ab' * 32}\n"
        "    fetched_at: '2026-10-13T12:00:00Z'\n"
    )


def test_the_manifests_items_come_with_the_locks_pins(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "repos:\n"
        "  enhancements: {url: 'https://github.com/kubernetes/enhancements'}\n"
        "  sig-release: {url: 'https://github.com/kubernetes/sig-release'}\n"
        "decision_chains:\n"
        "  - seed: kep:1\n"
        "    items:\n"
        "      - {repo: sig-release, kind: discussions, number: 12}\n"
        "      - {repo: enhancements, kind: issues, number: 1}\n"
        "  - seed: kep:2\n"
        "    items:\n"
        "      - {repo: enhancements, kind: issues, number: 1}\n",  # listed twice: read once
        encoding="utf-8",
    )
    lock = tmp_path / "lock.yaml"
    lock.write_text(LOCK, encoding="utf-8")
    update_lock(lock, {"enhancements/issues/1": GithubPin("cd" * 32, "2026-10-13T12:00:00Z")})

    assert load_github_items(manifest, lock) == [
        GithubItem("sig-release", "discussions", 12),
        GithubItem("enhancements", "issues", 1, GithubPin("cd" * 32, "2026-10-13T12:00:00Z")),
    ]


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ("{repo: gitlab, kind: issues, number: 1}", "repo gitlab is not a key of repos"),
        ("{repo: enhancements, kind: commits, number: 1}", "kind commits is not one of"),
        ("{repo: enhancements, kind: issues, number: '1'}", "number '1' is not a positive"),
    ],
)
def test_a_bad_item_is_refused(tmp_path: Path, entry: str, problem: str) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "repos:\n  enhancements: {url: 'https://github.com/kubernetes/enhancements'}\n"
        f"decision_chains:\n  - seed: kep:1\n    items:\n      - {entry}\n",
        encoding="utf-8",
    )
    lock = tmp_path / "lock.yaml"
    lock.write_text(LOCK, encoding="utf-8")

    with pytest.raises(ValueError, match=problem):
        load_github_items(manifest, lock)


def test_the_real_manifest_lists_both_chains_items() -> None:
    items = load_github_items(
        ROOT / "config" / "corpus_manifest.yaml", ROOT / "config" / "corpus_manifest.lock.yaml"
    )

    # The S13-R1 contract: chain 1 (kep:2572) and the held-out chain (kep:3015).
    assert [(i.repo, i.kind, i.number) for i in items] == [
        ("sig-release", "discussions", 1290),
        ("enhancements", "issues", 2572),
        ("enhancements", "pull", 2567),
        ("enhancements", "issues", 3015),
        ("enhancements", "pull", 3010),
    ]
