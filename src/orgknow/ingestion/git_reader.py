"""Read locked snapshots, and the blog's history up to the locked head, from the corpus clones
with the `git` command.

The clones are partial (`--filter=blob:none`): git fetches a missing file content from GitHub
the first time it's read. Any git failure (offline, an unknown SHA) raises GitError and stops
ingestion; a file is never skipped because git failed.
"""

import logging
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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


def _ignore_nothing(path: str) -> bool:
    return False


def read_files(
    repo: Path,
    paths: Sequence[str],
    snapshots: Sequence[Snapshot],
    suffixes: tuple[str, ...],
    ignore: Callable[[str], bool] = _ignore_nothing,
) -> tuple[dict[str, list[bytes | None]], list[str]]:
    """Read every file under `paths` at each snapshot.

    Returns ({file path: its content at each snapshot, None where absent}, skipped files). A
    skipped file is "<snapshot> <path>: <reason>": a symlink, a submodule, or a name without
    one of `suffixes`. A file `ignore` names is left out: neither read nor skipped (e.g. the
    images in a KEP's folder). A manifest path absent from a snapshot is logged, not an error.
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
            if ignore(path):
                continue
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


def read_file(repo: Path, sha: str, path: str) -> bytes:
    """The content of `path` at commit `sha`, e.g. to re-read a stored version's file."""
    return _git(repo, "cat-file", "blob", f"{sha}:{path}")


def parse_commit_time(text: str) -> datetime:
    """A `%cI` committer time (ISO 8601 with the committer's offset) as a UTC datetime."""
    at = datetime.fromisoformat(text)
    if at.utcoffset() is None:
        raise ValueError(f"commit time {text!r} has no UTC offset")
    return at.astimezone(UTC)


def commit_time(repo: Path, sha: str) -> datetime:
    """The committer time, in UTC, of commit `sha` itself. A CHANGELOG version starts at the lock
    head's (S05-R2 decision 6): a git fact, read from the clone."""
    return parse_commit_time(_git(repo, "log", "-1", "--format=%cI", sha).decode().strip())


def merge_time(repo: Path, since: str | None, until: str, paths: Sequence[str]) -> datetime | None:
    """When the last change to `paths` in `since..until` (all of `until`'s history if `since` is
    None) was merged into the default branch: the committer time, in UTC, of the last
    first-parent commit touching them (ADR-002 D3). None if no commit touches them.

    `--first-parent` follows only the default branch: a pull request's merge commit, whose time
    is when the change went live, not the commits on its branch (S05-R2 sitting).
    """
    revisions = until if since is None else f"{since}..{until}"
    out = _git(repo, "log", "--first-parent", "-1", "--format=%cI", revisions, "--", *paths)
    line = out.decode().strip()
    return parse_commit_time(line) if line else None


def first_present(repo: Path, sha: str, paths: Sequence[str]) -> str | None:
    """The first of `paths` that exists at commit `sha`, or None if none does."""
    listing = _git(repo, "ls-tree", "--name-only", "-z", sha, "--", *paths).decode().split("\0")
    return next((path for path in paths if path in listing), None)


# ADR-002 D4: git's default rename threshold, the fallback after the declared signals for web
# pages and gates, the only rename signal for governance docs (S05-R2 decisions 2 and 9), and
# what follows a moved blog post (decision 5). An identity rule, not a tuning knob: changing it
# changes canonical ids. Untuned: every docs rename it was graded on is real (spike §4 F).
RENAME_SIMILARITY = "50%"


def similar_renames(
    repo: Path, before: str, after: str, paths: Sequence[str]
) -> list[tuple[str, str]]:
    """The renames git finds between commits `before` and `after` among `paths` only: (old path,
    new path) for each deleted file it pairs with an added one at least 50% similar."""
    if not paths:
        return []  # an empty pathspec would compare the whole tree
    out = _git(
        repo,
        "--literal-pathspecs",  # paths are file names, never patterns
        "diff",
        f"-M{RENAME_SIMILARITY}",
        "--name-status",
        "-z",
        before,
        after,
        "--",
        *paths,
    )
    # -z output: a status, then its path, or for a rename (R<score>) its old and new paths.
    tokens = iter(out.decode().split("\0"))
    renames = []
    for status in tokens:
        if status.startswith("R"):
            renames.append((next(tokens), next(tokens)))
        elif status:
            next(tokens)
    return renames


def read_blob(repo: Path, blob: str) -> bytes:
    """A file's content by its blob id (as `git log --raw` lists it)."""
    return _git(repo, "cat-file", "blob", blob)


@dataclass(frozen=True)
class PostCommit:
    """One first-parent commit on the default branch that touches a blog post's file."""

    committed: datetime  # committer time, UTC
    sha: str
    path: str  # the post's file at this commit
    blob: str | None  # its content's blob id; None: deleted by this commit


def post_histories(repo: Path, head: str, paths: Sequence[str]) -> list[list[PostCommit]]:
    """The history of every `.md` file under `paths` (folders), in one first-parent log of the
    default branch up to `head` (ADR-002 D3, S05-R2 decision 5): per post, one entry per commit
    touching it, oldest first; posts in order of first commit.

    git's rename detection (50%, ADR-002 D4) follows a moved post, so a move continues its
    history; renames are scored among `.md` files only. A file that loses its `.md` (website PR
    #53902's two extensionless interviews) is deleted there: Hugo doesn't render it.
    """
    out = _git(
        repo,
        "log",
        "--first-parent",
        "--diff-merges=first-parent",  # a merge's changes against main before it
        f"--find-renames={RENAME_SIMILARITY}",
        "--raw",
        "--no-abbrev",
        "-z",
        "--format=@%H %cI",
        head,
        "--",
        *(f"{path}*.md" for path in paths),
    )
    # -z output, newest commit first: "@<sha> <time>", then per file
    # ":<modes> <old blob> <new blob> <status>" and its path, or for a rename its old and new path.
    commits: list[tuple[str, datetime, list[tuple[str | None, str, str | None]]]] = []
    tokens = (token.lstrip("\n") for token in out.decode().split("\0"))
    for token in tokens:
        if token.startswith("@"):
            commit, time_text = token[1:].split(" ")
            commits.append((commit, parse_commit_time(time_text), []))
        elif token.startswith(":"):
            new_blob, status = token.split()[3:5]
            moved_from = next(tokens) if status.startswith("R") else None
            deleted = set(new_blob) == {"0"}
            commits[-1][2].append((moved_from, next(tokens), None if deleted else new_blob))
    histories: list[list[PostCommit]] = []
    current: dict[str, list[PostCommit]] = {}  # path -> the history of the post there
    for sha, committed, changes in reversed(commits):
        for old, path, blob in changes:
            # A move continues the moved post's history. A history it displaces stays listed.
            history = current.pop(old, None) if old is not None else current.get(path)
            if history is None:
                history = []
                histories.append(history)
            current[path] = history
            history.append(PostCommit(committed, sha, path, blob))
    return histories
