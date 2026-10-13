"""S12-R1 sitting probe (scratch, never imported by src/): ADR-010 D4's separate detector call,
the "one-off comparison", run in the sitting instead of as the run's first step.

For v0's 43 questions plus the conflict set's c01 and c02: retrieve in authority mode from the
stored vectors and routes (checked equal to conflict run 1's hits), find the rule-found
conflicts, then ask Haiku 5.5 (effort low) for the pairs of chunks that disagree, with the
answer call's own user prompt (evidence, rule-found conflicts, settle line, question). Its pairs
go through `model_conflicts` and are scored with `score_conflicts` against conflict set v0.

Two system prompts, each on all 45 questions once, then q01 twice more (3 in all):
- A (neutral): the answer prompt's conflict sentence, as the detector's only job.
- B: A plus one line on a KEP whose claimed status is out of date against what other chunks show.

Pass criteria, fixed before the run (2026-10-12), per variant:
1. q01: a flag matches seed k02 AND its summary names KEP-2572's out-of-date status or the
   cadence it proposes not being in force (the S10 summary check), in 3 of 3 calls; the
   summaries are printed verbatim for the developer to judge.
2. Raw precision of the detector's flags >= 0.70 (the answer call's worst run: 10 of 14).
Also reported: recall (vs. the answer call's 0.317-0.350), seeds, latency p50/p95, cost.

Paid: ~94 Haiku calls, ~US$0.15. Usage: uv run python -u eval/results/s12-sitting/probe_detector.py OUT.json
"""

import json
import statistics
import sys
import time

import anthropic
import psycopg
from pydantic import BaseModel

from orgknow.cli import load_reranker
from orgknow.eval import runner
from orgknow.eval.conflicts import matches, score_conflicts
from orgknow.generation.conflicts import Conflict
from orgknow.generation.conflicts import ModelConflict, model_conflicts, rule_conflicts
from orgknow.generation.prompt import user_prompt
from orgknow.retrieval.retrieve import retrieve
from orgknow.settings import Settings

MODEL = "claude-haiku-5-5"
EFFORT = "low"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # $/M tokens, as in the S11 probes
RUN1 = "eval/results/conflict-20261012T170000Z"

BASE = """\
You check evidence for disagreements before a question about Kubernetes is answered. The \
evidence is chunks of the Kubernetes docs and of KEPs (Kubernetes Enhancement Proposals). Each \
chunk starts with a line giving its id and the releases it was valid in ("now": still valid in \
the latest release), then its authority tier (1 = docs and feature-gate pages, 2 = release notes, \
3 = shipped KEPs, 4 = governance docs, 5 = unshipped KEPs, 6 = blog posts). A KEP chunk adds the \
status and stage the KEP claimed, with its latest milestone, and its stage at the asked-about \
release.

List every pair of chunks whose texts disagree (two sources, or an older and a newer version of \
one text), with one sentence on what differs. Don't answer the question. Conflicts found by code \
are listed after the evidence: don't list them again. Return an empty list when nothing \
disagrees.
"""
EXTRA_B = """
A KEP whose claimed status or latest milestone is out of date, compared with what other chunks \
show is in force, disagrees with those chunks: list the KEP chunk with the chunk that shows it.
"""
PROMPTS = {"A": BASE, "B": BASE + EXTRA_B}


class Detected(BaseModel):
    conflicts: list[ModelConflict]


def main() -> None:
    s = Settings()
    assert s.anthropic_api_key and s.retrieval_mode == "authority"
    client = anthropic.Anthropic(api_key=s.anthropic_api_key.get_secret_value())
    reranker = load_reranker(s)
    vectors = runner.load_vectors(s.eval_vectors_dir / f"{s.embedding_model}.json")
    routes = runner.load_routes(runner._routes_path(s))
    stored = runner.StoredVectors(s.embedding_model, vectors)
    run1 = {}
    for name in ("questions.jsonl", "conflict_questions.jsonl"):
        for line in open(f"{RUN1}/{name}"):
            row = json.loads(line)
            run1[row["id"]] = [h["chunk_id"] for h in row["hits"]]
    out = {"model": MODEL, "effort": EFFORT, "prompts": PROMPTS, "calls": []}
    tokens = {"in": 0, "out": 0}

    def detect(variant, qid, question, hits, found):
        start = time.monotonic()
        response = client.messages.parse(
            model=MODEL,
            max_tokens=4000,
            system=PROMPTS[variant],
            messages=[{"role": "user", "content": user_prompt(question, hits, found)}],
            output_format=Detected,
            output_config={"effort": EFFORT},
        )
        seconds = time.monotonic() - start
        tokens["in"] += response.usage.input_tokens
        tokens["out"] += response.usage.output_tokens
        pairs = [] if response.parsed_output is None else response.parsed_output.conflicts
        kept, dropped = model_conflicts(pairs, hits, found)
        call = {"variant": variant, "id": qid, "s": round(seconds, 2),
                "stop_reason": response.stop_reason,
                "in": response.usage.input_tokens, "out": response.usage.output_tokens,
                "pairs": [p.model_dump() for p in pairs],
                "kept": [c.model_dump(mode="json") for c in kept], "dropped": len(dropped)}
        out["calls"].append(call)
        print(json.dumps({k: call[k] for k in ("variant", "id", "s", "stop_reason", "dropped")}
                         | {"kept": len(kept)}), flush=True)
        return kept

    with psycopg.connect(s.database_url) as conn:
        golden, _ = runner.check_golden(conn, s.eval_golden_path)
        cset = runner.check_conflicts(conn, golden, s.eval_conflicts_path)
        pool = [(q.id, q.question) for q in golden.questions]
        pool += [(q.id, q.question) for q in cset.questions]
        retrieved = []
        for qid, question in pool:
            route = routes[runner.question_key(question)]
            hits = retrieve(question, stored, conn, s, reranker, route)
            assert [h.chunk_id for h in hits] == run1[qid], f"{qid}: hits differ from run 1"
            retrieved.append((qid, question, hits, rule_conflicts(conn, hits, s)))
        print(f"retrieved {len(retrieved)} questions; hits equal run 1's", flush=True)

        for variant in PROMPTS:
            scored = []
            for qid, question, hits, found in retrieved:
                kept = detect(variant, qid, question, hits, found)
                scored.append((qid, hits, [*found, *kept]))
            counts = score_conflicts(cset.conflicts, scored)
            out[f"counts_{variant}"] = counts.model_dump(mode="json")
            q01 = next(r for r in retrieved if r[0] == "q01")
            for _ in range(2):
                detect(variant, *q01)
        k02 = next(c for c in cset.conflicts if c.id == "k02")
        q01_hits = next(r[2] for r in retrieved if r[0] == "q01")
        for call in out["calls"]:
            if call["id"] == "q01":
                call["k02"] = any(matches(Conflict(**k), k02, q01_hits) for k in call["kept"])

    for variant in PROMPTS:
        calls = [c for c in out["calls"] if c["variant"] == variant]
        seconds = sorted(c["s"] for c in calls)
        c = out[f"counts_{variant}"]
        print(f"\n== Variant {variant}: {len(calls)} calls; latency p50 {statistics.median(seconds):.2f} s,"
              f" p95 {seconds[int(0.95 * (len(seconds) - 1))]:.2f} s")
        print(f"precision all {c['precision']}, rule {c['precision_rule']}, model {c['precision_model']}")
        print(f"recall all {c['recall']}, rule {c['recall_rule']}, texts {c['recall_texts']}")
        print("seeds: " + "; ".join(f"{x['conflict_id']} {x['question_id']} retrieved={x['retrieved']}"
                                    f" surfaced={x['surfaced']}" for x in c["seeds"]))
        print("q01's kept pairs, verbatim (3 calls):")
        for n, call in enumerate(c2 for c2 in calls if c2["id"] == "q01"):
            for k in call["kept"]:
                print(f"  call {n + 1} (k02 matched: {call['k02']}): {k['chunk_ids']} {k['resolution']}: {k['summary']}")
            if not call["kept"]:
                print(f"  call {n + 1}: (none)")
    cost = tokens["in"] * PRICE_IN / 1e6 + tokens["out"] * PRICE_OUT / 1e6
    print(f"\nTOTAL tokens in {tokens['in']}, out {tokens['out']}, cost ${cost:.4f}")
    json.dump(out, open(sys.argv[1], "w"), indent=1)


main()
