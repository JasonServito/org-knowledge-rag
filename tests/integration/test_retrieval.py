"""Dense retrieval (S04-T5) against the test database: `search` and `retrieve`.

Expected distances are hand arithmetic: the cosine distance of two unit vectors is 1 - cos θ.
Every test builds its own rows inside `conn`'s rolled-back transaction.
"""

import hashlib
import math
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import TupleRow
from tests.conftest import FakeEmbedder

from orgknow.db.chunks import add_chunks, add_embedding
from orgknow.db.documents import create_document
from orgknow.db.models import NewChunk, NewVersion
from orgknow.db.retrieval import search
from orgknow.db.versions import insert_version
from orgknow.embeddings.embedder import DIMENSIONS
from orgknow.retrieval.dense import retrieve
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

MODEL = "test-model"
# Typed by hand: 64 and 40 lowercase hex characters.
VERSION_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
ORPHAN_HASH = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
SHA_OLD = "1111111111111111111111111111111111111111"
SHA_NEW = "2222222222222222222222222222222222222222"
# Release dates from the manifest (00:00 UTC).
D24 = datetime(2022, 5, 3, tzinfo=UTC)
D25 = datetime(2022, 8, 23, tzinfo=UTC)
D26 = datetime(2022, 12, 8, tzinfo=UTC)


def _vector(*components: float) -> list[float]:
    """A 1024-number vector starting with `components`, zeros after."""
    return [*components] + [0.0] * (DIMENSIONS - len(components))


E1 = _vector(1.0)
E2 = _vector(0.0, 1.0)
E1_PLUS_E2 = _vector(math.sqrt(0.5), math.sqrt(0.5))  # (e1 + e2) / √2, a unit vector
MINUS_E1 = _vector(-1.0)


def _version(
    conn: Conn,
    document_id: int,
    releases: tuple[int, int | None],
    dates: tuple[datetime, datetime | None],
    sha: str = SHA_NEW,
    path: str = "content/en/docs/test/page.md",
    title: str = "Test page",
) -> int:
    version = NewVersion(
        document_id=document_id,
        content_hash=VERSION_HASH,
        source_path=path,
        snapshot_repo="website",
        snapshot_ref=f"release-1.{releases[0]}",
        snapshot_sha=sha,
        valid_from_release=releases[0],
        valid_until_release=releases[1],
        valid_from_date=dates[0],
        valid_until_date=dates[1],
        metadata={"title": title},
    )
    return insert_version(conn, version)


def _page(conn: Conn, canonical_id: str, texts: list[str]) -> list[int]:
    """A docs page with one current version (since 1.24) holding one chunk per text."""
    version_id = _version(
        conn, create_document(conn, canonical_id, "docs_page"), (24, None), (D24, None)
    )
    chunks = [NewChunk(ordinal=i, heading_path=[], text=text) for i, text in enumerate(texts)]
    return add_chunks(conn, version_id, chunks)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embed(conn: Conn, text: str, vector: list[float], model: str = MODEL) -> None:
    add_embedding(conn, _hash(text), model, vector)


def test_hits_are_ordered_by_cosine_distance(conn: Conn) -> None:
    # Stored farthest first, so the order can't come from insertion.
    _page(conn, "web:/test/page/", ["minus e1", "e2", "e1 plus e2", "e1"])
    _embed(conn, "minus e1", MINUS_E1)
    _embed(conn, "e2", E2)
    _embed(conn, "e1 plus e2", E1_PLUS_E2)
    _embed(conn, "e1", E1)

    hits = search(conn, E1, MODEL, 10)

    assert [hit.text for hit in hits] == ["e1", "e1 plus e2", "e2", "minus e1"]
    # 1 - cos θ for θ = 0°, 45°, 90°, 180°: 1 - 1, 1 - 1/√2 (= 0.2928932), 1 - 0, 1 - (-1).
    assert [hit.distance for hit in hits] == pytest.approx([0, 0.2928932, 1, 2], abs=1e-6)


def test_a_text_in_two_versions_is_one_hit_citing_the_newest(conn: Conn) -> None:
    # Decision 4: a page in 1.24, missing from 1.25, back from 1.26 with the same section text.
    # Stored out of order, so only the date can pick the newest version: the [26, open] version
    # gets the lower version id, and its chunk's id falls between the old version's two chunks
    # (not the lowest id, not the highest).
    document_id = create_document(conn, "web:/test/gap/", "docs_page")
    new = _version(conn, document_id, (26, None), (D26, None), SHA_NEW, "new/page.md", "New title")
    old = _version(conn, document_id, (24, 24), (D24, D25), SHA_OLD, "old/page.md", "Old title")
    add_chunks(conn, old, [NewChunk(ordinal=0, heading_path=["Usage"], text="shared")])
    [new_chunk_id] = add_chunks(
        conn, new, [NewChunk(ordinal=0, heading_path=["Usage"], text="shared")]
    )
    add_chunks(conn, old, [NewChunk(ordinal=1, heading_path=["Usage"], text="shared")])
    _embed(conn, "shared", E1)

    hits = search(conn, E1, MODEL, 10)

    assert len(hits) == 1
    assert hits[0].distance == pytest.approx(0, abs=1e-6)
    # Two windows, never merged into one span across the 1.25 gap; every other field is the
    # newest version's.
    assert hits[0].model_dump(exclude={"distance"}) == {
        "chunk_id": new_chunk_id,
        "content_hash": _hash("shared"),
        "text": "shared",
        "canonical_id": "web:/test/gap/",
        "source_type": "docs_page",
        "heading_path": ["Usage"],
        "release_windows": [(24, 24), (26, None)],
        "claimed_status": None,
        "claimed_stage": None,
        "snapshot_repo": "website",
        "snapshot_sha": SHA_NEW,
        "source_path": "new/page.md",
        "metadata": {"title": "New title"},
    }


def test_a_version_holding_a_text_twice_cites_its_first_chunk_and_lists_it_once(
    conn: Conn,
) -> None:
    document_id = create_document(conn, "web:/test/repeat/", "docs_page")
    old = _version(conn, document_id, (24, 24), (D24, D25))
    new = _version(conn, document_id, (25, None), (D25, None))
    add_chunks(conn, old, [NewChunk(ordinal=0, heading_path=[], text="repeated")])
    first, _ = add_chunks(
        conn,
        new,
        [
            NewChunk(ordinal=0, heading_path=[], text="repeated"),
            NewChunk(ordinal=1, heading_path=[], text="repeated"),
        ],
    )
    _embed(conn, "repeated", E1)

    hits = search(conn, E1, MODEL, 10)

    # One window per version, adjacent windows not merged either.
    assert [(hit.chunk_id, hit.release_windows) for hit in hits] == [
        (first, [(24, 24), (25, None)])
    ]


def test_orphan_and_other_model_vectors_are_never_returned(conn: Conn) -> None:
    _page(conn, "web:/test/page/", ["kept", "other model only"])
    _embed(conn, "kept", E2)  # distance 1 from the query
    _embed(conn, "kept", E1, model="other-model")  # the same text, nearer, another model
    _embed(conn, "other model only", E1, model="other-model")
    add_embedding(conn, ORPHAN_HASH, MODEL, E1)  # nearer than everything, but no chunk has it

    # k = 1: the three nearer vectors are filtered out before the LIMIT, so they can't take the
    # one slot and leave the result empty.
    hits = search(conn, E1, MODEL, 1)

    assert [hit.text for hit in hits] == ["kept"]
    assert hits[0].distance == pytest.approx(1, abs=1e-6)


def test_equal_distances_are_ordered_by_content_hash(conn: Conn) -> None:
    _page(conn, "web:/test/page/", ["tie a", "tie b"])
    _embed(conn, "tie a", E1)
    _embed(conn, "tie b", E1)

    hits = search(conn, E1, MODEL, 10)

    # By hand, `printf '%s' 'tie b' | sha256sum` (2cd1…) sorts before 'tie a' (feab…).
    assert [hit.content_hash for hit in hits] == [
        "2cd1ee8949e778d6684ae2a73b0796ba459cf53d77880ca035e36c45d5e1f855",
        "feab290957a9f83fa09556c536794432073db7966be8f3d721f4e2faf81e6bfd",
    ]


def test_an_empty_table_gives_no_hits(conn: Conn) -> None:
    # The test database holds no rows outside a test, and this test adds none.
    assert search(conn, E1, MODEL, 10) == []


def test_retrieve_embeds_the_question_as_a_query_and_keeps_the_top_k(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    _page(conn, "web:/test/page/", ["nearest", "farther"])
    # The fake embeds every text as [0.5] * 1024: "nearest" holds that vector (distance 0).
    _embed(conn, "nearest", [0.5] * DIMENSIONS, model=fake_embedder.model)
    _embed(conn, "farther", E1, model=fake_embedder.model)

    hits = retrieve(
        "What is a pod?", fake_embedder, conn, settings.model_copy(update={"retrieval_top_k": 1})
    )

    assert fake_embedder.calls == [("query", ["What is a pod?"])]
    assert [hit.text for hit in hits] == ["nearest"]
