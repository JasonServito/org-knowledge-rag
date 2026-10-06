"""Fixtures shared by unit and integration tests."""

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from orgknow.embeddings.embedder import DIMENSIONS, EmbedResult, InputType
from orgknow.generation.schema import Generation, ModelAnswer, TokenUsage


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


class FakeEmbedder:
    """The `Embedder` protocol with no network: records every call, returns a fixed vector."""

    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[tuple[InputType, list[str]]] = []

    def embed(self, texts: Sequence[str], input_type: InputType) -> EmbedResult:
        self.calls.append((input_type, list(texts)))
        return EmbedResult(vectors=[[0.5] * DIMENSIONS for _ in texts], total_tokens=len(texts))


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


class FakeGenerator:
    """The `Generator` protocol with no network: records every call, returns a canned output."""

    usage = TokenUsage(input_tokens=1000, output_tokens=300, thinking_tokens=200)

    def __init__(self, output: ModelAnswer | None, stop_reason: str | None = "end_turn") -> None:
        self.output = output
        self.stop_reason = stop_reason
        self.calls: list[tuple[str, str]] = []  # (system, prompt) per call

    def generate(self, system: str, prompt: str) -> Generation:
        self.calls.append((system, prompt))
        return Generation(output=self.output, stop_reason=self.stop_reason, usage=self.usage)
