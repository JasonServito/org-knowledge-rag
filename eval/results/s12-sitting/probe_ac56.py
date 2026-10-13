"""S12-R1 sitting (scratch, free): AC5 and AC6 readings on S10's 3 saved conflict runs.
AC5 over the 10 CURRENT questions, AC6 over the 9 HISTORY questions with a golden release window.
A citation is "valid at" a release when one of its release windows holds it (ADR-003's "valid at the
latest release"; the latest is 1.37). Labels match by document + heading-path prefix (ADR-007 D2).
Usage: uv run python eval/results/s12-sitting/probe_ac56.py [PIPELINE ...] (default: conflict).
The window is the golden one (`runner.golden_window`), so runs saved before S09-T3 score too."""

import sys

import glob
import json

import psycopg

from orgknow.eval import runner
from orgknow.eval.golden import label_matches
from orgknow.settings import Settings

LATEST = 37


def minor(release):
    return None if release is None else int(release.split(".")[1])


def overlaps(evidence, lo, hi):
    return any(minor(s) <= hi and (LATEST if u is None else minor(u)) >= lo
               for s, u in evidence["release_windows"])


def labeled(question, evidence):
    path = [] if evidence["section"] is None else evidence["section"].split(" > ")
    return any(label_matches(label, evidence["document"], path) for label in question.labels)


s = Settings()
with psycopg.connect(s.database_url) as conn:
    golden, _ = runner.check_golden(conn, s.eval_golden_path)
questions = {q.id: q for q in golden.questions}
for path in [p for name in (sys.argv[1:] or ["conflict"]) for p in sorted(glob.glob(f"eval/results/{name}-2*/questions.jsonl"))]:
    rows = [json.loads(line) for line in open(path)]
    print(f"== {path.split('/')[2]}")
    ac5 = {"anchor": [], "every": []}
    ac6 = {"anchor": [], "anchor_or_label": [], "every": [], "every_or_label": [], "every_pm1": []}
    for r in rows:
        a = r["answer"]
        answered = a is not None and a["answer_status"] == "answered"
        cites = a["evidence"] if answered else []
        q = questions[r["id"]]
        window = runner.golden_window(q)
        if q.mode == "CURRENT":
            ac5["anchor"].append((r["id"], answered and any(overlaps(e, LATEST, LATEST) for e in cites)))
            ac5["every"].append((r["id"], answered and all(overlaps(e, LATEST, LATEST) for e in cites)))
        if q.mode == "HISTORY" and window:
            lo, hi = window
            lo, hi = (0 if lo is None else lo), (LATEST if hi is None else hi)
            inside = [overlaps(e, lo, hi) for e in cites]
            near = [overlaps(e, lo - 1, hi + 1) for e in cites]
            lab = [labeled(q, e) for e in cites]
            ac6["anchor"].append((r["id"], answered and any(inside)))
            ac6["anchor_or_label"].append((r["id"], answered and any(i or l for i, l in zip(inside, lab))))
            ac6["every"].append((r["id"], answered and all(inside)))
            ac6["every_or_label"].append((r["id"], answered and all(i or l for i, l in zip(inside, lab))))
            ac6["every_pm1"].append((r["id"], answered and all(near)))
    for name, results in [*(("AC5 " + k, v) for k, v in ac5.items()), *(("AC6 " + k, v) for k, v in ac6.items())]:
        failed = [qid for qid, ok in results if not ok]
        print(f"  {name:22} {len(results) - len(failed)} of {len(results)}" + (f"  fail: {' '.join(failed)}" if failed else ""))
