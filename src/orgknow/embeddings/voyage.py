"""Voyage AI embeddings over HTTP with the standard library's urllib (S04-R1 decision 7).

One POST per batch: no SDK and no HTTP library needed. The request and response shapes are
pinned in the run plan ("Voyage request"); `request_body` and `parse_response` hold them as
pure functions, and `VoyageEmbedder` adds the HTTP call and its retries.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, SecretStr

from orgknow.embeddings.embedder import DIMENSIONS, EmbedResult, InputType

log = logging.getLogger(__name__)


class _Item(BaseModel):
    index: int  # the position of its text in the request's `input`
    embedding: list[float]


class _Usage(BaseModel):
    total_tokens: int


class _Response(BaseModel):
    """The fields read from Voyage's response; the others are ignored."""

    data: list[_Item]
    usage: _Usage


def request_body(texts: Sequence[str], model: str, input_type: InputType) -> dict[str, Any]:
    """The JSON body of one request. Every request asks for 1024 numbers per vector."""
    return {
        "input": list(texts),
        "model": model,
        "input_type": input_type,
        "output_dimension": DIMENSIONS,
    }


def parse_response(raw: bytes, count: int) -> EmbedResult:
    """The vectors of a response to `count` texts, in input order (sorted by `index`).

    Raises ValueError unless there is exactly one vector per input text, each with 1024
    numbers: a missing or misplaced vector would be stored under the wrong text.
    """
    response = _Response.model_validate_json(raw)
    items = sorted(response.data, key=lambda item: item.index)
    indexes = [item.index for item in items]
    if indexes != list(range(count)):
        raise ValueError(f"expected indexes 0 to {count - 1}, got indexes {indexes}")
    for item in items:
        if len(item.embedding) != DIMENSIONS:
            raise ValueError(
                f"vector {item.index} has {len(item.embedding)} numbers, expected {DIMENSIONS}"
            )
    return EmbedResult(
        vectors=[item.embedding for item in items], total_tokens=response.usage.total_tokens
    )


class VoyageEmbedder:
    """The `Embedder` protocol on Voyage's embeddings API.

    Each try waits at most `timeout_s` seconds for each step (connect, each read): urllib's
    socket timeout. An HTTP 429 (rate limited) or 5xx (server error) is retried up to
    `max_retries` times, after 1 s, 2 s, 4 s, ... (doubling); any other error is a problem with
    the request, which retrying can't fix (S04-R1 plan, "Retries"; the counts are settings
    since S14-T3: VOYAGE_TIMEOUT_S, VOYAGE_MAX_RETRIES).
    """

    def __init__(
        self, url: str, api_key: SecretStr, model: str, *, timeout_s: float, max_retries: int
    ) -> None:
        self.url = url
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        # Kept as SecretStr until a request is built: printed or logged, it shows "**********".
        self._api_key = api_key

    def embed(self, texts: Sequence[str], input_type: InputType) -> EmbedResult:
        body = json.dumps(request_body(texts, self.model, input_type)).encode()
        return parse_response(self._post(body), len(texts))

    def _post(self, body: bytes) -> bytes:
        """POST `body`, retrying on 429 and 5xx. Raises RuntimeError with Voyage's reason (never
        the key) once retries run out, or at once on any other HTTP error."""
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        retries = 0
        while True:
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    raw: bytes = response.read()
                    return raw
            except urllib.error.HTTPError as exc:
                retryable = exc.code == 429 or exc.code >= 500
                if not retryable or retries == self.max_retries:
                    reason = exc.read().decode("utf-8", errors="replace")[:500]
                    raise RuntimeError(f"Voyage API returned HTTP {exc.code}: {reason}") from None
                delay = 2**retries  # 1 s, 2 s, 4 s, ...
                log.warning("Voyage API returned HTTP %d; retrying in %d s", exc.code, delay)
                time.sleep(delay)
                retries += 1
