"""The citation validator (S04-R2 decision 8) and the fill-in of each citation (decision 7).

A schema can't say "only ids from this query's retrieved set", so this is plain code (ADR-006
D2). Pure functions: no I/O.
"""

from collections.abc import Collection, Mapping

from orgknow.db.models import Hit
from orgknow.generation.schema import Evidence, ModelAnswer
from orgknow.ingestion.chunker import document_title


def cited_ids(output: ModelAnswer) -> list[int]:
    """The cited chunk ids in the model's order, each once (its first occurrence)."""
    return list(dict.fromkeys(output.evidence))


def out_of_set_ids(output: ModelAnswer, retrieved_ids: Collection[int]) -> list[int]:
    """The cited ids that weren't retrieved for this question, in the model's order."""
    return [chunk_id for chunk_id in cited_ids(output) if chunk_id not in retrieved_ids]


def rejection_reason(output: ModelAnswer, retrieved_ids: Collection[int]) -> str | None:
    """None when the answer passes. Otherwise `citation_validation_failed: [...]`, naming the
    out-of-set ids, or the rule broken: an answer with no citations, or an
    `insufficient_evidence` answer with an empty reason."""
    unknown = out_of_set_ids(output, retrieved_ids)
    if unknown:
        broken = ", ".join(str(chunk_id) for chunk_id in unknown)
    elif output.answer_status == "answered" and not output.evidence:
        broken = "no citations"
    elif (
        output.answer_status == "insufficient_evidence"
        and not (output.insufficient_evidence_reason or "").strip()
    ):
        broken = "empty reason"
    else:
        return None
    return f"citation_validation_failed: [{broken}]"


def fill_in(hit: Hit, repo_urls: Mapping[str, str]) -> Evidence:
    """A citation's provenance, all from the retrieved hit. `repo_urls` maps a manifest repo
    name to its GitHub URL (`load_repo_urls`); the link pins the snapshot commit."""
    return Evidence(
        chunk_id=hit.chunk_id,
        document=hit.canonical_id,
        title=document_title(hit.canonical_id, hit.source_type, hit.metadata),
        section=" > ".join(hit.heading_path) or None,
        source_type=hit.source_type,
        release_windows=[
            (f"1.{start}", None if until is None else f"1.{until}")
            for start, until in hit.release_windows
        ],
        claimed_status=hit.claimed_status,
        claimed_stage=hit.claimed_stage,
        source_url=f"{repo_urls[hit.snapshot_repo]}/blob/{hit.snapshot_sha}/{hit.source_path}",
    )
