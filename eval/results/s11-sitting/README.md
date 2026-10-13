# S11-R1 sitting evidence (2026-10-12)

The probes behind ADR-011 (corrective retrieval: not adopted). Scratch scripts written during the sitting and committed verbatim, with their raw outputs. They import `orgknow` internals as of the S11-R1 contract commit, are never imported by `src/`, and are excluded from ruff (`pyproject.toml`).

**Re-print every number, free:**

```bash
uv run python eval/results/s11-sitting/summarize.py
```

**Re-run a probe** (from the repo root, with `make up` and the reranker cached; `HF_HUB_OFFLINE=1`). The paid ones need `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY`, and their model-written queries differ from run to run.

| Probe | Script and command | Paid | Output | What it shows |
|---|---|---|---|---|
| — | `uv run python eval/results/s11-sitting/probe_relax.py` | no | `probe_relax.log` | q08 and c01 under every mode with no window: seed sides in the top 10 |
| — | `uv run python eval/results/s11-sitting/probe_c01.py` | no | `probe_c01.log` | c01's top 10 as routed and with no window; k04's sides |
| 1 | `uv run python eval/results/s11-sitting/probe_grader.py eval/results/s11-sitting/probe_grader.json` | Haiku ~US$0.03, Voyage | `probe_grader.json`, `.log` | The Haiku grader on v0's 45 questions; the 2 retries, scored against the labels and the conflict set |
| — | `uv run python eval/results/s11-sitting/probe_two.py eval/results/s11-sitting/probe_grader.json` | Voyage | `probe_two.log` | c01's and q48's merged top 10 after their retries |
| 2 | `uv run python eval/results/s11-sitting/probe_reworded.py eval/results/s11-sitting/probe_reworded.json` | router ~US$0.15, Haiku ~US$0.02, Voyage | `probe_reworded.json`, `.log` | The rephrased set (`eval/candidates/router-rewording-v0.yaml`): first search vs. v0 wording, the grader, 3 retry variants |
| 3 | `uv run python eval/results/s11-sitting/probe_forced.py eval/results/s11-sitting/probe_forced.json eval/results/s11-sitting/probe_reworded.json` | Haiku ~US$0.04, Voyage | `probe_forced.json`, `.log` | A second search on every question, new texts scored against the original question |
| — | `uv run python eval/results/s11-sitting/probe_look.py eval/results/s11-sitting` | Voyage | `probe_look.log` | What displaced the labeled hits in v0 q34 and rephrased q31 |
| — | `uv run python eval/results/s11-sitting/probe_pool.py eval/results/s11-sitting` | Voyage | `probe_pool.log` | The devil's advocate's candidate-pool test (q08, q31); k04's reachability for c01 with no window |
| 4 | `uv run python eval/results/s11-sitting/probe_rrf.py eval/results/s11-sitting` | Voyage | `probe_rrf.json`, `.log` | A second search on every question, ranked on its own query, RRF with the first 10 |
| 5 | `uv run python eval/results/s11-sitting/probe_confirm.py eval/results/s11-sitting` | Haiku ~US$0.15, Voyage | `probe_confirm.json`, `.log` | The concession test: stop / search + RRF, 3 runs, 4 checks fixed before the runs |
| — | `uv run --no-project --with langgraph==1.2.15 python graph.py` and `python plain.py`, in `spike/` | no | (printed) | The same flow on fakes with LangGraph (82 lines) and as a plain loop (30 lines) |

- `probe_reworded_lib.py` is `probe_reworded.py`'s `merged()` with its imports, for `probe_look.py`.
- Logs are the scripts' stdout with the reranker's progress bars removed.
- The small probes without a probe number were re-run after the sitting's main probes, so their logs could be saved; their output matched what the sitting saw.
- Total spent in the sitting: ~US$0.40 (Haiku US$0.24, router US$0.15, Voyage under US$0.01).
