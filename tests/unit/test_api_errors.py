"""Request IDs, the per-request JSON log line and the one error shape (S14-T2), offline:
`TestClient`, fakes and no database. Expected values are typed by hand from docs/interfaces.md
("Errors", "Request IDs", "Logs") and the S14-R1 run contract. The 502 and 503 envelopes are
checked in test_api.py, with the failures that cause them."""

import json
import logging
import re
from collections.abc import Iterator, Sequence
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import FakeEmbedder, FakeGenerator, FakeLangfuse

from orgknow import pipeline
from orgknow.api import app as api_app
from orgknow.api.app import create_app
from orgknow.api.middleware import choose_request_id
from orgknow.db.models import Hit
from orgknow.embeddings.embedder import EmbedResult, InputType
from orgknow.logs import JsonFormatter
from orgknow.provenance import chain as chain_module
from orgknow.settings import Settings

MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"
QUESTION = "What enforces pod security standards in-tree?"
NEW_ID = re.compile(r"[0-9a-f]{32}")  # a new random ID: 32 lowercase hex characters
# The per-request line's fields (docs/interfaces.md, "Logs"), in order; `trace_id` is extra.
REQUEST_FIELDS = [
    "ts",
    "level",
    "logger",
    "message",
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
]
TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00")  # ISO 8601, UTC, milliseconds


def _settings() -> Settings:
    """No .env, no Langfuse keys and hybrid mode: no reranker or router, and tracing off."""
    return Settings(
        _env_file=None,
        database_url="postgresql://orgknow:unused@127.0.0.1:5433/orgknow",
        corpus_manifest_path=MANIFEST,
        anthropic_api_key="sk-ant-fake",
        voyage_api_key="pa-fake",
        langfuse_public_key=None,
        langfuse_secret_key=None,
        retrieval_mode="hybrid",
    )


class JsonLines(logging.Handler):
    """Each record under `orgknow`, formatted as `make serve` writes it, when it is written (so
    the request ID is read inside the request, as in production), then parsed back."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


@pytest.fixture
def logged() -> Iterator[list[dict[str, Any]]]:
    handler = JsonLines()
    logger = logging.getLogger("orgknow")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler.lines
    logger.removeHandler(handler)
    logger.setLevel(level)


def _request_lines(logged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [line for line in logged if line["logger"] == "orgknow.api.middleware"]


def _assert_envelope(response: Any, status: int, code: str, message: str) -> None:
    """The one error shape, with the response's new request ID in the header and the body."""
    request_id = response.headers["X-Request-ID"]
    assert NEW_ID.fullmatch(request_id)
    assert response.status_code == status
    assert response.json() == {
        "error": {"code": code, "message": message, "request_id": request_id}
    }


@pytest.fixture
def no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """`POST /query` without a database: the connection is a placeholder, and `retrieve` embeds
    the question (as the real one does first) and finds nothing, so the model isn't called."""

    def retrieve(
        question: str,
        embedder: FakeEmbedder,
        conn: object,
        settings: Settings,
        reranker: Any = None,
        route: Any = None,
    ) -> list[Hit]:
        embedder.embed([question], "query")
        return []

    monkeypatch.setattr(api_app, "api_connection", lambda settings: nullcontext(object()))
    monkeypatch.setattr(pipeline, "retrieve", retrieve)
    monkeypatch.setattr(pipeline, "rule_conflicts", lambda conn, hits, settings: [])


# --- Request IDs (Claude's call b) -----------------------------------------------------------


@pytest.mark.parametrize("given", ["my-id-1", "A.b_c-9", "a" * 64], ids=["simple", "all", "64"])
def test_a_valid_caller_id_is_kept(given: str) -> None:
    assert choose_request_id(given) == given


@pytest.mark.parametrize(
    "given",
    [None, "", "a" * 65, "my-id-1\n", "my id", "café", "id/1"],
    ids=["missing", "empty", "65", "newline", "space", "non-ascii", "slash"],
)
def test_an_invalid_caller_id_is_replaced_by_a_new_one(given: str | None) -> None:
    assert NEW_ID.fullmatch(choose_request_id(given))


def test_a_valid_caller_id_is_echoed_in_the_header_the_body_and_the_log(
    logged: list[dict[str, Any]],
) -> None:
    client = TestClient(create_app(_settings()))  # no startup: the middleware works without it

    response = client.get("/no-such-path", headers={"X-Request-ID": "my-id-1"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "my-id-1"
    assert response.json()["error"]["request_id"] == "my-id-1"
    assert [line["request_id"] for line in logged] == ["my-id-1"]


@pytest.mark.parametrize(
    "given",
    [b"a" * 65, b"my id", "café".encode()],
    ids=["65", "space", "non-ascii"],
)
def test_an_invalid_caller_id_is_replaced_and_never_logged(
    logged: list[dict[str, Any]], given: bytes
) -> None:
    client = TestClient(create_app(_settings()))

    response = client.get("/health", headers={"X-Request-ID": given})

    new = response.headers["X-Request-ID"]
    assert NEW_ID.fullmatch(new)
    [line] = logged
    assert line["request_id"] == new
    assert given.decode() not in json.dumps(line, ensure_ascii=False)


# --- One JSON line per request ------------------------------------------------------------------


def test_each_request_logs_one_json_line_with_the_pinned_fields(
    logged: list[dict[str, Any]],
) -> None:
    client = TestClient(create_app(_settings()))

    response = client.get("/health?probe=1")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    [line] = logged
    assert list(line) == REQUEST_FIELDS
    assert TS.fullmatch(line["ts"])
    assert isinstance(line["duration_ms"], int | float)
    assert line["duration_ms"] >= 0
    assert {k: v for k, v in line.items() if k not in ("ts", "duration_ms")} == {
        "level": "INFO",
        "logger": "orgknow.api.middleware",
        "message": "GET /health 200",
        "request_id": response.headers["X-Request-ID"],
        "method": "GET",
        "path": "/health",  # without the query string
        "status": 200,
    }
    assert NEW_ID.fullmatch(line["request_id"])


def test_ready_gets_an_id_and_a_line_and_keeps_its_probe_body(
    logged: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_app, "is_reachable", lambda url, timeout: False)
    client = TestClient(create_app(_settings()))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}  # a probe answer, not the envelope
    [line] = logged
    assert line["message"] == "GET /ready 503"
    assert line["request_id"] == response.headers["X-Request-ID"]


class WarningEmbedder(FakeEmbedder):
    """A `FakeEmbedder` that first logs the warning the Voyage client logs before a retry."""

    def embed(self, texts: Sequence[str], input_type: InputType) -> EmbedResult:
        logging.getLogger("orgknow.embeddings.voyage").warning(
            "Voyage API returned HTTP 503; retrying in 1 s"
        )
        return super().embed(texts, input_type)


@pytest.mark.usefixtures("no_database")
def test_a_warning_inside_a_request_carries_its_id(logged: list[dict[str, Any]]) -> None:
    app = create_app(_settings(), embedder=WarningEmbedder(), generator=FakeGenerator(None))

    with TestClient(app) as client:
        response = client.post(
            "/query", json={"question": QUESTION}, headers={"X-Request-ID": "req-warn-1"}
        )

    assert response.status_code == 200
    assert [(line["logger"], line["level"], line.get("request_id")) for line in logged] == [
        ("orgknow.embeddings.voyage", "WARNING", "req-warn-1"),
        ("orgknow.api.middleware", "INFO", "req-warn-1"),
    ]


@pytest.mark.usefixtures("no_database")
def test_the_query_line_carries_the_trace_id_when_tracing_is_on(
    logged: list[dict[str, Any]],
) -> None:
    app = create_app(
        _settings(), embedder=FakeEmbedder(), generator=FakeGenerator(None), langfuse=FakeLangfuse()
    )

    with TestClient(app) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.json()["trace_id"] == "fake-trace-id"
    [line] = _request_lines(logged)
    assert list(line) == [*REQUEST_FIELDS, "trace_id"]
    assert line["trace_id"] == "fake-trace-id"


@pytest.mark.usefixtures("no_database")
def test_without_tracing_the_query_line_has_no_trace_id(logged: list[dict[str, Any]]) -> None:
    app = create_app(_settings(), embedder=FakeEmbedder(), generator=FakeGenerator(None))

    with TestClient(app) as client:  # startup: no Langfuse keys, so tracing is off
        response = client.post("/query", json={"question": QUESTION})

    assert response.json()["trace_id"] is None
    [line] = _request_lines(logged)
    assert "trace_id" not in line  # absent, not null
    assert line["message"] == "POST /query 200"


# --- The one error shape ------------------------------------------------------------------------


def test_an_unknown_path_is_404_not_found() -> None:
    response = TestClient(create_app(_settings())).get("/no-such-path")

    _assert_envelope(response, 404, "not_found", "Not Found")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (json.dumps({}), "body.question: Field required"),
        (json.dumps({"question": " "}), "body.question: String should match pattern '\\S'"),
        (
            json.dumps({"question": ["secret-input-1"]}),
            "body.question: Input should be a valid string",
        ),
        ("not json", "body.0: JSON decode error"),
    ],
    ids=["missing", "blank", "not-a-string", "not-json"],
)
def test_a_bad_query_body_is_422_naming_the_field_never_the_input(
    content: str, message: str
) -> None:
    client = TestClient(
        create_app(_settings(), embedder=FakeEmbedder(), generator=FakeGenerator(None))
    )

    response = client.post("/query", content=content, headers={"content-type": "application/json"})

    _assert_envelope(response, 422, "invalid_request", message)
    assert "secret-input-1" not in response.text


def test_a_wrong_method_keeps_fastapis_405_body_with_an_id() -> None:
    response = TestClient(create_app(_settings())).get("/query")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}
    assert NEW_ID.fullmatch(response.headers["X-Request-ID"])


def test_an_unexpected_error_is_a_500_without_its_text_and_logged_with_its_traceback(
    logged: list[dict[str, Any]],
) -> None:
    app = create_app(_settings())

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret-xyz")

    # As a real client sees it: the test client doesn't re-raise the server's exception.
    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    _assert_envelope(response, 500, "internal", "internal error")
    assert "secret-xyz" not in response.text
    error, request = logged
    assert (error["logger"], error["level"], error["message"]) == (
        "orgknow.api.middleware",
        "ERROR",
        "unexpected error",
    )
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["exc_info"].endswith("RuntimeError: secret-xyz")
    assert (request["message"], request["status"]) == ("GET /boom 500", 500)
    assert request["request_id"] == response.headers["X-Request-ID"]


UNDEFINED_TABLE = 'relation "decisions" does not exist'


def _missing_table(*args: object, **kwargs: object) -> None:
    raise psycopg.errors.UndefinedTable(UNDEFINED_TABLE)


@pytest.mark.parametrize(
    ("method", "path", "patch"),
    [
        ("POST", "/query", (pipeline, "retrieve")),
        ("GET", "/decisions/kep:2572", (chain_module, "stored_decision")),
    ],
    ids=["query", "decisions"],
)
def test_a_database_error_that_is_not_a_connection_failure_is_a_500(
    logged: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    patch: tuple[object, str],
) -> None:
    # K1 (S14-R1 step 0): a missing table is a database error but not a connection failure.
    monkeypatch.setattr(api_app, "api_connection", lambda settings: nullcontext(object()))
    monkeypatch.setattr(*patch, _missing_table)
    app = create_app(_settings(), embedder=FakeEmbedder(), generator=FakeGenerator(None))

    response = TestClient(app).request(method, path, json={"question": QUESTION})

    _assert_envelope(response, 500, "internal", "internal error")
    assert UNDEFINED_TABLE not in response.text
    assert logged[0]["exc_info"].endswith(f"UndefinedTable: {UNDEFINED_TABLE}")


# --- Logging stays the caller's choice (the CLI's stderr is unchanged) ---------------------------


def test_building_and_calling_the_app_configures_no_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, orgknow = logging.getLogger(), logging.getLogger("orgknow")
    # Without pytest's capture handlers, as in the CLI: a `logging.basicConfig` call would then
    # add a handler (with one present, it does nothing).
    monkeypatch.setattr(root, "handlers", [])
    before = (root.level, list(orgknow.handlers), orgknow.level)

    TestClient(create_app(_settings())).get("/health")

    assert root.handlers == []
    assert (root.level, list(orgknow.handlers), orgknow.level) == before
