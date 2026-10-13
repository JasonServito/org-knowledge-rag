"""S12-R1 sitting (scratch, free): print every detector flag of one variant (its 45 first calls)
that matches no conflict of its question in conflict set v0, with both chunks' texts, for
Claude's verdict (judged precision, as in S10-T8). Hits come from conflict run 1 (equal to the
probe's, checked in probe_detector.py). Usage: uv run python eval/results/s12-sitting/probe_unmatched.py B"""

import json
import sys
from types import SimpleNamespace

import psycopg

from orgknow.eval import runner
from orgknow.eval.conflicts import matches
from orgknow.generation.conflicts import Conflict
from orgknow.settings import Settings

variant = sys.argv[1]
s = Settings()
probe = json.load(open("eval/results/s12-sitting/probe_detector.json"))
run1 = "eval/results/conflict-20261012T170000Z"
hits = {}
for name in ("questions.jsonl", "conflict_questions.jsonl"):
    for line in open(f"{run1}/{name}"):
        row = json.loads(line)
        hits[row["id"]] = [SimpleNamespace(chunk_id=h["chunk_id"], canonical_id=h["canonical_id"],
                                           heading_path=h["heading_path"]) for h in row["hits"]]
calls = [c for c in probe["calls"] if c["variant"] == variant][:45]
with psycopg.connect(s.database_url) as conn:
    golden, _ = runner.check_golden(conn, s.eval_golden_path)
    cset = runner.check_conflicts(conn, golden, s.eval_conflicts_path)
    n = 0
    for call in calls:
        mine = [c for c in cset.conflicts if c.question == call["id"]]
        for k in call["kept"]:
            flag = Conflict(**k)
            if any(matches(flag, c, hits[call["id"]]) for c in mine):
                continue
            n += 1
            print(f"\n######## U{n} {call['id']} {flag.chunk_ids} {flag.kind} {flag.resolution}")
            print(f"SUMMARY: {flag.summary}")
            for cid in flag.chunk_ids:
                doc, path, text = conn.execute(
                    "select d.canonical_id, c.heading_path, c.text from chunks c "
                    "join document_versions v on v.id = c.document_version_id join documents d on d.id = v.document_id "
                    "where c.id = %s", (cid,)).fetchone()
                body = text.split("\n\n", 1)[-1]
                print(f"--- {cid} {doc} | {' > '.join(path)}\n{body[:1400]}")
    print(f"\nUNMATCHED: {n}")
