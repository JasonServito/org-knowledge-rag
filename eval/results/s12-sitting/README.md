# S12-R1 sitting evidence (2026-10-12)

The probes behind the S12-R1 sitting's decisions:
- ADR-010 D4's detector is not adopted.
- AC4 closes as a stated exception.
- AC5 and AC6 get their definitions.

These are scratch scripts written during the sitting and committed verbatim, with their outputs. They import `orgknow` internals as of the S12-R1 contract commit, are never imported by `src/`, and are excluded from ruff (`pyproject.toml`).

Run from the repo root, with `make up`. The scripts that retrieve also need the reranker cached and `HF_HUB_OFFLINE=1`.

| Script and command | Paid | Output | What it shows |
|---|---|---|---|
| `uv run python -u eval/results/s12-sitting/probe_detector.py eval/results/s12-sitting/probe_detector.json` | Haiku 5.5, US$0.099 | `probe_detector.json`, `probe_detector.log` | ADR-010 D4's "one-off comparison": a separate detector call on v0's 43 questions + c01, c02, in 2 prompt wordings (A neutral, B + out-of-date KEP status). Scored against conflict set v0; q01 asked 3 times each. Its hits are checked equal to conflict run 1's |
| `uv run python eval/results/s12-sitting/probe_unmatched.py B` | no | `probe_unmatched_B.log` | B's 30 flags that match no conflict in the set, with both chunks' texts |
| (Claude's reading of the above) | no | `verdicts_B.md` | The verdict on each of the 30: 3 real; judged precision 0.690 |
| `uv run python eval/results/s12-sitting/probe_ranks.py` | no | `probe_ranks.log` | Where seeds k03 (q08) and k04 (c01) rank in the top 40: k03 is rank 10 in hybrid mode, 20 after the reranker; k04's in-window text isn't among c01's 20 candidates |
| `uv run python eval/results/s12-sitting/probe_ac56.py` | no | `probe_ac56.log` | AC5 and AC6 readings on S10's 3 conflict runs |
| `uv run python eval/results/s12-sitting/probe_ac56.py dense hybrid rerank authority conflict-smoke conflict` | no | `probe_ac56_control.log` | The same readings on every saved run: the negative control (a reading the time-blind dense baseline passes proves nothing) |

- The pass criteria for the detector probe are in `probe_detector.py`'s docstring, fixed before it ran. Neither wording passed both.
- `probe_detector.log` is the script's stdout, with the reranker's progress bars and uv's build lines removed.
- The two devil's-advocate reviews (the AC4 plan; the AC5/AC6 definitions) are summarized in the S12 slice doc's run contract.
- **Total spent in the sitting:** US$0.099 (the detector probe). Everything else is free.
