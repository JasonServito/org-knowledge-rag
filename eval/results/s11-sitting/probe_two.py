"""Show the merged top 10 for the 2 questions the grader sent to retry (c01, q48)."""
import json, psycopg, sys
from orgknow.settings import Settings
from orgknow.cli import load_reranker
from orgknow.db.releases import list_releases
from orgknow.db.retrieval import search, search_lexical
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.retrieval.authority import target_release, weigh
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.rerank import rerank
from orgknow.retrieval.retrieve import attach_authority, retrieve, temporal_plan
s = Settings(); rr = load_reranker(s)
voyage = VoyageEmbedder(s.voyage_api_url, s.voyage_api_key, s.embedding_model)
rows = {r["id"]: r for r in json.load(open(sys.argv[1]))}
vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
routes = runner.load_routes(runner._routes_path(s)); stored = runner.StoredVectors(s.embedding_model, vectors)
with psycopg.connect(s.database_url) as conn:
    golden, _ = runner.check_golden(conn, s.eval_golden_path)
    cset = runner.check_conflicts(conn, golden, s.eval_conflicts_path)
    qs = {q.id: q.question for q in golden.questions} | {q.id: q.question for q in cset.questions}
    latest = list_releases(conn)[-1].minor
    for qid in ("c01", "q48"):
        question, query = qs[qid], rows[qid]["query"]; route = routes[runner.question_key(question)]
        hits = retrieve(question, stored, conn, s, rr, route); seen = {h.chunk_id for h in hits}
        window, temporal = temporal_plan(conn, route, s)
        v = voyage.embed([query], "query").vectors[0]
        fused = fuse(search(conn, v, s.embedding_model, s.retrieval_candidates, s.hnsw_ef_search, temporal),
                     search_lexical(conn, query, s.retrieval_candidates, temporal), s.rrf_k, 99)
        new = [h for h in fused if h.chunk_id not in seen]
        new = attach_authority(conn, rerank(new, rr.score(question, [h.text for h in new]), len(new)), target_release(route.mode, window, latest))
        final = weigh([*hits, *new], route.mode, latest, s.authority_boost, s.authority_demote)[:10]
        print(f"== {qid}: {question} | query: {query}")
        for i, h in enumerate(final, 1):
            tag = "NEW" if h.chunk_id not in seen else "   "
            print(f" {i:2} {tag} {h.chunk_id} {h.canonical_id} | {' > '.join(h.heading_path)[-70:]} | p*f={h.authority_score:.3f}")
