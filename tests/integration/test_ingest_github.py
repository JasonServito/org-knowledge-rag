"""S13-T1: GitHub items into the test database (ADR-012 D3): a cached snapshot stored as a
`discussion` document, chunked by post; re-ingesting gives the same fingerprint; a snapshot the
lock doesn't pin stops ingest before any write; the chain label check counts stored texts.

The snapshot is synthetic, shaped like the ones `make fetch-github` writes: no GitHub text is
committed (ADR-001). Expected values are typed by hand from the S13-R1 contract's rules.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.eval.chains import ChainLabel, count_texts
from orgknow.ingestion.github import GithubSnapshotError, ItemSnapshot, snapshot_bytes
from orgknow.ingestion.ingest import Summary, ingest
from orgknow.ingestion.manifest import (
    GithubItem,
    GithubPin,
    Scope,
    load_normalization,
    load_releases,
)
from orgknow.ingestion.report import database_report

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

ROOT = Path(__file__).parents[2]
RELEASES = load_releases(ROOT / "config" / "corpus_manifest.yaml")
STRIP = load_normalization(ROOT / "config" / "corpus_manifest.yaml")
FETCHED = "2026-10-13T12:00:00Z"

DISCUSSION = ItemSnapshot.model_validate(
    {
        "kind": "discussions",
        "number": 12,
        "url": "https://github.com/kubernetes/sig-release/discussions/12",
        "title": "How often should we release?",
        "author": "erin",
        "created_at": "2020-10-14T20:00:00Z",
        "closed_at": None,
        "body": "Should we release three times a year?\r\n",
        "posts": [
            {
                "kind": "comment",
                "author": "frank",
                "created_at": "2020-10-14T21:00:00Z",
                "body": "Yes.",
            },
            {
                "kind": "reply",
                "author": "erin",
                "created_at": "2020-10-16T09:00:00Z",
                "body": "Why?",
            },
            {
                "kind": "comment",
                "author": "k8s-triage-robot",
                "created_at": "2021-01-10T00:00:00Z",
                "body": "/lifecycle stale",
            },
            {
                "kind": "comment",
                "author": "grace",
                "created_at": "2021-03-26T10:00:00Z",
                "body": "Agreed: three.",
            },
        ],
    }
)


def _cached(cache_dir: Path, snapshot: ItemSnapshot = DISCUSSION) -> GithubItem:
    """Write the snapshot to the cache as `make fetch-github` would, and pin it."""
    raw = snapshot_bytes(snapshot)
    path = cache_dir / "github" / "sig-release" / "discussions" / "12.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    pin = GithubPin(sha256=hashlib.sha256(raw).hexdigest(), fetched_at=FETCHED)
    return GithubItem("sig-release", "discussions", 12, pin)


def _ingest(conn: Conn, cache_dir: Path, item: GithubItem) -> Summary:
    scope = Scope("github", (), (), github=(item,))
    return ingest(conn, scope, cache_dir, RELEASES, STRIP, {"GA": "stable"}, 512)


def _version(conn: Conn) -> tuple[Any, ...] | None:
    return conn.execute(
        """
        SELECT d.source_type, v.source_path, v.snapshot_repo, v.snapshot_ref, v.snapshot_sha,
               v.valid_from_release, v.valid_until_release, v.valid_from_date,
               v.valid_until_date, v.claimed_status, v.metadata
        FROM documents d JOIN document_versions v ON v.document_id = d.id
        WHERE d.canonical_id = 'gh:sig-release/discussions/12'
        """
    ).fetchone()


def test_a_snapshot_is_stored_as_a_discussion_document_chunked_by_post(
    conn: Conn, tmp_path: Path
) -> None:
    item = _cached(tmp_path)
    assert item.pin is not None

    summary = _ingest(conn, tmp_path, item)

    assert summary.documents == {"discussion": 1}
    assert summary.failures == []
    # The last kept post is grace's (2021-03-26): the bot's is dropped. 1.20 was released on
    # 2020-12-08, 1.21 on 2021-04-08.
    assert _version(conn) == (
        "discussion",
        "github/sig-release/discussions/12.json",
        "sig-release",
        FETCHED,
        item.pin.sha256[:40],
        20,
        None,
        datetime(2021, 3, 26, 10, 0, tzinfo=UTC),
        None,
        None,
        {
            "kind": "discussions",
            "number": 12,
            "url": "https://github.com/kubernetes/sig-release/discussions/12",
            "title": "How often should we release?",
            "author": "erin",
            "created_at": "2020-10-14T20:00:00Z",
            "closed_at": None,
        },
    )
    chunks = conn.execute(
        """
        SELECT c.heading_path, c.text FROM chunks c
        JOIN document_versions v ON v.id = c.document_version_id
        JOIN documents d ON d.id = v.document_id
        WHERE d.canonical_id = 'gh:sig-release/discussions/12'
        ORDER BY c.ordinal
        """
    ).fetchall()
    assert [path for path, _ in chunks] == [
        ["Opening post · @erin · 2020-10-14"],
        ["Comments", "@frank · 2020-10-14"],
        ["Comments", "@erin · 2020-10-16 · reply"],
        ["Comments", "@grace · 2021-03-26"],
    ]
    assert chunks[3][1] == (
        "Source: discussion\n"
        "Title: How often should we release?\n"
        "Document: gh:sig-release/discussions/12\n"
        "Section: Comments > @grace · 2021-03-26\n\n"
        "Agreed: three."
    )


def test_re_ingesting_the_same_snapshot_gives_an_identical_fingerprint(
    conn: Conn, tmp_path: Path
) -> None:
    item = _cached(tmp_path)
    _ingest(conn, tmp_path, item)
    first = database_report(conn)

    again = _ingest(conn, tmp_path, item)

    assert database_report(conn) == first
    assert first[-1].startswith("Fingerprint: sha256:")
    assert (again.new_documents, again.new_versions, again.new_chunks) == (0, 0, 0)
    assert again.unchanged_documents == 1


def _discussions(conn: Conn) -> int:
    row = conn.execute("SELECT count(*) FROM documents WHERE source_type = 'discussion'").fetchone()
    assert row is not None
    return int(row[0])


def test_a_snapshot_the_lock_doesnt_pin_stops_ingest_before_any_write(
    conn: Conn, tmp_path: Path
) -> None:
    item = _cached(tmp_path)
    other = GithubItem(item.repo, item.kind, item.number, GithubPin("0" * 64, FETCHED))

    with pytest.raises(GithubSnapshotError, match="sig-release/discussions/12: the cached"):
        _ingest(conn, tmp_path, other)

    assert _discussions(conn) == 0


def test_the_chain_label_check_counts_the_stored_texts_each_label_matches(
    conn: Conn, tmp_path: Path
) -> None:
    _ingest(conn, tmp_path, _cached(tmp_path))
    labels = [
        ChainLabel(
            seed="kep:1",
            step="discussion",
            document="gh:sig-release/discussions/12",
            section="Comments",
        ),
        ChainLabel(
            seed="kep:1",
            step="problem",
            document="gh:sig-release/discussions/12",
            section="Opening post · @erin · 2020-10-14",
        ),
        # The bot's post isn't stored, and an item that isn't ingested has no text.
        ChainLabel(
            seed="kep:1",
            step="discussion",
            document="gh:sig-release/discussions/12",
            section="Comments > @k8s-triage-robot · 2021-01-10",
        ),
        ChainLabel(seed="kep:1", step="decision", document="gh:enhancements/pull/1"),
    ]

    assert count_texts(conn, labels) == [3, 1, 0, 0]
