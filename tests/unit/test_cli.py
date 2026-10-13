"""`orgknow ask`'s route line in temporal mode (S09-T4), from hand-written routes, windows and
filters: the wording is the run contract's ("Route: HISTORY, releases until 1.27 (searched until
1.28)", "Route: CURRENT, current text only", "Route: WHY, no filter")."""

from pathlib import Path

import anthropic
import httpx2
import pytest
from tests.conftest import FakeEmbedder, FakeLangfuse

from orgknow import cli, pipeline
from orgknow.cli import route_line
from orgknow.db import models
from orgknow.db.models import TemporalFilter
from orgknow.generation.conflicts import Conflict
from orgknow.generation.schema import Generation
from orgknow.retrieval.router import Mode, Route
from orgknow.retrieval.temporal import Window
from orgknow.settings import Settings


def _route(mode: Mode) -> Route:
    # The line reads only the mode; the time scope is filler.
    return Route.model_validate(
        {"mode": mode, "time_scope": {"kind": "none", "start": None, "end": None}}
    )


def _filter(
    current_only: bool = False, from_release: int | None = None, until_release: int | None = None
) -> TemporalFilter:
    return TemporalFilter(
        current_only=current_only, from_release=from_release, until_release=until_release
    )


@pytest.mark.parametrize(
    ("mode", "window", "temporal", "expected"),
    [
        ("CURRENT", None, _filter(current_only=True), "Route: CURRENT, current text only"),
        (
            "HISTORY",
            Window(until_release=27),
            _filter(until_release=28),
            "Route: HISTORY, releases until 1.27 (searched until 1.28)",
        ),
        (
            "HISTORY",
            Window(from_release=30),
            _filter(from_release=29),
            "Route: HISTORY, releases from 1.30 (searched from 1.29)",
        ),
        (
            "HISTORY",
            Window(from_release=23, until_release=26),
            _filter(from_release=22, until_release=27),
            "Route: HISTORY, releases 1.23 to 1.26 (searched 1.22 to 1.27)",
        ),
        ("HISTORY", None, None, "Route: HISTORY, no filter"),
        # A window on a WHY route plans no filter (S09-R1 decision 3).
        ("WHY", Window(from_release=28, until_release=28), None, "Route: WHY, no filter"),
        ("CHANGE", None, None, "Route: CHANGE, no filter"),
    ],
)
def test_the_route_line(
    mode: Mode, window: Window | None, temporal: TemporalFilter | None, expected: str
) -> None:
    assert route_line(_route(mode), window, temporal) == expected


# S12-R1 triage g, on the CLI's path: when the answer call fails, the trace's `generate` still
# logs the rule-found conflicts. `retrieve` and `rule_conflicts` read the database, so here they
# return a hand-built hit and conflict; Langfuse is a fake.


class RaisingGenerator:
    """A `Generator` whose call fails the way the Anthropic SDK can."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, system: str, prompt: str) -> Generation:
        raise self.error


def test_a_failed_answer_still_traces_the_rule_found_conflicts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hit = models.Hit(
        chunk_id=5,
        content_hash="b" * 64,
        distance=0.2,
        text="Graduated to stable in v1.25.",
        canonical_id="kep:2579",
        source_type="kep",
        heading_path=["Implementation History"],
        release_windows=[(25, None)],
        current=True,
        claimed_status="implemented",
        claimed_stage="stable",
        snapshot_repo="enhancements",
        snapshot_sha="0123456789abcdef0123456789abcdef01234567",
        source_path="keps/sig-auth/2579-psp-replacement/README.md",
        metadata={"title": "PSP replacement"},
    )
    conflict = Conflict(
        kind="history_date",
        found_by="rule",
        chunk_ids=[5],
        documents=["kep:2579"],
        summary="A hand-written history-date conflict.",
        resolution="observed_beats_claimed",
        prevails=None,
    )
    monkeypatch.setattr(pipeline, "retrieve", lambda *args, **kwargs: [hit])
    monkeypatch.setattr(pipeline, "rule_conflicts", lambda conn, hits, settings: [conflict])
    settings = Settings(
        _env_file=None,
        database_url="postgresql://unused",
        corpus_manifest_path=Path(__file__).parents[2] / "config" / "corpus_manifest.yaml",
        langfuse_public_key=None,
        langfuse_secret_key=None,
        retrieval_mode="hybrid",
    )
    langfuse = FakeLangfuse()
    failing = RaisingGenerator(
        anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        )
    )

    code = cli.ask(
        "When did KEP-2579 graduate?", object(), FakeEmbedder(), failing, settings, langfuse
    )

    assert code == 1
    assert capsys.readouterr().err.splitlines() == ["error: Connection error."]
    [trace] = langfuse.traces
    assert (trace.name, [child.name for child in trace.children]) == (
        "ask",
        ["retrieve", "generate"],
    )
    generate = trace.children[1]
    assert generate.fields["level"] == "ERROR"
    assert generate.fields["metadata"] == {
        "stop_reason": None,  # an API error has none
        "conflicts": [
            {
                "kind": "history_date",
                "found_by": "rule",
                "chunk_ids": [5],
                "documents": ["kep:2579"],
                "summary": "A hand-written history-date conflict.",
                "resolution": "observed_beats_claimed",
                "prevails": None,
            }
        ],
    }
