"""DA's free test: where do the labeled sources sit in the whole candidate pool (before the top-10
cut), for the first search and for the forced retry's search? Plus k04's reachability for c01
with no time window."""
import json, sys, psycopg, yaml
from orgknow.settings import Settings
from orgknow.cli import load_reranker
from orgknow.db.releases import list_releases
from orgknow.db.retrieval import search, search_lexical
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.conflicts import reachable
from orgknow.eval.metrics import gains
from orgknow.retrieval.authority import target_release, weigh
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.rerank import rerank
from orgknow.retrieval.retrieve import attach_authority, retrieve, temporal_plan
from orgknow.retrieval.router import Route, TimeScope
s = Settings(); rr = load_reranker(s)
voyage = VoyageEmbedder(s.voyage_api_url, s.voyage_api_key, s.embedding_model)
forced = {(r["set"], r["id"]): r for r in json.load(open(f"{sys.argv[1]}/probe_forced.json"))}
rew = {i["id"]: i["reworded"] for i in yaml.safe_load(open("eval/candidates/router-rewording-v0.yaml"))["questions"]}
routes = runner.load_routes(runner._routes_path(s))
vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
def pool(conn, question, qvec, qtext, route, latest):
    """Every candidate both searches find for (qvec, qtext) under the route's filter, scored
    against `question`, weighed, best first."""
    window, temporal = temporal_plan(conn, route, s)
    dense = search(conn, qvec, s.embedding_model, s.retrieval_candidates, s.hnsw_ef_search, temporal)
    lexical = search_lexical(conn, qtext, s.retrieval_candidates, temporal)
    fused = fuse(dense, lexical, s.rrf_k, len(dense) + len(lexical))
    scored = rerank(fused, rr.score(question, [h.text for h in fused]), len(fused))
    scored = attach_authority(conn, scored, target_release(route.mode, window, latest))
    return weigh(scored, route.mode, latest, s.authority_boost, s.authority_demote)
with psycopg.connect(s.database_url) as conn:
    golden, _ = runner.check_golden(conn, s.eval_golden_path); by = {q.id: q for q in golden.questions}
    cset = runner.check_conflicts(conn, golden, s.eval_conflicts_path)
    latest = list_releases(conn)[-1].minor
    for qid in ("q08", "q31"):
        gq = by[qid]; q = rew[qid]; route = routes[runner.question_key(gq.question)]
        qvec = voyage.embed([q], "query").vectors[0]
        first = pool(conn, q, qvec, q, route, latest)
        rq = forced[("reworded", qid)]["query"]
        retry = pool(conn, q, voyage.embed([rq], "query").vectors[0], rq, route, latest)
        for name, p in (("first search", first), ("retry search", retry)):
            g = gains(gq.labels, p)
            pos = [i for i, x in enumerate(g, 1) if x]
            print(f"{qid} rephrased, {name}: pool {len(p)} texts; labeled at ranks {pos or 'none'} (of {len(gq.labels)} labels)")
        print(f"   retry query: {rq}")
    c01 = next(q for q in cset.questions if q.id == "c01"); k04 = next(c for c in cset.conflicts if c.id == "k04")
    stored = runner.StoredVectors(s.embedding_model, vectors)
    for label, route in (("as routed", routes[runner.question_key(c01.question)]),
                         ("no window", Route(mode="HISTORY", time_scope=TimeScope(kind="none", start=None, end=None)))):
        hits = retrieve(c01.question, stored, conn, s, rr, route)
        print(f"c01 {label}: k04 reachable in top 10: {reachable(k04, hits)}")
