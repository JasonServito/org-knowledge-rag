"""`python -m orgknow.eval run`'s results name (S07-T3): the retrieval mode by default, an explicit
`--name` as given. `run` is replaced, so nothing is called or written."""

import pytest

from orgknow.eval import __main__ as eval_main
from orgknow.settings import Settings


@pytest.mark.parametrize(
    ("mode", "argv", "expected"),
    [
        ("dense", ["run"], "dense"),
        ("hybrid", ["run"], "hybrid"),
        ("hybrid", ["run", "--name", "custom"], "custom"),
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
