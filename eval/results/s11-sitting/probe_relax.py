"""Scratch probe (S11 sitting): do deterministic route relaxations retrieve the 2 missed seeds,
and what do the unanswerables retrieve? Free: stored vectors/routes, local reranker."""
import psycopg, yaml
from orgknow.settings import Settings
from orgknow.cli import load_reranker
from orgknow.eval import runner
from orgknow.retrieval.retrieve import retrieve
from orgknow.retrieval.router import Route, TimeScope

s = Settings()
golden = yaml.safe_load(open(s.eval_golden_path))
cset = yaml.safe_load(open(s.eval_conflicts_path))
qs = {q["id"]: q["question"] for q in golden["questions"]}
qs.update({q["id"]: q["question"] for q in cset["questions"]})
vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
routes = runner.load_routes(runner._routes_path(s))
stored = runner.StoredVectors(s.embedding_model, vectors)
rr = load_reranker(s)
seed_docs = {"q08": [("kep:2579", "Implementation History")],
             "c01": [("sig-release:release-engineering/versioning.md", "Supported releases"),
                     ("web:/docs/setup/release/version-skew-policy/", "Supported versions"),
                     ("web:/releases/patch-releases/", "Support Period"),
                     ("web:/docs/setup/release/", "")]}
def show(qid, route, label):
    hits = retrieve(qs[qid], stored, conn, s, rr, route)
    marks = []
    for h in hits:
        for doc, sec in seed_docs.get(qid, []):
            if h.canonical_id == doc and sec in " > ".join(h.heading_path):
                marks.append(f"r{hits.index(h)+1}:{doc.split('/')[-2] if doc.endswith('/') else doc.split(':')[-1]}")
    print(f"{qid} [{label}] route={route.mode}/{route.time_scope.kind}:{route.time_scope.start},{route.time_scope.end} -> {marks or 'no seed side'}")
    return hits
with psycopg.connect(s.database_url) as conn:
    for qid in ("q08", "c01"):
        r = routes[runner.question_key(qs[qid])]
        show(qid, r, "as routed")
        for mode in ("CURRENT", "HISTORY", "CHANGE", "WHY"):
            show(qid, Route(mode=mode, time_scope=TimeScope(kind="none", start=None, end=None)), f"{mode}, no window")
    print("--- unanswerable routes")
    for q in golden["questions"]:
        if not q.get("answerable", True):
            r = routes[runner.question_key(q["question"])]
            print(q["id"], r.mode, r.time_scope.kind, "|", q["question"][:90])
