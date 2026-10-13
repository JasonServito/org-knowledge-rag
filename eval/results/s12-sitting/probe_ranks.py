"""S12-R1 sitting probe (scratch, free): where seeds k03 (q08) and k04 (c01) rank past the top 10.
Retrieves q08 and c01 from the stored vectors and routes with retrieval_top_k = 40, in authority
mode (as routed), and q08 also in hybrid and rerank modes. Marks hits on a seed's sides.
Checks the S12 devil's advocate's claims 4 and 7. Usage: uv run python eval/results/s12-sitting/probe_ranks.py"""

import psycopg

from orgknow.cli import load_reranker
from orgknow.eval import runner
from orgknow.eval.conflicts import _on_side
from orgknow.retrieval.retrieve import retrieve
from orgknow.settings import Settings

base = Settings()
reranker = load_reranker(base)
vectors = runner.load_vectors(base.eval_vectors_dir / f"{base.embedding_model}.json")
routes = runner.load_routes(runner._routes_path(base))
stored = runner.StoredVectors(base.embedding_model, vectors)
with psycopg.connect(base.database_url) as conn:
    golden, _ = runner.check_golden(conn, base.eval_golden_path)
    cset = runner.check_conflicts(conn, golden, base.eval_conflicts_path)
    questions = {q.id: q.question for q in golden.questions} | {q.id: q.question for q in cset.questions}
    seeds = {c.question: c for c in cset.conflicts if c.id in ("k03", "k04")}
    for qid, modes in (("c01", ("authority",)), ("q08", ("authority", "rerank", "hybrid"))):
        seed = seeds[qid]
        for mode in modes:
            s = base.model_copy(update={"retrieval_mode": mode, "retrieval_top_k": 40})
            route = routes[runner.question_key(questions[qid])] if mode == "authority" else None
            hits = retrieve(questions[qid], stored, conn, s, reranker if mode != "hybrid" else None, route)
            print(f"== {qid} {seed.id} {mode} ({len(hits)} candidates)" + (f" route {route.mode} {route.time_scope}" if route else ""))
            for rank, h in enumerate(hits, 1):
                first = _on_side(seed.first, h)
                second = seed.second is not None and _on_side(seed.second, h)
                mark = ("F" if first else "") + ("S" if second else "")
                if mark or rank <= 10:
                    windows = [(a, b) for a, b in h.release_windows]
                    print(f"  {rank:2} {mark:2} {h.chunk_id} {h.canonical_id} | {' > '.join(h.heading_path)[-70:]} | {windows}")
