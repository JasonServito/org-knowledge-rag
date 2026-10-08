"""Retrieval metrics: score one question's ranked hits against its labels (ADR-007 D3).

Pure: a question and its hits in, a record out. No database, no network; K is passed in.
"""

import math
from collections.abc import Sequence

from pydantic import BaseModel

from orgknow.db.models import Hit
from orgknow.eval.golden import Label, Question, label_matches


class RetrievalMetrics(BaseModel):
    """One answerable question's scores over its top K hits. The field names are the results
    file's `metrics` keys."""

    recall: float  # labels matched by a top-K hit / labels
    hit: int  # 1 if any label is matched, else 0
    mrr: float  # 1 / rank of the first matching hit; 0 if none
    ndcg: float  # DCG / IDCG
    distinct_sections: int  # distinct (document, heading path) pairs: a diagnostic, not a target


def gains(labels: Sequence[Label], hits: Sequence[Hit]) -> list[int]:
    """Each hit's gain, in rank order: 1 if it matches a label no earlier hit matched, else 0.
    So each label is credited once, at its first matching hit, and a near-duplicate of an
    already-found section gains nothing. A hit matches at most one label, because the loader
    rejects nested labels (ADR-007 D2)."""
    credited: set[int] = set()  # positions in `labels` of the labels found so far
    result = []
    for hit in hits:
        matched = {
            position
            for position, label in enumerate(labels)
            if label_matches(label, hit.canonical_id, hit.heading_path)
        }
        new = matched - credited
        credited |= new
        result.append(1 if new else 0)
    return result


def score_retrieval(question: Question, hits: Sequence[Hit], k: int) -> RetrievalMetrics | None:
    """The question's metrics over its top `k` hits (k >= 1), or None if it has no labels (an
    unanswerable question: AC3 scores it, not these metrics). With fewer than `k` hits, the
    metrics use the hits there are; the ideal ranking still covers min(labels, k) ranks."""
    if not question.labels:
        return None
    top = hits[:k]
    # The ranks (from 1) where a label is found, in order.
    found = [rank for rank, gain in enumerate(gains(question.labels, top), start=1) if gain]
    # DCG sums 1 / log2(rank + 1) over the found ranks; IDCG is the same sum when every label
    # that fits in the top k is found at the top ranks.
    dcg = sum(1 / math.log2(rank + 1) for rank in found)
    idcg = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(question.labels), k) + 1))
    return RetrievalMetrics(
        recall=len(found) / len(question.labels),
        hit=1 if found else 0,
        mrr=1 / found[0] if found else 0.0,
        ndcg=dcg / idcg,
        distinct_sections=len({(hit.canonical_id, tuple(hit.heading_path)) for hit in top}),
    )
