import psycopg, yaml
from orgknow.settings import Settings
from orgknow.cli import load_reranker
from orgknow.eval import runner
from orgknow.retrieval.retrieve import retrieve
from orgknow.retrieval.router import Route, TimeScope
s = Settings()
cset = yaml.safe_load(open(s.eval_conflicts_path))
k04 = next(c for c in cset["conflicts"] if c["id"] == "k04")
print("k04 second sides:"); [print("  ", e) for e in k04["second"]]
q = next(x["question"] for x in cset["questions"] if x["id"] == "c01")
vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
routes = runner.load_routes(runner._routes_path(s))
stored = runner.StoredVectors(s.embedding_model, vectors); rr = load_reranker(s)
with psycopg.connect(s.database_url) as conn:
    for label, route in [("as routed", routes[runner.question_key(q)]),
                         ("HISTORY no window", Route(mode="HISTORY", time_scope=TimeScope(kind="none", start=None, end=None)))]:
        print("==", label, route.model_dump())
        for i, h in enumerate(retrieve(q, stored, conn, s, rr, route), 1):
            print(f"  {i:2} {h.chunk_id} {h.canonical_id} | {' > '.join(h.heading_path)[-80:]} | {h.release_windows if hasattr(h,'release_windows') else ''}")
