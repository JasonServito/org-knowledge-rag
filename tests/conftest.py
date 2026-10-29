"""Fixtures shared by unit and integration tests."""

import os
import subprocess
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from orgknow.embeddings.embedder import DIMENSIONS, EmbedResult, InputType
from orgknow.generation.schema import Generation, ModelAnswer, TokenUsage
from orgknow.retrieval.router import Route


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

    def switch(self, branch: str, create: bool = False) -> None:
        """Check out `branch`; with `create`, a new branch at the current commit."""
        self._git("switch", "--quiet", *(["--create"] if create else []), branch)

    def merge(self, branch: str, when: str) -> str:
        """Merge `branch` into the current branch with a merge commit (never a fast-forward), as
        GitHub merges a pull request, at committer time `when`; return the merge commit's SHA."""
        dates = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        self._git(
            "merge", "--quiet", "--no-ff", "-m", f"merge {branch} at {when}", branch, env=dates
        )
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


class FakeReranker:
    """The `Reranker` protocol with no model: records every call, scores each text from a table."""

    def __init__(self, scores: Mapping[str, float]) -> None:
        self.scores = scores
        self.calls: list[tuple[str, list[str]]] = []  # (question, texts) per call

    def score(self, question: str, texts: Sequence[str]) -> list[float]:
        self.calls.append((question, list(texts)))
        return [self.scores[text] for text in texts]


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


class FakeRouter:
    """The `Router` protocol with no network: records every call, routes each question from a
    table."""

    def __init__(self, routes: Mapping[str, Route]) -> None:
        self.routes = routes
        self.calls: list[str] = []  # the question per call

    def route(self, question: str) -> Route:
        self.calls.append(question)
        return self.routes[question]


class FakeObservation:
    """A Langfuse span or generation with no network: records its name, its fields (`update`
    replaces a field) and the observations started inside it."""

    trace_id = "fake-trace-id"

    def __init__(self, name: str, **fields: Any) -> None:
        self.name = name
        self.fields: dict[str, Any] = dict(fields)
        self.children: list[FakeObservation] = []

    def update(self, **fields: Any) -> None:
        self.fields.update(fields)

    def start_observation(self, name: str, **fields: Any) -> "FakeObservation":
        child = FakeObservation(name, **fields)
        self.children.append(child)
        return child

    @contextmanager
    def start_as_current_observation(self, name: str, **fields: Any) -> Iterator["FakeObservation"]:
        yield self.start_observation(name, **fields)

    def end(self) -> None:
        pass


class FakeLangfuse:
    """The Langfuse client calls an ask makes, with no network: one root observation per trace,
    and a count of flushes."""

    def __init__(self) -> None:
        self.traces: list[FakeObservation] = []
        self.flushes = 0

    @contextmanager
    def start_as_current_observation(self, name: str, **fields: Any) -> Iterator[FakeObservation]:
        root = FakeObservation(name, **fields)
        self.traces.append(root)
        yield root

    def flush(self) -> None:
        self.flushes += 1
