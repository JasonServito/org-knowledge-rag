"""S13-R1 sitting: PR #2567's Prow commands and approvals, in time order.

Shows which post decision 1's rule cites: the last `/approve` before the merge
(not the last Prow command, which is `/hold cancel`).
Usage: python prow_order.py <dir from fetch_items.sh>
"""

import json
import re
import sys
from pathlib import Path

from expected_posts import load

d = Path(sys.argv[1])
cmd = re.compile(r"^/(?:lgtm|approve|hold)[^\r\n]*", re.M)
events = [(c["created_at"], c["user"]["login"], "comment", cmd.findall(c["body"]))
          for c in load(d / "pr-2567-comments.json") if cmd.search(c["body"])]
events += [(r["submitted_at"], r["user"]["login"], "review:" + r["state"], cmd.findall(r["body"] or ""))
           for r in load(d / "pr-2567-reviews-all.json")
           if r["state"] == "APPROVED" or cmd.search(r["body"] or "")]
for event in sorted(events):
    print(*event)
print("merged_at", json.loads((d / "pr-2567.json").read_text())["merged_at"])
