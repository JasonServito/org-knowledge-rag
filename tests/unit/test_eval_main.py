"""`python -m orgknow.eval run`'s results name (S07-T3, T4): the retrieval mode by default, plus
`-smoke` with `--smoke`, an explicit `--name` as given. `run` is replaced, so nothing is called or
written. And the run's dirty check (S07-T4), in a throwaway git repo, never this one."""

import subprocess
from pathlib import Path

import pytest

from orgknow.eval import __main__ as eval_main
from orgknow.eval.runner import _git_state
from orgknow.settings import Settings


@pytest.mark.parametrize(
    ("mode", "argv", "expected"),
    [
        ("dense", ["run"], "dense"),
        ("hybrid", ["run"], "hybrid"),
        ("hybrid", ["run", "--name", "custom"], "custom"),
        # S07-T4 fix 2: smoke runs get their own ablation-table row.
        ("dense", ["run", "--smoke"], "dense-smoke"),
        ("hybrid", ["run", "--smoke"], "hybrid-smoke"),
        ("hybrid", ["run", "--smoke", "--name", "custom"], "custom"),
        # S08-T2.
        ("rerank", ["run"], "rerank"),
        ("rerank", ["run", "--smoke"], "rerank-smoke"),
    ],
)
def test_the_run_name_defaults_to_the_retrieval_mode(
    monkeypatch: pytest.MonkeyPatch, mode: str, argv: list[str], expected: str
) -> None:
    names: list[str] = []

    def fake_run(settings: Settings, smoke: bool, name: str) -> int:
        names.append(name)
        return 0

    monkeypatch.setattr(eval_main, "run", fake_run)
    settings = Settings(_env_file=None, database_url="x", retrieval_mode=mode)

    assert eval_main.main(argv, settings) == 0
    assert names == [expected]


def test_the_dirty_check_ignores_eval_results(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    table = tmp_path / "eval" / "results" / "ablation.md"
    table.parent.mkdir(parents=True)
    table.write_text("run 1\n", encoding="utf-8")
    code = tmp_path / "code.py"
    code.write_text("x = 1\n", encoding="utf-8")
    git("init")
    git("add", ".")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
        "commit", "-m", "start",
    )  # fmt: skip

    # A run rewrites the tracked ablation table: the next run is still on clean code.
    table.write_text("run 1\nrun 2\n", encoding="utf-8")
    assert _git_state(tmp_path)[1] is False

    code.write_text("x = 2\n", encoding="utf-8")
    assert _git_state(tmp_path)[1] is True
