"""Read the corpus manifest (config/corpus_manifest.yaml) and its lock file."""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any

# PyYAML ships no type hints, so safe_load returns Any: everything it returns is checked below.
import yaml  # type: ignore[import-untyped]

from orgknow.db.models import Release


def _read_yaml(path: Path) -> dict[str, Any]:
    # safe_load builds only plain values (dicts, lists, strings, dates), never Python objects.
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a YAML mapping")
    return data


def load_releases(path: Path) -> list[Release]:
    """Return the manifest's releases, oldest first, after checking the list is complete.

    A malformed entry raises pydantic's ValidationError; a broken rule raises ValueError.
    """
    block = _read_yaml(path)["releases"]
    first, latest = block["first"], block["latest"]
    releases = [
        Release(
            version=entry["version"],
            release_date=entry["release_date"],
            end_of_life_date=entry["end_of_life"],
        )
        for entry in block["list"]
    ]

    if not releases or releases[0].version != first or releases[-1].version != latest:
        raise ValueError(
            f"releases.list must run from releases.first ({first}) to releases.latest ({latest})"
        )
    for release in releases:
        if release.end_of_life_date <= release.release_date:
            raise ValueError(
                f"{release.version}: end of life {release.end_of_life_date} is not after "
                f"its release date {release.release_date}"
            )
    for prev, cur in pairwise(releases):
        if cur.minor != prev.minor + 1:
            raise ValueError(f"releases must be contiguous: {cur.version} follows {prev.version}")
        if cur.release_date <= prev.release_date:
            raise ValueError(
                f"release dates must be strictly ascending: {cur.version} ({cur.release_date}) "
                f"is not after {prev.version} ({prev.release_date})"
            )
    return releases


def load_repo_urls(path: Path) -> dict[str, str]:
    """The manifest's `repos.<name>.url` by repo name, e.g. "website" -> its GitHub URL."""
    return {str(name): str(repo["url"]) for name, repo in _read_yaml(path)["repos"].items()}


def load_normalization(path: Path) -> dict[str, frozenset[str]]:
    """Return the front-matter keys to strip before hashing, per kind, lowercased (ADR-002 D2).

    Hugo matches keys case-insensitively, so the lists are compared lowercased. Raises
    ValueError if a list strips a `never_strip` key (identity, time or lifecycle).
    """
    block = _read_yaml(path)["normalization"]
    never = {str(key).lower() for key in block["never_strip"]}
    strip = {
        str(kind): frozenset(str(key).lower() for key in keys)
        for kind, keys in block["strip_front_matter"].items()
    }
    bad = sorted({key for keys in strip.values() for key in keys if key in never})
    if bad:
        raise ValueError(f"strip_front_matter lists never_strip keys: {bad}")
    return strip


@dataclass(frozen=True)
class Snapshot:
    """One locked commit to read: a release branch head, or a default branch at a date."""

    release: int | None  # minor of the release (24 for v1.24); None for the `head` snapshot
    ref: str  # branch, e.g. release-1.24, main or master
    sha: str

    @property
    def label(self) -> str:
        return "head" if self.release is None else f"1.{self.release}"


@dataclass(frozen=True)
class ReleaseGroup:
    """Files read from the website's release branches, one snapshot per release (ADR-002 D1).

    Its files are hashed with the manifest's strip list for `source_type`.
    """

    source_type: str  # ADR-003 D1: docs_page, release_record or feature_gate_reference
    repo: str
    paths: tuple[str, ...]  # a path ending in "/" is a directory prefix
    snapshots: tuple[Snapshot, ...]  # one per release, from the scope's first release


@dataclass(frozen=True)
class DateGroup:
    """Files read from a repo's default branch at each release date, plus `head` (ADR-002 D1).

    A version is dated by when its change was merged, not by its snapshot (ADR-002 D3).
    """

    source_type: str  # ADR-003 D1: kep or governance_doc
    repo: str
    paths: tuple[str, ...]  # a path ending in "/" is a directory prefix
    snapshots: tuple[Snapshot, ...]  # the default branch at every release date, then head


@dataclass(frozen=True)
class BlogGroup:
    """Blog posts: one first-parent log of the default branch up to `head`, following renames
    (ADR-002 D1, D3; S05-R2 decision 5). A post's versions are dated by commit and publication.
    """

    source_type: str  # blog_post
    repo: str
    ref: str  # the default branch, e.g. main
    head: str  # the lock's head SHA of `repo`
    paths: tuple[str, ...]  # folders holding the posts
    since: datetime  # 00:00 UTC of `from_release`'s release date: posts published from then
    permalink: str  # Hugo's blog permalink, e.g. /:section/:year/:month/:day/:slug/


@dataclass(frozen=True)
class ChangelogGroup:
    """The CHANGELOGs: one file per release in scope, all read at the repo's lock head (ADR-002
    D1). Their snapshot is their own, not a website release branch (S05-R2, parked P2)."""

    source_type: str  # release_record
    repo: str  # kubernetes
    snapshot: Snapshot  # the default branch at the lock head; release None ("head")
    files: tuple[tuple[int, str], ...]  # (release, path): (20, "CHANGELOG/CHANGELOG-1.20.md")


def _same_files(a: str, b: str) -> bool:
    """Whether some file is matched by both manifest paths (one ending in "/" is a folder)."""
    return a == b or (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b))


@dataclass(frozen=True)
class Scope:
    """What `make ingest` reads: a named subset of the manifest at the lock's SHAs."""

    name: str
    release_groups: tuple[ReleaseGroup, ...]
    date_groups: tuple[DateGroup, ...]  # the KEPs, then the governance docs
    blog: BlogGroup | None = None
    changelogs: ChangelogGroup | None = None

    def __post_init__(self) -> None:
        """Refuse a scope where one file would be read by two groups, so stored twice."""
        for a, b in combinations(self.release_groups, 2):
            for path_a in a.paths:
                for path_b in b.paths:
                    if a.repo == b.repo and _same_files(path_a, path_b):
                        raise ValueError(
                            f"scope {self.name!r}: {a.source_type} path {path_a} and "
                            f"{b.source_type} path {path_b} match the same files"
                        )


def load_scope(manifest_path: Path, lock_path: Path, name: str) -> Scope:
    """Resolve the manifest's `scopes.<name>` against its sources and the lock's SHAs.

    Release-scoped groups (docs pages, website release records, feature gates) are read from
    each release's branch, from the group's `from_release` to the latest. A release-record source
    with a `branch` (the CHANGELOGs) has one file per release in scope, all read at that branch's
    lock head, which must be the repo's locked default branch. Date-scoped groups
    (KEPs, governance docs) are read from their repo's default branch at every release date,
    plus `head` (ADR-002 D1). `kep: all` reads every KEP in `sources.kep.sig_dirs`; otherwise
    `kep: {traced: [...]}` reads only those KEPs' directories. `blog_post: all` reads the blog's
    history up to the lock's head, keeping posts published from `sources.blog_post.from_release`.
    """
    manifest = _read_yaml(manifest_path)
    lock = _read_yaml(lock_path)
    scopes = manifest["scopes"]
    if name not in scopes:
        raise ValueError(f"unknown scope {name!r}; the manifest has: {', '.join(scopes)}")
    scope = scopes[name]
    sources = manifest["sources"]
    versions = [str(entry["version"]) for entry in manifest["releases"]["list"]]

    def scope_versions(from_release: str) -> list[str]:
        if from_release not in versions:
            raise ValueError(
                f"scope {name!r}: from_release {from_release} is not a manifest release"
            )
        return versions[versions.index(from_release) :]

    def release_snapshots(from_release: str) -> tuple[Snapshot, ...]:
        return tuple(
            Snapshot(
                int(v.removeprefix("1.")),
                lock["website_releases"][v]["ref"],
                lock["website_releases"][v]["sha"],
            )
            for v in scope_versions(from_release)
        )

    docs = scope["docs_page"]
    docs_paths = tuple(path for sig in docs["sigs"] for path in sources["docs_page"]["sigs"][sig])
    groups = [
        ReleaseGroup(
            "docs_page",
            str(sources["docs_page"]["repo"]),
            docs_paths,
            release_snapshots(docs["from_release"]),
        )
    ]
    changelogs = None
    if "release_record" in scope:
        records = scope["release_record"]
        by_repo = {entry["repo"]: entry for entry in sources["release_record"]}
        for repo in records["repos"]:
            entry = by_repo[repo]
            if "branch" not in entry:  # the website's: read at each release branch
                groups.append(
                    ReleaseGroup(
                        "release_record",
                        str(repo),
                        tuple(entry["paths"]),
                        release_snapshots(records["from_release"]),
                    )
                )
                continue
            # The CHANGELOGs (S05-T6): the lock holds only the default branch's head.
            if entry["branch"] != lock["repos"][repo]["default_branch"]:
                raise ValueError(
                    f"release_record {repo} branch {entry['branch']} is not the locked default "
                    f"branch {lock['repos'][repo]['default_branch']}"
                )
            (template,) = entry["paths"]  # e.g. CHANGELOG/CHANGELOG-{version}.md
            changelogs = ChangelogGroup(
                "release_record",
                str(repo),
                Snapshot(None, str(entry["branch"]), lock["repos"][repo]["head"]),
                tuple(
                    (int(v.removeprefix("1.")), template.format(version=v))
                    for v in scope_versions(records["from_release"])
                ),
            )
    if "feature_gate_reference" in scope:
        gates = sources["feature_gate_reference"]
        groups.append(
            ReleaseGroup(
                "feature_gate_reference",
                str(gates["repo"]),
                tuple(gates["paths"]),
                release_snapshots(scope["feature_gate_reference"]["from_release"]),
            )
        )

    def date_snapshots(repo: str) -> tuple[Snapshot, ...]:
        branch = lock["repos"][repo]["default_branch"]
        dated = lock["release_date_snapshots"][repo]
        return (
            *(Snapshot(int(v.removeprefix("1.")), branch, dated[v]["sha"]) for v in versions),
            Snapshot(None, branch, lock["repos"][repo]["head"]),
        )

    kep = sources["kep"]
    if scope["kep"] == "all":
        kep_paths = tuple(str(path) for path in kep["sig_dirs"])
    else:
        kep_paths = tuple(str(kep["traced"][number]) for number in scope["kep"]["traced"])
    date_groups = [DateGroup("kep", str(kep["repo"]), kep_paths, date_snapshots(kep["repo"]))]
    if "governance_doc" in scope:
        if scope["governance_doc"] != "all":
            raise ValueError(f"scope {name!r}: governance_doc must be `all`")
        date_groups += [
            DateGroup(
                "governance_doc",
                str(entry["repo"]),
                tuple(entry["paths"]),
                date_snapshots(entry["repo"]),
            )
            for entry in sources["governance_doc"]
        ]
    blog = None
    if "blog_post" in scope:
        if scope["blog_post"] != "all":
            raise ValueError(f"scope {name!r}: blog_post must be `all`")
        posts = sources["blog_post"]
        if posts["exclude_drafts"] is not True:
            # The publication rules assume it: Hugo never renders a draft (ADR-002 D3).
            raise ValueError("sources.blog_post.exclude_drafts must be true")
        dates = {
            str(entry["version"]): entry["release_date"] for entry in manifest["releases"]["list"]
        }
        if str(posts["from_release"]) not in dates:
            raise ValueError(f"blog_post from_release {posts['from_release']} is not a release")
        blog = BlogGroup(
            "blog_post",
            str(posts["repo"]),
            str(posts["branch"]),
            lock["repos"][posts["repo"]]["head"],
            tuple(str(path) for path in posts["paths"]),
            datetime.combine(dates[str(posts["from_release"])], time(), UTC),
            str(posts["permalink"]),
        )
    return Scope(name, tuple(groups), tuple(date_groups), blog, changelogs)
