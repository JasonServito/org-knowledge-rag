"""S02-T2 spike: partial-clone the manifest repos into CORPUS_CACHE_DIR and lock their SHAs.

Run: uv run python spikes/fetch.py [--relock]

- No lock file yet (or --relock): resolve the SHAs and write config/corpus_manifest.lock.yaml.
- Lock file present: fetch (the shallow kubernetes clone fetches its locked SHA, not master),
  check every locked SHA exists locally, and leave the lock unchanged.

Throwaway spike code (docs/slices/S02-corpus-spike.md): never imported by src/.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "config" / "corpus_manifest.yaml"
LOCK = REPO_ROOT / "config" / "corpus_manifest.lock.yaml"

# The only git subcommands this script may run: no push, no delete.
NETWORK_GIT = {"clone", "fetch"}
# Read-only commands run with protocol.allow=never, so a missing object in a partial clone
# fails instead of being fetched silently. (git 2.43 has no --no-lazy-fetch.)
LOCAL_GIT = {"rev-parse", "rev-list", "cat-file", "ls-tree", "log", "diff"}

# CHANGELOG is read from master's head only, so no history is needed (ADR-002 D1).
SHALLOW_REPOS = {"kubernetes"}
# Clone every branch: the release-1.R branches are the per-release docs snapshots.
ALL_BRANCH_REPOS = {"website"}
# Snapshotted as the default branch "as of R's release date" (ADR-002 D1).
DATE_REPOS = ("enhancements", "community", "sig-release")

CUTOFF_RULE = (
    "last first-parent commit on the default branch with committer date "
    "<= YYYY-MM-DDT23:59:59Z (UTC) on the release date"
)


def git(*args: str, repo: Path | None = None) -> str:
    """Print and run one git command; return its stdout."""
    if args[0] not in NETWORK_GIT | LOCAL_GIT:
        sys.exit(f"refusing: git {args[0]} is not an allowed subcommand")
    cmd = ["git"]
    if repo is not None:
        cmd += ["-C", str(repo)]
    if args[0] in LOCAL_GIT:
        cmd += ["-c", "protocol.allow=never"]
    cmd += args
    print("+", shlex.join(cmd), flush=True)
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True).stdout.strip()


def cache_dir_or_exit() -> Path:
    raw = os.environ.get("CORPUS_CACHE_DIR", "").strip()
    if not raw:
        sys.exit("refusing: CORPUS_CACHE_DIR is unset. Export an absolute path outside this repo.")
    cache = Path(raw).expanduser().resolve()
    if cache.is_relative_to(REPO_ROOT):
        sys.exit(f"refusing: CORPUS_CACHE_DIR resolves to {cache}, inside the repo {REPO_ROOT}")
    return cache


def clone_or_fetch(name: str, url: str, branch: str, dest: Path, pin: str | None) -> None:
    """Clone if missing, else fetch the branch. With `pin` (a locked SHA), fetch that commit
    instead of the branch: a depth-1 clone holds only the branch tip, not the locked commit."""
    shallow = ["--depth", "1"] if name in SHALLOW_REPOS else []
    if not dest.exists():
        # blob:none = commits and trees only; file contents are fetched when first read.
        cmd = ["clone", "--filter=blob:none", "--no-checkout", *shallow]
        if name not in ALL_BRANCH_REPOS:
            cmd += ["--single-branch", "--branch", branch]
        git(*cmd, url, str(dest))
    elif not (dest / ".git").is_dir():
        sys.exit(f"refusing: {dest} exists but is not a git clone; move it aside")
    elif pin is None:
        # --depth 1 keeps the shallow clone shallow. No --prune: fetch never deletes refs.
        git("fetch", *shallow, "origin", repo=dest)
    if pin is not None:
        git("fetch", *shallow, "origin", pin, repo=dest)


def head(repo: Path, branch: str) -> str:
    return git("rev-parse", "--verify", f"refs/remotes/origin/{branch}^{{commit}}", repo=repo)


def resolve_lock(manifest: dict[str, Any], cache: Path) -> dict[str, Any]:
    repos = manifest["repos"]
    releases = manifest["releases"]["list"]
    latest = manifest["releases"]["latest"]
    branches = manifest["website_release_branches"]

    lock: dict[str, Any] = {
        "schema_version": 0,
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release_date_cutoff": CUTOFF_RULE,
        "repos": {
            name: {
                "url": repo["url"],
                "default_branch": repo["default_branch"],
                "head": head(cache / name, repo["default_branch"]),
            }
            for name, repo in repos.items()
        },
        "website_releases": {},
        "release_date_snapshots": {name: {} for name in DATE_REPOS},
    }

    for rel in releases:
        version = rel["version"]
        if version == latest:
            ref = branches["latest"]
        else:
            ref = branches["pattern"].format(version=version)
        lock["website_releases"][version] = {"ref": ref, "sha": head(cache / "website", ref)}

    for name in DATE_REPOS:
        branch = repos[name]["default_branch"]
        for rel in releases:
            cutoff = f"{rel['release_date'].isoformat()}T23:59:59Z"
            sha = git(
                "rev-list",
                "-1",
                "--first-parent",
                f"--before={cutoff}",
                f"refs/remotes/origin/{branch}",
                repo=cache / name,
            )
            if not sha:
                sys.exit(f"{name}: no commit on {branch} at or before {cutoff}")
            snapshot = {"date": rel["release_date"].isoformat(), "sha": sha}
            lock["release_date_snapshots"][name][rel["version"]] = snapshot
    return lock


def locked_shas(lock: dict[str, Any]) -> list[tuple[str, str]]:
    """Every (repo name, SHA) pair recorded in the lock."""
    pairs = [(name, repo["head"]) for name, repo in lock["repos"].items()]
    pairs += [("website", entry["sha"]) for entry in lock["website_releases"].values()]
    for name, snapshots in lock["release_date_snapshots"].items():
        pairs += [(name, entry["sha"]) for entry in snapshots.values()]
    return pairs


def verify_lock(lock: dict[str, Any], cache: Path) -> None:
    missing = []
    for name, sha in locked_shas(lock):
        try:
            git("cat-file", "-e", f"{sha}^{{commit}}", repo=cache / name)
        except subprocess.CalledProcessError:
            missing.append(f"{name} {sha}")
    if missing:
        sys.exit("locked SHAs missing locally (--relock re-resolves):\n" + "\n".join(missing))
    print(f"verified: all {len(locked_shas(lock))} locked SHAs exist locally")


def assert_traced_keps(manifest: dict[str, Any], lock: dict[str, Any], cache: Path) -> None:
    """The manifest lists the traced KEPs so the fetch can assert they exist."""
    enhancements_head = lock["repos"]["enhancements"]["head"]
    for kep, path in manifest["sources"]["kep"]["traced"].items():
        try:
            tree = f"{enhancements_head}:{path.rstrip('/')}"
            git("rev-parse", "--verify", tree, repo=cache / "enhancements")
        except subprocess.CalledProcessError:
            sys.exit(f"traced KEP {kep} not found at {path} in enhancements {enhancements_head}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Partial-clone the corpus repos and lock SHAs.")
    parser.add_argument("--relock", action="store_true", help="re-resolve SHAs, overwrite lock")
    args = parser.parse_args()

    cache = cache_dir_or_exit()
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    cache.mkdir(parents=True, exist_ok=True)
    lock = None
    if LOCK.exists() and not args.relock:
        lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))

    for name, repo in manifest["repos"].items():
        # With a lock, the shallow repo fetches its locked SHA; only a (re)lock fetches the tip.
        pin = lock["repos"][name]["head"] if lock is not None and name in SHALLOW_REPOS else None
        clone_or_fetch(name, repo["url"], repo["default_branch"], cache / name, pin)

    if lock is not None:
        verify_lock(lock, cache)
        assert_traced_keps(manifest, lock, cache)
        print(f"lock unchanged: {LOCK.relative_to(REPO_ROOT)}")
        return

    lock = resolve_lock(manifest, cache)
    assert_traced_keps(manifest, lock, cache)
    header = (
        "# Generated by spikes/fetch.py (S02-T2). Don't edit by hand; use --relock.\n"
        "# The single record of corpus SHAs; see the S02-T2 notes in docs/slices/.\n"
    )
    LOCK.write_text(header + yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    print(f"wrote {LOCK.relative_to(REPO_ROOT)}: {len(locked_shas(lock))} SHAs")


if __name__ == "__main__":
    main()
