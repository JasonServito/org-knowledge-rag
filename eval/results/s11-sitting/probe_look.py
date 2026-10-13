import json, sys, psycopg, yaml
from orgknow.settings import Settings
from orgknow.cli import load_reranker
from orgknow.db.releases import list_releases
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.metrics import gains
from orgknow.retrieval.retrieve import retrieve, temporal_plan
sys.path.insert(0, sys.argv[1]); from probe_reworded_lib import merged  # noqa
s = Settings(); rr = load_reranker(s)
voyage = VoyageEmbedder(s.voyage_api_url, s.voyage_api_key, s.embedding_model)
forced = {(r["set"], r["id"]): r for r in json.load(open(f"{sys.argv[1]}/probe_forced.json"))}
rew = {i["id"]: i["reworded"] for i in yaml.safe_load(open("eval/candidates/router-rewording-v0.yaml"))["questions"]}
vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
routes = runner.load_routes(runner._routes_path(s)); stored = runner.StoredVectors(s.embedding_model, vectors)
with psycopg.connect(s.database_url) as conn:
    golden, _ = runner.check_golden(conn, s.eval_golden_path); by = {q.id: q for q in golden.questions}
    latest = list_releases(conn)[-1].minor
    for st, qid in (("v0", "q34"), ("reworded", "q31")):
        gq = by[qid]; q = gq.question if st == "v0" else rew[qid]
        route = routes[runner.question_key(gq.question)]
        emb = stored if st == "v0" else runner.StoredVectors(s.embedding_model, {runner.question_key(q): voyage.embed([q], "query").vectors[0]})
        hits = retrieve(q, emb, conn, s, rr, route); seen = {h.chunk_id for h in hits}
        query = forced[(st, qid)]["query"]; window, temporal = temporal_plan(conn, route, s)
        final = merged(conn, s, rr, q, route, window, hits, voyage.embed([query], "query").vectors[0], query, temporal, latest)
        print(f"== {st} {qid}: {q}\n   query: {query}")
        for label, hs in (("first", hits), ("merged", final)):
            g = gains(gq.labels, hs)
            print(f"   -- {label}")
            for i, (h, gain) in enumerate(zip(hs, g), 1):
                print(f"   {i:2} {'NEW' if h.chunk_id not in seen else '   '} {'L' if gain else ' '} {h.canonical_id} | {' > '.join(h.heading_path)[-60:]}")
                if label == "merged" and i <= 2 and h.chunk_id not in seen: print("        ", h.text[h.text.find('\n\n')+2:][:300].replace("\n"," "))
            if label == "first" and qid == "q31":
                for h in hs[:4]: print("        ", h.canonical_id, h.text[h.text.find('\n\n')+2:][:250].replace("\n"," "))
