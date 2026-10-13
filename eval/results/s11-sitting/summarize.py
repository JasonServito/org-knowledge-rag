"""S11-R1 sitting: print every table of the sitting evidence from the probes' saved outputs.

Free: reads only the JSON files in this folder. Run from the repo root:
    uv run python eval/results/s11-sitting/summarize.py
"""

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent


def load(name: str) -> list[dict]:
    return json.loads((HERE / name).read_text())


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def grader() -> None:
    rows = load("probe_grader.json")
    hard = {r["id"] for r in rows if r.get("recall_before") is not None and r["recall_before"] < 0.5}

    def group(r: dict) -> str:
        if r["answerable"] is False:
            return "unanswerable"
        if r["answerable"] is None:
            return "conflict questions (c01, c02)"
        return "hard (Recall@10 < 0.5)" if r["id"] in hard else "answerable, not hard"

    print("## 1. Haiku grader on v0's stored hits (probe_grader.py)")
    print(f"hard questions: {' '.join(sorted(hard))}")
    for (g, verdict), n in sorted(Counter((group(r), r["verdict"]) for r in rows).items()):
        print(f"  {g}: {verdict} {n}")
    times = [r["grade_s"] for r in rows]
    print(f"grade time p50 {statistics.median(times):.2f} s, p95 {p95(times):.2f} s")
    for r in rows:
        if r["verdict"] == "retry":
            print(f"  retry {r['id']}: query {r['query']!r}; recall {r.get('recall_before')} -> "
                  f"{r.get('recall_after')}; reachable conflicts {r['reachable_before']} -> "
                  f"{r['reachable_after']} of {r['conflicts']}; seeds {r['seeds_after']}")


def rephrased() -> None:
    rows = load("probe_reworded.json")
    print("\n## 2. The rephrased set: first search and the Haiku grader (probe_reworded.py)")
    for label, key in (("v0 wording", "orig"), ("rephrased", "rew")):
        print(f"  {label}: Recall@10 {mean([r[key + '_recall'] for r in rows]):.3f}, "
              f"Hit@10 {mean([r[key + '_hit'] for r in rows]):.3f}, "
              f"MRR {mean([r[key + '_mrr'] for r in rows]):.3f}")
    print(f"  router mode = golden mode: {sum(r['route'] == r['golden_mode'] for r in rows)} of {len(rows)}")
    print(f"  verdicts: {dict(Counter(r['verdict'] for r in rows))}")
    print(f"  Hit@10 lost: {[r['id'] for r in rows if r['orig_hit'] and not r['rew_hit']]}")


def forced() -> None:
    rows = load("probe_forced.json")
    print("\n## 3. A second search on every question, new texts scored against the original "
          "question (probe_forced.py)")
    for st in ("v0", "reworded"):
        rs = [r for r in rows if r["set"] == st]
        up = [r["id"] for r in rs if r["recall"][1] > r["recall"][0] + 1e-9]
        down = [r["id"] for r in rs if r["recall"][1] < r["recall"][0] - 1e-9]
        print(f"  {st}: Recall@10 {mean([r['recall'][0] for r in rs]):.3f} -> "
              f"{mean([r['recall'][1] for r in rs]):.3f}, Hit@10 {mean([r['hit'][0] for r in rs]):.3f}"
              f" -> {mean([r['hit'][1] for r in rs]):.3f}, MRR {mean([r['mrr'][0] for r in rs]):.3f} -> "
              f"{mean([r['mrr'][1] for r in rs]):.3f}; up {len(up)}, down {len(down)}")


def rrf() -> None:
    rows = load("probe_rrf.json")
    print("\n## 4. A second search on every question, ranked on the new query, RRF with the "
          "first 10 (probe_rrf.py)")
    for st in ("v0", "reworded"):
        rs = [r for r in rows if r["set"] == st]
        for key in ("first", "retry_only", "rrf"):
            print(f"  {st} {key}: Recall@10 {mean([r[key][0] for r in rs]):.3f}, "
                  f"Hit@10 {mean([r[key][1] for r in rs]):.3f}, MRR {mean([r[key][2] for r in rs]):.3f}")
        up = [r["id"] for r in rs if r["rrf"][0] > r["first"][0] + 1e-9]
        down = [r["id"] for r in rs if r["rrf"][0] < r["first"][0] - 1e-9]
        print(f"  {st} rrf: up {len(up)}, down {len(down)}")


def confirm() -> None:
    rows = load("probe_confirm.json")
    print("\n## 5. The concession test: stop | search, RRF, 3 runs (probe_confirm.py)")
    for run in (1, 2, 3):
        rs = [r for r in rows if r["run"] == run]
        for st in ("v0", "rephrased"):
            scored = [r for r in rs if r["set"] == st and "before" in r]
            deltas = [mean([r["after"][i] for r in scored]) - mean([r["before"][i] for r in scored])
                      for i in range(4)]
            stops = sum(r["verdict"] == "stop" for r in scored)
            print(f"  run {run} {st}: Recall/Hit/MRR/nDCG deltas "
                  + " / ".join(f"{d:+.3f}" for d in deltas)
                  + f"; answerable 'stop' {stops} of {len(scored)}")
        totals = [r["total_s"] for r in rs if r["set"] == "v0"]
        unanswerable = {r["id"]: r["verdict"] for r in rs if r["set"] == "v0" and not r["answerable"]}
        print(f"  run {run}: p95 total {p95(totals):.1f} s; unanswerable verdicts {unanswerable}")


if __name__ == "__main__":
    grader()
    rephrased()
    forced()
    rrf()
    confirm()
    sys.exit(0)
