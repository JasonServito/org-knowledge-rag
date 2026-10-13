"""S13-R1 (T6): v0's retrieval per question, with the GitHub `discussion` texts searchable,
against S12's final run. Free and read-only: stored question vectors and routes, the local
reranker, no Voyage or Anthropic call. The dev database is never changed.

1. With the discussions: each answerable question retrieved in RETRIEVAL_MODE (authority, the
   default) from its stored vector and route, scored on v0's labels, and compared with S12's saved
   row: its 4 metrics and its top 10 (by chunk id). A question whose scores or top 10 differ is
   printed with its top 10 now (`+` marks a chunk not in S12's top 10) and S12's labeled ranks.
2. Without them: the same, after deleting every `discussion` chunk inside a transaction that is
   always rolled back (`psycopg.Rollback`), then the discussion chunk count after the rollback.

Prints ids, heading paths, ranks and scores only (no GitHub text).
Usage, from the repo root, with `make up`:
  uv run python eval/results/s13-chains/per_question.py \
      eval/results/conflict-20261012T171932Z/questions.jsonl \
      > eval/results/s13-chains/per_question.log
"""

import json
import sys
from types import SimpleNamespace

import psycopg

from orgknow.eval import runner
from orgknow.eval.metrics import gains, score_retrieval
from orgknow.pipeline import load_reranker
from orgknow.retrieval.retrieve import retrieve
from orgknow.settings import Settings

METRICS = ("recall", "hit", "mrr", "ndcg")
DELETE_DISCUSSION_CHUNKS = """
DELETE FROM chunks WHERE document_version_id IN (
    SELECT v.id FROM document_versions v JOIN documents d ON d.id = v.document_id
    WHERE d.source_type = 'discussion')
"""
COUNT_DISCUSSION_CHUNKS = """
SELECT count(*) FROM chunks c
JOIN document_versions v ON v.id = c.document_version_id
JOIN documents d ON d.id = v.document_id
WHERE d.source_type = 'discussion'
"""


def run(conn, questions, stored, routes, settings, reranker, old, show):
    """Retrieve and score every question; print the changed ones (when `show`) and the means."""
    sums = dict.fromkeys(METRICS, 0.0)
    current_mrr = []
    changed_scores, changed_top = [], []
    for q in questions:
        hits = retrieve(q.question, stored, conn, settings, reranker,
                        routes[runner.question_key(q.question)])
        k = settings.retrieval_top_k
        m = score_retrieval(q, hits, k)
        for name in METRICS:
            sums[name] += getattr(m, name)
        if q.mode == "CURRENT":
            current_mrr.append(m.mrr)
        before = old[q.id]
        old_top = [h["chunk_id"] for h in before["hits"][:k]]
        new_top = [h.chunk_id for h in hits[:k]]
        scores_differ = any(abs(getattr(m, n) - before["metrics"][n]) > 1e-12 for n in METRICS)
        top_differs = old_top != new_top
        if scores_differ:
            changed_scores.append(q.id)
        elif top_differs:
            changed_top.append(q.id)
        if show and (scores_differ or top_differs):
            o = before["metrics"]
            print(f"{q.id} {q.mode}: recall {o['recall']:.3f} -> {m.recall:.3f}, "
                  f"hit {o['hit']} -> {m.hit}, mrr {o['mrr']:.3f} -> {m.mrr:.3f}, "
                  f"ndcg {o['ndcg']:.3f} -> {m.ndcg:.3f}")
            # `gains` reads only a hit's canonical_id and heading_path, which S12's rows saved.
            saved = [SimpleNamespace(canonical_id=h["canonical_id"], heading_path=h["heading_path"])
                     for h in before["hits"][:k]]
            old_labeled = [r for r, g in enumerate(gains(q.labels, saved), 1) if g]
            new_labeled = [r for r, g in enumerate(gains(q.labels, hits[:k]), 1) if g]
            print(f"   ranks where a label is credited: S12 {old_labeled}, now {new_labeled}")
            for rank, h in enumerate(hits[:k], 1):
                mark = " " if h.chunk_id in old_top else "+"
                path = " > ".join(h.heading_path)
                print(f"   {mark}{rank:2} {h.source_type:22} {h.canonical_id} | {path}")
    n = len(questions)
    means = "  ".join(f"{name} {sums[name] / n:.3f}" for name in METRICS)
    print(f"Means over {n}: {means}  CURRENT MRR {sum(current_mrr) / len(current_mrr):.3f}")
    print(f"Scores differ from S12: {len(changed_scores)} {changed_scores}")
    print(f"Top 10 differs from S12, scores equal: {len(changed_top)} {changed_top}")


def main() -> None:
    old = {}
    for line in open(sys.argv[1], encoding="utf-8"):
        row = json.loads(line)
        old[row["id"]] = row
    settings = Settings()
    print(f"Mode: {settings.retrieval_mode}. S12's run: {sys.argv[1]}")
    reranker = load_reranker(settings)
    # autocommit: the rolled-back block below is its own transaction (BEGIN ... ROLLBACK).
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        golden, _ = runner.check_golden(conn, settings.eval_golden_path)
        questions = [q for q in golden.questions if q.answerable]
        vectors_path = settings.eval_vectors_dir / f"{settings.embedding_model}.json"
        stored = runner.StoredVectors(settings.embedding_model, runner.load_vectors(vectors_path))
        routes = runner.load_routes(runner._routes_path(settings))

        print("\n## 1. With the discussion texts (as stored)")
        run(conn, questions, stored, routes, settings, reranker, old, show=True)

        print("\n## 2. Without them (deleted inside a transaction that is always rolled back)")
        with conn.transaction():
            deleted = conn.execute(DELETE_DISCUSSION_CHUNKS).rowcount
            print(f"Discussion chunks deleted inside the transaction: {deleted}")
            run(conn, questions, stored, routes, settings, reranker, old, show=False)
            raise psycopg.Rollback()
        left = conn.execute(COUNT_DISCUSSION_CHUNKS).fetchone()[0]
        print(f"After the rollback, discussion chunks stored: {left}")


if __name__ == "__main__":
    main()
