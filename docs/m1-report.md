# M1 report: Phase 1 closeout

- **Written:** 2026-10-13, in S12-R1 (the decisions: the S12-R1 sitting, 2026-10-12).
- **Verdict:** Phase 1 is closed (milestone M1) with 3 stated exceptions: AC4, AC5 and AC6.
- **Final pipeline:** `authority` retrieval plus conflict detection (the ablation table's `conflict` row): hybrid search, the reranker, the time filter and authority weights, the 2 conflict rules and the answer model's conflict pairs.
- **Test set:** golden set v0 (43 questions: 36 answerable, 7 unanswerable; frozen) and conflict set v0 (62 conflicts, 4 seed cases).

A **stated exception** is a criterion that fails at Phase 1's close, recorded with its measured cause instead of being re-scoped until it passes.

## Acceptance criteria and must-have 10

Results are the final pipeline's 3 runs (`eval/results/conflict-20261012T170000Z`, `-171009Z`, `-171932Z`) unless the row says otherwise. Every "free" command reads saved results or the database and makes no paid call.

| # | Criterion (short) | Result | Proof command (free unless marked) | Source |
|---|---|---|---|---|
| AC1 | Every answered response has ≥ 1 citation, each resolving to a stored chunk with URL, release, source type and tier | **Pass:** 36 of 36 in each run; 100% in every ablation row | `make eval-table` (AC1 column) | The 3 runs' `summary.json` |
| AC2 | 0 fabricated citations | **Pass:** 43 of 43 in each run | `make eval-table` (AC2) | The same |
| AC3 | Every unanswerable question gets `insufficient_evidence` with a reason | **Pass:** 7 of 7 in each run | `make eval-table` (AC3) | The same |
| AC4 | On the 4 seed conflict cases, the answer surfaces the conflict | **Stated exception: 1 of 4.** 2 of 4 by matching; q01's summary names the wrong disagreement (S11-R1 Step 0) | `make eval-table` (AC4: 0.500 by matching); `HF_HUB_OFFLINE=1 make eval-conflicts` (seeds retrieved: 2 of 4); `uv run python eval/results/s12-sitting/probe_ranks.py` | The 3 runs; `docs/evaluation.md` ("The S10 eval", "Phase 1 closeout (S12)"); `eval/results/s12-sitting/probe_ranks.log` |
| AC5 | CURRENT answers: every citation valid at the latest release (rule: S12-R1 decision 3) | **Stated exception: 8 of 10** in each run (q01, q16 fail). Dense baseline: 2 of 10 | `make eval-table` (AC5); independently, `uv run python eval/results/s12-sitting/probe_ac56.py dense hybrid rerank authority conflict-smoke conflict` | Every run's `summary.json`; `eval/results/s12-sitting/probe_ac56_control.log` |
| AC6 | Dated HISTORY answers: at least one citation inside the exact golden window (rule: S12-R1 decision 4) | **Stated exception: 8 of 9** in each run (q02 fails). The criterion's literal population (naming a release or date, 7 questions): 6 of 7. Dense baseline: 6 of 9 | `make eval-table` (AC6); the same probe | The same |
| AC7 | The ablation table covers dense → +lexical/RRF → +rerank → +temporal/authority → +conflict → +corrective; every kept stage improves its target metric | **Pass.** Each kept stage passed the improvement rule on its target: hybrid MRR +0.060; rerank Recall@10 +0.134; authority stale rate −0.380, temporal accuracy +0.167, authority selection +0.444; conflict recall 0 → 0.333. +corrective: tested, not adopted (ADR-011) | `make eval-table`; `RETRIEVAL_MODE=<mode> make eval-retrieval` for each mode's retrieval line | `eval/results/ablation.md` (in the README); `docs/evaluation.md`, each stage's "improvement rule" table |
| AC8 | Re-ingesting gives identical version counts and hashes; `make eval` runs end to end locally | **Pass.** Two from-empty ingests printed byte-identical reports, fingerprint `sha256:458effad…` (S05-T8). On 2026-10-13 the dev database (the one the evals read) prints the same fingerprint. 16 saved eval runs, 0 errors | `make ingest-report` (prints `Fingerprint: sha256:458effad5a650bc761e49eff6c2528f9e7dff27a0b00c1a2a83aaec642e01271`); `make eval-table` (Errors column: 0 in every row); `make eval-smoke` (paid) | `docs/slices/S05-stage1-subset-ingestion.md` (T8); the 16 run folders in `eval/results/` |
| Must-have 10 | A FastAPI `/query` endpoint and Langfuse traces | **Done (S12-T2).** `POST /query` returns the JSON `orgknow ask` prints; the reranker loads once per process; one Langfuse trace per request | `make check` (`tests/unit/test_api.py`); `make test-int` (`tests/integration/test_api.py`); the demo below (paid, ~US$0.07) | The S12-T2 demo, run by the main session on 2026-10-13 |

**Must-have 10's demo (2026-10-13, authority mode):** `make serve`, then 2 requests, each `curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' -d '{"question": "What enforces pod security standards in-tree?"}'`.

- Both returned HTTP 200, `answer_status` "answered", with 9 evidence items each, in 12.0 s and 11.2 s.
- **The reranker loaded once:** the server log has one "Loading weights … 201/201" line at startup and none after. Each request logged `Route: CURRENT, current text only` and `"POST /query HTTP/1.1" 200 OK`.
- **One trace per request,** read back through Langfuse's v2 observations API: `bcbc5446fd9cd3d37ff5d0a46dce9c40` and `31ef1a9c7823a6ba95f3135745ba7e5f`, each with the spans ask → retrieve → generate → validate.
- 0 secret values in the responses or the traces.
- **Spent:** about US$0.07 (the answer calls US$0.0578 from the traces' token usage at `GENERATION_PRICE_*`, plus ~US$0.008 for the 2 router calls, estimated).

## Phase 1 thresholds (product spec) on the final pipeline

From the ablation table's `conflict` row (3-run mean, with its range), except where noted.

| Metric | Threshold | Final pipeline | Result |
|---|---|---|---|
| Recall@10 | ≥ 0.46 | 0.552 | Pass |
| MRR | ≥ 0.69 | 0.813 | Pass |
| nDCG@10 | ≥ 0.45 | 0.535 | Pass |
| Hit@10 | ≥ 0.944 | 1.000 | Pass |
| False refusals | ≤ the baseline's 2–3 of 36 | 0 of 36 in each run (`docs/evaluation.md`) | Pass |
| p95 latency | ≤ 23 s | 16.3 s (14.9–18.7) | Pass |
| Cost per question | ≤ $0.06 | $0.0378 | Pass |
| Stale-result rate | ≤ 0.01 | 0.000 | Pass |
| Temporal accuracy | ≥ 0.51 | 0.522 | Pass |
| Authority-selection accuracy | ≥ 0.88 | 1.000 | Pass |
| Router accuracy | ≥ 0.90 | 0.972 (35 of 36) | Pass |
| Conflict precision, judged | ≥ 0.90 | 0.955–1.000 (raw 0.878, 0.818–0.952; `docs/evaluation.md`) | Pass |
| Conflict recall | ≥ 0.30 | 0.333 (0.317–0.350) | Pass |
| AC4 | 4 of 4 | 1 of 4 | Stated exception |

- **The eval's latency leaves out the question embedding and the router call,** since both are stored (`docs/evaluation.md`, "Known limits"). With the router's p95 (4.27 s): 16.3 + 4.27 = 20.6 s, under 23 s. Adding two p95s overstates it; the embedding's time isn't measured.

## The 3 stated exceptions

Decided in the S12-R1 sitting (decisions 2–4). Each failure's cause was measured, free, from the saved runs and the stored vectors (`eval/results/s12-sitting/`).

- **AC4: 1 of 4 seed conflict cases surfaced.**
  - q01 (KEP-2572's out-of-date status): the answer flags a pair that matches the seed's sides, but its summary is about the cadence ("4 times per year"), not the KEP's status. A separate detector call that fixed it (wording B, 3 of 3) had judged precision 0.690, below the spec's 0.90, so it wasn't adopted (ADR-010, amendment 2026-10-12).
  - q08 (KEP-2579's beta date): a search miss. Its text is rank 10 in hybrid mode and rank 20 after the reranker: the reranker pushes it out.
  - c01 (`versioning.md`'s "every three months"): a search miss. As routed (HISTORY, 1.30), no `versioning.md` text is among its 20 candidates.
  - Golden/conflict set v1's AC4 wording is fixed now, before any v1 result (product spec, AC4 note).
- **AC5: 8 of 10 CURRENT answers cite only text valid at 1.37.** q01 and q16 also cite older release notes. The rule separates the systems: dense 2 of 10, the final pipeline 8 of 10.
- **AC6: 8 of 9 dated HISTORY answers cite text inside the asked-for window.** q02's citations, its top label included, all postdate "before 2021". Dense 6 of 9, the final pipeline 8 of 9.

## Slice by slice

| Slice | What shipped | The metric it moved |
|---|---|---|
| S01 Repo foundation | The `make` and CI loop, Postgres 18 + pgvector, Alembic, `/health` and `/ready` | None by design: a fresh clone runs green locally and in CI |
| S02 Corpus spike | The corpus manifest, 77 pinned commit SHAs, 6 throwaway measurement scripts | 12 rules in ADR-002 and ADR-003 changed on the evidence |
| S03 Domain model | 6 tables, 15 rules (12 enforced by the database), 10 data-access functions, the releases seed | None by design: each rule has a test |
| S04 First vertical slice | Ingest, chunk, embed and `orgknow ask` over SIG Auth docs 1.24–1.37 and KEP-2579; citation check; Langfuse | Seeds #6–#10: 3 pass, 2 partial, 0 fail |
| S05 Subset ingestion | The full manifest: 1,168 documents, 2,882 versions, 48,273 chunks, 21,552 vectors | Two from-empty ingests identical (AC8, first part) |
| S06 Eval harness | Golden set v0 (43 questions, 184 labels), `make eval`, the ablation table | The dense baseline: Recall@10 0.384, MRR 0.614 |
| S07 Hybrid retrieval | Postgres full-text search fused with dense search by RRF | MRR 0.614 → 0.675 |
| S08 Reranking | A local cross-encoder (`BAAI/bge-reranker-base`) on CPU | Recall@10 0.382 → 0.516 |
| S09 Temporal and authority | The query router, the time filter, the observed lifecycle, authority tiers and weights | Stale rate 0.380 → 0.000; temporal accuracy 0.356 → 0.522; authority selection 5 → 9 of 9 |
| S10 Conflict detection | `conflicts[]` in every answer (2 code rules, the model's pairs), conflict set v0 | Conflict recall 0 → 0.333; judged precision 0.955–1.000; AC4 1 of 4 |
| S11 Corrective retrieval | 5 sitting probes; not adopted (ADR-011) | None: probe 5's hard-set Recall@10 moved −0.006, +0.008 and −0.007 (needed ≥ +0.03) |
| S12 Phase 1 closeout | AC5 and AC6 checks, `POST /query`, the detector probe (not adopted), this report | AC5 8 of 10 and AC6 8 of 9 measured (dense: 2 of 10, 6 of 9) |

## Not verified

- **Claim support:** AC5 and AC6 check each citation's release windows, not whether the cited text supports the answer's claims. No grader reads the answer.
- **Faithfulness:** no grading model scores it, so it has no threshold (product spec).
- **v0 was tuned on, so it isn't a clean test:**
  - Hybrid: about 30 retrieval configurations were tried on it.
  - Rerank: about 9 setups, and Recall@10 was named the target after they were seen.
  - Authority: the filter's ±1 release slack and the weights were chosen on it.
  - AC5 and AC6: the rules were chosen on the runs they score; the negative control is the only guard.
  - Golden set v1 is the clean test of all of these.
- **Label coverage:** the developer spot-checked 6 of v0's 43 questions; Claude checked the rest. The conflict set's 3 labeling passes split 0.526 of the time, so conflict precision is reported raw and judged.
- **The 3 runs aren't 3 confirmations:** retrieval repeats exactly, so they differ only in the answer model's choices.
- **`POST /query` under load:** concurrent requests share one reranker; tested with 2 requests in a row only.
- **Server sizing:** on 2 CPUs the projected answer p95 is over the 23 s ceiling in 2 of 3 runs (S08's projection; S15 decides).

## Reproduce

Free, after `make up`, from the repo root:

```bash
make eval-table                       # the ablation table, from the 16 saved runs
HF_HUB_OFFLINE=1 RETRIEVAL_MODE=authority make eval-retrieval   # the final retrieval line
HF_HUB_OFFLINE=1 make eval-conflicts  # the conflict set: reachable conflicts, seeds retrieved
make ingest-report                    # the database fingerprint (AC8)
uv run python eval/results/s12-sitting/probe_ac56.py dense hybrid rerank authority conflict-smoke conflict
```
