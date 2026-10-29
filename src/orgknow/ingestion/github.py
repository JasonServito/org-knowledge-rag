"""GitHub issues, PRs and discussions as `discussion` documents (S13-T1; ADR-012 D3).

Only the items a decision chain lists in the manifest (`decision_chains`), never others (ADR-001).
Two halves, pinned in the S13-R1 plan ("Pinned: T1"):

- **Fetch** (`make fetch-github`, network, needs GITHUB_TOKEN): each item's data in one snapshot
  shape (`ItemSnapshot`), written to `<corpus cache>/github/<repo>/<kind>/<number>.json`, its
  sha256 and fetch time recorded in the lock's `github:` section. REST for issues and PRs (the
  item, its comments, a PR's reviews), GraphQL for discussions (comments, replies). Every list is
  paged. A PR's comments on diff lines are never fetched: they need the diff to read. Bot posts
  are kept in the snapshot; rendering drops them.
- **Render** (pure; `make ingest` reads only the cached snapshot, checked against the lock):
  `# Opening post · @<author> · <YYYY-MM-DD>` and the item's body, then `# Comments` and one
  `## @<login> · <YYYY-MM-DD>` per kept post in time order (` · reply` for a discussion reply,
  ` · review` for a review body). Kept: posts whose login doesn't end in `-robot`, `-bot` or
  `[bot]`, and review bodies that aren't blank. Headings inside a post are pushed below its
  heading (one level in the opening post, two in a comment; at most level 6). CRLF and CR become
  LF. Dates are UTC.

A version is one snapshot, date-scoped from its last kept post (ADR-002 D3): the stored text was
the live thread from then on.
"""

import hashlib
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from itertools import takewhile
from pathlib import Path
from typing import Any, Literal

import httpx2

# PyYAML ships no type hints; safe_load and safe_dump handle only plain values.
import yaml  # type: ignore[import-untyped]
from pydantic import AwareDatetime, BaseModel, SecretStr

from orgknow.db.models import Release, VersionData
from orgknow.ingestion.chunker import Heading, scan
from orgknow.ingestion.history import Observed, date_history
from orgknow.ingestion.manifest import (
    GithubItem,
    GithubPin,
    Snapshot,
    load_github_items,
    load_repo_urls,
)
from orgknow.ingestion.normalize import FileState, content_hash
from orgknow.settings import Settings

BOT_SUFFIXES = ("-robot", "-bot", "[bot]")
HEADING_SUFFIX = {"comment": "", "reply": " · reply", "review": " · review"}
PER_PAGE = 100  # the most GitHub returns per page, REST and GraphQL


class Post(BaseModel):
    """A comment, a discussion reply or a review, as fetched."""

    kind: Literal["comment", "reply", "review"]
    author: str  # the login; "ghost" for a deleted account
    created_at: AwareDatetime  # a review's submission time
    body: str


class ItemSnapshot(BaseModel):
    """One item as `make fetch-github` stores it: only the fields its document uses."""

    kind: Literal["issues", "pull", "discussions"]
    number: int
    url: str  # the item's page on GitHub
    title: str
    author: str
    created_at: AwareDatetime
    closed_at: AwareDatetime | None
    merged_at: AwareDatetime | None = None  # PRs only
    merged_by: str | None = None  # PRs only: the merge comes from the PR, so a bot's survives
    body: str  # the opening post: an issue's or discussion's, a PR's description
    posts: list[Post]  # in the API's order; rendering sorts them by time


# --- Render (pure) --------------------------------------------------------------------------------


def is_bot(login: str) -> bool:
    """Bots are found by login, never by account type: Prow's bots are typed "User"."""
    return login.endswith(BOT_SUFFIXES)


def kept_posts(snapshot: ItemSnapshot) -> list[Post]:
    """The posts the document keeps, in time order (a stable sort: equal times keep the API's
    order): every post by a login that isn't a bot's, except a review with a blank body."""
    kept = [
        post
        for post in snapshot.posts
        if not is_bot(post.author) and (post.kind != "review" or post.body.strip())
    ]
    return sorted(kept, key=lambda post: post.created_at)


def _day(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%d")


def _demote(body: str, levels: int) -> str:
    """The body with LF line ends and no leading or trailing blank lines, each heading pushed
    `levels` levels down, at most to 6. Headings are the chunker's (`scan`), so a `#` line in a
    code block or an HTML comment is left alone."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n")
    for item in scan(lines):
        if isinstance(item, Heading):
            line = lines[item.line]
            marks = len(line) - len(line.lstrip("#"))
            lines[item.line] = "#" * min(marks + levels, 6) + line[marks:]
    return "\n".join(lines)


def render(snapshot: ItemSnapshot) -> str:
    """The document's text: the opening post, then `# Comments` with each kept post. An item
    with no kept post has no `# Comments` heading."""
    parts = [
        f"# Opening post · @{snapshot.author} · {_day(snapshot.created_at)}",
        _demote(snapshot.body, 1),
    ]
    posts = kept_posts(snapshot)
    if posts:
        parts.append("# Comments")
    for post in posts:
        parts.append(f"## @{post.author} · {_day(post.created_at)}{HEADING_SUFFIX[post.kind]}")
        parts.append(_demote(post.body, 2))
    return "\n\n".join(parts) + "\n"


def last_post_time(snapshot: ItemSnapshot) -> datetime:
    """When the stored text became the live thread: the last kept post's time, or the opening
    post's when none is kept."""
    return max([snapshot.created_at, *(post.created_at for post in kept_posts(snapshot))])


def item_metadata(snapshot: ItemSnapshot) -> dict[str, Any]:
    """The version's metadata: kind, number, url, title, author, created_at, closed_at, and for a
    PR merged_at and merged_by. Times as UTC ISO 8601 strings."""
    fields = {"kind", "number", "url", "title", "author", "created_at", "closed_at"}
    if snapshot.kind == "pull":
        fields |= {"merged_at", "merged_by"}
    metadata: dict[str, Any] = snapshot.model_dump(mode="json", include=fields)
    return metadata


def canonical_id(item: GithubItem) -> str:
    """`gh:<repo key>/<issues|pull|discussions>/<number>` (ADR-002 D4, S13-R1)."""
    return f"gh:{item.key}"


def snapshot_path(item: GithubItem) -> str:
    """The snapshot's path in the corpus cache, the version's `source_path`."""
    return f"github/{item.key}.json"


def snapshot_bytes(snapshot: ItemSnapshot) -> bytes:
    """The snapshot file's bytes: the sha256 the lock pins is theirs."""
    return (snapshot.model_dump_json(indent=2) + "\n").encode("utf-8")


class GithubSnapshotError(Exception):
    """An item's cached snapshot is missing, or isn't the one the lock pins. One line, naming the
    item; `make ingest` stops before any write."""


def read_snapshot(cache_dir: Path, item: GithubItem) -> tuple[ItemSnapshot, GithubPin]:
    """The item's cached snapshot and its pin. Raises GithubSnapshotError when the lock pins none,
    the file is missing, or its sha256 differs from the pin. No network."""
    if item.pin is None:
        raise GithubSnapshotError(f"{item.key}: the lock pins no snapshot; run `make fetch-github`")
    path = cache_dir / snapshot_path(item)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise GithubSnapshotError(
            f"{item.key}: no snapshot at {path}; run `make fetch-github`"
        ) from None
    sha256 = hashlib.sha256(raw).hexdigest()
    if sha256 != item.pin.sha256:
        raise GithubSnapshotError(
            f"{item.key}: the cached snapshot's sha256 is {sha256}, the lock pins "
            f"{item.pin.sha256}; run `make fetch-github`"
        )
    return ItemSnapshot.model_validate_json(raw), item.pin


def item_version(
    item: GithubItem, pin: GithubPin, snapshot: ItemSnapshot, releases: Sequence[Release]
) -> VersionData:
    """The item's one version: the rendered text's hash (ADR-002 D2's normalization, no strip
    list), dated from the last kept post (ADR-002 D3's date-scoped rule), `claimed_status` null.

    Its snapshot is the cached file: `source_path` its path in the cache, `snapshot_repo` the
    manifest repo, `snapshot_ref` the lock's fetch time, and `snapshot_sha` the first 40 hex
    characters of its sha256 (the column holds a git SHA's 40).
    """
    text = render(snapshot)
    state = FileState(
        content_hash=content_hash({}, text, frozenset()),
        source_path=snapshot_path(item),
        metadata=item_metadata(snapshot),
    )
    at = Snapshot(None, pin.fetched_at, pin.sha256[:40])
    (version,) = date_history(item.repo, [Observed(at, state, last_post_time(snapshot))], releases)
    return version


def snapshot_text(path: Path, snapshot_sha: str) -> bytes:
    """The rendered text, as UTF-8, of the cached snapshot a version was stored from (chunking).
    Raises ValueError when the file is gone or a later fetch replaced it."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"no snapshot at {path}: {exc.strerror}") from None
    if hashlib.sha256(raw).hexdigest()[:40] != snapshot_sha:
        raise ValueError(f"{path} isn't the snapshot this version was stored from")
    return render(ItemSnapshot.model_validate_json(raw)).encode("utf-8")


# --- Fetch (network) ------------------------------------------------------------------------------

DISCUSSION_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussion(number: $number) {
      title url createdAt closedAt body author { login }
      comments(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id createdAt body author { login }
          replies(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes { createdAt body author { login } }
          }
        }
      }
    }
  }
}
"""

REPLIES_QUERY = """
query($id: ID!, $after: String) {
  node(id: $id) {
    ... on DiscussionComment {
      replies(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { createdAt body author { login } }
      }
    }
  }
}
"""


def github_client(
    token: SecretStr, timeout_s: float, transport: httpx2.BaseTransport | None = None
) -> httpx2.Client:
    """An HTTP client sending the token as a bearer header, waiting at most `timeout_s` seconds
    for each step of a request (GITHUB_TIMEOUT_S), with no retries. Tests pass a MockTransport."""
    return httpx2.Client(
        headers={
            "Authorization": f"Bearer {token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=timeout_s,
        transport=transport,
    )


def _login(user: Mapping[str, Any] | None) -> str:
    """A REST `user` or GraphQL `author`'s login; a deleted account has none and shows as
    "ghost"."""
    return "ghost" if user is None else str(user["login"])


def _get(client: httpx2.Client, url: str) -> httpx2.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def _rest_list(client: httpx2.Client, url: str) -> list[dict[str, Any]]:
    """Every element of a REST list, following each page's `Link: <...>; rel="next"`."""
    elements: list[dict[str, Any]] = []
    next_url: str | None = f"{url}?per_page={PER_PAGE}"
    while next_url is not None:
        response = _get(client, next_url)
        elements += response.json()
        next_url = response.links.get("next", {}).get("url")
    return elements


def _graphql(
    client: httpx2.Client, api_url: str, query: str, variables: Mapping[str, Any]
) -> dict[str, Any]:
    """One GraphQL request's `data`. Raises ValueError with GitHub's first error message."""
    response = client.post(f"{api_url}/graphql", json={"query": query, "variables": variables})
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    if payload.get("errors"):
        raise ValueError(f"GitHub GraphQL error: {payload['errors'][0]['message']}")
    data: dict[str, Any] = payload["data"]
    return data


def _all_nodes(
    connection: Mapping[str, Any], next_page: Callable[[str], Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Every node of a GraphQL connection: its first page's, then each next page's
    (`next_page(endCursor)`) while `hasNextPage`."""
    nodes = list(connection["nodes"])
    while connection["pageInfo"]["hasNextPage"]:
        connection = next_page(connection["pageInfo"]["endCursor"])
        nodes += connection["nodes"]
    return nodes


def _rest_post(kind: str, element: Mapping[str, Any], created_at: str) -> Post:
    return Post.model_validate(
        {
            "kind": kind,
            "author": _login(element["user"]),
            "created_at": element[created_at],
            "body": element["body"] or "",
        }
    )


def _rest_item(
    client: httpx2.Client, api_url: str, repo_path: str, item: GithubItem
) -> ItemSnapshot:
    """An issue or a PR: the item, its comments, and a PR's reviews (never its diff-line
    comments). A review with no submission time is pending, never posted: it isn't kept."""
    base = f"{api_url}/repos/{repo_path}"
    path = "pulls" if item.kind == "pull" else "issues"
    fields = _get(client, f"{base}/{path}/{item.number}").json()
    comments = _rest_list(client, f"{base}/issues/{item.number}/comments")
    posts = [_rest_post("comment", comment, "created_at") for comment in comments]
    merged: dict[str, Any] = {}
    if item.kind == "pull":
        reviews = _rest_list(client, f"{base}/pulls/{item.number}/reviews")
        posts += [
            _rest_post("review", review, "submitted_at")
            for review in reviews
            if review["submitted_at"] is not None
        ]
        merged_by = fields["merged_by"]
        merged = {
            "merged_at": fields["merged_at"],
            "merged_by": None if merged_by is None else _login(merged_by),
        }
    return ItemSnapshot.model_validate(
        {
            "kind": item.kind,
            "number": item.number,
            "url": fields["html_url"],
            "title": fields["title"],
            "author": _login(fields["user"]),
            "created_at": fields["created_at"],
            "closed_at": fields["closed_at"],
            "body": fields["body"] or "",
            "posts": posts,
            **merged,
        }
    )


def _graphql_post(kind: str, node: Mapping[str, Any]) -> Post:
    return Post.model_validate(
        {
            "kind": kind,
            "author": _login(node["author"]),
            "created_at": node["createdAt"],
            "body": node["body"] or "",
        }
    )


def _replies(
    client: httpx2.Client, api_url: str, comment: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Every reply of a discussion comment: the first page came with the comment."""

    def next_page(after: str) -> Mapping[str, Any]:
        variables = {"id": comment["id"], "after": after}
        replies: Mapping[str, Any] = _graphql(client, api_url, REPLIES_QUERY, variables)["node"][
            "replies"
        ]
        return replies

    return _all_nodes(comment["replies"], next_page)


def _discussion(
    client: httpx2.Client, api_url: str, repo_path: str, item: GithubItem
) -> ItemSnapshot:
    """A discussion over GraphQL: its comments, each followed by its replies, every list paged."""
    owner, name = repo_path.split("/")

    def comments_page(after: str | None) -> Mapping[str, Any]:
        variables = {"owner": owner, "name": name, "number": item.number, "after": after}
        discussion: Mapping[str, Any] = _graphql(client, api_url, DISCUSSION_QUERY, variables)[
            "repository"
        ]["discussion"]
        return discussion

    discussion = comments_page(None)
    posts = []
    comments = _all_nodes(discussion["comments"], lambda after: comments_page(after)["comments"])
    for comment in comments:
        posts.append(_graphql_post("comment", comment))
        posts += [_graphql_post("reply", reply) for reply in _replies(client, api_url, comment)]
    return ItemSnapshot.model_validate(
        {
            "kind": item.kind,
            "number": item.number,
            "url": discussion["url"],
            "title": discussion["title"],
            "author": _login(discussion["author"]),
            "created_at": discussion["createdAt"],
            "closed_at": discussion["closedAt"],
            "body": discussion["body"] or "",
            "posts": posts,
        }
    )


def fetch_item(
    client: httpx2.Client, api_url: str, repo_path: str, item: GithubItem
) -> ItemSnapshot:
    """The item's snapshot from GitHub's API. `repo_path` is `<owner>/<name>`, e.g.
    kubernetes/enhancements. Raises httpx2.HTTPError or ValueError on a failed request."""
    if item.kind == "discussions":
        return _discussion(client, api_url, repo_path, item)
    return _rest_item(client, api_url, repo_path, item)


def save_snapshots(
    cache_dir: Path, items: Sequence[GithubItem], snapshots: Sequence[ItemSnapshot], now: str
) -> dict[str, GithubPin]:
    """Write each snapshot to the cache and return each item's pin by key. An item whose
    snapshot has the sha256 it was pinned with keeps its pin, fetch time included; any other gets
    the new hash and `now`."""
    pins = {}
    for item, snapshot in zip(items, snapshots, strict=True):
        raw = snapshot_bytes(snapshot)
        path = cache_dir / snapshot_path(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        sha256 = hashlib.sha256(raw).hexdigest()
        if item.pin is not None and item.pin.sha256 == sha256:
            pins[item.key] = item.pin
        else:
            pins[item.key] = GithubPin(sha256, now)
    return pins


def update_lock(lock_path: Path, pins: Mapping[str, GithubPin]) -> None:
    """Replace the lock's `github:` section with `pins`, keeping its other sections and its
    leading comment lines. The lock is written by `yaml.safe_dump` (spikes/fetch.py), so dumping
    it again leaves the other sections' text as it was."""
    text = lock_path.read_text(encoding="utf-8")
    header = "".join(takewhile(lambda line: line.startswith("#"), text.splitlines(keepends=True)))
    lock = yaml.safe_load(text)
    lock["github"] = {
        key: {"sha256": pin.sha256, "fetched_at": pin.fetched_at} for key, pin in pins.items()
    }
    lock_path.write_text(header + yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")


def main() -> None:
    """`make fetch-github`: fetch every decision chain's item, then write the snapshots and the
    lock. Nothing is written unless every item was fetched."""
    settings = Settings()
    if settings.github_token is None or not settings.github_token.get_secret_value():
        sys.exit("GITHUB_TOKEN is not set: add a GitHub token to .env (`gh auth token`).")
    manifest, lock = settings.corpus_manifest_path, settings.corpus_lock_path
    items = load_github_items(manifest, lock)
    repo_urls = load_repo_urls(manifest)
    snapshots = []
    with github_client(settings.github_token, settings.github_timeout_s) as client:
        for item in items:
            repo_path = repo_urls[item.repo].removeprefix("https://github.com/")
            try:
                snapshots.append(fetch_item(client, settings.github_api_url, repo_path, item))
            except (httpx2.HTTPError, ValueError) as exc:
                sys.exit(f"Nothing written: {item.key}: {str(exc).splitlines()[0]}")
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    pins = save_snapshots(settings.corpus_cache_dir.expanduser(), items, snapshots, now)
    update_lock(lock, pins)
    for item, snapshot in zip(items, snapshots, strict=True):
        old = item.pin.sha256 if item.pin else None
        status = (
            "new" if old is None else "unchanged" if old == pins[item.key].sha256 else "changed"
        )
        print(
            f"{item.key}: opening post + {len(snapshot.posts)} comments, replies and reviews "
            f"fetched; sha256 {pins[item.key].sha256[:12]} ({status})"
        )
    print(f"Lock updated: {lock} (github: {len(pins)} items).")


if __name__ == "__main__":
    main()
