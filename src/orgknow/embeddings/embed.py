"""Embed every chunk text that has no vector yet: `make embed` (S04-R1 decision 4).

One vector per unique text per model. The `embeddings` table is the cache: only texts with no
row for the model are sent, so a re-run sends 0 requests. Paid: it calls the Voyage API.

1. List the texts with no vector for the model (DB), and estimate their tokens as characters / 4.
   Above EMBED_MAX_TOKENS_PER_RUN, refuse to start: nothing is sent or deleted.
2. Delete orphan vectors: a vector whose hash no chunk has any more (DB).
3. Send the texts in batches of at most EMBED_BATCH_MAX_TEXTS texts and EMBED_BATCH_MAX_TOKENS
   estimated tokens, and store each batch's vectors in one transaction. A failure keeps the
   batches already stored, so the next run sends only what's missing.
"""

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.chunks import add_embedding, delete_orphan_embeddings, texts_without_embedding
from orgknow.db.models import TextToEmbed
from orgknow.embeddings.embedder import Embedder
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.ingestion.chunker import estimate_tokens
from orgknow.settings import Settings

log = logging.getLogger(__name__)


class RunTooLarge(Exception):
    """The texts to send are estimated above EMBED_MAX_TOKENS_PER_RUN."""


@dataclass
class Summary:
    texts: int = 0  # texts with no vector for the model, before this run
    estimated_tokens: int = 0  # their tokens, as characters / 4
    orphans_deleted: int = 0
    requests: int = 0
    embedded: int = 0  # texts stored with their vector
    total_tokens: int = 0  # the provider's count (Voyage's usage.total_tokens), summed


def estimate_run(texts: Sequence[TextToEmbed], max_tokens_per_run: int) -> int:
    """The run's estimated tokens. Raises RunTooLarge above `max_tokens_per_run`."""
    estimate = sum(estimate_tokens(t.text) for t in texts)
    if estimate > max_tokens_per_run:
        raise RunTooLarge(
            f"{len(texts)} texts to embed come to {estimate:,} estimated tokens, above "
            f"EMBED_MAX_TOKENS_PER_RUN ({max_tokens_per_run:,}). Nothing was sent. Raise the "
            "limit only if this many is expected."
        )
    return estimate


def batch_texts(
    texts: Sequence[TextToEmbed], max_texts: int, max_tokens: int
) -> list[list[TextToEmbed]]:
    """Consecutive texts, greedily, at most `max_texts` and `max_tokens` estimated tokens per
    batch. A single text over `max_tokens` is a batch on its own."""
    batches: list[list[TextToEmbed]] = []
    batch: list[TextToEmbed] = []
    tokens = 0
    for text in texts:
        size = estimate_tokens(text.text)
        if batch and (len(batch) == max_texts or tokens + size > max_tokens):
            batches.append(batch)
            batch, tokens = [], 0
        batch.append(text)
        tokens += size
    if batch:
        batches.append(batch)
    return batches


def embed_missing(
    conn: psycopg.Connection[TupleRow],
    embedder: Embedder,
    max_texts: int,
    max_batch_tokens: int,
    max_tokens_per_run: int,
) -> Summary:
    """Embed every chunk text with no vector for `embedder.model`; delete orphan vectors.

    Raises RunTooLarge before any request or write when the estimate is above the cap.
    """
    texts = texts_without_embedding(conn, embedder.model)
    summary = Summary(texts=len(texts), estimated_tokens=estimate_run(texts, max_tokens_per_run))
    with conn.transaction():
        summary.orphans_deleted = delete_orphan_embeddings(conn)
    batches = batch_texts(texts, max_texts, max_batch_tokens)
    for number, batch in enumerate(batches, start=1):
        result = embedder.embed([t.text for t in batch], "document")
        with conn.transaction():
            for text, vector in zip(batch, result.vectors, strict=True):
                add_embedding(conn, text.content_hash, embedder.model, vector)
        summary.requests += 1
        summary.embedded += len(batch)
        summary.total_tokens += result.total_tokens
        log.info(
            "Request %d/%d: %d texts, %d tokens (estimated %d)",
            number,
            len(batches),
            len(batch),
            result.total_tokens,
            sum(estimate_tokens(t.text) for t in batch),
        )
    return summary


def main(settings: Settings | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = settings or Settings()
    api_key = settings.voyage_api_key
    if api_key is None or not api_key.get_secret_value():
        sys.exit(
            "VOYAGE_API_KEY is not set. `make embed` calls the Voyage API: add the key to .env "
            "(see .env.example)."
        )
    embedder = VoyageEmbedder(settings.voyage_api_url, api_key, settings.embedding_model)
    # autocommit: each `conn.transaction()` block is its own committed transaction.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        try:
            summary = embed_missing(
                conn,
                embedder,
                settings.embed_batch_max_texts,
                settings.embed_batch_max_tokens,
                settings.embed_max_tokens_per_run,
            )
        except RunTooLarge as exc:
            sys.exit(str(exc))

    print(
        f"Model {embedder.model}: {summary.texts} texts had no vector "
        f"({summary.estimated_tokens:,} estimated tokens, characters / 4).\n"
        f"Requests: {summary.requests}. Texts embedded: {summary.embedded}. "
        f"Voyage usage.total_tokens: {summary.total_tokens:,} "
        f"(estimate: {summary.estimated_tokens:,}).\n"
        f"Orphan vectors deleted: {summary.orphans_deleted}."
    )


if __name__ == "__main__":
    main()
