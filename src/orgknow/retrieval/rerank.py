"""Reranking: reorder hybrid's fused texts by a cross-encoder's score (S08, ADR-008).

RRF (`fusion.py`) ranks a text by where dense and lexical search put it; nothing reads the
question and the text together. A cross-encoder does: it reads each (question, text) pair and
scores how well the text answers it. `rerank` mode scores hybrid's whole fused pool (about 21
texts from 20 + 20 candidates) and keeps the RETRIEVAL_TOP_K best (ADR-008 D3).

- `Reranker`: the interface, question + texts in, one score per text out. The real one is
  `cross_encoder.CrossEncoderReranker`; tests use a fake, so they need no model (ADR-008 D2).
- `rerank`: the ordering. Pure: no model, no database.
"""

from collections.abc import Sequence
from typing import Protocol

from orgknow.db.models import Hit


class Reranker(Protocol):
    def score(self, question: str, texts: Sequence[str]) -> list[float]:
        """One score per text, in the texts' order; higher is more relevant."""
        ...


def rerank(hits: Sequence[Hit], scores: Sequence[float], top_k: int) -> list[Hit]:
    """The `top_k` hits with the highest scores (all of them if fewer), best first.

    `hits` are in hybrid's fused order and `scores[i]` is `hits[i]`'s score. Scores are compared
    rounded to 4 decimals, and a tie keeps the earlier hit first, so near-equal scores, which can
    differ by ~1e-5 between runs, don't reorder (ADR-008 D3). Each returned hit keeps hybrid's
    fields and gets the raw score as `rerank_score`. A score count unlike the hit count raises
    ValueError.
    """
    if len(scores) != len(hits):
        raise ValueError(f"{len(scores)} scores for {len(hits)} hits: one score per hit")
    order = sorted(range(len(hits)), key=lambda i: (-round(scores[i], 4), i))
    return [hits[i].model_copy(update={"rerank_score": scores[i]}) for i in order[:top_k]]
