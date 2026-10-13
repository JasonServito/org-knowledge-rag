# S11: Corrective agentic retrieval

- **Status:** 🟨
- **Blueprint stage:** Stage 8 (agentic orchestration: §17; trajectory metrics: §19.2; trace fields: §20)
- **Started:** 2026-10-12
- **Finished:**

## Outcome

Corrective retrieval is tested and **not adopted** (ADR-011): the S11-R1 sitting's probes show no grader that can tell thin evidence from enough, and no second-search design that passes the keep rule fixed before its test. The evidence re-runs from `eval/results/s11-sitting/`, and `docs/evaluation.md` says why.

## Why now

- **Search gets one try.** When the 10 results miss, the answer model can only answer from them or refuse. c01 ("In Kubernetes 1.30, how long was a minor release supported?") gets 7 release-note chunks in its top 10, and the model refused in 2 of S10's 3 runs.
- **It's the last ablation step** (AC7): dense → +lexical/RRF → +rerank → +temporal/authority → +conflict → **+corrective**.
- **Spec must-have 8:** bounded LangGraph corrective retrieval (≤ 3 iterations), kept only if it measurably helps.
- **AC4's search misses were S11's** (S10-R2 decision 3): k03 (q08) and k04 (c01) aren't retrieved in authority mode.

## Exit checks

- [ ] ADR-011 (corrective retrieval: not adopted) is Accepted.
- [ ] The sitting's probes, raw outputs and `summarize.py` are committed; `summarize.py` prints every number in the write-up.
- [ ] `docs/evaluation.md` has the S11 section; the product spec's must-have 8 and AC7 say the stage was tested and not adopted.
- [ ] AC4's open seeds have owners in the backlog's S12 (S11-R1 decisions 1 and 6).
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| ADR-011 and its sitting evidence (5 probes, ~US$0.40) | A grader, a second search, a LangGraph graph, or any change to `src/` |
| The S11 write-up, the spec's must-have 8 and AC7 notes | A 3-run paid eval of a corrective step |
| ADR-006 and ADR-010 cross-references to ADR-011 | ADR-010 D4's fallbacks (S12, decision 1); AC4's q08 and c01 (S12's sitting, decision 6) |
| Backlog: S12's AC4 items; proposed additions from the sitting | Golden or conflict set changes (both frozen); Jev (dropped) |
| The retro | Query rewriting for informal wording (a proposed addition) |

## Metric to move

- **None adopted.** The sitting measured the candidates on v0 and on the rephrased set (S09's 36 blind rewordings of v0's answerable questions, v0's labels): Recall@10, Hit@10, MRR, nDCG@10, the grader's verdicts, p95 and cost (ADR-011, "Sitting evidence").
- **The keep rule a revisit must pass** is ADR-011 D2 (S11-R1 decision 5): every run of 3 passes.

## Tasks

These mirror `docs/backlog.md`; details live here. The sitting's first draft planned a grader, a retry step, a graph, trajectory metrics and a paid eval (T2–T6); decision 3 replaced them with the tasks below.

### S11-T1: ADR-011 corrective retrieval `[core]` ✅

- **Goal:** decide in the R1 sitting whether and how corrective retrieval enters the pipeline.
- **Status:** done in the S11-R1 sitting (2026-10-12): not adopted. ADR-011 is in the run contract commit.
- **Deps:** none.

### S11-T2: The S11 write-up `[commodity]`

- **Goal:** `docs/evaluation.md`'s "Corrective retrieval (S11)" section from `summarize.py`'s output; the spec's must-have 8 and AC7 notes; ADR-006 and ADR-010 amendments pointing to ADR-011; the ADR index; `.greptile/files.json`; glossary terms.
- **Done when:** every number in the section matches `summarize.py`'s output; `make check` is green.
- **Deps:** T1.

### S11-T3: The backlog after S11 `[commodity]`

- **Goal:** S11's tasks; S12's two AC4 items; the ADR queue (011 corrective retrieval, 012 deployment); the proposed additions from the sitting.
- **Done when:** each item in the contract's list is in `docs/backlog.md`; `make check` is green.
- **Deps:** T1.

### S11-T4: The S11 retro `[commodity]`

- **Goal:** `/slice-retro S11` as the run's last commit: the slice brief, S11 ✅ and S12 🟨, `docs/architecture.md`, the memory review.
- **Done when:** the retro's exit checks pass.
- **Deps:** T2, T3.

## Risks & unknowns

- **The evidence is a sitting probe,** not a 3-run eval: retrieval only, Haiku at effort low, one prompt per probe. ADR-011 lists the limits; the write-up must repeat them.
- **The labels list primary sources only,** so an MRR drop may hide relevant unlabeled hits. The one displaced hit read (q34) was noise.
- **AC4 stays at 1 of 4** until S12.

## Decisions expected (ADRs)

- **ADR-011:** corrective retrieval, not adopted (R1 sitting, done). The ADR queue's deployment ADR moves to 012.

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit.

### Run S11-R1: close S11 as a measured negative result

- **Status:** planned
- **Tasks:** T2, T3, T4 (T1 was decided in the sitting). Docs only; no change to `src/` or `tests/`.
- **Goal (plain words):** write down what the sitting measured, why the stage isn't adopted, and who owns AC4's open seeds; then close the slice.

#### Sitting evidence (2026-10-12)

The table is in ADR-011 ("Sitting evidence"). The scripts, their raw outputs and logs are in `eval/results/s11-sitting/` (its `README.md` lists each one's command, cost and output); `uv run python eval/results/s11-sitting/summarize.py` prints probes 1–5 for free. Extra findings, from the logs:

- **c01:** as routed (HISTORY, 1.30 ± 1), its top 10 holds kep:1498, 2 sections of the v1.30 release blog and 7 release-note chunks; with no window, `versioning.md`'s support section is at ranks 1–2 and k04 is reachable (`probe_relax.log`, `probe_c01.log`, `probe_pool.log`).
- **q08:** no mode or window change retrieves KEP-2579's date line (k03) (`probe_relax.log`).
- **The devil's advocate's candidate-pool test** (`probe_pool.log`): rephrased q08's first search holds 0 of its 8 labels among 20 candidates; the second search holds 4, at ranks 14–20 against the informal question. Rephrased q31's label is in neither.
- **The LangGraph spike** (`spike/`): the same flow on fakes takes 82 lines with LangGraph and 30 as a plain loop, with 1 type cast for mypy; both skip the grader at 0 retries.

#### Decisions (made in the sitting, 2026-10-12)

| # | Decision | Rejected | Why |
|---|---|---|---|
| Step 0 | q01's seed **fails** the summary check: AC4 is 1 of 4. The 3 real conflicts missing from conflict set v0 (q18, q34, q35) are parked for v1. Jev is dropped from S11 | q01 passes; drop the 3 | The pair's summary is about "4 times per year", not KEP-2572's status; v0 is frozen |
| 1 | ADR-010 D4's fallbacks (the separate detector call, the stale-KEP rule) are an early S12 task with their own row | Before S11's loop; inside S11's eval | One change per ablation row; the credit covers only this order |
| Run shape | 1 run, 1 PR | 1 PR in 2 parts; 2 runs | The developer's choice |
| 2 | Test the loop on v0 plus the rephrased set, after a probe | v0 only; stop S11 at once | On v0 the loop has almost nothing to fix (probe 1) |
| Spot-check | The rephrased set: the developer checked q30, q02, q03, q04 and q07 (a seeded draw, 1 per mode + 1 random): all keep the meaning and time scope. Claude read all 36 | — | CLAUDE.md's bulk-review rule |
| 3 | B after the devil's advocate's test; the test failed checks 1–2, so **A: close S11 as a measured negative result** (ADR-011) | Build the RRF second search now; re-run the test without "stop" | The rule fixed before the test says A; a re-test after a fail is a choice made after seeing results |
| 4 | LangGraph, with guardrails (moot: nothing is built; recorded in ADR-011 D2) | A plain function | The developer's choice (résumé value) |
| 5 | Keep rule: every run of 3 must pass (ADR-011 D2; applied to probe 5) | 3-run means | Retrieval varies per run once a model writes queries; the design was picked on the hard set |
| 6 | AC4's q08 and c01: S12's sitting decides, with q01's fallback result in hand; c01's "drop the window" lead recorded | Change AC4 now; keep AC4 and fail it | Decided with all the facts |

**Claude's calls** (reversible):
- The probe scripts and raw outputs are committed verbatim in `eval/results/s11-sitting/`, with `summarize.py` and a README; `eval/results` joins ruff's `extend-exclude` (it holds tool outputs; the scripts are throwaway, never imported by `src/`).
- ADR-011 is this decision; the deployment ADR becomes 012.
- The retro is the run's last commit.

#### Pinned: T2's write-up

- **`docs/evaluation.md`:** a section "Corrective retrieval (S11)" after "Conflicts", before "Known limits":
  1. What was tested, in 3 lines (grade → second search → merge), and the two question sets.
  2. Probes 1–5, each a short table or line, numbers copied from `summarize.py`'s output, never retyped; the extra findings above.
  3. The verdict: ADR-011 D1 and the rule (D2), with probe 5's check table (4 checks × 3 runs).
  4. The limits, as in ADR-011's Consequences.
  5. What's next: S12's AC4 items; the proposed addition.
- **The product spec:**
  - Must-have 8 gets: "Tested in S11 and not adopted (ADR-011, 2026-10-12)."
  - AC7's row gets: "+corrective was tested in the S11-R1 sitting and not adopted (ADR-011): its evidence is retrieval-only sitting probes, not an ablation row."
- **ADR amendments** (dated `## Amendment 2026-10-12`, no decision changed):
  - ADR-006: D3's revisit trigger "the S11 LangGraph integration" closes; S11 added no LangGraph (ADR-011).
  - ADR-010: Consequences' "S11's grader … Revisit with S11's design" closes; there is no grader (ADR-011).
- **`docs/decisions/README.md`:** the index row for ADR-011.
- **`.greptile/files.json`:** ADR-011's entry.
- **Glossary** (`docs/learning/glossary.md`, "Retrieval and evaluation"): corrective RAG; evidence grader; query rewriting. One line each.

#### Pinned: T3's backlog items

- **S11's entry:** slice doc pointer; "Metrics to move: none adopted (ADR-011)"; T1–T4 as here.
- **S12's candidate tasks, added first:**
  - "ADR-010 D4's fallbacks: a separate detector call and the stale-KEP rule, measured as their own row (S11-R1 decision 1). AC4's q01."
  - "AC4 plan for q08 (k03) and c01 (k04), decided in the S12 sitting (S11-R1 decision 6). Lead: c01's k04 is reachable when its 1.30 window is dropped (`eval/results/s11-sitting/probe_pool.log`)."
- **ADR queue:** 011 Corrective retrieval: S11 (Accepted); 012 Deployment topology: S15. S15's row says ADR-012.
- **Proposed additions:**
  - New: "Query rewriting for informal wording (S11-R1 sitting lead)": a second search on every question with a Haiku-written query, RRF with the first 10. Rephrased Recall@10 0.427 → 0.468 and MRR 0.607 → 0.671, v0 neutral; 1 run, the best of 4 designs, v0's routes reused; ~5.5 s more per question; it would run on unanswerable questions too (q48). Test it on golden v1's verified rephrased set with ADR-011 D2's rule.
  - New: "Conflict set v1 candidates (S10-T8; parked in the S11-R1 sitting)": q18 `gate:StrictIPCIDRValidation` 10419 vs. 10420; q34 `gate:KMSv2` 9930 vs. 9931; q35 the v1.28 blog 41925 vs. 42160 (borderline).
  - The Jev item's S11 line: "dropped in the S11-R1 sitting; no grader adopted (ADR-011)".
  - The "Golden set v1: a router check set" item: "S11-R1: the developer spot-checked 5 of 36 (all match) and Claude read all 36; the set was the sitting's hard set."

#### Handoffs between tasks

- T2 and T3 both read ADR-011 and this contract, not each other's output. T3's AC4 lines quote T2's numbers only through ADR-011.
- T4 (the retro) reads T2's section and T3's backlog, and the sitting evidence above.

#### Edge cases

- **Numbers that differ by probe:** the rephrased set's first-search MRR is 0.606 in probe 2 (its own routes) and 0.607 in probes 4–5 (v0's routes reused). Quote each with its probe; don't merge them.
- **Probe 5's prompt differs from probe 4's** only by the "stop" option: say so wherever probe 4's +0.041 is quoted.
- **"Hard" means two things:** probe 1's 12 v0 questions with Recall@10 < 0.5, and the rephrased set as a whole. Name which.
- **The ablation table** (`eval/results/ablation.md`) is generated from run folders; `eval/results/s11-sitting/` isn't a run folder and gets no row. Check that `make eval-table` still prints the same table.
- **No paid call:** the probes are never re-run in the run. `summarize.py` reads the saved JSON.

#### Files in scope

- Sitting commits: `docs/decisions/ADR-011-corrective-retrieval.md`, this slice doc, `eval/results/s11-sitting/` (scripts, outputs, logs, `summarize.py`, `README.md`), `pyproject.toml` (ruff's `extend-exclude`).
- T2: `docs/evaluation.md`, `docs/product-spec.md`, `docs/decisions/ADR-006-generation-and-tracing.md`, `docs/decisions/ADR-010-conflict-detection.md`, `docs/decisions/README.md`, `.greptile/files.json`, `docs/learning/glossary.md`.
- T3: `docs/backlog.md`.
- T4: `docs/learning/S11-corrective-retrieval.md`, `docs/backlog.md` (status), this slice doc (retro), `docs/architecture.md`, the auto-memory review.

#### Proof map

| Task | "Done when" | Proof | Expected values from |
|---|---|---|---|
| T2 | Every number in the S11 section matches | `uv run python eval/results/s11-sitting/summarize.py`, compared line by line by the reviewer | The probes' saved outputs (the sitting's tool output) |
| T2 | The spec, ADR amendments, index, Greptile list, glossary | `grep -n "ADR-011"` over the 6 files | This contract |
| T2, T3 | `make check` green | `make check` | — |
| T3 | Each pinned backlog item is present | `grep -n` for each item's key phrase | This contract |
| T4 | The retro's exit checks | `/slice-retro`'s checklist | The slice doc's exit checks |

#### Break-it rules

- None: the run changes no logic. The number check (the reviewer compares the write-up with `summarize.py`'s output) is the safeguard.

#### Real-data demo

```bash
uv run python eval/results/s11-sitting/summarize.py
```

Free: it reads the saved JSON only.

#### Bundle-level check

- `make check` (green)
- `make test-int` (code unchanged; checks Postgres is up at the run's start)
- `make eval-table` prints the same table as `eval/results/ablation.md`
- `summarize.py`'s output matches every number in the S11 section and ADR-011

#### PR plan

- 1 PR, docs and config only: Greptile is skipped (CLAUDE.md). Greptile: 17/50.

#### Paid calls allowed

- **None.** Credit at sitting: US$9.45 (2026-10-12). The sitting's probes spent ~US$0.40 (Haiku US$0.24, router US$0.15, Voyage under US$0.01): estimate **~US$9.05 left**.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S11-*.md`
