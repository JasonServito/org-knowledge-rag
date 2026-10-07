"""Read the corpus manifest (config/corpus_manifest.yaml) and its lock file."""

from dataclasses import dataclass
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

    source_type: str  # ADR-003 D1: docs_page or release_record
    repo: str
    paths: tuple[str, ...]  # a path ending in "/" is a directory prefix
    snapshots: tuple[Snapshot, ...]  # one per release, from the scope's first release


def _same_files(a: str, b: str) -> bool:
    """Whether some file is matched by both manifest paths (one ending in "/" is a folder)."""
    return a == b or (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b))


@dataclass(frozen=True)
class Scope:
    """What `make ingest` reads: a named subset of the manifest at the lock's SHAs."""

    name: str
    release_groups: tuple[ReleaseGroup, ...]
    kep_repo: str
    keps: tuple[tuple[int, str], ...]  # (KEP number, its directory)
    kep_snapshots: tuple[Snapshot, ...]  # default branch at each release date, then head

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

    Release-scoped groups (docs pages, website release records) are read from each release's
    branch, from the group's `from_release` to the latest. KEPs are read from the default branch
    at every release date, plus `head` (ADR-002 D1).
    """
    manifest = _read_yaml(manifest_path)
    lock = _read_yaml(lock_path)
    scopes = manifest["scopes"]
    if name not in scopes:
        raise ValueError(f"unknown scope {name!r}; the manifest has: {', '.join(scopes)}")
    scope = scopes[name]
    sources = manifest["sources"]
    versions = [str(entry["version"]) for entry in manifest["releases"]["list"]]

    def release_snapshots(from_release: str) -> tuple[Snapshot, ...]:
        if from_release not in versions:
            raise ValueError(
                f"scope {name!r}: from_release {from_release} is not a manifest release"
            )
        return tuple(
            Snapshot(
                int(v.removeprefix("1.")),
                lock["website_releases"][v]["ref"],
                lock["website_releases"][v]["sha"],
            )
            for v in versions[versions.index(from_release) :]
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
    if "release_record" in scope:
        records = scope["release_record"]
        by_repo = {entry["repo"]: entry for entry in sources["release_record"]}
        groups += [
            ReleaseGroup(
                "release_record",
                str(repo),
                tuple(by_repo[repo]["paths"]),
                release_snapshots(records["from_release"]),
            )
            for repo in records["repos"]
        ]

    kep = sources["kep"]
    kep_repo = str(kep["repo"])
    keps = tuple((int(number), str(kep["traced"][number])) for number in scope["kep"]["traced"])
    branch = lock["repos"][kep_repo]["default_branch"]
    dated = lock["release_date_snapshots"][kep_repo]
    kep_snapshots = (
        *(Snapshot(int(v.removeprefix("1.")), branch, dated[v]["sha"]) for v in versions),
        Snapshot(None, branch, lock["repos"][kep_repo]["head"]),
    )
    return Scope(name, tuple(groups), kep_repo, keps, kep_snapshots)
