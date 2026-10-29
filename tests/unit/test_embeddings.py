"""S04-R1 decision 7 and the embeddings edge cases: batching, the run cap, the pinned Voyage
request and response, retries, and the missing key. No network, no database.

Expected values are hand arithmetic: a text of n characters is ceil(n / 4) estimated tokens.
The request and response shapes are Voyage's API reference (read 2026-10-04).
"""

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from pydantic import SecretStr

from orgknow.db.models import TextToEmbed
from orgknow.embeddings.embed import RunTooLarge, batch_texts, estimate_run, main
from orgknow.embeddings.voyage import VoyageEmbedder, parse_response, request_body
from orgknow.settings import Settings

URL = "https://voyage.invalid/v1/embeddings"
KEY = "pa-test-key-do-not-print"


def _texts(*sizes: int) -> list[TextToEmbed]:
    """One text per size, `size` characters long, each with its own (fake) hash."""
    return [TextToEmbed(content_hash=f"{i:064x}", text="x" * n) for i, n in enumerate(sizes)]


def _sizes(batches: list[list[TextToEmbed]]) -> list[int]:
    return [len(batch) for batch in batches]


# --- Batching: at most 128 texts and 60,000 estimated tokens per request -----------------------


def test_300_small_texts_make_batches_of_128_128_44() -> None:
    texts = _texts(*[4] * 300)  # 1 token each

    assert _sizes(batch_texts(texts, 128, 60_000)) == [128, 128, 44]


def test_texts_of_25000_tokens_go_two_per_batch() -> None:
    # 100,000 characters = 25,000 tokens: 2 make 50,000 <= 60,000; 3 would make 75,000.
    texts = _texts(*[100_000] * 5)

    assert _sizes(batch_texts(texts, 128, 60_000)) == [2, 2, 1]


def test_a_text_over_the_token_budget_goes_alone() -> None:
    # 240,004 characters = 60,001 tokens.
    texts = _texts(4, 4, 240_004, 4, 4)

    batches = batch_texts(texts, 128, 60_000)

    assert _sizes(batches) == [2, 1, 2]
    assert batches[1] == [texts[2]]
    assert [t for batch in batches for t in batch] == texts  # order kept, none lost


# --- Run cap: refuse to start above EMBED_MAX_TOKENS_PER_RUN ----------------------------------


def test_an_estimate_above_the_run_cap_is_refused() -> None:
    # 20 characters = 5 tokens; 21 characters = 6 tokens. 5 + 6 = 11 > 10.
    with pytest.raises(RunTooLarge, match="11 estimated tokens"):
        estimate_run(_texts(20, 21), max_tokens_per_run=10)


def test_an_estimate_at_the_run_cap_is_allowed() -> None:
    assert estimate_run(_texts(20, 20), max_tokens_per_run=10) == 10


# --- The pinned Voyage request and response ----------------------------------------------------


def test_request_body_matches_the_pinned_format() -> None:
    assert request_body(["first", "second"], "voyage-4-large", "document") == {
        "input": ["first", "second"],
        "model": "voyage-4-large",
        "input_type": "document",
        "output_dimension": 1024,
    }


def _response(items: list[tuple[int, list[float]]], total_tokens: int = 7) -> bytes:
    """A Voyage response body: one `data` item per (index, embedding), in the order given."""
    data = [{"object": "embedding", "embedding": e, "index": i} for i, e in items]
    return json.dumps(
        {
            "object": "list",
            "data": data,
            "model": "voyage-4-large",
            "usage": {"total_tokens": total_tokens},
        }
    ).encode()


def test_response_vectors_are_put_in_input_order() -> None:
    zeros, ones = [0.0] * 1024, [1.0] * 1024

    result = parse_response(_response([(1, ones), (0, zeros)]), count=2)

    assert result.vectors == [zeros, ones]
    assert result.total_tokens == 7


@pytest.mark.parametrize(
    ("items", "error"),
    [
        ([(0, [0.0] * 1024), (1, [0.0] * 1023)], "1023 numbers"),
        ([(0, [0.0] * 1024), (2, [0.0] * 1024)], r"indexes \[0, 2\]"),
        ([(0, [0.0] * 1024)], r"indexes \[0\]"),
    ],
)
def test_a_malformed_response_is_refused(items: list[tuple[int, list[float]]], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_response(_response(items), count=2)


# --- HTTP: header, retries, and the key never in an error --------------------------------------


class _FakeUrlopen:
    """Stands in for urllib.request.urlopen: replays `outcomes`, recording each request."""

    def __init__(self, outcomes: list[bytes | int]) -> None:
        self.outcomes = outcomes
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, int):
            body = io.BytesIO(b'{"detail": "error detail"}')
            raise urllib.error.HTTPError(request.full_url, outcome, "error", {}, body)
        return io.BytesIO(outcome)


def _patch_http(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[bytes | int]
) -> tuple[Any, list[float]]:
    fake = _FakeUrlopen(outcomes)
    sleeps: list[float] = []
    monkeypatch.setattr("orgknow.embeddings.voyage.urllib.request.urlopen", fake)
    monkeypatch.setattr("orgknow.embeddings.voyage.time.sleep", sleeps.append)
    return fake, sleeps


def _embedder(max_retries: int, timeout_s: int = 60) -> VoyageEmbedder:
    return VoyageEmbedder(
        URL, SecretStr(KEY), "voyage-4-large", timeout_s=timeout_s, max_retries=max_retries
    )


def test_429_and_5xx_are_retried_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, sleeps = _patch_http(monkeypatch, [429, 503, _response([(0, [0.25] * 1024)])])
    embedder = _embedder(max_retries=3)

    result = embedder.embed(["hello"], "document")

    assert result.vectors == [[0.25] * 1024]
    assert len(fake.requests) == 3
    assert sleeps == [1, 2]  # the run plan's backoff: 1 s, 2 s, 4 s
    request = fake.requests[0]
    assert request.get_method() == "POST"
    assert request.full_url == URL
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert json.loads(request.data) == {  # the pinned format, typed by hand
        "input": ["hello"],
        "model": "voyage-4-large",
        "input_type": "document",
        "output_dimension": 1024,
    }


def test_retries_stop_after_three(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, sleeps = _patch_http(monkeypatch, [500, 500, 500, 500])
    embedder = _embedder(max_retries=3)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        embedder.embed(["hello"], "document")

    assert len(fake.requests) == 4  # 1 try + 3 retries
    assert sleeps == [1, 2, 4]


# S14-T3: the retry count is VOYAGE_MAX_RETRIES, the waits double from 1 s, and every try waits
# at most VOYAGE_TIMEOUT_S. Counted by hand: 1 try + n retries; the waits 1, 2, 4, 8 s.
@pytest.mark.parametrize(
    ("max_retries", "tries", "waits"),
    [(0, 1, []), (1, 2, [1]), (4, 5, [1, 2, 4, 8])],
    ids=["no-retry", "1-retry", "4-retries"],
)
def test_retries_stop_after_voyage_max_retries(
    monkeypatch: pytest.MonkeyPatch, max_retries: int, tries: int, waits: list[int]
) -> None:
    fake, sleeps = _patch_http(monkeypatch, [503] * 10)  # always 503: more than any case uses
    embedder = _embedder(max_retries=max_retries, timeout_s=7)

    with pytest.raises(RuntimeError, match="HTTP 503"):
        embedder.embed(["hello"], "document")

    assert len(fake.requests) == tries
    assert sleeps == waits
    assert fake.timeouts == [7] * tries


def test_a_client_error_is_not_retried_and_never_shows_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, sleeps = _patch_http(monkeypatch, [401])
    embedder = _embedder(max_retries=3)

    with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
        embedder.embed(["hello"], "document")

    assert (len(fake.requests), sleeps) == (1, [])
    assert "error detail" in str(exc_info.value)  # Voyage's reason, for the person running it
    assert KEY not in str(exc_info.value)
    assert KEY not in repr(embedder)


# --- make embed without a key ------------------------------------------------------------------


def test_make_embed_without_a_key_stops_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    # An unreachable database: the key check must come before any connection.
    settings = Settings(_env_file=None, database_url="postgresql://u:p@db.invalid:5432/x")

    with pytest.raises(SystemExit, match="VOYAGE_API_KEY is not set"):
        main(settings)
