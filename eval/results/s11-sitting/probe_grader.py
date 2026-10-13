"""S11-R1 sitting probe (scratch, never imported by src/): a Haiku grader on each question's stored
authority-mode hits; for each "retry", one search with the grader's query under the same route
filter, the new texts scored by the cross-encoder against the ORIGINAL question, merged with the
first 10, re-weighed, cut to 10. Scored against the golden labels and the conflict set.
Paid: ~45 Haiku calls + a few Voyage embeds."""

import json
import sys
import time
from typing import Literal

import anthropic
import psycopg
from pydantic import BaseModel

from orgknow.cli import load_reranker
from orgknow.db.releases import list_releases
from orgknow.db.retrieval import search, search_lexical
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.conflicts import reachable
from orgknow.eval.metrics import score_retrieval
from orgknow.generation.prompt import evidence_block
from orgknow.retrieval.authority import target_release, weigh
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.rerank import rerank
from orgknow.retrieval.retrieve import attach_authority, retrieve, temporal_plan
from orgknow.settings import Settings

GRADER_MODEL = "claude-haiku-5-5"
EFFORT = "low"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # $/M tokens

SYSTEM = """\
You check whether search results are enough to answer a question about Kubernetes, before an \
answer is written. The evidence is chunks of the Kubernetes docs, KEPs (Kubernetes Enhancement \
Proposals), release notes and blog posts; each starts with its id and the releases it was valid in.

Give one verdict:
- enough: the evidence holds what an answer needs.
- retry: part of what an answer needs is missing, and the public Kubernetes docs, KEPs, release \
notes or blog posts plausibly hold it. Write one new search query for the missing part.
- stop: what is missing is something these sources don't hold: private discussions or meeting \
notes, unpublished data or survey results, numbers about real clusters, or plans for future \
releases.

The query is a short search query, not a question, in the words the missing text would use. \
Don't repeat the question's wording, and don't name a release the question doesn't name.
"""


class Grade(BaseModel):
    verdict: Literal["enough", "retry", "stop"]
    missing: str
    query: str | None


def main() -> None:
    s = Settings()
    assert s.anthropic_api_key and s.voyage_api_key
    client = anthropic.Anthropic(api_key=s.anthropic_api_key.get_secret_value())
    voyage = VoyageEmbedder(s.voyage_api_url, s.voyage_api_key, s.embedding_model)
    reranker = load_reranker(s)
    assert reranker is not None
    vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
    routes = runner.load_routes(runner._routes_path(s))
    stored = runner.StoredVectors(s.embedding_model, vectors)
    rows = []
    tokens_in = tokens_out = 0
    with psycopg.connect(s.database_url) as conn:
        golden, _ = runner.check_golden(conn, s.eval_golden_path)
        cset = runner.check_conflicts(conn, golden, s.eval_conflicts_path)
        pool = [(q.id, q.question, q) for q in golden.questions]
        pool += [(q.id, q.question, None) for q in cset.questions]
        latest = list_releases(conn)[-1].minor
        for qid, question, golden_q in pool:
            route = routes[runner.question_key(question)]
            hits = retrieve(question, stored, conn, s, reranker, route)
            start = time.monotonic()
            response = client.messages.parse(
                model=GRADER_MODEL,
                max_tokens=4000,
                system=SYSTEM,
                messages=[{"role": "user", "content": "Evidence:\n\n"
                           + "\n\n".join(evidence_block(h) for h in hits)
                           + f"\n\nQuestion: {question}"}],
                output_format=Grade,
                output_config={"effort": EFFORT},
            )
            grade_s = time.monotonic() - start
            tokens_in += response.usage.input_tokens
            tokens_out += response.usage.output_tokens
            grade = response.parsed_output
            row = {"id": qid, "mode": route.mode,
                   "answerable": None if golden_q is None else golden_q.answerable,
                   "verdict": None if grade is None else grade.verdict,
                   "missing": None if grade is None else grade.missing,
                   "query": None if grade is None else grade.query,
                   "stop_reason": response.stop_reason, "grade_s": round(grade_s, 2),
                   "in_tokens": response.usage.input_tokens,
                   "out_tokens": response.usage.output_tokens}
            final = hits
            if grade is not None and grade.verdict == "retry" and grade.query:
                start = time.monotonic()
                vector = voyage.embed([grade.query], "query").vectors[0]
                embed_s = time.monotonic() - start
                window, temporal = temporal_plan(conn, route, s)
                dense = search(conn, vector, s.embedding_model, s.retrieval_candidates,
                               s.hnsw_ef_search, temporal)
                lexical = search_lexical(conn, grade.query, s.retrieval_candidates, temporal)
                fused = fuse(dense, lexical, s.rrf_k, len(dense) + len(lexical))
                seen = {h.chunk_id for h in hits}
                new = [h for h in fused if h.chunk_id not in seen]
                if new:
                    scores = reranker.score(question, [h.text for h in new])  # ORIGINAL question
                    new = rerank(new, scores, len(new))
                    target = target_release(route.mode, window, latest)
                    new = attach_authority(conn, new, target)
                    final = weigh([*hits, *new], route.mode, latest, s.authority_boost,
                                  s.authority_demote)[: s.retrieval_top_k]
                row.update(retry_s=round(time.monotonic() - start, 2), embed_s=round(embed_s, 2),
                           new_candidates=len(new),
                           new_in_top10=sum(h.chunk_id not in seen for h in final))
            if golden_q is not None and golden_q.answerable:
                before = score_retrieval(golden_q, hits, s.retrieval_top_k)
                after = score_retrieval(golden_q, final, s.retrieval_top_k)
                row.update(recall_before=round(before.recall, 3), recall_after=round(after.recall, 3),
                           mrr_before=round(before.mrr, 3), mrr_after=round(after.mrr, 3))
            mine = [c for c in cset.conflicts if c.question == qid]
            row.update(reachable_before=sum(reachable(c, hits) for c in mine),
                       reachable_after=sum(reachable(c, final) for c in mine),
                       conflicts=len(mine),
                       seeds_after={c.id: reachable(c, final) for c in mine if c.seed})
            rows.append(row)
            print(json.dumps(row), flush=True)
    cost = tokens_in * PRICE_IN / 1e6 + tokens_out * PRICE_OUT / 1e6
    print(f"TOTAL grader tokens in {tokens_in}, out {tokens_out}, cost ${cost:.4f}", flush=True)
    json.dump(rows, open(sys.argv[1], "w"), indent=1)


main()
