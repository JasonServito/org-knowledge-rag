"""`scripts/deploy.sh`'s clean-tree check (S16-T4, contract c3), in a throwaway git repo, never this
one. A stub `make`, first on PATH, logs its arguments and fails, so the script stops at its first
build step: nothing is built, pushed or deployed, and no network is used."""

import os
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).parents[2] / "scripts" / "deploy.sh"


def _repo(tmp_path: Path) -> Path:
    """A git repo holding one committed file."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")
    git("init")
    git("add", ".")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
        "commit", "-m", "start",
    )  # fmt: skip
    return repo


def _deploy(tmp_path: Path, repo: Path) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the deploy script in `repo`; return its result and the stub `make`'s calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "make-calls.log"
    stub = bin_dir / "make"
    stub.write_text(f"#!/bin/sh\necho \"$*\" >> '{calls}'\nexit 1\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=repo, env=env, capture_output=True, text=True, check=False
    )
    made = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, made


def test_a_modified_tracked_file_stops_it_before_any_build(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")

    result, made = _deploy(tmp_path, repo)

    assert result.returncode == 1
    assert "uncommitted changes" in result.stderr
    assert made == []


def test_an_untracked_file_alone_does_not_stop_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "ingest1.log").write_text("a log\n", encoding="utf-8")

    result, made = _deploy(tmp_path, repo)

    assert "uncommitted changes" not in result.stderr
    # The stub `make` fails, so the script stops at its first build step: the audit.
    assert made == ["audit"]
    assert result.returncode != 0
