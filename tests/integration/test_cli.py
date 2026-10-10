"""`orgknow ask` (S04-T7) offline: the fake embedder and generator, the test database, no keys.

Expected outputs are written by hand from the pinned `ask` output (S04-R2 run contract). Tests
never contact Langfuse, Anthropic or Voyage: `ask` gets fakes, and `main` stops before it builds
a client.
"""

import hashlib
import json
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import anthropic
import httpx2
import psycopg
import pytest
from psycopg.rows import TupleRow
from tests.conftest import FakeEmbedder, FakeGenerator, FakeReranker, FakeRouter

from orgknow.cli import ask, langfuse_client, main
from orgknow.db.chunks import add_chunks, add_embedding
from orgknow.db.documents import create_document
from orgknow.db.models import NewChunk, NewVersion
from orgknow.db.versions import insert_version
from orgknow.embeddings.embedder import DIMENSIONS, EmbedResult, InputType
from orgknow.generation.schema import Answer, Generation, ModelAnswer
from orgknow.retrieval.router import Route, RouterError
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"
QUESTION = "What enforces pod security standards in-tree?"
TEXT = "The Pod Security admission controller enforces the Pod Security Standards."
# Typed by hand: 64 and 40 lowercase hex characters.
VERSION_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SHA = "0123456789abcdef0123456789abcdef01234567"
PATH = "content/en/docs/concepts/security/pod-security-admission.md"
# Fake secrets: neither may appear in anything `ask` prints.
FAKE_ANTHROPIC_KEY = "sk-ant-fake-secret-0f1e2d3c"
FAKE_VOYAGE_KEY = "pa-fake-secret-4b5a6978"
TRACING_OFF = "tracing off: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to trace each ask"


@pytest.fixture
def cli_settings(settings: Settings) -> Settings:
    """The test database and the committed manifest, fake API keys and no Langfuse keys.

    No .env file, and the Langfuse keys are passed as None, so neither a local .env nor the
    shell can turn tracing on. Hybrid mode, whatever the default mode is, so no test loads the
    reranker's model.
    """
    return Settings(
        _env_file=None,
        database_url=settings.database_url,
        corpus_manifest_path=MANIFEST,
        anthropic_api_key=FAKE_ANTHROPIC_KEY,
        voyage_api_key=FAKE_VOYAGE_KEY,
        langfuse_public_key=None,
        langfuse_secret_key=None,
        retrieval_mode="hybrid",
    )


def _store_one_chunk(conn: Conn) -> int:
    """The Pod Security Admission page, current since 1.30, with one chunk under "Exemptions"
    and its vector under the fake embedder's model. Returns the chunk id."""
    document_id = create_document(
        conn, "web:/docs/concepts/security/pod-security-admission/", "docs_page"
    )
    version = NewVersion(
        document_id=document_id,
        content_hash=VERSION_HASH,
        source_path=PATH,
        snapshot_repo="website",
        snapshot_ref="release-1.30",
        snapshot_sha=SHA,
        valid_from_release=30,
        valid_from_date=datetime(2024, 4, 17, tzinfo=UTC),
        metadata={"title": "Pod Security Admission"},
    )
    [chunk_id] = add_chunks(
        conn,
        insert_version(conn, version),
        [NewChunk(ordinal=0, heading_path=["Exemptions"], text=TEXT)],
    )
    content_hash = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()  # rule R13
    add_embedding(conn, content_hash, FakeEmbedder.model, [1.0] + [0.0] * (DIMENSIONS - 1))
    return chunk_id


def _answered(chunk_id: int) -> FakeGenerator:
    return FakeGenerator(
        ModelAnswer(
            answer_status="answered",
            answer="The Pod Security admission controller.",
            evidence=[chunk_id],
            insufficient_evidence_reason=None,
        )
    )


def test_ask_prints_the_answer_json_offline(
    conn: Conn,
    cli_settings: Settings,
    fake_embedder: FakeEmbedder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chunk_id = _store_one_chunk(conn)
    generator = _answered(chunk_id)

    code = ask(
        QUESTION, conn, fake_embedder, generator, cli_settings, langfuse_client(cli_settings)
    )

    out, _ = capsys.readouterr()
    assert code == 0
    assert out.endswith("\n")
    assert out.count("\n") == 1  # one line of JSON
    Answer.model_validate_json(out)  # parses into the output model
    # The pinned format, written by hand; trace_id is null with tracing off.
    assert json.loads(out) == {
        "question": QUESTION,
        "answer_status": "answered",
        "answer": "The Pod Security admission controller.",
        "evidence": [
            {
                "chunk_id": chunk_id,
                "document": "web:/docs/concepts/security/pod-security-admission/",
                "title": "Pod Security Admission",
                "section": "Exemptions",
                "source_type": "docs_page",
                "release_windows": [["1.30", None]],
                "claimed_status": None,
                "claimed_stage": None,
                "source_url": f"https://github.com/kubernetes/website/blob/{SHA}/{PATH}",
            }
        ],
        "insufficient_evidence_reason": None,
        "model": "claude-opus-5-5",
        "trace_id": None,
    }
    # One query embedding, one model call.
    assert fake_embedder.calls == [("query", [QUESTION])]
    assert len(generator.calls) == 1


def test_no_langfuse_keys_turn_tracing_off_and_no_secret_is_printed(
    conn: Conn,
    cli_settings: Settings,
    fake_embedder: FakeEmbedder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generator = _answered(_store_one_chunk(conn))

    code = ask(
        QUESTION, conn, fake_embedder, generator, cli_settings, langfuse_client(cli_settings)
    )

    out, err = capsys.readouterr()
    assert code == 0
    # Our one line, and nothing from the Langfuse SDK.
    assert err.splitlines() == [TRACING_OFF]
    for secret in (FAKE_ANTHROPIC_KEY, FAKE_VOYAGE_KEY):
        assert secret not in out
        assert secret not in err


class RaisingEmbedder:
    """An `Embedder` whose call fails the way the Voyage client can."""

    model = FakeEmbedder.model

    def __init__(self, error: Exception) -> None:
        self.error = error

    def embed(self, texts: list[str], input_type: InputType) -> EmbedResult:
        raise self.error


class RaisingGenerator:
    """A `Generator` whose call fails the way the Anthropic SDK can."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, system: str, prompt: str) -> Generation:
        raise self.error


@pytest.mark.parametrize(
    ("embedder", "generator", "expected"),
    [
        (
            FakeEmbedder(),
            FakeGenerator(None, stop_reason="refusal"),
            "error: no usable answer from the model (stop reason: refusal)",
        ),
        (
            FakeEmbedder(),
            RaisingGenerator(
                anthropic.APIConnectionError(
                    request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
                )
            ),
            "error: Connection error.",
        ),
        (
            RaisingEmbedder(RuntimeError("Voyage API returned HTTP 503: upstream\nunavailable")),
            FakeGenerator(None),
            "error: Voyage API returned HTTP 503: upstream unavailable",  # one line
        ),
        (
            RaisingEmbedder(urllib.error.URLError(ConnectionRefusedError(111, "refused"))),
            FakeGenerator(None),
            "error: <urlopen error [Errno 111] refused>",
        ),
    ],
    ids=["generation-error", "anthropic-api-error", "voyage-http-error", "voyage-no-connection"],
)
def test_an_error_is_one_stderr_line_and_exit_1(
    conn: Conn,
    cli_settings: Settings,
    embedder: FakeEmbedder | RaisingEmbedder,
    generator: FakeGenerator | RaisingGenerator,
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store_one_chunk(conn)

    code = ask(QUESTION, conn, embedder, generator, cli_settings, langfuse_client(cli_settings))

    out, err = capsys.readouterr()
    assert code == 1
    assert out == ""
    # "tracing off", then the error on one line: no traceback.
    assert err.splitlines() == [TRACING_OFF, expected]


# Temporal mode (S09-T4): `ask` routes the question live (here with a fake router), prints the
# route line on stderr, then retrieves with the route's filter. The stored chunk is the PSA page's,
# current since 1.30.


def _temporal(settings: Settings) -> Settings:
    return settings.model_copy(update={"retrieval_mode": "temporal"})


def _route(mode: str, kind: str = "none", start: str | None = None) -> Route:
    return Route.model_validate(
        {"mode": mode, "time_scope": {"kind": kind, "start": start, "end": None}}
    )


def test_a_temporal_ask_prints_the_route_line_then_answers_from_the_filtered_texts(
    conn: Conn,
    cli_settings: Settings,
    fake_embedder: FakeEmbedder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chunk_id = _store_one_chunk(conn)
    generator = _answered(chunk_id)
    router = FakeRouter({QUESTION: _route("CURRENT")})
    settings = _temporal(cli_settings)

    code = ask(
        QUESTION,
        conn,
        fake_embedder,
        generator,
        settings,
        langfuse_client(settings),
        FakeReranker({TEXT: 0.5}),
        router,
    )

    out, err = capsys.readouterr()
    assert code == 0
    assert router.calls == [QUESTION]
    # The route line goes to stderr, so stdout stays one line of JSON.
    assert err.splitlines() == [TRACING_OFF, "Route: CURRENT, current text only"]
    assert [e["chunk_id"] for e in json.loads(out)["evidence"]] == [chunk_id]
    assert len(generator.calls) == 1


def test_a_temporal_ask_whose_filter_keeps_nothing_is_insufficient_evidence_without_a_call(
    conn: Conn,
    cli_settings: Settings,
    fake_embedder: FakeEmbedder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # "before 1.28": until 1.27, searched until 1.28 (slack 1). The page is valid from 1.30 only.
    _store_one_chunk(conn)
    generator, reranker = _answered(0), FakeReranker({TEXT: 0.5})
    router = FakeRouter({QUESTION: _route("HISTORY", "before", "1.28")})
    settings = _temporal(cli_settings)

    code = ask(
        QUESTION,
        conn,
        fake_embedder,
        generator,
        settings,
        langfuse_client(settings),
        reranker,
        router,
    )

    out, err = capsys.readouterr()
    assert code == 0
    assert err.splitlines() == [
        TRACING_OFF,
        "Route: HISTORY, releases until 1.27 (searched until 1.28)",
    ]
    answer = json.loads(out)
    assert (answer["answer_status"], answer["insufficient_evidence_reason"]) == (
        "insufficient_evidence",
        "no evidence retrieved",
    )
    assert (generator.calls, reranker.calls) == ([], [])


class RaisingRouter:
    """A `Router` whose call fails the way the Claude router can."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def route(self, question: str) -> Route:
        raise self.error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            RouterError("no route from the model (stop reason: refusal)"),
            "error: no route from the model (stop reason: refusal)",
        ),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            "error: Connection error.",
        ),
    ],
    ids=["router-error", "anthropic-api-error"],
)
def test_a_router_failure_is_one_stderr_line_and_exit_1(
    conn: Conn,
    cli_settings: Settings,
    fake_embedder: FakeEmbedder,
    error: Exception,
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store_one_chunk(conn)
    generator = _answered(0)
    settings = _temporal(cli_settings)

    code = ask(
        QUESTION,
        conn,
        fake_embedder,
        generator,
        settings,
        langfuse_client(settings),
        FakeReranker({TEXT: 0.5}),
        RaisingRouter(error),
    )

    out, err = capsys.readouterr()
    assert code == 1
    assert out == ""
    assert err.splitlines() == [TRACING_OFF, expected]
    # It stops before the question is embedded or answered.
    assert (fake_embedder.calls, generator.calls) == ([], [])


@pytest.mark.parametrize("question", ["", "   "])
def test_an_empty_question_exits_2(question: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["ask", question])

    assert exit_info.value.code == 2
    assert "orgknow ask: error: the question is empty" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        (
            "anthropic_api_key",
            "ANTHROPIC_API_KEY is not set: add the key to .env (see .env.example).",
        ),
        ("voyage_api_key", "VOYAGE_API_KEY is not set: add the key to .env (see .env.example)."),
    ],
)
def test_a_missing_api_key_stops_with_a_clear_message(
    cli_settings: Settings, missing: str, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = cli_settings.model_copy(update={missing: None})

    code = main(["ask", QUESTION], settings)

    out, err = capsys.readouterr()
    assert code == 1
    assert out == ""
    assert err.splitlines() == [expected]
