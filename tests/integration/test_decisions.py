"""S13-T3: the decision tables (migration 0008), `make chains`' build and store, the stored chain
read back (`load_chain`, `orgknow chain`, and S13-T5's `GET /decisions/{canonical_id}`), and
`make reset-corpus` emptying the tables.

Every row is synthetic, built inside `conn`'s rolled-back transaction: a seed KEP, its tracking
issue, the discussion and the proposal PR the issue's fields name, blog posts, docs pages and
vectors. No GitHub text. Expected picks and dates are typed by hand from the S13-R1 contract's
rules; distances are hand arithmetic (the cosine distance of two unit vectors is 1 - cos θ).
"""

import math
import re
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation, UniqueViolation
from psycopg.rows import TupleRow

from orgknow import cli
from orgknow.api import app as api_app
from orgknow.api.app import create_app
from orgknow.db.chunks import add_chunks, add_embedding
from orgknow.db.decisions import nearest_current_texts, replace_decision
from orgknow.db.documents import create_document
from orgknow.db.models import NewChunk, NewEvidence, NewVersion
from orgknow.db.versions import insert_version
from orgknow.embeddings.embedder import DIMENSIONS
from orgknow.ingestion.chunker import chunk_text
from orgknow.ingestion.manifest import load_repo_urls
from orgknow.provenance.build import store_chain
from orgknow.provenance.chain import load_chain
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

ROOT = Path(__file__).parents[2]
MODEL = "test-model"
SHA = "3333333333333333333333333333333333333333"
VERSION_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
# Release dates from the manifest (00:00 UTC): 1.20, 1.21 and 1.30.
D20 = datetime(2020, 12, 8, tzinfo=UTC)
D21 = datetime(2021, 4, 8, tzinfo=UTC)
D30 = datetime(2024, 4, 17, tzinfo=UTC)
LATEST = 37  # the manifest's latest release

FIELDS = "\n".join(
    [
        "- Kubernetes Enhancement Proposal: https://github.com/kubernetes/enhancements/pull/9003",
        "- Discussion Link: https://github.com/kubernetes/sig-release/discussions/9002",
        "- [ ] Alpha",
        "  - [ ] KEP (`k/enhancements`) update PR(s): "
        "https://github.com/kubernetes/enhancements/pull/9003",
    ]
)


def _vector(*components: float) -> list[float]:
    """A 1024-number vector starting with `components`, zeros after."""
    return [*components] + [0.0] * (DIMENSIONS - len(components))


E1 = _vector(1.0)
E2 = _vector(0.0, 1.0)
E1_PLUS_E2 = _vector(math.sqrt(0.5), math.sqrt(0.5))  # (e1 + e2) / √2: 1 - √0.5 from e1


def _store(
    conn: Conn,
    canonical_id: str,
    source_type: str,
    sections: list[tuple[list[str], str]],
    releases: tuple[int, int | None] = (30, None),
    dates: tuple[datetime, datetime | None] = (D30, None),
    metadata: dict[str, Any] | None = None,
    source_path: str = "made/up.md",
    claimed_status: str | None = None,
) -> list[int]:
    """A document with one version holding one chunk per (heading path, body); return the chunk
    ids, by ordinal."""
    document_id = create_document(conn, canonical_id, source_type)
    version_id = insert_version(
        conn,
        NewVersion(
            document_id=document_id,
            content_hash=VERSION_HASH,
            source_path=source_path,
            snapshot_repo="enhancements",
            snapshot_ref="made-up",
            snapshot_sha=SHA,
            valid_from_release=releases[0],
            valid_until_release=releases[1],
            valid_from_date=dates[0],
            valid_until_date=dates[1],
            claimed_status=claimed_status,
            metadata={"title": "Made up", **(metadata or {})},
        ),
    )
    chunks = [
        NewChunk(
            ordinal=ordinal,
            heading_path=path,
            text=chunk_text(source_type, "Made up", canonical_id, path, text),
        )
        for ordinal, (path, text) in enumerate(sections)
    ]
    return add_chunks(conn, version_id, chunks)


def _embed(conn: Conn, chunk_id: int, vector: list[float]) -> None:
    row = conn.execute("SELECT content_hash FROM chunks WHERE id = %s", (chunk_id,)).fetchone()
    assert row is not None
    add_embedding(conn, row[0], MODEL, vector)


def _item(number: int, kind: str, repo: str, created_at: str, **times: str) -> dict[str, Any]:
    url = f"https://github.com/kubernetes/{repo}/{kind}/{number}"
    return {"url": url, "kind": kind, "number": number, "created_at": created_at, **times}


def _corpus(conn: Conn) -> dict[str, int]:
    """KEP-9001's chain, every link recorded, plus texts each rule must skip. Return the chunk
    ids the expected rows name."""
    kep = _store(
        conn,
        "kep:9001",
        "kep",
        [
            (["KEP-9001: Made up"], "Intro."),
            (["KEP-9001: Made up", "Summary"], "The summary."),
            (["KEP-9001: Made up", "Motivation"], "The motivation."),
        ],
        metadata={"creation-date": "2021-01-21", "status": "implementable"},
        source_path="keps/sig-release/9001-made-up/README.md",
        claimed_status="implementable",
    )
    issue = _store(
        conn,
        "gh:enhancements/issues/9001",
        "discussion",
        [
            (["Opening post · @owner · 2021-03-15", "Enhancement Description"], FIELDS),
            (["Comments", "@someone · 2021-05-12"], "Tracked."),
        ],
        metadata=_item(9001, "issues", "enhancements", "2021-03-15T04:38:31Z"),
    )
    discussion = _store(
        conn,
        "gh:sig-release/discussions/9002",
        "discussion",
        [
            (["Opening post · @owner · 2020-10-14"], "Fewer releases?"),
            (["Comments", "@first · 2020-10-15"], "Yes."),
            (["Comments", "@second · 2020-10-16"], "No."),
        ],
        metadata=_item(9002, "discussions", "sig-release", "2020-10-14T20:36:05Z"),
    )
    pr = _store(
        conn,
        "gh:enhancements/pull/9003",
        "discussion",
        [
            (["Opening post · @owner · 2021-03-12"], "Adds the KEP."),
            (["Comments", "@a · 2021-04-20"], "/approve"),
            (["Comments", "@b · 2021-04-22"], "/approve "),
            (["Comments", "@owner · 2021-04-23"], "/hold cancel"),
        ],
        metadata=_item(
            9003,
            "pull",
            "enhancements",
            "2021-03-12T14:32:43Z",
            merged_at="2021-04-23T15:38:03Z",
        ),
    )
    # Rule 7: an earlier linking blog (before the decision) and the one to cite.
    _store(
        conn,
        "web:/blog/2021/03/01/early/",
        "blog_post",
        [([], "See KEP-9001.")],
        releases=(20, None),
        dates=(datetime(2021, 3, 1, tzinfo=UTC), None),
    )
    # A docs page links the KEP earlier, but only blog posts and release records are candidates.
    _store(
        conn,
        "web:/docs/links/",
        "docs_page",
        [([], "See KEP-9001.")],
        releases=(21, None),
        dates=(datetime(2021, 5, 1, tzinfo=UTC), None),
    )
    blog = _store(
        conn,
        "web:/blog/2021/07/20/cadence/",
        "blog_post",
        [([], "Intro."), (["More"], "See https://github.com/kubernetes/enhancements/issues/9001.")],
        releases=(21, None),
        dates=(datetime(2021, 7, 20, tzinfo=UTC), None),
    )
    # Rule 8: the Summary's vector is e1. Nearer texts that don't count: a CHANGELOG, a docs page
    # no longer valid at the latest release, and the KEP's own Summary (a KEP is no current doc).
    near = _store(conn, "web:/docs/near/", "docs_page", [(["Near"], "Near text.")])
    far = _store(conn, "web:/docs/far/", "docs_page", [(["Far"], "Far text.")])
    changelog = _store(conn, "changelog:1.30", "release_record", [(["v1.30.0"], "Same.")])
    old = _store(
        conn,
        "web:/docs/old/",
        "docs_page",
        [(["Old"], "Old text.")],
        releases=(30, 31),
        dates=(D30, datetime(2024, 12, 11, tzinfo=UTC)),  # until 1.32's release
    )
    _embed(conn, kep[1], E1)
    _embed(conn, near[0], E1_PLUS_E2)
    _embed(conn, far[0], E2)
    _embed(conn, changelog[0], E1)
    _embed(conn, old[0], E1)
    return {
        "summary": kep[1],
        "fields": issue[0],
        "opening": discussion[0],
        "first comment": discussion[1],
        "last approve": pr[2],
        "blog link": blog[1],
        "near": near[0],
    }


@pytest.fixture
def chain_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"embedding_model": MODEL})


def _evidence(conn: Conn) -> list[tuple[Any, ...]]:
    """Every stored step except its id, by step."""
    return conn.execute(
        """
        SELECT x.document_id, x.title, e.step, e.chunk_id, e.occurred_at, e.found_by,
               e.via_chunk_id, e.missing_reason
        FROM decision_evidence e JOIN decisions x ON x.id = e.decision_id
        ORDER BY x.document_id, e.step
        """
    ).fetchall()


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def test_make_chains_stores_each_step_as_the_rules_pick_it(
    conn: Conn, chain_settings: Settings
) -> None:
    ids = _corpus(conn)

    evidence = store_chain(conn, "kep:9001", chain_settings)

    fields = ids["fields"]
    assert evidence == [
        NewEvidence(
            step="problem",
            chunk_id=ids["opening"],
            occurred_at=_at("2020-10-14T20:36:05Z"),
            found_by="template_field",
            via_chunk_id=fields,
        ),
        NewEvidence(
            step="discussion",
            chunk_id=ids["first comment"],
            occurred_at=_at("2020-10-15T00:00:00Z"),
            found_by="template_field",
            via_chunk_id=fields,
        ),
        NewEvidence(
            step="proposal",
            chunk_id=ids["summary"],
            occurred_at=_at("2021-03-12T14:32:43Z"),
            found_by="seed",
            via_chunk_id=fields,
        ),
        NewEvidence(
            step="decision",
            chunk_id=ids["last approve"],
            occurred_at=_at("2021-04-23T15:38:03Z"),
            found_by="merge_event",
            via_chunk_id=fields,
        ),
        NewEvidence(
            step="implementation",
            chunk_id=ids["blog link"],
            occurred_at=_at("2021-07-20T00:00:00Z"),
            found_by="linking_text",
            via_chunk_id=ids["blog link"],
        ),
        NewEvidence(
            step="current_docs",
            chunk_id=ids["near"],
            occurred_at=D30,
            found_by="similarity",
        ),
    ]
    assert len(_evidence(conn)) == 6


def test_re_running_make_chains_stores_the_same_rows(conn: Conn, chain_settings: Settings) -> None:
    _corpus(conn)
    store_chain(conn, "kep:9001", chain_settings)
    first = _evidence(conn)

    store_chain(conn, "kep:9001", chain_settings)

    assert _evidence(conn) == first
    assert conn.execute("SELECT count(*) FROM decisions").fetchone() == (1,)


def test_a_seed_that_is_not_stored_stops_with_a_message(
    conn: Conn, chain_settings: Settings
) -> None:
    with pytest.raises(ValueError, match="kep:9999 is not stored"):
        store_chain(conn, "kep:9999", chain_settings)


def test_the_nearest_current_text_uses_the_filter_and_a_missing_vector_gives_none(
    conn: Conn,
) -> None:
    ids = _corpus(conn)
    summary_hash = conn.execute("SELECT content_hash FROM chunks WHERE id = %s", (ids["summary"],))
    query_hash = summary_hash.fetchone()[0]  # type: ignore[index]

    nearest = nearest_current_texts(conn, query_hash, MODEL, LATEST, 10, 100)
    no_vector = nearest_current_texts(conn, "f" * 64, MODEL, LATEST, 10, 100)

    assert [(text.canonical_id, round(text.distance, 4)) for text in nearest] == [
        ("web:/docs/near/", round(1 - math.sqrt(0.5), 4)),
        ("web:/docs/far/", 1.0),
    ]
    assert nearest[0].chunk_id == ids["near"]
    assert no_vector == []


def test_load_chain_gives_each_step_its_source_url_and_tier(
    conn: Conn, chain_settings: Settings
) -> None:
    _corpus(conn)
    store_chain(conn, "kep:9001", chain_settings)
    repo_urls = load_repo_urls(ROOT / "config" / "corpus_manifest.yaml")

    chain = load_chain(conn, "kep:9001", repo_urls)

    assert chain is not None
    assert (chain.seed, chain.title) == ("kep:9001", "KEP-9001: Made up")
    assert [(step.step, step.tier, step.source_url) for step in chain.steps] == [
        ("problem", 7, "https://github.com/kubernetes/sig-release/discussions/9002"),
        ("discussion", 7, "https://github.com/kubernetes/sig-release/discussions/9002"),
        (
            "proposal",
            5,  # implementable, no gates: not shipped
            f"https://github.com/kubernetes/enhancements/blob/{SHA}/"
            "keps/sig-release/9001-made-up/README.md",
        ),
        ("decision", 7, "https://github.com/kubernetes/enhancements/pull/9003"),
        ("implementation", 6, f"https://github.com/kubernetes/enhancements/blob/{SHA}/made/up.md"),
        ("current_docs", 1, f"https://github.com/kubernetes/enhancements/blob/{SHA}/made/up.md"),
    ]
    assert (chain.steps[0].via_canonical_id, chain.steps[0].via_heading_path) == (
        "gh:enhancements/issues/9001",
        ["Opening post · @owner · 2021-03-15", "Enhancement Description"],
    )
    assert load_chain(conn, "kep:9999", repo_urls) is None


def test_orgknow_chain_prints_the_stored_chain(
    conn: Conn, chain_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(conn)
    store_chain(conn, "kep:9001", chain_settings)

    code = cli.chain("kep:9001", conn, chain_settings)

    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    assert lines[0].startswith("kep:9001: KEP-9001: Made up (built ")
    assert lines[4] == (
        "2021-04-23  decision        https://github.com/kubernetes/enhancements/pull/9003  "
        "gh:enhancements/pull/9003 \u203a Comments > @b · 2021-04-22  tier 7  merge_event via "
        "gh:enhancements/issues/9001 \u203a Opening post · @owner · 2021-03-15 > "
        "Enhancement Description"
    )
    assert len(lines) == 7


def test_orgknow_chain_with_no_stored_chain_exits_1(
    chain_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["chain", "kep:9999"], chain_settings)

    out, err = capsys.readouterr()
    assert (code, out) == (1, "")
    assert err.splitlines() == [
        "no stored decision chain for kep:9999; chains are built by make chains"
    ]


# --- Migration 0008's rules ----------------------------------------------------------------------


def _decision(conn: Conn) -> tuple[int, int]:
    """A decision for a fresh KEP document, and a chunk to cite."""
    chunk_id = _store(conn, "kep:9100", "kep", [(["KEP-9100: Made up", "Summary"], "S.")])[0]
    document_id = conn.execute("SELECT id FROM documents WHERE canonical_id = 'kep:9100'")
    decision_id = replace_decision(conn, document_id.fetchone()[0], "Made up", [])  # type: ignore[index]
    return decision_id, chunk_id


def _insert(conn: Conn, decision_id: int, **row: Any) -> None:
    fields = {"step": "problem", "chunk_id": None, "found_by": None, "missing_reason": None}
    conn.execute(
        """
        INSERT INTO decision_evidence (decision_id, step, chunk_id, found_by, missing_reason)
        VALUES (%(decision_id)s, %(step)s, %(chunk_id)s, %(found_by)s, %(missing_reason)s)
        """,
        {"decision_id": decision_id, **(fields | row)},
    )


@pytest.mark.parametrize(
    ("row", "constraint"),
    [
        ({"step": "outcome", "missing_reason": "no_link"}, "decision_evidence_step_check"),
        ({"chunk": True, "found_by": "guess"}, "decision_evidence_found_by_check"),
        ({"missing_reason": "unknown"}, "decision_evidence_missing_reason_check"),
        ({}, "decision_evidence_cited_or_missing_check"),  # neither
        (
            {"chunk": True, "found_by": "seed", "missing_reason": "no_link"},
            "decision_evidence_cited_or_missing_check",  # both
        ),
        ({"chunk": True}, "decision_evidence_found_by_set_check"),
        ({"missing_reason": "no_link", "found_by": "seed"}, "decision_evidence_found_by_set_check"),
    ],
)
def test_evidence_rows_are_checked(conn: Conn, row: dict[str, Any], constraint: str) -> None:
    decision_id, chunk_id = _decision(conn)
    if row.pop("chunk", False):
        row["chunk_id"] = chunk_id

    with pytest.raises(CheckViolation, match=constraint), conn.transaction():
        _insert(conn, decision_id, **row)


def test_a_step_is_stored_once_per_decision_and_a_kep_has_one_decision(conn: Conn) -> None:
    decision_id, chunk_id = _decision(conn)
    _insert(conn, decision_id, chunk_id=chunk_id, found_by="seed")
    document_id = conn.execute("SELECT document_id FROM decisions").fetchone()[0]  # type: ignore[index]

    step_key = "decision_evidence_decision_id_step_key"
    with pytest.raises(UniqueViolation, match=step_key), conn.transaction():
        _insert(conn, decision_id, missing_reason="no_link")
    with pytest.raises(UniqueViolation, match="decisions_document_id_key"), conn.transaction():
        conn.execute(
            "INSERT INTO decisions (document_id, title, built_at) VALUES (%s, 'X', now())",
            (document_id,),
        )


def test_deleting_a_cited_chunk_deletes_its_step(conn: Conn) -> None:
    decision_id, chunk_id = _decision(conn)
    _insert(conn, decision_id, chunk_id=chunk_id, found_by="seed")

    conn.execute("DELETE FROM chunks WHERE id = %s", (chunk_id,))

    assert conn.execute("SELECT count(*) FROM decision_evidence").fetchone() == (0,)


def _reset_corpus(conn: Conn) -> None:
    """The statement `make reset-corpus` runs on the dev database, read from the Makefile and run
    here inside the rolled-back transaction."""
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r'"(TRUNCATE [^"]+)"', makefile)
    assert match is not None
    conn.execute(match[1])  # type: ignore[arg-type]


def test_make_reset_corpus_empties_both_tables(conn: Conn, chain_settings: Settings) -> None:
    _corpus(conn)
    store_chain(conn, "kep:9001", chain_settings)

    _reset_corpus(conn)

    assert conn.execute("SELECT count(*) FROM decisions").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM decision_evidence").fetchone() == (0,)


def test_get_decisions_returns_load_chains_model_then_404_after_the_reset(
    conn: Conn, chain_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The chain is stored inside this test's rolled-back transaction, which a new connection
    # can't see: the request gets this test's connection instead of opening its own.
    _corpus(conn)
    store_chain(conn, "kep:9001", chain_settings)
    monkeypatch.setattr(api_app.psycopg, "connect", lambda *args, **kwargs: nullcontext(conn))
    client = TestClient(create_app(chain_settings))  # no startup: the route needs no paid client

    stored = client.get("/decisions/kep:9001")

    assert stored.status_code == 200
    # The model `orgknow chain` prints from, for the same rows (its steps are checked by hand in
    # test_load_chain_gives_each_step_its_source_url_and_tier), dumped to JSON.
    chain = load_chain(conn, "kep:9001", load_repo_urls(ROOT / "config" / "corpus_manifest.yaml"))
    assert chain is not None
    assert stored.json() == chain.model_dump(mode="json")
    assert [step["step"] for step in stored.json()["steps"]] == [
        "problem",
        "discussion",
        "proposal",
        "decision",
        "implementation",
        "current_docs",
    ]

    _reset_corpus(conn)
    after_reset = client.get("/decisions/kep:9001")

    assert after_reset.status_code == 404
    assert after_reset.json() == {
        "detail": "no stored decision chain for kep:9001; chains are built by make chains"
    }
