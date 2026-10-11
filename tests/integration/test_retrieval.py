"""Dense retrieval (S04-T5), lexical search (S07-T1) and hybrid retrieval (S07-T3) against the
test database: `search`, `search_lexical` and `retrieve` (with each hit's authority, S09-T6, and
authority mode's weights, S09-T7).

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
from orgknow.db.lifecycle import replace_observations
from orgknow.db.models import Authority, NewChunk, NewVersion, Observation, TemporalFilter
from orgknow.db.retrieval import search, search_lexical
from orgknow.db.versions import insert_version
from orgknow.embeddings.embedder import DIMENSIONS
from orgknow.retrieval.retrieve import retrieve
from orgknow.retrieval.router import Mode, Route
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
    # Two windows, never merged into one span across the 1.25 gap; current, because the [26, open]
    # version holds it (S09-T3); every other field is the newest version's.
    assert hits[0].model_dump(exclude={"distance"}) == {
        "chunk_id": new_chunk_id,
        "content_hash": _hash("shared"),
        "text": "shared",
        "canonical_id": "web:/test/gap/",
        "source_type": "docs_page",
        "heading_path": ["Usage"],
        "release_windows": [(24, 24), (26, None)],
        "current": True,
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
        "authority": None,  # `retrieve` attaches it, not the search (S09-T6)
        "authority_score": None,  # authority mode's `retrieve` sets it (S09-T7)
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
            "current": True,
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
            "authority": None,  # `retrieve` attaches it, not the search (S09-T6)
            "authority_score": None,  # authority mode's `retrieve` sets it (S09-T7)
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

    assert [(hit.chunk_id, hit.release_windows, hit.current, hit.lexical_rank) for hit in hits] == [
        (new_chunk_id, [(24, 24), (26, None)], True, 1)
    ]


def test_a_text_held_only_by_closed_versions_is_not_current_in_either_search(conn: Conn) -> None:
    # S09-T3: a text is current when some version holding it has an open date window. The page's
    # 1.24 and 1.25 versions are closed by dates; 1.26 is open. "replaced" is in the first two
    # only; "kept" is in all three.
    document_id = create_document(conn, "web:/test/edited/", "docs_page")
    first = _version(conn, document_id, (24, 24), (D24, D25))
    second = _version(conn, document_id, (25, 25), (D25, D26))
    latest = _version(conn, document_id, (26, None), (D26, None))
    replaced = "The legacy admission webhook replaced text."
    kept = "The legacy admission webhook kept text."
    for version_id in (first, second):
        add_chunks(conn, version_id, [NewChunk(ordinal=0, heading_path=[], text=replaced)])
    for version_id in (first, second, latest):
        add_chunks(conn, version_id, [NewChunk(ordinal=1, heading_path=[], text=kept)])
    _embed(conn, replaced, E1)
    _embed(conn, kept, E2)

    dense = search(conn, E1, MODEL, 10, WIDTH)
    lexical = search_lexical(conn, "legacy admission webhook", 10)

    # Dense: "replaced" is nearer (distance 0, against 1). Lexical: both hold the 3 words, in the
    # same places, so their order is the content hashes': only the pairs are compared.
    assert [(hit.text, hit.release_windows, hit.current) for hit in dense] == [
        (replaced, [(24, 24), (25, 25)], False),
        (kept, [(24, 24), (25, 25), (26, None)], True),
    ]
    assert {(hit.text, hit.current) for hit in lexical} == {(replaced, False), (kept, True)}


# The temporal filters (S09-T4, S09-R1 decisions 2-4), inside both searches. One page, with a
# closed version [20, 22] (dates 1.20 to 1.23) and a current one [23, now]. NEW_ONLY is in the
# current version only, OLD_ONLY in the closed one only (so it isn't current), BOTH in both. Both
# searches rank them NEW_ONLY, BOTH, OLD_ONLY: by cosine distance to e1, 0, 1 - 1/√2 and 1; and by
# ts_rank_cd for "kubelet version skew policy", checked in psql: 0.1 (the 4 words adjacent),
# 0.0333 (spread over 6 positions) and 0.02 (over 8).

D20 = datetime(2020, 12, 8, tzinfo=UTC)
D23 = datetime(2021, 12, 7, tzinfo=UTC)
NEW_ONLY = "Kubelet version skew policy in the new text."
BOTH = "Kubelet version skew and its policy, in both."
OLD_ONLY = "Kubelet version skew, then later the old policy."
SKEW_QUESTION = "kubelet version skew policy"


def _filtered_rows(conn: Conn, model: str = MODEL) -> dict[str, int]:
    """The page above, its 3 texts and their `model` vectors. Returns the current version's chunk
    ids."""
    document_id = create_document(conn, "web:/test/skew/", "docs_page")
    old = _version(conn, document_id, (20, 22), (D20, D23), SHA_OLD)
    new = _version(conn, document_id, (23, None), (D23, None), SHA_NEW)
    add_chunks(
        conn,
        old,
        [
            NewChunk(ordinal=0, heading_path=[], text=BOTH),
            NewChunk(ordinal=1, heading_path=[], text=OLD_ONLY),
        ],
    )
    new_ids = add_chunks(
        conn,
        new,
        [
            NewChunk(ordinal=0, heading_path=[], text=NEW_ONLY),
            NewChunk(ordinal=1, heading_path=[], text=BOTH),
        ],
    )
    _embed(conn, NEW_ONLY, E1, model)
    _embed(conn, BOTH, E1_PLUS_E2, model)
    _embed(conn, OLD_ONLY, E2, model)
    return {NEW_ONLY: new_ids[0], BOTH: new_ids[1]}


def _filter(
    current_only: bool = False, from_release: int | None = None, until_release: int | None = None
) -> TemporalFilter:
    return TemporalFilter(
        current_only=current_only, from_release=from_release, until_release=until_release
    )


@pytest.mark.parametrize(
    ("temporal", "expected"),
    [
        # No filter, and a filter with every condition off: today's results.
        (None, [NEW_ONLY, BOTH, OLD_ONLY]),
        (_filter(), [NEW_ONLY, BOTH, OLD_ONLY]),
        # CURRENT: OLD_ONLY is held only by the closed version.
        (_filter(current_only=True), [NEW_ONLY, BOTH]),
        # HISTORY "until 20": BOTH passes through its [20, 22] version; NEW_ONLY, only in [23, now],
        # doesn't.
        (_filter(until_release=20), [BOTH, OLD_ONLY]),
        (_filter(until_release=22), [BOTH, OLD_ONLY]),
        (_filter(until_release=23), [NEW_ONLY, BOTH, OLD_ONLY]),
        # "from": [20, 22] reaches 22, inclusive, not 23; an open end reaches every release.
        (_filter(from_release=22), [NEW_ONLY, BOTH, OLD_ONLY]),
        (_filter(from_release=23), [NEW_ONLY, BOTH]),
        (_filter(from_release=21, until_release=21), [BOTH, OLD_ONLY]),
        # A window outside the corpus matches nothing.
        (_filter(until_release=19), []),
        (_filter(from_release=40), [NEW_ONLY, BOTH]),  # an open version is valid at 1.40 too
    ],
    ids=[
        "none",
        "all-off",
        "current",
        "until-20",
        "until-22",
        "until-23",
        "from-22",
        "from-23",
        "21-to-21",
        "until-19",
        "from-40",
    ],
)
def test_both_searches_keep_a_text_when_some_version_holding_it_passes(
    conn: Conn, temporal: TemporalFilter | None, expected: list[str]
) -> None:
    _filtered_rows(conn)

    dense = search(conn, E1, MODEL, 10, WIDTH, temporal)
    lexical = search_lexical(conn, SKEW_QUESTION, 10, temporal)

    assert [hit.text for hit in dense] == expected
    assert [hit.text for hit in lexical] == expected


def test_a_kept_text_cites_its_newest_version_and_lists_every_window(conn: Conn) -> None:
    # "until 20" keeps BOTH through its old version; the hit is still the whole text: the chunk in
    # the newest version holding it, every window, and current (S04-R2 decision 4, S09-T3).
    chunk_ids = _filtered_rows(conn)

    dense = search(conn, E1, MODEL, 10, WIDTH, _filter(until_release=20))
    lexical = search_lexical(conn, SKEW_QUESTION, 10, _filter(until_release=20))

    for hits in (dense, lexical):
        assert [(hit.chunk_id, hit.release_windows, hit.current) for hit in hits[:1]] == [
            (chunk_ids[BOTH], [(20, 22), (23, None)], True)
        ]


def test_the_filter_runs_before_each_searchs_limit(conn: Conn) -> None:
    # One place each: NEW_ONLY ranks first in both searches, but "until 20" drops it before the
    # LIMIT, so BOTH takes the place instead of leaving it empty.
    _filtered_rows(conn)

    assert [hit.text for hit in search(conn, E1, MODEL, 1, WIDTH, _filter(until_release=20))] == [
        BOTH
    ]
    assert [
        hit.text for hit in search_lexical(conn, SKEW_QUESTION, 1, _filter(until_release=20))
    ] == [BOTH]


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
    # S09-T4: so does the iterative scan, which keeps walking the index past the width while the
    # filters drop rows (pgvector's default is off).
    with conn.transaction():
        search(conn, E1, MODEL, 10, WIDTH)
        values = conn.execute(
            "SELECT current_setting('hnsw.ef_search'), current_setting('hnsw.iterative_scan')"
        ).fetchone()

    assert values == ("100", "strict_order")


def test_on_an_autocommit_connection_the_width_ends_with_the_search(settings: Settings) -> None:
    # `search` opens its own transaction block, so on an autocommit connection the width and the
    # iterative scan apply to its query and are gone afterwards: back to pgvector's defaults.
    with psycopg.connect(settings.database_url, autocommit=True) as autocommit:
        assert search(autocommit, E1, MODEL, 10, WIDTH) == []  # no rows outside a test
        values = autocommit.execute(
            "SELECT current_setting('hnsw.ef_search'), current_setting('hnsw.iterative_scan')"
        ).fetchone()

    assert values == ("40", "off")


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


# Temporal mode (S09-T4), through `retrieve` with the fake embedder, a fake reranker and a route,
# on the skew page above. The fake embeds every question as the all-ones direction, so dense search
# ranks by cosine distance to it, by hand: e1 and e2 both 1 - 1/32 = 0.96875, (e1 + e2) / √2
# 0.955806. With 20 candidates per search every text fits, so the pool is whatever the filter keeps.


def _temporal_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "retrieval_mode": "temporal",
            "retrieval_candidates": 20,
            "retrieval_top_k": 10,
            "history_window_slack": 1,
        }
    )


def _route(mode: Mode, kind: str = "none", start: str | None = None) -> Route:
    return Route.model_validate(
        {"mode": mode, "time_scope": {"kind": kind, "start": start, "end": None}}
    )


SKEW_SCORES = {NEW_ONLY: 0.9, BOTH: 0.5, OLD_ONLY: 0.1}


@pytest.mark.parametrize(
    ("route", "pool"),
    [
        # CURRENT: current text only, whatever the time scope.
        (_route("CURRENT"), {NEW_ONLY, BOTH}),
        # HISTORY "before 1.21": until 20, searched until 21 (slack 1): BOTH through [20, 22].
        (_route("HISTORY", "before", "1.21"), {BOTH, OLD_ONLY}),
        # HISTORY "since 1.24": from 24, searched from 23: OLD_ONLY's [20, 22] ends before it.
        (_route("HISTORY", "since", "1.24"), {NEW_ONLY, BOTH}),
        # No filter: HISTORY with no time scope, and WHY even with one (decision 3).
        (_route("HISTORY"), {NEW_ONLY, BOTH, OLD_ONLY}),
        (_route("WHY", "in", "1.20"), {NEW_ONLY, BOTH, OLD_ONLY}),
    ],
    ids=["current", "history-before-1.21", "history-since-1.24", "history-no-scope", "why"],
)
def test_temporal_mode_reranks_only_the_texts_the_routes_filter_keeps(
    conn: Conn,
    settings: Settings,
    fake_embedder: FakeEmbedder,
    route: Route,
    pool: set[str],
) -> None:
    _filtered_rows(conn, fake_embedder.model)
    reranker = FakeReranker(SKEW_SCORES)

    hits = retrieve(
        SKEW_QUESTION, fake_embedder, conn, _temporal_settings(settings), reranker, route
    )

    # One reranker call with the filtered pool; hits in the fake's score order.
    assert [set(texts) for _, texts in reranker.calls] == [pool]
    assert [hit.text for hit in hits] == [t for t in (NEW_ONLY, BOTH, OLD_ONLY) if t in pool]


def test_temporal_mode_with_a_filter_keeping_nothing_returns_no_hits_without_a_model_call(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    # "before 1.15" is outside the corpus: until 14, searched until 15; every version starts at 20.
    _filtered_rows(conn, fake_embedder.model)
    reranker = FakeReranker(SKEW_SCORES)
    route = _route("HISTORY", "before", "1.15")

    hits = retrieve(
        SKEW_QUESTION, fake_embedder, conn, _temporal_settings(settings), reranker, route
    )

    assert (hits, reranker.calls) == ([], [])


def test_temporal_mode_without_a_reranker_raises(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    _filtered_rows(conn, fake_embedder.model)

    with pytest.raises(ValueError, match="temporal mode needs a reranker"):
        retrieve(
            SKEW_QUESTION, fake_embedder, conn, _temporal_settings(settings), None, _route("WHY")
        )


# Authority per hit (S09-T6), through `retrieve` in every mode. A KEP like KEP-2579 (claims
# implemented/stable, names the PodSecurity gate) and a docs page, each current since 1.20 with one
# text holding the question's 3 words. PodSecurity's rows are the dev table's: alpha at 1.22 and
# stable at 1.25 (both high), none at 1.37. Expected values from the T6 rules, by hand.

PSA_QUESTION = "pod security admission"
KEP_SUMMARY = "Pod security admission replaces PodSecurityPolicy."
PSA_PAGE = "Pod security admission enforces the pod security standards."


def _authority_rows(conn: Conn, model: str) -> None:
    kep_version = insert_version(
        conn,
        NewVersion(
            document_id=create_document(conn, "kep:2579", "kep"),
            content_hash=VERSION_HASH,
            source_path="keps/sig-auth/2579-psp-replacement/README.md",
            snapshot_repo="enhancements",
            snapshot_ref="master",
            snapshot_sha=SHA_NEW,
            valid_from_release=20,
            valid_from_date=D20,
            claimed_status="implemented",
            claimed_stage="stable",
            metadata={
                "title": "PSP Replacement Policy",
                "feature-gates": [{"name": "PodSecurity", "components": ["kube-apiserver"]}],
            },
        ),
    )
    add_chunks(conn, kep_version, [NewChunk(ordinal=0, heading_path=[], text=KEP_SUMMARY)])
    page = create_document(conn, "web:/test/psa/", "docs_page")
    page_version = _version(conn, page, (20, None), (D20, None))
    add_chunks(conn, page_version, [NewChunk(ordinal=0, heading_path=[], text=PSA_PAGE)])
    _embed(conn, KEP_SUMMARY, E1, model)
    _embed(conn, PSA_PAGE, E2, model)
    replace_observations(
        conn,
        [
            Observation(gate="PodSecurity", release=22, stage="alpha", status_confidence="high"),
            Observation(gate="PodSecurity", release=25, stage="stable", status_confidence="high"),
        ],
    )


AT_37 = {
    # No row at 1.37: the claim, low; shipped (a row at 1.22, up to 1.37): tier 3.
    "kep:2579": Authority(
        target_release=37, tier=3, effective_stage="stable", stage_confidence="low"
    ),
    "web:/test/psa/": Authority(
        target_release=37, tier=1, effective_stage=None, stage_confidence=None
    ),
}
AT_22 = {
    "kep:2579": Authority(
        target_release=22, tier=3, effective_stage="alpha", stage_confidence="high"
    ),
    "web:/test/psa/": Authority(
        target_release=22, tier=1, effective_stage=None, stage_confidence=None
    ),
}


@pytest.mark.parametrize(
    ("mode", "route", "expected"),
    [
        # No route: the latest release.
        ("dense", None, AT_37),
        ("hybrid", None, AT_37),
        ("rerank", None, AT_37),
        # A route given outside temporal mode is ignored.
        ("rerank", _route("HISTORY", "in", "1.22"), AT_37),
        # Temporal and authority: CURRENT → the latest; HISTORY "in 1.22" → its until, 1.22.
        ("temporal", _route("CURRENT"), AT_37),
        ("temporal", _route("HISTORY", "in", "1.22"), AT_22),
        ("authority", _route("CURRENT"), AT_37),
        ("authority", _route("HISTORY", "in", "1.22"), AT_22),
    ],
    ids=[
        "dense",
        "hybrid",
        "rerank",
        "rerank-ignores-route",
        "temporal-current",
        "temporal-1.22",
        "authority-current",
        "authority-1.22",
    ],
)
def test_every_mode_attaches_each_hits_authority_at_the_target_release(
    conn: Conn,
    settings: Settings,
    fake_embedder: FakeEmbedder,
    mode: str,
    route: Route | None,
    expected: dict[str, Authority],
) -> None:
    _authority_rows(conn, fake_embedder.model)
    reranker = FakeReranker({KEP_SUMMARY: 0.9, PSA_PAGE: 0.1})
    settings = _temporal_settings(settings).model_copy(update={"retrieval_mode": mode})

    hits = retrieve(PSA_QUESTION, fake_embedder, conn, settings, reranker, route)

    assert {hit.canonical_id: hit.authority for hit in hits} == expected


# Authority mode (S09-T7, S09-R2 decisions 3 and 9), on the KEP and the docs page above. The fake
# scores the KEP 0.5 and the page 0.1, so temporal mode puts the KEP first. The weights by hand,
# boost 1.25: routed CURRENT, the page (tier 1, valid at 1.37) is boosted, sigmoid(0.1) * 1.25 =
# 0.524979 * 1.25 = 0.656224; the KEP (tier 3) keeps factor 1, sigmoid(0.5) = 0.622459. So the page
# comes first. Routed HISTORY, no hit is weighted: the KEP stays first.

AUTHORITY_SCORES = {KEP_SUMMARY: 0.5, PSA_PAGE: 0.1}


def _authority_settings(settings: Settings, top_k: int = 10) -> Settings:
    return _temporal_settings(settings).model_copy(
        update={
            "retrieval_mode": "authority",
            "retrieval_top_k": top_k,
            "authority_boost": 1.25,
            "authority_demote": 0.8,
        }
    )


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (_route("CURRENT"), [("web:/test/psa/", 0.656224), ("kep:2579", 0.622459)]),
        (_route("HISTORY"), [("kep:2579", 0.622459), ("web:/test/psa/", 0.524979)]),
    ],
    ids=["current", "history"],
)
def test_authority_mode_orders_by_the_probability_times_the_routes_factor(
    conn: Conn,
    settings: Settings,
    fake_embedder: FakeEmbedder,
    route: Route,
    expected: list[tuple[str, float]],
) -> None:
    _authority_rows(conn, fake_embedder.model)

    hits = retrieve(
        PSA_QUESTION,
        fake_embedder,
        conn,
        _authority_settings(settings),
        FakeReranker(AUTHORITY_SCORES),
        route,
    )

    assert [hit.canonical_id for hit in hits] == [canonical_id for canonical_id, _ in expected]
    assert [hit.authority_score for hit in hits] == pytest.approx(
        [score for _, score in expected], abs=1e-6
    )
    # Each hit keeps its raw score and its tier at the latest release.
    assert {hit.canonical_id: (hit.rerank_score, hit.authority) for hit in hits} == {
        "kep:2579": (0.5, AT_37["kep:2579"]),
        "web:/test/psa/": (0.1, AT_37["web:/test/psa/"]),
    }


def test_authority_mode_weighs_the_whole_reranked_pool_before_the_top_k_cut(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    # A top 1: temporal mode cuts the reranked pool to the KEP; authority mode weighs both texts
    # first, then keeps the page.
    _authority_rows(conn, fake_embedder.model)
    reranker = FakeReranker(AUTHORITY_SCORES)
    temporal = _temporal_settings(settings).model_copy(update={"retrieval_top_k": 1})

    temporal_hits = retrieve(
        PSA_QUESTION, fake_embedder, conn, temporal, reranker, _route("CURRENT")
    )
    authority_hits = retrieve(
        PSA_QUESTION,
        fake_embedder,
        conn,
        _authority_settings(settings, 1),
        reranker,
        _route("CURRENT"),
    )

    assert [hit.canonical_id for hit in temporal_hits] == ["kep:2579"]
    assert [hit.canonical_id for hit in authority_hits] == ["web:/test/psa/"]
    # One reranker call each, with the whole pool.
    assert [set(texts) for _, texts in reranker.calls] == [{KEP_SUMMARY, PSA_PAGE}] * 2


def test_authority_mode_with_a_filter_keeping_nothing_returns_no_hits_without_a_model_call(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    # As in temporal mode: "before 1.15" keeps no text of the skew page.
    _filtered_rows(conn, fake_embedder.model)
    reranker = FakeReranker(SKEW_SCORES)
    route = _route("HISTORY", "before", "1.15")

    hits = retrieve(
        SKEW_QUESTION, fake_embedder, conn, _authority_settings(settings), reranker, route
    )

    assert (hits, reranker.calls) == ([], [])


def test_authority_mode_without_a_route_or_a_reranker_raises(
    conn: Conn, settings: Settings, fake_embedder: FakeEmbedder
) -> None:
    _filtered_rows(conn, fake_embedder.model)
    reranker = FakeReranker(SKEW_SCORES)

    with pytest.raises(ValueError, match="authority mode needs a route"):
        retrieve(SKEW_QUESTION, fake_embedder, conn, _authority_settings(settings), reranker)
    with pytest.raises(ValueError, match="authority mode needs a reranker"):
        retrieve(
            SKEW_QUESTION, fake_embedder, conn, _authority_settings(settings), None, _route("WHY")
        )
    # The missing route stops it before any call.
    assert (fake_embedder.calls, reranker.calls) == ([("query", [SKEW_QUESTION])], [])
