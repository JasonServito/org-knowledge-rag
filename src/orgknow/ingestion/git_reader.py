"""Read locked snapshots from the corpus clones with the `git` command.

The clones are partial (`--filter=blob:none`): git fetches a missing file content from GitHub
the first time it's read. Any git failure (offline, an unknown SHA) raises GitError and stops
ingestion; a file is never skipped because git failed.
"""

import logging
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from orgknow.ingestion.manifest import Snapshot

log = logging.getLogger(__name__)

SYMLINK_MODE = "120000"


class GitError(RuntimeError):
    """A git command failed. The message holds git's own error."""


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        raise GitError(f"git {' '.join(args)} failed in {repo}: {error}")
    return result.stdout


def _matches(path: str, wanted: str) -> bool:
    """A manifest path ending in "/" is a directory prefix; anything else is one file."""
    return path.startswith(wanted) if wanted.endswith("/") else path == wanted


def read_files(
    repo: Path, paths: Sequence[str], snapshots: Sequence[Snapshot], suffixes: tuple[str, ...]
) -> tuple[dict[str, list[bytes | None]], list[str]]:
    """Read every file under `paths` at each snapshot.

    Returns ({file path: its content at each snapshot, None where absent}, skipped files). A
    skipped file is "<snapshot> <path>: <reason>": a symlink, a submodule, or a name without
    one of `suffixes`. A manifest path absent from a snapshot is logged, not an error.
    """
    files: dict[str, list[bytes | None]] = {}
    skipped: list[str] = []
    contents: dict[str, bytes] = {}  # by blob id: a file unchanged across snapshots is read once
    absent: dict[str, list[str]] = {}
    for i, snapshot in enumerate(snapshots):
        listing = _git(repo, "ls-tree", "-r", "-z", snapshot.sha, "--", *paths)
        found: list[str] = []
        for entry in filter(None, listing.decode().split("\0")):
            info, path = entry.split("\t", 1)
            mode, kind, oid = info.split()
            found.append(path)
            if mode == SYMLINK_MODE:
                skipped.append(f"{snapshot.label} {path}: symlink")
            elif kind != "blob":
                skipped.append(f"{snapshot.label} {path}: not a file ({kind})")
            elif not path.endswith(suffixes):
                skipped.append(f"{snapshot.label} {path}: not a {'/'.join(suffixes)} file")
            else:
                if oid not in contents:
                    contents[oid] = _git(repo, "cat-file", "blob", oid)
                files.setdefault(path, [None] * len(snapshots))[i] = contents[oid]
        for wanted in paths:
            if not any(_matches(path, wanted) for path in found):
                absent.setdefault(wanted, []).append(snapshot.label)
    for wanted, labels in absent.items():
        log.info("manifest path %s is absent at %s", wanted, ", ".join(labels))
    return files, skipped


def parse_commit_time(text: str) -> datetime:
    """A `%cI` committer time (ISO 8601 with the committer's offset) as a UTC datetime."""
    at = datetime.fromisoformat(text)
    if at.utcoffset() is None:
        raise ValueError(f"commit time {text!r} has no UTC offset")
    return at.astimezone(UTC)


def commit_times(repo: Path, since: str | None, until: str, paths: Sequence[str]) -> list[datetime]:
    """Committer times of the commits touching `paths` in `since..until` (all of `until`'s
    history if `since` is None), newest first."""
    revisions = until if since is None else f"{since}..{until}"
    out = _git(repo, "log", "--format=%cI", revisions, "--", *paths)
    return [parse_commit_time(line) for line in out.decode().split()]
