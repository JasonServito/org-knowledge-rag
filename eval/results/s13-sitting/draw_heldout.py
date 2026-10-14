"""S13-R1 sitting, decision 2: draw the held-out KEP.

Pool: implemented KEPs (current version's kep.yaml `status: implemented`) in the corpus
(sig-release, sig-auth, sig-network) with a latest milestone of v1.25 or later, minus
the 4 KEPs the corpus gate traced (2572, 2579, 2799, 4858). Sorted by KEP number.
Seed: the S13-R1 contract commit's full SHA as an integer, so the draw can only have
happened after the rules were committed.
Usage: python3 eval/results/s13-sitting/draw_heldout.py <contract commit SHA>
"""

import random
import subprocess
import sys

SQL = """
select substr(d.canonical_id, 5)::int, v.metadata->>'title', v.metadata->>'latest-milestone'
from documents d join document_versions v on v.document_id = d.id
where d.source_type = 'kep' and v.valid_until_date is null
  and d.canonical_id ~ '^kep:[0-9]+$'
  and d.canonical_id not in ('kep:2572', 'kep:2579', 'kep:2799', 'kep:4858')
  and v.metadata->>'status' = 'implemented'
  and v.metadata->>'latest-milestone' ~ '^v1\\.[0-9]+$'
  and substr(v.metadata->>'latest-milestone', 4)::int >= 25
order by 1
"""

sha = sys.argv[1]
out = subprocess.run(
    ["docker", "compose", "exec", "-T", "db", "psql", "-U", "orgknow", "-d", "orgknow", "-At", "-F", "\t", "-c", SQL],
    check=True, capture_output=True, text=True,
).stdout
pool = [line.split("\t") for line in out.splitlines() if line]
print(f"seed: {sha} ({len(pool)} KEPs in the pool)")
for number, title, milestone in pool:
    print(f"  {number}\t{milestone}\t{title}")
number, title, milestone = random.Random(int(sha, 16)).choice(pool)
print(f"drawn: KEP-{number} ({milestone}): {title}")
