"""Variant the DA flagged: the retry's search ranked by the normal pipeline on the REWRITTEN
query (its own top 10), then RRF of the first 10 and the retry's 10 (k = RRF_K), top 10.
Same forced queries as probe_forced.json; only Voyage embeds are paid."""
import json, sys, psycopg, yaml
from orgknow.settings import Settings
from orgknow.cli import load_reranker
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.metrics import score_retrieval
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.retrieve import retrieve
s = Settings(); rr = load_reranker(s)
voyage = VoyageEmbedder(s.voyage_api_url, s.voyage_api_key, s.embedding_model)
forced = json.load(open(f"{sys.argv[1]}/probe_forced.json"))
rew = {i["id"]: i["reworded"] for i in yaml.safe_load(open("eval/candidates/router-rewording-v0.yaml"))["questions"]}
routes = runner.load_routes(runner._routes_path(s))
stored = runner.StoredVectors(s.embedding_model, runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json"))
rows = []
with psycopg.connect(s.database_url) as conn:
    golden, _ = runner.check_golden(conn, s.eval_golden_path); by = {q.id: q for q in golden.questions}
    for r in forced:
        gq = by[r["id"]]; route = routes[runner.question_key(gq.question)]
        q = gq.question if r["set"] == "v0" else rew[r["id"]]
        texts = [q, r["query"]] if r["set"] == "reworded" else [r["query"]]
        vecs = voyage.embed(texts, "query").vectors
        emb = runner.StoredVectors(s.embedding_model, {**({} if r["set"] == "v0" else {runner.question_key(q): vecs[0]}), runner.question_key(r["query"]): vecs[-1]})
        first = retrieve(q, stored if r["set"] == "v0" else emb, conn, s, rr, route)
        second = retrieve(r["query"], emb, conn, s, rr, route)
        fused = fuse(first, second, s.rrf_k, s.retrieval_top_k)
        a, b, c = (score_retrieval(gq, h, 10) for h in (first, second, fused))
        row = {"set": r["set"], "id": r["id"], "first": [round(a.recall, 3), a.hit, round(a.mrr, 3)],
               "retry_only": [round(b.recall, 3), b.hit, round(b.mrr, 3)], "rrf": [round(c.recall, 3), c.hit, round(c.mrr, 3)]}
        rows.append(row); print(json.dumps(row), flush=True)
json.dump(rows, open(f"{sys.argv[1]}/probe_rrf.json", "w"), indent=1)
