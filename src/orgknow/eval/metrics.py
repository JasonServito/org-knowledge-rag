"""Retrieval metrics: score one question's ranked hits against its labels (ADR-007 D3); the S09
time metrics, pooled over many questions' hits (S09-T3); and authority-selection accuracy over
the CURRENT questions (S09-T7).

Pure: questions and their hits in, scores out. No database, no network; K is passed in.
"""

import math
from collections.abc import Iterable, Sequence
from typing import Protocol

from pydantic import BaseModel

from orgknow.db.models import Authority, Hit
from orgknow.eval.golden import Label, Mode, Question, label_matches


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


# The S09 time metrics (S09-T3, S09-R1 decision 1). Each pools hits over questions, by the
# question's golden mode or window, and returns (count, total) for the caller's `Count` or `Rate`;
# None when no hit applies. Each question's hits are its top K, as retrieval returned them.


class TimedHit(Protocol):
    """The 2 fields the time metrics read from a hit. Both a `Hit` and a results file's hit have
    them; a results file written before S09-T3 has neither (None)."""

    @property
    def current(self) -> bool | None: ...

    @property
    def release_windows(self) -> Sequence[tuple[int, int | None]] | None: ...


# A golden release window as minors, (from, until), both inclusive; None is an open end.
GoldenWindow = tuple[int | None, int | None]


def stale_count(
    questions: Iterable[tuple[Mode | None, Sequence[TimedHit]]],
) -> tuple[int, int] | None:
    """Stale-result rate's (stale hits, hits) over the hits of the questions whose golden mode is
    CURRENT, given as (golden mode, hits). A hit is stale when no current version (an open date
    window) holds its text: `current` is False. So a CHANGELOG section, valid only at its own
    release, isn't stale until an edit replaces it. None when no CURRENT question has a hit, or
    one of its hits has no `current` (a results file written before S09-T3)."""
    hits = [hit for mode, hits in questions if mode == "CURRENT" for hit in hits]
    if not hits or any(hit.current is None for hit in hits):
        return None
    return sum(1 for hit in hits if not hit.current), len(hits)


def in_window(windows: Sequence[tuple[int, int | None]], window: GoldenWindow) -> bool:
    """Whether any of a hit's release windows overlaps the golden `window`, ends inclusive, an
    open end (None) on either side open: a version from 20 to 22 is in "until 20", one from 21
    on isn't."""
    start, end = window
    return any(
        (end is None or valid_from <= end)
        and (start is None or valid_until is None or valid_until >= start)
        for valid_from, valid_until in windows
    )


def temporal_count(
    questions: Iterable[tuple[GoldenWindow | None, Sequence[TimedHit]]],
) -> tuple[int, int] | None:
    """Temporal accuracy's (hits in the window, hits) over the hits of the questions with a
    golden release window, given as (golden window, hits): a hit is in it when one of its
    release windows overlaps the exact golden window (`in_window`; no slack). None when no such
    question has a hit, or one of its hits has no release windows (a results file written before
    S09-T3)."""
    pairs = [(window, hit) for window, hits in questions if window is not None for hit in hits]
    if not pairs:
        return None
    passed = 0
    for window, hit in pairs:
        if hit.release_windows is None:
            return None
        if in_window(hit.release_windows, window):
            passed += 1
    return passed, len(pairs)


def router_count(modes: Iterable[tuple[Mode, Mode]]) -> tuple[int, int] | None:
    """Router accuracy's (routes matching the golden mode, questions), given (golden mode, routed
    mode) for each answerable question. None for no questions."""
    pairs = list(modes)
    if not pairs:
        return None
    return sum(1 for golden, routed in pairs if golden == routed), len(pairs)


# Authority-selection accuracy (S09-T7, S09-R2 decision 4; ADR-003's consequences).


class TieredHit(Protocol):
    """The 3 fields authority selection reads from a hit. Both a `Hit` and a results file's hit
    have them; a results file written before S09-T6 has no `authority` (None)."""

    @property
    def canonical_id(self) -> str: ...

    @property
    def heading_path(self) -> Sequence[str]: ...

    @property
    def authority(self) -> Authority | None: ...


# One question as authority selection reads it: its golden mode, its labels, each label's tier in
# label order (None when the row predates S09-T7), and its top K hits.
AuthorityQuestion = tuple[
    Mode | None, Sequence[Label], Sequence[int | None] | None, Sequence[TieredHit]
]


def authority_count(questions: Iterable[AuthorityQuestion]) -> tuple[int, int] | None:
    """Authority-selection accuracy's (right, counted) over the questions whose golden mode is
    CURRENT.

    A question is counted when its label tiers hold 2+ distinct values (None, a superseded
    proposal's, is one value, and the worst), so the labels alone fix the denominator. It is
    right when its first hit matching a label has the best label tier, the lowest number; with
    no hit matching a label, it is wrong. None when no question is counted, or a CURRENT question
    has no label tiers, or a counted question's first labeled hit has no authority (rows written
    before S09-T7).
    """
    right = counted = 0
    for mode, labels, label_tiers, hits in questions:
        if mode != "CURRENT":
            continue
        if label_tiers is None:
            return None
        if len(set(label_tiers)) < 2:
            continue
        counted += 1
        best = min(tier for tier in label_tiers if tier is not None)  # 2+ values: one is a tier
        first = next(
            (
                hit
                for hit in hits
                if any(label_matches(label, hit.canonical_id, hit.heading_path) for label in labels)
            ),
            None,
        )
        if first is None:
            continue
        if first.authority is None:
            return None
        if first.authority.tier == best:
            right += 1
    return (right, counted) if counted else None
