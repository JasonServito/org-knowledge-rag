"""`make embed`'s run against the test database, with the call-counting fake (tests/conftest.py).

S04-T4 is done when a second run makes 0 API calls: the `embeddings` table is the cache, keyed by
(content_hash, model) (S04-R1 decision 4). Expected counts are hand arithmetic.
"""

from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow
from tests.conftest import FakeEmbedder

from orgknow.db.chunks import add_chunks, add_embedding
from orgknow.db.documents import create_document
from orgknow.db.models import NewChunk, NewVersion
from orgknow.db.versions import insert_version
from orgknow.embeddings.embed import RunTooLarge, Summary, embed_missing

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

# Typed by hand: 64 and 40 lowercase hex characters.
VERSION_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
ORPHAN_HASH = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
SHA = "0123456789abcdef0123456789abcdef01234567"


def _page(conn: Conn, canonical_id: str, texts: list[str]) -> None:
    """A docs page with one version (current since 1.30) holding one chunk per text."""
    document_id = create_document(conn, canonical_id, "docs_page")
    version = NewVersion(
        document_id=document_id,
        content_hash=VERSION_HASH,
        source_path="content/en/docs/test/page.md",
        snapshot_repo="website",
        snapshot_ref="release-1.30",
        snapshot_sha=SHA,
        valid_from_release=30,
        valid_from_date=datetime(2024, 4, 17, tzinfo=UTC),
    )
    chunks = [NewChunk(ordinal=i, heading_path=[], text=text) for i, text in enumerate(texts)]
    add_chunks(conn, insert_version(conn, version), chunks)


def _embed(conn: Conn, embedder: FakeEmbedder, max_tokens_per_run: int = 2_000_000) -> Summary:
    # The default batch limits: 128 texts and 60,000 estimated tokens.
    return embed_missing(conn, embedder, 128, 60_000, max_tokens_per_run)


def _vectors(conn: Conn) -> list[tuple[Any, ...]]:
    return conn.execute("SELECT content_hash, model FROM embeddings ORDER BY 1, 2").fetchall()


def test_a_second_run_makes_no_api_calls(conn: Conn, fake_embedder: FakeEmbedder) -> None:
    # Two pages share texts 100-199: 400 chunks, 300 distinct texts.
    _page(conn, "web:/test/page-a/", [f"text {i}" for i in range(0, 200)])
    _page(conn, "web:/test/page-b/", [f"text {i}" for i in range(100, 300)])

    first = _embed(conn, fake_embedder)
    first_calls = list(fake_embedder.calls)
    second = _embed(conn, fake_embedder)

    # ceil(300 / 128) = 3 requests of 128 + 128 + 44 texts; each distinct text sent once.
    assert [len(texts) for _, texts in first_calls] == [128, 128, 44]
    assert {input_type for input_type, _ in first_calls} == {"document"}
    sent = sorted(text for _, texts in first_calls for text in texts)
    assert sent == sorted(f"text {i}" for i in range(300))
    assert (first.texts, first.requests, first.embedded) == (300, 3, 300)
    # The second run: 0 texts without a vector, so 0 calls.
    assert fake_embedder.calls == first_calls
    assert (second.texts, second.requests, second.embedded) == (0, 0, 0)
    assert len(_vectors(conn)) == 300
    # Every one of the 400 chunks finds its vector by hash.
    joined = conn.execute(
        "SELECT count(*) FROM chunks c "
        "JOIN embeddings e ON e.content_hash = c.content_hash AND e.model = 'fake-model'"
    ).fetchone()
    assert joined == (400,)


def test_orphan_vectors_are_deleted(conn: Conn, fake_embedder: FakeEmbedder) -> None:
    _page(conn, "web:/test/page/", ["kept"])
    row = conn.execute("SELECT content_hash FROM chunks WHERE text = 'kept'").fetchone()
    assert row is not None
    kept = row[0]
    add_embedding(conn, kept, "fake-model", [0.5] * 1024)
    # No chunk has ORPHAN_HASH: its vectors are orphans, under any model.
    add_embedding(conn, ORPHAN_HASH, "fake-model", [0.5] * 1024)
    add_embedding(conn, ORPHAN_HASH, "other-model", [0.5] * 1024)

    summary = _embed(conn, fake_embedder)

    assert summary.orphans_deleted == 2
    assert _vectors(conn) == [(kept, "fake-model")]
    assert fake_embedder.calls == []  # "kept" already had its vector


def test_a_run_above_the_cap_refuses_before_any_call(
    conn: Conn, fake_embedder: FakeEmbedder
) -> None:
    # 40 characters = 10 estimated tokens each: 20 in all, one above a cap of 19.
    _page(conn, "web:/test/page/", ["x" * 40, "y" * 40])
    add_embedding(conn, ORPHAN_HASH, "fake-model", [0.5] * 1024)

    with pytest.raises(RunTooLarge, match="20 estimated tokens"):
        _embed(conn, fake_embedder, max_tokens_per_run=19)

    assert fake_embedder.calls == []
    assert _vectors(conn) == [(ORPHAN_HASH, "fake-model")]  # nothing written or deleted
