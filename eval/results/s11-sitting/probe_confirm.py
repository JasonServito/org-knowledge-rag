"""S11-R1 sitting: the devil's advocate's concession test for the RRF second search, as it would be
built. Per question: the first authority retrieve (deterministic, once); then, in each of 3 runs,
one Haiku call (stop | search + query) and, on "search", a normal authority retrieve on the query,
RRF of the two top 10s (k = RRF_K), top 10. Pre-set checks (all must hold):
  1. rephrased Recall@10 gain >= +0.03 in every run
  2. no v0 metric (Recall@10, Hit@10, MRR, nDCG@10) drops by more than 0.03 in any run
  3. p95 over v0's 43 questions of (first retrieve + grade + second retrieve + S10 answer time) <= 23 s
  4. q48's added hits contain no future-release text (read by Claude; regex flag shown)
Paid: Haiku calls (~$0.05 per run), Voyage embeds."""

import json
import math
import re
import sys
import time
from typing import Literal

import anthropic
import psycopg
import yaml
from pydantic import BaseModel

from orgknow.cli import load_reranker
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.metrics import score_retrieval
from orgknow.generation.prompt import evidence_block
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.retrieve import retrieve
from orgknow.settings import Settings

MODEL, EFFORT = "claude-haiku-5-5", "low"
SYSTEM = """\
You write search queries for a search over the Kubernetes docs, KEPs (Kubernetes Enhancement \
Proposals), release notes and blog posts. You get a question and the evidence a first search \
found.

- If what the question needs is something these sources don't hold (private discussions or \
meeting notes, unpublished data or survey results, numbers about real clusters, or plans for \
future releases), the verdict is "stop", with no query.
- Otherwise the verdict is "search": write one new search query for the part of the answer the \
evidence covers least, in the words the missing text would use: full names, not abbreviations. \
Don't name a release the question doesn't name.
"""
FUTURE = re.compile(r"\b(?:v?1\.(?:3[89]|[4-9]\d))\b|will graduate|targeted for|planned for", re.I)


class Grade(BaseModel):
    verdict: Literal["stop", "search"]
    missing: str
    query: str | None


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def main() -> None:
    sp = sys.argv[1]
    s = Settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key.get_secret_value())
    voyage = VoyageEmbedder(s.voyage_api_url, s.voyage_api_key, s.embedding_model)
    rr = load_reranker(s)
    routes = runner.load_routes(runner._routes_path(s))
    vectors = dict(runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json"))
    rew = {i["id"]: i["reworded"] for i in yaml.safe_load(open("eval/candidates/router-rewording-v0.yaml"))["questions"]}
    # S10's answer time per question and run (latency - retrieve), runs 1-3 in time order
    s10 = ["conflict-20261012T170000Z", "conflict-20261012T171009Z", "conflict-20261012T171932Z"]
    answer_s = []
    for folder in s10:
        rows = [json.loads(line) for line in open(f"eval/results/{folder}/questions.jsonl")]
        answer_s.append({r["id"]: r["latency_s"] - r["retrieve_s"] for r in rows})
    tin = tout = 0
    out = []
    with psycopg.connect(s.database_url) as conn:
        golden, _ = runner.check_golden(conn, s.eval_golden_path)
        items = [("v0", q.id, q.question, q) for q in golden.questions]
        by_id = {q.id: q for q in golden.questions}
        items += [("rephrased", qid, text, by_id[qid]) for qid, text in rew.items()]
        missing = [text for st, _, text, _ in items if runner.question_key(text) not in vectors]
        for text, vec in zip(missing, voyage.embed(missing, "query").vectors):
            vectors[runner.question_key(text)] = vec
        first = {}
        for st, qid, text, gq in items:
            route = routes[runner.question_key(gq.question)]  # v0's route (as in the earlier probes)
            t = time.monotonic()
            hits = retrieve(text, runner.StoredVectors(s.embedding_model, vectors), conn, s, rr, route)
            first[(st, qid)] = (hits, time.monotonic() - t, route)
        print("first searches done", flush=True)
        for run in range(3):
            for st, qid, text, gq in items:
                hits, first_s, route = first[(st, qid)]
                t = time.monotonic()
                resp = client.messages.parse(
                    model=MODEL, max_tokens=4000, system=SYSTEM,
                    messages=[{"role": "user", "content": "Evidence:\n\n"
                               + "\n\n".join(evidence_block(h) for h in hits) + f"\n\nQuestion: {text}"}],
                    output_format=Grade, output_config={"effort": EFFORT})
                grade_s = time.monotonic() - t
                tin += resp.usage.input_tokens
                tout += resp.usage.output_tokens
                g = resp.parsed_output
                final, second_s, added = hits, 0.0, []
                if g is not None and g.verdict == "search" and g.query:
                    t = time.monotonic()
                    vec = voyage.embed([g.query], "query").vectors[0]
                    emb = runner.StoredVectors(s.embedding_model, {runner.question_key(g.query): vec})
                    second = retrieve(g.query, emb, conn, s, rr, route)
                    final = fuse(hits, second, s.rrf_k, s.retrieval_top_k)
                    second_s = time.monotonic() - t
                    seen = {h.chunk_id for h in hits}
                    added = [h for h in final if h.chunk_id not in seen]
                row = {"run": run + 1, "set": st, "id": qid, "answerable": gq.answerable,
                       "verdict": None if g is None else g.verdict, "query": None if g is None else g.query,
                       "first_s": round(first_s, 2), "grade_s": round(grade_s, 2), "second_s": round(second_s, 2),
                       "added": [h.chunk_id for h in added]}
                if gq.answerable:
                    a, b = score_retrieval(gq, hits, 10), score_retrieval(gq, final, 10)
                    row["before"] = [a.recall, a.hit, a.mrr, a.ndcg]
                    row["after"] = [b.recall, b.hit, b.mrr, b.ndcg]
                if st == "v0":
                    row["total_s"] = round(first_s + grade_s + second_s + answer_s[run].get(qid, 0.0), 2)
                if qid in ("q05", "q10", "q15", "q20", "q27", "q47", "q48") and added:
                    row["added_text"] = [{"chunk": h.chunk_id, "doc": h.canonical_id,
                                          "future_flag": bool(FUTURE.search(h.text)),
                                          "snippet": h.text[h.text.find("\n\n") + 2:][:400]} for h in added]
                out.append(row)
                print(json.dumps({k: v for k, v in row.items() if k != "added_text"}), flush=True)
            # the run's summary and the checks
            for st in ("v0", "rephrased"):
                rows = [r for r in out if r["run"] == run + 1 and r["set"] == st and "before" in r]
                n = len(rows)
                mean = lambda key, i: sum(r[key][i] for r in rows) / n
                deltas = [mean("after", i) - mean("before", i) for i in range(4)]
                print(f"RUN {run + 1} {st}: n={n} before R/H/MRR/nDCG "
                      + "/".join(f"{mean('before', i):.3f}" for i in range(4)) + " after "
                      + "/".join(f"{mean('after', i):.3f}" for i in range(4)) + " deltas "
                      + "/".join(f"{d:+.3f}" for d in deltas), flush=True)
            totals = [r["total_s"] for r in out if r["run"] == run + 1 and r["set"] == "v0"]
            print(f"RUN {run + 1} p95 total (v0, 43): {p95(totals):.1f} s; "
                  f"search verdicts: {sum(r['verdict'] == 'search' for r in out if r['run'] == run + 1)} of {len(items)}", flush=True)
    print(f"TOTAL Haiku in {tin} out {tout} cost ${tin * 0.10 / 1e6 + tout * 0.50 / 1e6:.4f}", flush=True)
    json.dump(out, open(f"{sp}/probe_confirm.json", "w"), indent=1)


main()
