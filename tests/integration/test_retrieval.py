"""Dense retrieval (S04-T5), lexical search (S07-T1) and hybrid retrieval (S07-T3) against the
test database: `search`, `search_lexical` and `retrieve`.

Expected distances are hand arithmetic: the cosine distance of two unit vectors is 1 - cos θ.
Expected lexical results come from the hand-written texts and Postgres's full-text rules.
Expected fused scores are hand RRF arithmetic. Every test builds its own rows inside `conn`'s
rolled-back transaction.
"""

import hashlib
import math
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import TupleRow
from tests.conftest import FakeEmbedder, FakeReranker

from orgknow.db.chunks import add_chunks, add_embedding
from orgknow.db.documents import create_document
from orgknow.db.models import NewChunk, NewVersion
from orgknow.db.retrieval import search, search_lexical
from orgknow.db.versions import insert_version
from orgknow.embeddings.embedder import DIMENSIONS
from orgknow.retrieval.retrieve import retrieve
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

MODEL = "test-model"
# The HNSW search width every `search` here sets: the settings default (S07-R1 decision 3).
WIDTH = 100
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

    hits = search(conn, E1, MODEL, 10, WIDTH)

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

    hits = search(conn, E1, MODEL, 10, WIDTH)

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
        # S07-R1 decision 4's score and rank fields: `search` sets only its own rank.
        "rrf_score": None,
        "dense_rank": 1,
        "lexical_rank": None,
        "rerank_score": None,
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

    hits = search(conn, E1, MODEL, 10, WIDTH)

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
    hits = search(conn, E1, MODEL, 1, WIDTH)

    assert [hit.text for hit in hits] == ["kept"]
    assert hits[0].distance == pytest.approx(1, abs=1e-6)


def test_equal_distances_are_ordered_by_content_hash(conn: Conn) -> None:
    _page(conn, "web:/test/page/", ["tie a", "tie b"])
    _embed(conn, "tie a", E1)
    _embed(conn, "tie b", E1)

    hits = search(conn, E1, MODEL, 10, WIDTH)

    # By hand, `printf '%s' 'tie b' | sha256sum` (2cd1…) sorts before 'tie a' (feab…).
    assert [hit.content_hash for hit in hits] == [
        "2cd1ee8949e778d6684ae2a73b0796ba459cf53d77880ca035e36c45d5e1f855",
        "feab290957a9f83fa09556c536794432073db7966be8f3d721f4e2faf81e6bfd",
    ]


def test_an_empty_table_gives_no_hits(conn: Conn) -> None:
    # The test database holds no rows outside a test, and this test adds none.
    assert search(conn, E1, MODEL, 10, WIDTH) == []


def test_retrieve_embeds_the_question_as_a_query_and_keeps_the_top_k(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    _page(conn, "web:/test/page/", ["nearest", "farther"])
    # The fake embeds every text as [0.5] * 1024: "nearest" holds that vector (distance 0).
    _embed(conn, "nearest", [0.5] * DIMENSIONS, model=fake_embedder.model)
    _embed(conn, "farther", E1, model=fake_embedder.model)

    # Hybrid mode, whatever the default is: rerank mode needs a reranker (tested below).
    hybrid = settings.model_copy(update={"retrieval_top_k": 1, "retrieval_mode": "hybrid"})
    hits = retrieve("What is a pod?", fake_embedder, conn, hybrid)

    assert fake_embedder.calls == [("query", ["What is a pod?"])]
    assert [hit.text for hit in hits] == ["nearest"]


# Lexical search (S07-T1). `plainto_tsquery('english', …)` keeps a question's content words,
# stemmed, joined by AND (decision 1); `ts_rank_cd` ranks a match higher the closer together its
# words sit (cover density). No vectors are stored: lexical search needs none.

GATE_TEXT = (
    "The LegacyServiceAccountTokenCleanUp feature gate deletes unused legacy service account "
    "tokens."
)
TOKENS_TEXT = "Service account tokens are mounted into every pod."
PODS_TEXT = "A pod runs one or more containers."


def test_lexical_an_exact_term_ranks_its_text_first(conn: Conn) -> None:
    [gate_chunk_id, _, _] = _page(conn, "web:/test/page/", [GATE_TEXT, TOKENS_TEXT, PODS_TEXT])

    hits = search_lexical(conn, "What does LegacyServiceAccountTokenCleanUp do?", 10)

    # The gate's name is one word that only GATE_TEXT holds; "what", "does", "do" are stop words.
    # Every field a dense hit has, with no distance (no vector was compared) and rank 1.
    assert [hit.model_dump() for hit in hits] == [
        {
            "chunk_id": gate_chunk_id,
            "content_hash": _hash(GATE_TEXT),
            "distance": None,
            "text": GATE_TEXT,
            "canonical_id": "web:/test/page/",
            "source_type": "docs_page",
            "heading_path": [],
            "release_windows": [(24, None)],
            "claimed_status": None,
            "claimed_stage": None,
            "snapshot_repo": "website",
            "snapshot_sha": SHA_NEW,
            "source_path": "content/en/docs/test/page.md",
            "metadata": {"title": "Test page"},
            "rrf_score": None,
            "dense_rank": None,
            "lexical_rank": 1,
            "rerank_score": None,
        }
    ]


def test_lexical_every_word_of_the_question_must_match(conn: Conn) -> None:
    all_words = "Pod security admission enforces the Pod Security Standards."
    some_words = "A security context sets a pod's user and group."  # no "admission"
    _page(conn, "web:/test/page/", [all_words, some_words])

    hits = search_lexical(conn, "pod security admission", 10)

    assert [hit.text for hit in hits] == [all_words]


def test_lexical_words_close_together_rank_higher(conn: Conn) -> None:
    # Each text holds each of the 3 words once; only their distance apart differs.
    adjacent = "Pod security admission checks namespaces against the standards."
    scattered = "Admission checks namespaces; the pod standards cover security."
    _page(conn, "web:/test/page/", [scattered, adjacent])  # stored in the losing order

    hits = search_lexical(conn, "pod security admission", 10)

    assert [(hit.text, hit.lexical_rank) for hit in hits] == [(adjacent, 1), (scattered, 2)]


def test_lexical_a_text_in_two_versions_is_one_hit_with_both_windows(conn: Conn) -> None:
    # As in the dense test above: in 1.24, missing from 1.25, back from 1.26 unchanged.
    document_id = create_document(conn, "web:/test/gap/", "docs_page")
    new = _version(conn, document_id, (26, None), (D26, None), SHA_NEW, "new/page.md", "New title")
    old = _version(conn, document_id, (24, 24), (D24, D25), SHA_OLD, "old/page.md", "Old title")
    add_chunks(conn, old, [NewChunk(ordinal=0, heading_path=["Usage"], text=GATE_TEXT)])
    [new_chunk_id] = add_chunks(
        conn, new, [NewChunk(ordinal=0, heading_path=["Usage"], text=GATE_TEXT)]
    )

    hits = search_lexical(conn, "LegacyServiceAccountTokenCleanUp", 10)

    assert [(hit.chunk_id, hit.release_windows, hit.lexical_rank) for hit in hits] == [
        (new_chunk_id, [(24, 24), (26, None)], 1)
    ]


def test_lexical_no_match_and_stop_words_only_give_no_hits(conn: Conn) -> None:
    # The texts hold "the", "and" and "of", but those are stop words: the query keeps no word.
    _page(conn, "web:/test/page/", [GATE_TEXT, "The history of the API and its removal."])

    assert search_lexical(conn, "kerberos", 10) == []
    assert search_lexical(conn, "the and of", 10) == []


# The HNSW search width (S07-R1 decision 3). pgvector's default `hnsw.ef_search` is 40, so 100
# can only come from `search`'s set_config.


def test_search_sets_the_search_width_for_its_query(conn: Conn) -> None:
    # set_config(..., true) is local to the transaction. `search` runs inside this outer block, so
    # its own block is a savepoint and the local value lasts until the outer block ends: read it
    # there.
    with conn.transaction():
        search(conn, E1, MODEL, 10, WIDTH)
        width = conn.execute("SELECT current_setting('hnsw.ef_search')").fetchone()

    assert width == ("100",)


def test_on_an_autocommit_connection_the_width_ends_with_the_search(settings: Settings) -> None:
    # `search` opens its own transaction block, so on an autocommit connection the width applies
    # to its query and is gone afterwards: back to pgvector's default.
    with psycopg.connect(settings.database_url, autocommit=True) as autocommit:
        assert search(autocommit, E1, MODEL, 10, WIDTH) == []  # no rows outside a test
        width = autocommit.execute("SELECT current_setting('hnsw.ef_search')").fetchone()

    assert width == ("40",)


# Hybrid retrieval (S07-T3), through `retrieve` with the fake embedder, which embeds every
# question as [0.5] * 1024 (the all-ones direction). Cosine distances to it, by hand: all ones 0;
# (e1 + e2) / √2: 1 - 2 / (√2 · 32) = 0.955806; e1: 1 - 1/32 = 0.96875.
# For "pod security admission", ADJACENT ranks above SCATTERED in lexical search (as in
# test_lexical_words_close_together_rank_higher); NEAREST and FARTHER lack a word.

QUESTION = "pod security admission"
NEAREST = PODS_TEXT  # all ones: dense rank 1
ADJACENT = "Pod security admission checks namespaces against the standards."  # dense 2, lexical 1
FARTHER = TOKENS_TEXT  # e1: dense rank 3
SCATTERED = "Admission checks namespaces; the pod standards cover security."  # lexical 2; no vector


def _hybrid_rows(conn: Conn, model: str) -> dict[str, int]:
    """The 4 texts on one page, and vectors for all but SCATTERED. Returns chunk ids by text."""
    texts = [NEAREST, ADJACENT, FARTHER, SCATTERED]
    chunk_ids = dict(zip(texts, _page(conn, "web:/test/page/", texts), strict=True))
    _embed(conn, NEAREST, [0.5] * DIMENSIONS, model)
    _embed(conn, ADJACENT, E1_PLUS_E2, model)
    _embed(conn, FARTHER, E1, model)
    return chunk_ids


def test_hybrid_fuses_dense_and_lexical_candidates_in_the_hand_predicted_order(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    chunk_ids = _hybrid_rows(conn, fake_embedder.model)
    # 2 candidates per search: dense keeps NEAREST and ADJACENT, so FARTHER (dense rank 3) is out.
    hybrid = settings.model_copy(
        update={
            "retrieval_mode": "hybrid",
            "retrieval_candidates": 2,
            "retrieval_top_k": 10,
            "rrf_k": 60,
            "hnsw_ef_search": WIDTH,
        }
    )

    hits = retrieve(QUESTION, fake_embedder, conn, hybrid)

    assert fake_embedder.calls == [("query", [QUESTION])]
    # ADJACENT: dense 2 + lexical 1 = 1/62 + 1/61 = 0.032522
    # NEAREST:  dense 1              = 1/61        = 0.016393
    # SCATTERED: lexical 2           = 1/62        = 0.016129, no distance (no vector)
    # 3 fused texts, fewer than the top 10: all of them.
    assert [
        (hit.chunk_id, hit.dense_rank, hit.lexical_rank, hit.distance is None) for hit in hits
    ] == [
        (chunk_ids[ADJACENT], 2, 1, False),
        (chunk_ids[NEAREST], 1, None, False),
        (chunk_ids[SCATTERED], None, 2, True),
    ]
    assert [hit.rrf_score for hit in hits] == pytest.approx(
        [0.032522, 0.016393, 0.016129], abs=1e-6
    )
    assert [hits[0].distance, hits[1].distance] == pytest.approx([0.955806, 0], abs=1e-6)


def test_dense_mode_records_the_distance_and_dense_rank_only(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    chunk_ids = _hybrid_rows(conn, fake_embedder.model)
    dense = settings.model_copy(update={"retrieval_mode": "dense", "retrieval_top_k": 10})

    hits = retrieve(QUESTION, fake_embedder, conn, dense)

    # The 3 texts with a vector, nearest first; SCATTERED has none, so dense can't find it.
    assert [(hit.chunk_id, hit.dense_rank, hit.rrf_score, hit.lexical_rank) for hit in hits] == [
        (chunk_ids[NEAREST], 1, None, None),
        (chunk_ids[ADJACENT], 2, None, None),
        (chunk_ids[FARTHER], 3, None, None),
    ]
    assert [hit.distance for hit in hits] == pytest.approx([0, 0.955806, 0.96875], abs=1e-6)


# Rerank mode (S08-T2), through `retrieve` with the fake embedder and a fake reranker, on the
# hybrid rows above. With 2 candidates per search, hybrid's fused pool is, in order: ADJACENT,
# NEAREST, SCATTERED (as in the hybrid test). The fake scores SCATTERED, last in the pool, highest.


def _rerank_settings(settings: Settings) -> Settings:
    """Rerank mode, 2 candidates per search, and a top 2: the pool (3 texts) is longer than the
    top K, so a pool cut to the top K before scoring would lose SCATTERED."""
    return settings.model_copy(
        update={
            "retrieval_mode": "rerank",
            "retrieval_candidates": 2,
            "retrieval_top_k": 2,
            "rrf_k": 60,
            "hnsw_ef_search": WIDTH,
        }
    )


def test_rerank_scores_hybrids_whole_pool_and_keeps_the_top_k_by_score(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    chunk_ids = _hybrid_rows(conn, fake_embedder.model)
    reranker = FakeReranker({ADJACENT: 0.1, NEAREST: 0.5, SCATTERED: 0.9})

    hits = retrieve(QUESTION, fake_embedder, conn, _rerank_settings(settings), reranker)

    # One call with the whole pool, in fused order.
    assert reranker.calls == [(QUESTION, [ADJACENT, NEAREST, SCATTERED])]
    # The fake's order, top 2: SCATTERED (0.9), NEAREST (0.5). Each keeps its fused score and
    # ranks: SCATTERED lexical 2, 1/62 = 0.016129; NEAREST dense 1, 1/61 = 0.016393.
    assert [(hit.chunk_id, hit.rerank_score, hit.dense_rank, hit.lexical_rank) for hit in hits] == [
        (chunk_ids[SCATTERED], 0.9, None, 2),
        (chunk_ids[NEAREST], 0.5, 1, None),
    ]
    assert [hit.rrf_score for hit in hits] == pytest.approx([0.016129, 0.016393], abs=1e-6)


def test_rerank_mode_without_a_reranker_raises(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    _hybrid_rows(conn, fake_embedder.model)

    with pytest.raises(ValueError, match="rerank mode needs a reranker"):
        retrieve(QUESTION, fake_embedder, conn, _rerank_settings(settings))


def test_rerank_with_an_empty_pool_returns_no_hits_without_a_model_call(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    # No rows: dense and lexical search both find nothing.
    reranker = FakeReranker({})

    assert retrieve(QUESTION, fake_embedder, conn, _rerank_settings(settings), reranker) == []
    assert reranker.calls == []
