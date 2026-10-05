"""Fixtures shared by unit and integration tests."""

import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest


class GitRepo:
    """A tiny local git repo for ingestion tests: no remote, no network."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True)
        self._git("init", "--quiet", "--initial-branch=main")

    def _git(self, *args: str, env: Mapping[str, str] | None = None) -> str:
        result = subprocess.run(
            [
                *("git", "-C", str(self.path), "-c", "user.name=Test", "-c", "user.email=t@x.org"),
                *("-c", "commit.gpgsign=false", *args),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=None if env is None else {**os.environ, **env},
        )
        return result.stdout.strip()

    def commit(
        self, files: Mapping[str, bytes | None], when: str = "2022-01-01T00:00:00+00:00"
    ) -> str:
        """Write (bytes) or delete (None) files, commit everything at committer time `when`
        (ISO 8601 with an offset), and return the new commit's SHA."""
        for name, content in files.items():
            target = self.path / name
            if content is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        self._git("add", "--all")
        dates = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        self._git("commit", "--quiet", "--allow-empty", "-m", f"commit at {when}", env=dates)
        return self._git("rev-parse", "HEAD")


@pytest.fixture
def make_git_repo(tmp_path: Path) -> Callable[[str], GitRepo]:
    """Build a repo at tmp_path/<name>; a folder of them stands in for CORPUS_CACHE_DIR."""
    return lambda name: GitRepo(tmp_path / name)
