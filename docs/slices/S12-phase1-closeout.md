# S12: Phase 1 closeout

- **Status:** ✅
- **Blueprint stage:** Phase 1 closeout (§30.1); product spec AC1–AC8, must-have 10
- **Started:** 2026-10-12
- **Finished:** 2026-10-13

## Outcome

Every Phase 1 acceptance criterion (AC1–AC8) and must-have 10 has a recorded proof in an M1 report. Phase 1 closes with 3 stated exceptions (AC4 1 of 4, AC5 8 of 10, AC6 8 of 9), each with its measured cause. `POST /query` answers through the same pipeline as `orgknow ask`, with one Langfuse trace per request.

## Why now

- **AC4 is 1 of 4** (S11-R1 Step 0): q01's model-found pair summarizes the wrong disagreement; q08 (k03) and c01 (k04) aren't retrieved.
- **ADR-010 D4's switch rule fired:** with q01 read as a miss, a separate detector call was due. The S12-R1 sitting probed it (not adopted).
- **AC5 and AC6 have no answer-side check:** AC5 is proven on hits only (stale rate 0 of 100); AC6's definition was open (S09-R2).
- **Must-have 10 is half done:** Langfuse traces each `ask`, but there is no `/query` endpoint.
- **AC7's story isn't told:** the ablation table exists (`eval/results/ablation.md`), but the README has neither the table nor the narrative.

## Exit checks

- [x] AC5 and AC6 are scored on cited evidence for every saved run, free, by the rules decided in the S12-R1 sitting.
- [x] `POST /query` returns the same answer shape as `orgknow ask`, loads the reranker once per process, and leaves one Langfuse trace per request (rule-found conflicts logged when the answer call fails).
- [x] ADR-010 records the detector probe (not adopted); the product spec records AC4–AC6's results and definitions; `docs/evaluation.md` has the S12 section.
- [x] The README has the ablation table and a results narrative; `docs/architecture.md` matches the code.
- [x] The M1 report lists AC1–AC8 and must-have 10, each with its proof command and result, and the 3 stated exceptions with their causes.
- [x] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| AC5/AC6 answer-side checks on saved rows (summary, table) | A grading model for claim support or faithfulness |
| `POST /query`, reranker loaded once, Langfuse on that path, `make serve`, `uvicorn` | Auth, async jobs, deployment (S14–S15); Streamlit (S17's UI replaces any Phase 1 UI) |
| The detector probe's write-up (ADR-010 amendment) | Building the detector (judged precision 0.690 < 0.90); ADR-010 D4's stale-KEP rule (a rule finding can't match seed k02, a two-text conflict) |
| AC4 as a stated exception, with its causes and v1's gate wording | Amending AC4; retrieval changes for q08 or c01 (tuning on frozen v0) |
| README table and narrative, architecture doc, M1 report, retro | Any paid eval run; edits to golden set v0 or conflict set v0 (frozen, human-owned) |
| Triage items a–e (sitting Step 0) | Query rewriting, golden v1, conflict set v1 (proposed additions) |

## Metric to move

- **None by design:** the pipeline doesn't change. S12 adds two measurements (AC5, AC6) and an entry point (`/query`).
- AC5 and AC6 are scored on every saved run. Each rule was chosen because it separates a time-aware pipeline from the time-blind dense baseline (the negative control).

## Tasks

These mirror `docs/backlog.md`; details live here. The run contract pins each one. The sitting's first draft (a detector, a paid 3-run eval) was replaced after decision 1.

### S12-T1: AC5 and AC6 answer-side checks `[core]`

- **Goal:** score AC5 (every citation of a CURRENT answer valid at the latest release) and AC6 (at least one citation of a dated HISTORY answer inside the golden window) from saved eval rows, in the summary and the ablation table.
- **Done when:** the run contract's proof map for T1 is all ✅.
- **Deps:** none.

### S12-T2: `POST /query` with Langfuse `[commodity]`

- **Goal:** the API answers through the `ask` pipeline, with the reranker loaded once per process and one trace per request.
- **Done when:** the run contract's proof map for T2 is all ✅.
- **Deps:** none.

### S12-T3: Closeout docs and the M1 report `[commodity]`

- **Goal:** ADR-010 and ADR-004 amendments, spec notes, the S12 evaluation section, README, architecture doc, the M1 report, items a–e, the backlog.
- **Done when:** the run contract's proof map for T3 is all ✅.
- **Deps:** T1, T2.

### S12-T4: The S12 retro `[commodity]`

- **Goal:** `/slice-retro S12` as the run's last commit: slice brief, S12 ✅ and S13 🟨, the memory review.
- **Deps:** T3.

## Risks & unknowns

- **The AC5/AC6 rules were chosen in the sitting, on the same saved runs they score.** The negative control (dense 2 of 10 and 6 of 9 vs. final 8 of 10 and 8 of 9) is the guard. Golden v1 is the first out-of-sample check.
- **AC5 checks citation validity, not claim support:** no grader reads the answer. It goes on the Not verified list.
- **Concurrent API requests share one reranker:** fine for a local dev server; a known limit.
- **The three runs aren't three confirmations:** retrieval is deterministic, so they differ only in which hits the model cites.

## Decisions expected (ADRs)

- ADR-010 amendment: D4's detector probed in the S12-R1 sitting, not adopted (T3).
- ADR-004 amendment: `uvicorn` as the API server (T2).
- Product spec notes: AC4's stated exception and v1 wording, AC5/AC6 definitions and results (T3).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit.

### Run S12-R1: Phase 1 closeout

- **Status:** planned
- **Tasks:** T1, T2, T3, T4.
- **Goal (plain words):** add the two missing answer checks, serve the pipeline over HTTP, and write down how Phase 1 ends (3 stated exceptions, each with its cause), then close the slice.

#### Sitting evidence (2026-10-12)

The scripts and outputs are in `eval/results/s12-sitting/`; its `README.md` lists each one's command, cost and output.

- **The detector probe (ADR-010 D4's one-off comparison, run in the sitting):** Haiku 5.5 at effort low, on the same 10 hits as conflict run 1 (checked equal), 45 questions, 2 prompt wordings. Pass criteria were fixed before the run (`probe_detector.py`).

  | | Answer call (S10, 3 runs) | Detector A (neutral) | Detector B (+ out-of-date KEP status) |
  |---|---|---|---|
  | Model pairs | 13–14 | 58 | 79 |
  | Raw precision, model pairs | 0.71–0.92 | 0.707 (41 of 58) | 0.620 (49 of 79) |
  | Recall | 0.317–0.350 | 0.550 (33 of 60) | 0.583 (35 of 60) |
  | q01 summary check (3 calls) | fail ×3 | fail ×3 | pass ×3 |
  | Latency p50 / p95 | — | 4.24 / 5.77 s | 5.14 / 6.43 s |

  - B's 30 unmatched pairs, judged (`verdicts_B.md`): 3 real. Judged precision 0.690 (60 of 87), below the spec's 0.90. 19 of the 27 false pairs compare a claim line from a KEP version that isn't valid at the target with a later state.
  - Cost: US$0.099 (576,293 tokens in, 82,675 out).
- **AC4's search misses** (`probe_ranks.log`, free):
  - q08: KEP-2579's Implementation History (k03) is rank 10 in hybrid mode and rank 20 in rerank and authority modes. The reranker pushes it out.
  - c01: as routed (HISTORY, 1.30), no `versioning.md` text is among its 20 candidates. Only kep:1498 (a k04 second side) is.
  - S11's "no window" lead was a false match: without the window, ranks 1–2 are chunks 36376 and 36383, both "every four months"; the seed's "every three months" is chunk 36362.
- **AC5/AC6 readings** (`probe_ac56_control.log`, free; 10 CURRENT questions, 9 HISTORY questions with a golden window):

  | Reading | dense | hybrid | rerank | authority | conflict |
  |---|---|---|---|---|---|
  | AC5: every citation valid at 1.37 | 2, 2, 2 | 1, 3, 2 | 3, 3, 3 | 8, 8, 8 | 8, 8, 8 |
  | AC5: at least one valid at 1.37 | 9, 8, 9 | 8, 9, 9 | 10, 10, 10 | 10, 10, 10 | 10, 10, 10 |
  | AC6: at least one inside the exact window | 6, 6, 6 | 6, 6, 6 | 6, 6, 6 | 8, 8, 8 | 8, 8, 8 |
  | AC6: at least one inside, or labeled | 8, 8, 8 | 8, 8, 8 | 8, 8, 8 | 9, 9, 9 | 9, 9, 9 |
  | AC6: every citation within ±1 | 4, 5, 5 | 5, 5, 5 | 4, 4, 5 | 8, 8, 8 | 8, 8, 8 |
  | AC6: every citation inside the exact window | 0, 1, 1 | 1, 0, 0 | 1, 0, 2 | 1, 1, 1 | 3, 1, 1 |

  The chosen readings (rows 1 and 3) fail: AC5 q01, q16 (they cite older release notes); AC6 q02 (all its citations, its top label included, postdate "before 2021"). conflict-smoke: AC5 1 of 3, AC6 2 of 2.
- **Two devil's-advocate reviews:**
  - **The AC4 plan:** argued against amending AC4 to "retrieved seeds only" (S10-R2 had rejected it, so it would move the goalposts), and proposed the 2 safeguards adopted in decision 2.
  - **The AC5/AC6 definitions:** argued that the first picks were the most lenient readings, chosen on the runs they score, and proposed the negative control, which changed both recommendations.

#### Decisions (made in the sitting, 2026-10-12)

| # | Decision | Rejected | Why |
|---|---|---|---|
| Step 0 | Triage a–h: all kept (a–e into T3; f decided here; g into T2; h into T2) | Dropping any | Each is small and in S12's scope |
| Run shape | 1 run, 1 PR; split after T2 (code │ docs) only if the size alarm fires | 2 runs; 2 PRs up front | The developer's choice; PR 2 would depend on PR 1 anyway |
| Dev UI | FastAPI's built-in `/docs` page, plus the CLI and Langfuse; Streamlit → S17's sitting | Streamlit; a hand-written HTML page | S17 builds the real UI; 0 lines and 0 dependencies |
| Scope | The stale-KEP rule out; the detector comparison runs in the sitting as a probe | Build the rule; compare as the run's first step | A rule finding can't match k02 (`eval/conflicts.py` `matches`); probe before building (S11's lesson) |
| 1 | **No detector.** Judge B's 30 unmatched pairs first; judged precision 0.690 < 0.90 → not built | Build B (q01 fixed, precision unknown); build A (q01 unfixed); stop at the raw-precision fail | The spec's own threshold decides; the judging was chosen after the raw fail and is labeled so |
| 2 | **AC4 closes as a stated exception (1 of 4)**, with 2 safeguards: q08 reported as a reranker regression against hybrid mode; golden/conflict set v1's AC4 wording written now | Amend AC4 to retrieved seeds (still 1 of 2, and moves the goalposts); keep S12 open | No in-scope path moves it; a stated fail with measured causes beats a re-scoped pass |
| 3 | **AC5 = every citation of a CURRENT answer is valid at the latest release:** 8 of 10, a stated exception | At least one citation (10 of 10, but dense passes 8–9 of 10); a grader (out of scope) | It separates the systems (dense 2 → final 8 of 10) |
| 4 | **AC6 = at least one citation of a dated HISTORY answer inside the exact golden window** (S09's `in_window`, no slack), over the 9 questions with a golden window: 8 of 9, a stated exception | Label exception (rescues only q02; dense 8 of 9); every within ±1 (passes by construction); every exact (fails every system) | It separates the systems (dense 6 → final 8 of 9); history is often written later, so "every" punishes good sources |

**Claude's calls** (reversible):
- The sitting's scripts and outputs are committed verbatim in `eval/results/s12-sitting/` with a README (already under ruff's `extend-exclude`).
- AC6's population is the 9 questions with a golden window (S09's temporal-accuracy population). The spec's literal "naming a release or date" is 7 (not q12, q17), 6 of 7 by the same rule. The M1 report states both.
- The M1 report is `docs/m1-report.md`, with a slice-by-slice table (the backlog's "slice-brief consolidation").
- T2's interface, server and trace (pinned below).
- Paid calls in the run: the T2 demo only.

#### Pinned: T1 (AC5, AC6)

- **AC5, per golden question with mode CURRENT:** pass when the answer is `answered` and **every** citation has a release window that holds the latest release (from ≤ latest ≤ until, an open until counting as the latest). A refusal or an error row fails; the rule is per question.
- **AC6, per golden question with mode HISTORY and a golden window (`golden_window`):** pass when the answer is `answered` and **at least one** citation's release windows overlap the golden window by `metrics.in_window` (exact, no slack). A refusal or an error row fails.
- Unanswerable questions and the conflict set's new questions are in neither.
- **The latest release:** read from the releases table (`db.releases.list_releases`) by `run` and `resummarize`, never hardcoded; the summary records it. For every run saved so far it is 1.37.
- **The window and mode** come from the golden question, not the row (rows written before S09-T3 have no `release_window`).
- **Output:** `ac5` and `ac6` as pass/total in `summary.json` (None when no such question ran); two table columns "AC5" and "AC6" after "AC3", formatted like AC1–AC3 but as counts ("8 of 10"), since the rule is per question; `summary_line` adds them.
- **Old folders:** `make eval-resummarize` fills both for every saved run. The sitting checked that re-summarizing today adds only empty fields and commas, with no value changes. Commit the refreshed `summary.json` files and the table.

#### Pinned: T2 (`POST /query`)

- **Dependency:** `uvicorn` (runtime), pinned in `uv.lock`; an ADR-004 amendment (dated, "Rejected: no server, `TestClient` only, which can't serve a request").
- **`make serve`:** `uv run uvicorn --factory orgknow.api.app:create_app --host 127.0.0.1 --port 8000`.
- **One shared function:** the route → retrieve → rule conflicts → answer path (traced when Langfuse is on) moves from `cli.py` into one function that `ask` and the endpoint both call. The CLI's output and exit codes are unchanged; existing CLI tests pass unedited.
- **Startup (FastAPI lifespan):** settings, the embedder, the generator, the router, the Langfuse client and the reranker (in rerank, temporal and authority modes) are built once. `create_app` accepts them injected, for tests. Langfuse flushes at shutdown.
- **Request:** `POST /query` with `{"question": "..."}` (non-empty). **Response 200:** the same `Answer` JSON `orgknow ask` prints, `trace_id` included (None when tracing is off).
- **Errors:** an `ASK_ERRORS` failure → 502 `{"detail": <one line>}`, as the CLI's stderr line; database unreachable → 503; a bad body → FastAPI's 422. Keys and settings never appear in a response or a trace.
- **Per request:** one database connection; one trace named `ask`, as the CLI's.
- **Triage g:** when the answer call fails, the `generate` span still logs the rule-found conflicts (CLI and API alike).
- **Known limit, documented:** concurrent requests share one reranker.

#### Pinned: T3 (docs)

- **ADR-010 amendment (dated 2026-10-12, no decision changed except D4's outcome):** D4's switch rule fired (S11-R1 Step 0); the one-off comparison ran in the S12-R1 sitting; neither wording passed (A: q01 fails; B: judged precision 0.690); the detector is not adopted; the stale-KEP rule isn't built (a rule finding can't match k02). Revisit trigger: a detector design that passes judged precision ≥ 0.90 on conflict set v1.
- **ADR-004 amendment:** `uvicorn` (T2).
- **Product spec:**
  - Must-have 10: done (`POST /query`, `make serve`).
  - AC4 note: "1 of 4 at Phase 1's close: a stated exception (S12-R1 decision 2)", with the 3 causes. **v1's AC4 wording, written now:** "On the v1 seed conflict cases, fixed before any v1 result, every seed counts, search misses included. A seed is surfaced only when a flagged conflict matches its sides and its summary names the seed's fact."
  - AC5 note: the rule (decision 3), "8 of 10: a stated exception", "checks citation validity, not claim support".
  - AC6 note: the rule and population (decision 4), "8 of 9: a stated exception".
  - Each note says the rule was chosen in the S12-R1 sitting on S10's saved runs, with the negative control.
- **`docs/evaluation.md`:** a section "Phase 1 closeout (S12)" after "Corrective retrieval (S11)", before "Known limits": the detector probe (table above), the verdicts, AC4's causes, the AC5/AC6 negative control, every number copied from the committed logs or `make eval-table`. "Known limits": the reranker reload line changes (the API keeps it loaded).
- **README:**
  - The status line (now "pre-development") becomes "Phase 1 closed (M1) with 3 stated exceptions".
  - The ablation table, copied from `eval/results/ablation.md` at the run's commit.
  - A results narrative of at most ~25 lines: what each stage moved, and the 3 exceptions with their causes.
  - The API: `make serve`, a `curl` example, `/docs`.
- **`docs/architecture.md`:** the API entry point (replaces "There is no server entry point yet"), the shared pipeline function, AC5/AC6 in the eval.
- **`docs/m1-report.md`:** one row per AC1–AC8 and must-have 10: the criterion, the result, the proof command, its source (the run folder or log); the 3 exceptions with causes; a slice-by-slice table (S01–S12: what shipped, the metric it moved); a "Not verified" list (claim support, faithfulness, v0 tuned on).
- **Items a–e:**
  - a. `CLAUDE.md`: target pipeline step 4 becomes "Conflict detection → structured answer with citations, or `insufficient_evidence` (corrective retrieval tested and not adopted, ADR-011)"; the repo map's `agent/` line is removed.
  - b. "1 type cast for mypy" (S11 slice doc lines 97 and 224, S11 slice brief line 44): becomes "needs 1 type cast to pass mypy --strict (not in the committed spike)", as `docs/evaluation.md` already says.
  - c. ADR-011 amendment: line 6's "prints every number below" → 4 numbers (0.065, 0.035, ~1.5 questions, ~$0.0006) are computed from printed ones.
  - d. `docs/decisions/README.md`: every ADR row lists its amendments and changes (ADR-010: changed in S10-R2 and after S10-T8's run 1; amended in S11-R1 and S12-R1; ADR-011: amended in S12-R1; ADR-004 adds S12-R1).
  - e. Three auto-memory notes into the repo: the golden-set copy procedure → `CLAUDE.md` ("Stop and ask before…", the golden_set bullet); "core decisions only" and "track open questions" → `.claude/skills/plan-run/SKILL.md`. If auto mode blocks the `.claude/` edit, park it.
- **`docs/backlog.md`:**
  - S12's entry: slice doc pointer, T1–T4 ticked.
  - The ADR queue unchanged.
  - Proposed additions:
    - Detector A for conflict recall (0.33 → 0.55; judged precision unknown; test on conflict set v1).
    - q08's reranker regression (k03 rank 10 → 20).
    - c01's search miss: k04's in-window text isn't among its 20 candidates.
    - Freeze AC5/AC6 rules for golden v1.
    - Streamlit as a note for S17's sitting.
  - Remove the "S12 sitting: define AC6" and "Trace: log the rule-found conflicts…" items (done).
- **Glossary:** negative control; stated exception (only if an interviewer would use it: negative control yes, stated exception no).

#### Pinned: T4 (retro)

- `/slice-retro S12` as the run's last commit: `docs/learning/S12-phase1-closeout.md`, the slice doc's retro and exit checks, S12 ✅ and S13 🟨 in the backlog, the memory review.

#### Handoffs between tasks

- T1 and T2 are independent.
- T3 quotes T1's numbers only from `make eval-table` / the refreshed summaries, and the sitting's numbers only from the committed logs. It documents T2's interface from the code.
- T4 reads T3's docs and this contract.

#### Edge cases

- **AC5's "valid at the latest release"** when a window ends exactly at 1.37 (e.g. `changelog:1.37`): it holds 1.37, so it passes. An open window passes.
- **A CURRENT answer with 0 citations** can't be `answered` (AC1), so it fails as a refusal.
- **Error rows** (none in saved runs) fail AC5/AC6.
- **conflict-smoke** has 3 CURRENT and 2 dated HISTORY questions: 1 of 3 and 2 of 2.
- **A request while the database is down:** 503, not a traceback.
- **No Langfuse keys:** `/query` answers with `trace_id` null; the server logs "tracing off" once at startup.
- **The reranker at startup in dense or hybrid mode:** not loaded (as the CLI).

#### Files in scope

- Sitting commits: this slice doc, `eval/results/s12-sitting/` (scripts, outputs, logs, verdicts, README).
- T1: `src/orgknow/eval/checks.py` or `runner.py` (where the rules sit), `src/orgknow/eval/table.py`, `tests/unit/` (checks, table), `eval/results/*/summary.json`, `eval/results/ablation.md`.
- T2: `src/orgknow/api/app.py`, `src/orgknow/cli.py`, one new module for the shared function if needed, `src/orgknow/settings.py` (only if needed), `pyproject.toml`, `uv.lock`, `Makefile`, `tests/unit/test_api.py`, `tests/unit/test_cli.py` (new tests only), `tests/integration/test_api.py`, `docs/decisions/ADR-004-toolchain.md`.
- T3: `docs/decisions/ADR-010-conflict-detection.md`, `docs/decisions/ADR-011-corrective-retrieval.md`, `docs/decisions/README.md`, `docs/product-spec.md`, `docs/evaluation.md`, `README.md`, `docs/architecture.md`, `docs/m1-report.md`, `CLAUDE.md`, `.claude/skills/plan-run/SKILL.md`, `docs/slices/S11-corrective-retrieval.md`, `docs/learning/S11-corrective-retrieval.md`, `docs/backlog.md`, `docs/learning/glossary.md`, `.greptile/files.json` (if it lists docs).
- T4: `docs/learning/S12-phase1-closeout.md`, `docs/backlog.md`, this slice doc, the auto-memory review.

#### Proof map

| Task | "Done when" | Proof | Expected values from |
|---|---|---|---|
| T1 | AC5/AC6 rules correct at the edges (every vs. any; exact window; open window; window ending at the latest; refusal) | New unit tests, written first (red → green) | Hand-computed fixtures |
| T1 | Every saved run's AC5/AC6 | `make eval-resummarize && make eval-table`; compare each folder | `probe_ac56_control.log` (sitting script, independent of `src/`): dense 2/2/2 of 10 and 6/6/6 of 9; hybrid 1/3/2 and 6/6/6; rerank 3/3/3 and 6/6/6; authority 8/8/8 and 8/8/8; conflict 8/8/8 and 8/8/8; conflict-smoke 1 of 3 and 2 of 2 |
| T1 | No other summary value changes | `git diff eval/results/*/summary.json`: only the new fields (and the commas and empty fields the sitting saw) | The sitting's check |
| T2 | Same JSON as `ask`; reranker loaded once over 2 requests; 422, 502, 503; rule-found conflicts in the trace on a failed answer; no key in a response | Unit tests (`TestClient`, fakes, a counting reranker loader) | The CLI's existing output for the same fakes |
| T2 | Works against real Postgres | `make test-int` (`tests/integration/test_api.py`, fake paid clients) | — |
| T2 | CLI unchanged | Existing `tests/unit/test_cli.py` and `tests/integration/test_cli.py` pass unedited | — |
| T3 | Every number in the new docs | The reviewer compares each with its log or `make eval-table` | The committed logs |
| T3 | Each pinned item present | `grep -n` for each item's key phrase | This contract |
| All | `make check` green; `make test-int` green | Both | — |
| T4 | The retro's exit checks | `/slice-retro`'s checklist | This slice doc |

#### Break-it rules

- **T1, AC5:** change "every citation" to "any citation" → the mixed-citation unit test fails. Restore; `git diff` clean.
- **T1, AC6:** add ±1 release of slack → the window-boundary unit test fails. Restore.
- **T2:** load the reranker inside the request handler → the "loaded once over 2 requests" test fails. Restore.

#### Real-data demo

```bash
make eval-resummarize && make eval-table   # free: AC5/AC6 columns for every saved run
make serve                                 # in a second terminal
curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question": "What enforces pod security standards in-tree?"}'
```

- Paid: 1–2 such requests (router + answer, ~US$0.04 each).
- The trace is read back from Langfuse (v2 observations API, `/api/public/v2/observations?traceId=…`) and its id goes in the brief.
- Show that the second request skips the reranker load: the server log or the two latencies.

#### Bundle-level check

- `make check`, `make test-int` (Postgres checked at the run's start).
- `make eval-table` prints the AC5/AC6 columns, matching `probe_ac56_control.log`.
- `uv run python eval/results/s12-sitting/probe_ac56.py dense hybrid rerank authority conflict-smoke conflict` reproduces `probe_ac56_control.log`.
- The demo above.

#### PR plan

- 1 PR (`s12-r1-phase1-closeout`). If the size alarm fires when it opens (> ~30 files or > ~800 reviewable lines), split after T2: PR 1 = T1–T2 (code), PR 2 = T3–T4 (docs), stacked.
- Greptile: once, after the PR opens (it has code). Greptile: 17/50 at the sitting, 18/50 after.

#### Paid calls allowed

- **T2's demo only:** at most 3 `POST /query` requests, at most US$0.20 in all.
- Credit at sitting: US$9.06 (2026-10-12). The sitting's detector probe spent US$0.099: estimate **~US$8.96 left**, ~US$8.76 after the run.

## Retro (fill in at the end)

- **Shipped (with numbers):**
  - **S12-R1** (1 run, 4 tasks), split after T2 into 2 stacked PRs (code │ docs): the code alone is ~1,700 reviewable lines, over the ~800 alarm.
    - **Sitting evidence:** the detector probe (US$0.099), AC4's seed ranks and the AC5/AC6 readings (free), 2 devil's-advocate reviews; all in `eval/results/s12-sitting/`.
    - **T1:** AC5 and AC6 per golden question, in `summary.json` and 2 ablation-table columns. All 16 saved runs re-summarized; each matches `probe_ac56_control.log`; no earlier value changed.
    - **T2:** `POST /query` and `make serve` (uvicorn, ADR-004 amendment), through one pipeline function shared with `orgknow ask`.
      - Demo (2026-10-13, authority mode): 2 requests, HTTP 200, 12.0 s and 11.2 s, the reranker loaded once, 1 trace each.
    - **T3:** ADR-010 and ADR-011 amendments, the ADR index; the spec's must-have 10 and AC4–AC6 notes; `docs/evaluation.md`'s S12 section; the README's table, narrative and API section.
      - Also `docs/architecture.md`, `docs/m1-report.md`, triage items a–e (3 memory notes into the repo), 1 glossary term.
    - **T4:** this retro and the slice brief.
  - **Result:** Phase 1 closes (M1) with 3 stated exceptions: AC4 1 of 4, AC5 8 of 10, AC6 8 of 9 (the dense baseline: 2 of 10, 6 of 9).
  - **Metrics:** none moved, by design; the final row stays Recall@10 0.552, MRR 0.813, p95 16.3 s, $0.0378 per question.
  - **Tests:** 896 unit (853 at S11's close), 189 integration.
  - **Reviews:** 0 must-fix in T1 and T2; 2 in T3 (a "rank 40" wording the log contradicts; ADR status lines edited in place), both fixed.
  - **Paid in S12:** ~US$0.17 (the sitting's probe US$0.099, the T2 demo ~US$0.07). Credit ~US$8.89 left. Greptile 17/50 before the PRs.
- **Surprises:**
  - **Detector B fixed q01 but flagged false conflicts:** it passed q01's summary check 3 of 3 times, but 19 of its 27 false flags compared a KEP claim not valid at the target release with a later state.
  - **S11's c01 lead was a false match:** the texts found with no window (chunks 36376, 36383) say "every four months"; the seed's "every three months" is chunk 36362.
  - **The reranker drops q08's source:** KEP-2579's Implementation History is rank 10 in hybrid mode and rank 20 after the reranker.
  - **The first AC5/AC6 picks were the lenient readings:** "at least one valid citation" passes the time-blind dense baseline 8–9 of 10. The negative control changed both picks.
  - **"Every citation inside the exact window" fails every system** (0–3 of 9): history is often written down later.
  - **The router call isn't in the trace** (no router span), so the demo's router cost (~US$0.008) is an estimate.
- **What didn't work / negative results:**
  - **A separate detector call (ADR-010 D4):** wording A failed q01's check 3 of 3 times; wording B's raw precision was 0.620, judged 0.690, under the spec's 0.90. Not adopted.
  - **Detector A's recall gain (0.33 → 0.55)** has an unknown judged precision: a proposed addition, for conflict set v1.
  - **The stale-KEP rule:** not built; a rule-found conflict can't match k02, a two-text conflict.
  - **AC4 stays at 1 of 4:** no in-scope change reaches q08 or c01 without tuning on frozen v0.
- **Do differently next slice:**
  - Fix a new metric's rule and its negative control before seeing any score; S12's AC5/AC6 rules were picked on the runs they score. S13's decision-chain completeness metric is next.
  - Check a lead down to the chunk text before handing it on: S11's c01 lead found the right page but the wrong text.
  - Estimate each task's reviewable lines in the sitting: moving the ask pipeline out of `cli.py` (T2) made the code alone ~1,700 lines.
  - After moving code, search the old module's name in docstrings: 3 stale ones were parked (2 still say "the CLI").
- **Slice brief:** `docs/learning/S12-phase1-closeout.md`
