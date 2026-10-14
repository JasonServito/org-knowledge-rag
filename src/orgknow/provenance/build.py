"""`make chains` (S13-T3; ADR-012 D1-D2): rebuild every decision chain the manifest lists
(`decision_chains`), each in one transaction: delete its decision, insert it and its 6 steps.

This module does the I/O: it reads the rows the rules need (`db/decisions.py`), applies the pure
rules (`rules.py`) and stores the result. Free and local: rule 8 compares stored vectors, so no
embedding call. Needs `make ingest` and `make embed`.
"""

import sys
from pathlib import Path

import psycopg

# PyYAML ships no type hints; safe_load handles only plain values.
import yaml  # type: ignore[import-untyped]
from psycopg.rows import TupleRow

from orgknow.db.decisions import (
    linking_candidates,
    nearest_current_texts,
    newest_document,
    replace_decision,
)
from orgknow.db.models import ChainDocument, NewEvidence
from orgknow.db.releases import list_releases
from orgknow.db.writer_lock import WriterBusy, writer_lock
from orgknow.ingestion.chunker import document_title
from orgknow.ingestion.manifest import load_repo_urls
from orgknow.provenance.rules import (
    DISCUSSION_FIELD,
    KEP_FIELD,
    UPDATE_PR_FIELD,
    Link,
    current_docs_step,
    decision_step,
    discussion_step,
    field_link,
    implementation_step,
    kep_number,
    kep_section,
    problem_step,
    proposal_link,
    proposal_step,
    repo_keys,
    tracking_issue_id,
)
from orgknow.settings import Settings


def chain_seeds(manifest_path: Path) -> list[str]:
    """The seed KEP of every chain in the manifest's `decision_chains`, in order."""
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return [str(chain["seed"]) for chain in manifest.get("decision_chains") or []]


def _item(conn: psycopg.Connection[TupleRow], link: Link) -> ChainDocument | None:
    """The stored item a field names, or None (no item named, or not stored)."""
    return None if link.canonical_id is None else newest_document(conn, link.canonical_id)


def build_chain(
    conn: psycopg.Connection[TupleRow], seed: str, settings: Settings
) -> tuple[ChainDocument, list[NewEvidence]]:
    """The seed KEP and its 6 steps, in step order, by rules 1-8. Writes nothing. Raises
    ValueError when the KEP isn't stored, lacks a Summary or Motivation, or no text has a
    vector."""
    kep = newest_document(conn, seed)
    if kep is None:
        raise ValueError(f"{seed} is not stored: run `make ingest`")
    number = kep_number(seed)
    keys = repo_keys(load_repo_urls(settings.corpus_manifest_path))
    issue = newest_document(conn, tracking_issue_id(number))
    discussion = field_link(issue, DISCUSSION_FIELD, keys)
    proposal = proposal_link(
        field_link(issue, KEP_FIELD, keys), field_link(issue, UPDATE_PR_FIELD, keys)
    )
    discussion_item, pr = _item(conn, discussion), _item(conn, proposal)

    proposed = proposal_step(proposal, pr, kep)
    decided = decision_step(proposal, pr)
    releases = list_releases(conn)  # oldest first
    release_dates = {release.minor: release.release_date for release in releases}
    candidates = linking_candidates(conn, number)
    summary = kep_section(kep, "Summary")
    nearest = nearest_current_texts(
        conn,
        summary.content_hash,
        settings.embedding_model,
        releases[-1].minor,
        settings.retrieval_top_k,
        settings.hnsw_ef_search,
    )
    return kep, [
        problem_step(discussion, discussion_item, kep),
        discussion_step(discussion, discussion_item),
        proposed,
        decided,
        implementation_step(candidates, kep, decided, proposed, release_dates),
        current_docs_step(nearest),
    ]


def store_chain(
    conn: psycopg.Connection[TupleRow], seed: str, settings: Settings
) -> list[NewEvidence]:
    """Build the chain and replace the stored one, in one transaction; return its steps."""
    with conn.transaction():
        kep, evidence = build_chain(conn, seed, settings)
        title = document_title(kep.canonical_id, kep.source_type, kep.metadata)
        replace_decision(conn, kep.document_id, title, evidence)
    return evidence


def chain_line(seed: str, evidence: list[NewEvidence]) -> str:
    """`make chains`' line per chain: `kep:2572: 6 steps stored, 5 found, 1 missing (decision:
    no_link)`."""
    gaps = [f"{step.step}: {step.missing_reason}" for step in evidence if step.missing_reason]
    line = f"{seed}: {len(evidence)} steps stored, {len(evidence) - len(gaps)} found"
    return f"{line}, {len(gaps)} missing ({'; '.join(gaps)})" if gaps else f"{line}, 0 missing"


def main() -> None:
    """`make chains`: rebuild every manifest chain, one transaction each, one line each. A chain
    that can't be built stops the run with one line naming it; chains stored before it stay."""
    settings = Settings()
    seeds = chain_seeds(settings.corpus_manifest_path)
    # autocommit: each chain's `conn.transaction()` block is its own committed transaction. The
    # writer lock (ADR-013 D3) is taken first, on this connection.
    try:
        with psycopg.connect(settings.database_url, autocommit=True) as conn, writer_lock(conn):
            for seed in seeds:
                try:
                    evidence = store_chain(conn, seed, settings)
                except ValueError as error:
                    sys.exit(f"{seed}: {error}")
                print(chain_line(seed, evidence))
    except WriterBusy as busy:
        sys.exit(str(busy))


if __name__ == "__main__":
    main()
