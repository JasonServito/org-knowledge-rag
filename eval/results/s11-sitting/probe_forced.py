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



import yaml
from orgknow.retrieval.router import ClaudeRouter


def merged(conn, s, reranker, question, route, window, hits, query_vec, query_text, temporal, latest):
    """hits + the new texts a search for query_text finds under temporal, the new ones scored
    against the ORIGINAL question, weighed, top 10."""
    dense = search(conn, query_vec, s.embedding_model, s.retrieval_candidates, s.hnsw_ef_search, temporal)
    lexical = search_lexical(conn, query_text, s.retrieval_candidates, temporal)
    fused = fuse(dense, lexical, s.rrf_k, len(dense) + len(lexical))
    seen = {h.chunk_id for h in hits}
    new = [h for h in fused if h.chunk_id not in seen]
    if not new:
        return hits
    new = rerank(new, reranker.score(question, [h.text for h in new]), len(new))
    new = attach_authority(conn, new, target_release(route.mode, window, latest))
    return weigh([*hits, *new], route.mode, latest, s.authority_boost, s.authority_demote)[: s.retrieval_top_k]


def stale(hits):
    return sum(all(until is not None for _, until in h.release_windows) for h in hits)



REWRITE = """\
You write search queries for a search over the Kubernetes docs, KEPs (Kubernetes Enhancement \
Proposals), release notes and blog posts. You get a question and the evidence a first search \
found. Write one new search query for the part of the answer the evidence covers least, in the \
words the missing text would use: full names, not abbreviations. Don't name a release the \
question doesn't name.
"""


class Rewrite(BaseModel):
    query: str


def main() -> None:
    s = Settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key.get_secret_value())
    voyage = VoyageEmbedder(s.voyage_api_url, s.voyage_api_key, s.embedding_model)
    reranker = load_reranker(s)
    vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
    routes = runner.load_routes(runner._routes_path(s))
    stored = runner.StoredVectors(s.embedding_model, vectors)
    prev = {r["id"]: r for r in json.load(open(sys.argv[2]))}
    items = yaml.safe_load(open("eval/candidates/router-rewording-v0.yaml"))["questions"]
    rows, tin, tout = [], 0, 0
    with psycopg.connect(s.database_url) as conn:
        golden, _ = runner.check_golden(conn, s.eval_golden_path)
        by_id = {q.id: q for q in golden.questions}
        latest = list_releases(conn)[-1].minor
        router_routes = {}
        for it in items:
            gq = by_id[it["id"]]
            for kind, q in (("v0", gq.question), ("reworded", it["reworded"])):
                if kind == "v0":
                    route = routes[runner.question_key(q)]
                    emb = stored
                else:
                    from orgknow.retrieval.router import Route, TimeScope
                    p = prev[it["id"]]
                    # reuse the probe's route by re-routing is paid; instead re-use golden route when modes match
                    route = routes[runner.question_key(gq.question)] if p["route"] == gq.mode else Route(mode=p["route"], time_scope=TimeScope(kind="none", start=None, end=None))
                    qvec = voyage.embed([q], "query").vectors[0]
                    emb = runner.StoredVectors(s.embedding_model, {runner.question_key(q): qvec})
                hits = retrieve(q, emb, conn, s, reranker, route)
                resp = client.messages.parse(model=GRADER_MODEL, max_tokens=4000, system=REWRITE,
                    messages=[{"role": "user", "content": "Evidence:\n\n" + "\n\n".join(evidence_block(h) for h in hits) + f"\n\nQuestion: {q}"}],
                    output_format=Rewrite, output_config={"effort": EFFORT})
                tin += resp.usage.input_tokens; tout += resp.usage.output_tokens
                query = resp.parsed_output.query
                window, temporal = temporal_plan(conn, route, s)
                qv = voyage.embed([query], "query").vectors[0]
                final = merged(conn, s, reranker, q, route, window, hits, qv, query, temporal, latest)
                a, b = score_retrieval(gq, hits, 10), score_retrieval(gq, final, 10)
                row = {"id": it["id"], "set": kind, "query": query,
                       "recall": [round(a.recall, 3), round(b.recall, 3)], "hit": [a.hit, b.hit],
                       "mrr": [round(a.mrr, 3), round(b.mrr, 3)],
                       "new_in_top10": sum(h.chunk_id not in {x.chunk_id for x in hits} for h in final)}
                rows.append(row); print(json.dumps(row), flush=True)
    print(f"TOTAL rewrite in {tin} out {tout} cost ${tin*PRICE_IN/1e6+tout*PRICE_OUT/1e6:.4f}", flush=True)
    json.dump(rows, open(sys.argv[1], "w"), indent=1)


main()
