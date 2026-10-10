# S09: Temporal and authority-aware retrieval

- **Status:** 🟨
- **Blueprint stage:** Stage 6 (project-specific metadata retrieval: query modes, temporal/version logic, authority)
- **Started:** 2026-10-09
- **Finished:**

## Outcome

`make eval` runs a pipeline that routes each question to a mode (CURRENT, HISTORY, CHANGE, WHY), filters and re-weights evidence by release validity and source authority (ADR-003), and its ablation row shows stale-result rate, temporal accuracy, authority-selection accuracy and router accuracy against `rerank`.

## Why now

- **The ranking ignores time.** In rerank's top 10, 38 of the 100 hits for CURRENT questions are text a later edit replaced. Only 32 of the 90 hits for HISTORY questions with a window fall inside it (S09-R1 sitting probe).
- **It's the next ablation step** (AC7): dense → +lexical/RRF → +rerank → **+temporal/authority** → …
- **AC5, AC6 and AC1's tier** need it: evidence valid at the right release, and each citation's authority tier.
- **S10 needs its inputs:** `observed_lifecycle` and `effective_stage` feed the `claim_mismatch` conflict (ADR-003 D2).

## Exit checks

- [ ] ADR-009 (query-mode routing) is Accepted; router accuracy on v0 is recorded.
- [ ] Time scopes ("before 2021", "before v1.28", "in Kubernetes 1.20") become release windows through the `releases` table.
- [ ] `make eval-retrieval` prints stale-result rate, temporal accuracy, router accuracy and authority-selection accuracy in every mode they apply to.
- [ ] `observed_lifecycle` is stored, and each hit carries `effective_stage` (KEPs) and an authority tier (ADR-003 D2–D3).
- [ ] Authority multipliers live in config (ADR-003 D4).
- [ ] The S09 row is in the ablation table (3 runs); `docs/evaluation.md` says whether it meets the improvement rule, and the product spec has thresholds for the 4 S09 metrics.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| ADR-009: an LLM router (mode + the time scope a question names) | Rules routing and Jev (ADR-009 alternatives) |
| Time scope → release window through the `releases` table | Implicit times ("before strict validation was default"); patch-level windows |
| The 4 S09 metrics in the eval | AC6 on the answer side (cited evidence in the window): its definition is open (see Risks) |
| Mode-specific retrieval plans (ADR-003 D4's filter column in R1) | Per-window-end retrieval for dated CHANGE questions (S09-R1 decision 3; proposed addition) |
| `observed_lifecycle` from the feature-gate reference; `effective_stage`; tiers | The CHANGELOG as a stage observation, and how a claimed `disabled` compares (deferred to S10 in the S09-R2 sitting) |
| Authority multipliers in config | Learned weights; tuning beyond a small sitting prototype |
| The S09 eval run and its row | Golden set changes (v0 is frozen); BM25 (proposed addition); conflicts (S10) |

## Metric to move

- **Stale-result rate** (CURRENT, lower is better) and **temporal accuracy** (HISTORY with a window, higher is better): the temporal stage's targets.
- **Authority-selection accuracy:** the authority stage's target. Over the golden CURRENT questions whose labeled documents span 2+ tiers (9 on v0, fixed by the labels), the share whose first labeled top-10 hit has the best tier among the question's labels; CURRENT-question MRR is printed beside it (S09-R2 decision 4).
- **Router accuracy:** a component metric, threshold ≥ 0.90 (ADR-009).
- Recall@10, MRR, nDCG@10 and Hit@10 must not drop by more than 0.03 against `rerank` (the improvement rule).

## Tasks

These mirror `docs/backlog.md`; details live here.

### S09-T1: ADR-009 query-mode routing `[core]` ✅

- **Goal:** decide in the R1 sitting how a question becomes a mode.
- **Status:** done in the S09-R1 sitting (2026-10-09): an LLM router (`claude-opus-5-5`, effort low); ADR-009 is in the run contract commit.
- **Deps:** none.

### S09-T2: Router and time scope → release window `[core]`

- **Goal:** the `Router` interface, the Claude router and a fake (ADR-009 D1); a pure function from a time scope to a release window (D2); the eval's stored routes and `make eval-routes` (D3).
- **Done when:** unit tests on hand-worked examples pass; `make eval-routes` stores 43 routes; `make eval-retrieval` in temporal mode prints router accuracy ≥ 34 of 36 and 7 of 9 windows.
- **Deps:** T1.

### S09-T3: S09 metrics in the eval `[core]`

- **Goal:** stale-result rate, temporal accuracy and router accuracy, defined in `docs/evaluation.md`, printed by `make eval-retrieval`, stored in `summary.json`, shown in the ablation table.
- **Done when:** unit tests match hand-computed values; `make eval-retrieval` in dense, hybrid and rerank prints the sitting's baselines.
- **Deps:** none (router accuracy appears once T2's routes exist).

### S09-T4: Temporal retrieval mode `[core]`

- **Goal:** a `temporal` mode: route, resolve, then apply ADR-003 D4's filter column inside both searches, on top of `rerank`.
- **Done when:** integration tests on fixtures pass; `make eval-retrieval` in temporal mode prints the sitting's prototype numbers.
- **Deps:** T2.

### S09-T5: `observed_lifecycle` from the feature-gate reference `[core]`

- **Goal:** a migration and an ingestion step: per gate × minor release, the stage read from that release's own snapshot (1.29+ per-gate `stages`; pre-1.29 tables), with `status_confidence` (ADR-003 D2).
- **Done when:** hand-worked unit tests pass; `make lifecycle` stores the sitting's 3,295 rows (per-release counts and spot rows as pinned in run S09-R2); a re-run stores identical rows.
- **Deps:** none.

### S09-T6: `effective_stage` and authority tier per hit `[core]`

- **Goal:** each hit carries its tier (ADR-003 D3) for the question's target release; KEPs use `effective_stage` through their `kep.yaml` feature gates (65 of 113 current KEP versions name a gate; 70 have the key); the tier reaches the prompt and citations (AC1).
- **Done when:** hand-worked unit tests pass; every hit in every mode carries a tier; the sitting's KEP examples and the 82 / 25 / 6 split at 1.37 match; AC1's check requires the tier; dense, hybrid, rerank and temporal print their old numbers.
- **Deps:** T5.

### S09-T7: Authority multipliers and authority-selection accuracy `[core]`

- **Goal:** ADR-003 D4's boost and demote columns, from config, applied per mode after the reranker on its probability, as an `authority` mode; the authority-selection metric.
- **Done when:** hand-worked unit tests pass; `make eval-retrieval` in authority mode prints the sitting's prototype numbers, every mode prints the authority line with the sitting's baselines, and the flipped-tier check gives the sitting's numbers.
- **Deps:** T4, T6.

### S09-T8: S09 eval run `[commodity]`

- **Goal:** 3 paid runs of `make eval` in the final S09 mode; the row; the write-up; thresholds for the 4 S09 metrics in the product spec.
- **Done when:** the free gate passes before any paid call; the row and its spread are committed; `docs/evaluation.md` states pass or fail against the improvement rule with numbers; the product spec has the 4 thresholds by the sitting's rule (S09-R2 decision 5).
- **Deps:** T7.

## Risks & unknowns

- **Later documents describe the past.** For HISTORY questions with a window, 7 of 41 labeled sources have no text within ±1 release of it (e.g. the 2021 cadence blog for "before 2021"). The ±1 filter still scored best (S09-R1 decision 2).
- **AC6 conflicts with the labels.** AC6 says cited evidence must be valid within the window, but v0 labels later documents as primary sources for HISTORY questions. Out of S09's scope; the S09-R2 sitting deferred its definition to the S12 (Phase 1 closeout) sitting.
- **A hit cites the newest copy of its text,** even for a HISTORY question whose window holds an older copy. Its windows list shows both; AC6 must allow for it.
- **Router latency.** Opus at effort low adds one call to each live ask: p50 1.71 s, p95 4.27 s over 43 calls (S09-R1).
- **Multipliers after RRF do nothing in rerank mode.** ADR-003 D4 applied them after RRF, but rerank re-sorts the whole pool by its own score. Resolved in the S09-R2 sitting: they apply after the reranker, on its probability (decision 3; ADR-003 change).
- **The authority metric leans toward the weights.** The same tier code drives both, so flipped tiers still lift it (3 → 6 of 9); CURRENT-question MRR, from human labels only, tells them apart (+0.146 real, −0.009 flipped). It is printed beside the metric (S09-R2 decision 4).
- **Tuning on the test set.** The filters are ADR-003's, chosen before any data, but v0 confirmed them; the router prompt was written from definitions, and checked on a blind rewording. v1 is the clean test.
- **CHANGELOG release records are valid only at their own release.** 26 of 105 non-HISTORY labels have no text valid at 1.37, so staleness is defined by replacement, not by release (S09-R1 decision 1).

## Decisions expected (ADRs)

- **ADR-009:** query-mode routing. Accepted in the S09-R1 sitting.
- **ADR-003 changes:** dated CHANGE retrieval deferred (R1, done); tiers by source type, multipliers after the reranker, the CHANGELOG as an observation deferred to S10 (R2 sitting, done).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S09-R1: route and filter by time

- **Status:** merged (PR #39)
- **Branch:** `s09-r1-temporal`
- **Tasks, in this order:** S09-T2 (router and windows) → S09-T3 (S09 metrics) → S09-T4 (`temporal` mode). T1 (ADR-009) was done in the sitting.
- **Closes the slice:** no; R2 (authority) follows.
- **Goal (plain words):**
  - Ask Claude which kind of question this is (now / back then / how it changed / why) and which release or year it names; turn that into releases with the release-dates table.
  - Score how often search returns rewritten text for "now" questions, and wrong-era text for dated "back then" questions, in every mode.
  - Add a `temporal` mode: "now" questions skip rewritten text, dated "back then" questions keep only texts from the asked-for releases ±1, inside both searches, then rerank as today.

#### Sitting evidence (2026-10-09)

All free except the router test. Scratch scripts, not committed.

- **Staleness, by two definitions** (labels of the 27 CURRENT, CHANGE and WHY questions, 105 labels):
  - "No current version holds any of the label's texts": 2 of 105 (q01 `web:/releases/release/`, q45 `web:/docs/reference/networking/virtual-ips/`).
  - "No text valid at 1.37": 26 of 105, of which 25 are CHANGELOG sections (valid only at their own release).
- **HISTORY labels vs. their window** (the 9 questions with a window, 41 labels): 7 have no text within ±1 release (q12 ×3, q24 KEP-3720, q33 blog, q42 `gate:IPv6DualStack`, q43 `changelog:1.22`); q12 names no release, so 4 of 36 for the 7 dated ones.
- **Baselines** (top 10, own SQL; one question's hits are the same in every run):

| Mode | Stale CURRENT hits | Dated-HISTORY hits in the exact window |
|---|---|---|
| dense | 39 / 100 | 31 / 90 |
| hybrid | 39 / 100 | 30 / 90 |
| rerank | 38 / 100 | 32 / 90 |

- **Filter prototype** (rerank + filters; golden modes; hand-resolved windows). Variant A reproduced rerank exactly:

| Variant | Recall@10 | Hit@10 | MRR | nDCG@10 | Stale | In window |
|---|---|---|---|---|---|---|
| A: rerank | 0.516 | 0.972 | 0.703 | 0.489 | 38/100 | 32/90 |
| B: CURRENT filter | 0.530 | 0.972 | 0.717 | 0.508 | 0/100 | 32/90 |
| **C: B + HISTORY ±1 (chosen)** | **0.5596** | **1.0000** | **0.7586** | **0.5351** | **0/100** | **47/90** |
| D: B + HISTORY exact | 0.541 | 1.000 | 0.750 | 0.525 | 0/100 | 82/90 |
| E: B + HISTORY soft (in-window first) | 0.539 | 1.000 | 0.759 | 0.522 | 0/100 | 42/90 |

  - C by mode: CURRENT 0.6104 / 1.0000 / 0.6367 / 0.5560; HISTORY 0.5050 / 1.0000 / 0.7278 / 0.4739; CHANGE and WHY unchanged from rerank.
  - C was re-run with the contract's SQL filter inside the dense query (width 100, iterative scan): identical numbers. Every filtered question still got 20 dense candidates; the index scanned 38 rows to find 20 current ones for q22.
- **pgvector 0.8.1:** iterative index scans are available (`hnsw.iterative_scan`), no new dependency.
- **Router test:** ADR-009's Context (rules 36/36 on v0 but 12/36 reworded; Opus 35/35; windows 7/9 on both sets; $0.31 for 72 Opus calls).
- **Empty evidence:** the generator already returns `insufficient_evidence` without a model call when retrieval finds nothing.

#### Decisions (made in the sitting, 2026-10-09)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Slice doc approved; bundle = T2–T4; S08 parked #5 (3 comments say "both modes") and #6 (the integration `settings` fixture reads `.env`) folded into T4; "near-duplicate crowding" kept (re-checked after T4 by distinct sections); "CI: cache mypy" kept as a proposed addition | — | #6 bites harder with a 4th mode; both touch T4's files |
| 1 | **Stale-result rate** = stale hits ÷ hits over CURRENT questions' top K, where a hit is stale when no current version (open date window) holds its text. **Temporal accuracy** = hits with a release window overlapping the exact golden window ÷ hits, over questions with a golden `release_window`. Both use the golden mode and window, pooled over hits | "Not valid at the latest release"; window ±1 | 2 of 105 vs. 26 of 105 correct labels flagged stale; ±1 would read 100% by construction under the filter |
| 2 | **HISTORY with a window: hard filter, ±1 release** (ADR-003 D4 as written); slack in config | Exact window; soft (in-window first) | Best on all 4 retrieval metrics; chosen by the ADR before any data |
| 3 | **CURRENT drops replaced text; CHANGE, WHY and HISTORY without a window: no filter.** Per-window-end retrieval for dated CHANGE questions is deferred (ADR-003 change table) | Build it now | No v0 CHANGE question names a release, so it can't be measured |
| 4 | **Filters run inside both searches** (each still returns 20 candidates) | After fusion | What the prototype measured; post-filtering leaves ~12 of 20 for CURRENT |
| 5 | **ADR-009: an LLM router**, `claude-opus-5-5`, effort low; code maps time scopes to releases; the eval stores routes | Rules; Haiku 5.5; rules + LLM fallback | 35/36 on v0 and on a blind rewording; rules 12/36 reworded. Devil's advocate: rules are fitted to the labeler's wording; its concession test failed at 0.33 |
| 6 | **Reporting:** 3 new summary fields and table columns, n/a for the 9 old rows; a side table of all 4 stages from `make eval-retrieval` in `docs/evaluation.md` | Re-grade the old runs from the database | Old results stay untouched; retrieval repeats exactly |
| 7 | **1 PR**, an explicit exception to the ~800-line alarm (estimate ~1,400 reviewable lines). Paid calls as listed below | 2 stacked PRs split after T3 (recommended) | The developer's call in the sitting |

**Claude's calls (overrulable):**

- **Layout:**
  - `retrieval/router.py`: `Mode`, `TimeScope`, `Route` (Pydantic), the `Router` protocol (`route(question) -> Route`), `SYSTEM_PROMPT`, `ClaudeRouter` (the Anthropic implementation), and a fake for tests.
  - `retrieval/temporal.py`: pure functions `resolve_window(scope, releases) -> Window | None` and `plan(route, releases, slack) -> TemporalFilter | None`.
  - `db/models.py`: `TemporalFilter(current_only: bool, from_release: int | None, until_release: int | None)`; `Hit.current: bool` (required).
  - Metric functions go in `eval/metrics.py`, as pure functions.
- **The router call:** `messages.parse(model=ROUTER_MODEL, max_tokens=ROUTER_MAX_TOKENS, system=SYSTEM_PROMPT, messages=[question], output_format=Route, output_config={"effort": ROUTER_EFFORT})`, as in the generator. No retries beyond the SDK's.
- **`retrieve` in temporal mode:** `retrieve(..., reranker, route)`; the route is required (`ValueError` without one). It reads `list_releases`, resolves the window, plans the filter, then runs rerank mode's pipeline with the filter passed to `search` and `search_lexical`. A filter with no match returns `[]` (no model call).
- **SQL** (one fixed query each, ADR-005; parameters make the conditions no-ops when there's no filter):
  - Both windows LATERALs add `bool_or(v.valid_until_date IS NULL) AS current`.
  - Both searches keep a text only if some version holding it passes: `(NOT current_only OR v.valid_until_date IS NULL) AND (from IS NULL OR v.valid_until_release IS NULL OR v.valid_until_release >= from) AND (until IS NULL OR v.valid_from_release <= until)`. Dense: inside the `nearest` CTE, before the LIMIT. Lexical: inside `matched`, before the LIMIT.
  - The dense query also sets `hnsw.iterative_scan` to `strict_order` with `set_config(..., true)`, next to `hnsw.ef_search`, in every mode.
- **Settings:**
  - `RETRIEVAL_MODE` gains `temporal`; the default stays `rerank` until T8.
  - `ROUTER_MODEL` (default `claude-opus-5-5`), `ROUTER_EFFORT` (default `low`), `ROUTER_MAX_TOKENS` (default 4096, 1–16000).
  - `HISTORY_WINDOW_SLACK` (default 1, 0–5), `EVAL_ROUTES_DIR` (default `eval/question_routes`).
  - `ROUTER_PRICE_INPUT_USD_PER_MTOK` (4.0) and `ROUTER_PRICE_OUTPUT_USD_PER_MTOK` (20.0), the `claude-opus-5-5` prices.
  - `.env.example` lists them all.
- **Stored routes:** `eval/question_routes/<ROUTER_MODEL>.json` = `{"prompt_sha256": …, "routes": {<question key>: <Route JSON>}}`, keyed as the question vectors are.
  - A different `prompt_sha256` is an `EvalError`: "made with a different router prompt: delete it and run `make eval-routes`".
  - `make eval-routes` (`python -m orgknow.eval routes`) routes every golden question (all 43) with no stored route.
  - `make eval` and `make eval-smoke` in temporal mode fill missing routes too, like the vectors.
  - `make eval-retrieval` in temporal mode raises `EvalError` naming `make eval-routes` when a route is missing.
- **Eval files:**
  - `run.json` `settings` gain `router_model`, `router_effort`, `history_window_slack` (null outside temporal mode and in old folders).
  - Each `questions.jsonl` row gains `release_window` (golden, `[from, until]` or null) and `route` (`{mode, time_scope, window, filter}`, null outside temporal mode).
  - Each hit gains `current` and `release_windows`. All optional, so old folders load.
- **Summary fields** (decision 6): `stale: Count | None`, `temporal: Rate | None`, `router: Rate | None`; None when no row applies (no CURRENT question, no golden window, not temporal mode).
- **`ask` in temporal mode** builds a `ClaudeRouter`, routes live, and prints one line before the answer: `Route: HISTORY, releases until 1.27 (searched until 1.28)`, or `Route: CURRENT, current text only`, or `Route: WHY, no filter`.
- **Trace:** the `retrieve` span records the route, the window and the filter.
- **S08 parked #5 and #6:**
  - The comments describe the 4 modes.
  - The integration `settings` fixture builds `Settings(_env_file=None, database_url=…)`.
- **Docs:**
  - `docs/architecture.md`: the router and the temporal mode.
  - README: `temporal` mode, `make eval-routes`.
  - `docs/evaluation.md`: the 3 metric definitions (decision 1), the side table (decision 6), the router's timing.
  - Glossary: "query router" if absent.

#### Pinned: the router prompt and schema

`SYSTEM_PROMPT`, word for word (the sitting measured this text):

```
You sort questions about Kubernetes by what they ask for, before a search runs.

Modes:
- CURRENT: how something is now, in the latest release. Use this when the question names no past time and asks about present behavior or advice.
- HISTORY: how something was at a past time, in a past release, or before some change.
- CHANGE: how something changed over time: when it was introduced, promoted (alpha, beta, GA), deprecated, frozen or removed, or the sequence of those steps.
- WHY: the reason, motivation or rationale for a design or a change.

Time scope: only a Kubernetes release ("1.N") or a calendar year that the question names explicitly. Give the relation (before, in, after, since, between) and the value(s) as written ("1.28", "2021"). If the question names no release number or year, the kind is "none"; never infer a release from an event.
```

Schema: `Route(mode: Literal["CURRENT", "HISTORY", "CHANGE", "WHY"], time_scope: TimeScope)`; `TimeScope(kind: Literal["none", "before", "in", "after", "since", "between"], start: str | None, end: str | None)`.

#### Pinned: time scope → release window (`resolve_window`)

"In effect on day d" = the latest release whose release date is on or before d (ADR-002 D3). A value is `1.N`, `v1.N` or `1.N.P` (minor N), or a 4-digit year. For every kind except `between`, the value is `start`, or `end` when `start` is empty. Anything else gives no window.

| Kind | Release value | Year value |
|---|---|---|
| before | until N − 1 | until the release in effect on (Y − 1)-12-31; none → no window |
| in | N to N | the release in effect on Y-01-01 (the first release if none yet) to the one in effect on Y-12-31; none on 12-31 → no window |
| after | from N + 1 | from the release in effect on (Y + 1)-01-01 (the first release if none yet: "after 2010" → from 20; S09-R2 sitting) |
| since | from N | from the release in effect on Y-01-01 (the first release if none yet) |
| between | A to B (A ≤ B, else no window) | in effect on A-01-01 (or the first) to in effect on B-12-31 |
| none | no window | no window |

Hand-worked examples (release dates from the `releases` table: 1.20 2020-12-08, 1.21 2021-04-08, 1.23 2021-12-07, 1.26 2022-12-08):
- before 1.28 → until 27
- before 2021 → until 20
- in 1.20 → 20–20
- in 2022 → 23–26
- after 1.30 → from 31
- since 1.30 → from 30
- before 2020 → none
- `v1.28.3` reads as 28.

**Plan:** CURRENT → current text only. HISTORY with a window → from − slack to until + slack (an open end stays open). Everything else → no filter.

**Plan table** (v0's 36 answerable questions; the sitting's Opus routes give exactly this):
- **Current only (10):** q01 q06 q11 q16 q21 q22 q30 q31 q40 q41.
- **Windowed (7), before slack:** q02 until 20; q23 until 27; q24 until 24; q32 28–28; q33 until 28; q42 20–20; q43 20–20.
- **No filter (19):** q03 q04 q07 q08 q09 q12 q13 q14 q17 q18 q19 q25 q26 q34 q35 q36 q44 q45 q46.

#### Pinned: output formats

`make eval-retrieval`, temporal mode:

```
Mode: temporal (candidates 20, k 60, width 100, model BAAI/bge-reranker-base@2cfc18c, max length 512, router claude-opus-5-5, slack 1). Answerable questions: 36.
Recall@10 0.560  Hit@10 1.000  MRR 0.759  nDCG@10 0.535
Stale rate 0.000 (0 of 100 CURRENT hits)  Temporal accuracy 0.522 (47 of 90 dated HISTORY hits)
Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  Plans: 10 current-only, 7 windowed, 19 unfiltered
Retrieve time: p50 4.91 s, p95 6.14 s (36 questions). Reranker load 7.4 s.
```

- **Times are examples.** Router accuracy may differ by a question (the LLM varies); the gate is ≥ 34 of 36 (see Proof map).
- **Dense, hybrid and rerank** keep their first two lines and their timing line exactly, with the stale/temporal line between them and no router line.
- **`Windows`** = questions whose resolved window (before slack) equals the golden one, of those with a golden window. `extra` = windows resolved where golden has none.

`make eval-routes`:

```
Routed 43 questions with claude-opus-5-5 (0 already stored). Route time: p50 1.84 s, p95 3.02 s. Cost $0.19.
```

- Times and cost are examples. p95 is nearest rank over this command's calls.
- The cost uses `ROUTER_PRICE_INPUT_USD_PER_MTOK` (default 4.0) and `ROUTER_PRICE_OUTPUT_USD_PER_MTOK` (default 20.0), both in settings and `.env.example`.
- With nothing missing: `Routed 0 questions with claude-opus-5-5 (43 already stored).` and no time or cost.

**Ablation table:** 3 columns after `Cost/question ($)`: `Stale rate`, `Temporal acc.`, `Router acc.`. Cells are count ÷ total, 3 decimals, mean (min–max) over runs; `n/a` when absent. The 9 old rows: `n/a` in all 3, with every other cell unchanged.

**Side table** in `docs/evaluation.md` ("Time scores by stage", retrieval only, from `make eval-retrieval`):

| Stage | Recall@10 | MRR | Stale rate | Temporal accuracy | Router accuracy |
|---|---|---|---|---|---|
| dense | 0.384 | 0.614 | 0.390 | 0.344 | n/a |
| hybrid | 0.382 | 0.675 | 0.390 | 0.333 | n/a |
| rerank | 0.516 | 0.703 | 0.380 | 0.356 | n/a |
| temporal | 0.560 | 0.759 | 0.000 | 0.522 | the run's value |

#### Handoffs between tasks

- T2 → T3: the `Route` type and the stored routes, for router accuracy.
- T2 → T4: `route`, `resolve_window` and `plan`.
- T3 → T4: `Hit.current` and the stale/temporal line, which T4's gate reads.
- If T2 parks, T3 still ships without its router line, and T4 parks. If T3 parks, T4 can still ship; its gate then checks only the 4 retrieval metrics.

#### Edge cases

- **A filter leaves no text:** `[]`, no reranker call, and `ask` returns `insufficient_evidence`.
- **A window outside the corpus** ("before 1.15", "in 1.40"): kept as numbers. "before 1.15" matches nothing → `[]`. "in 1.40" still keeps current text, whose release window is open (corrected in the S09-R2 sitting: the code is kept; only HISTORY routes get a window, so a future-release question rarely reaches the filter).
- **A time scope on a non-HISTORY route** (e.g. WHY "in v1.28"): no filter (decision 3).
- **A route of HISTORY with no time scope** (q07, q12, q17): no filter.
- **A text in several versions:** it passes if any of them passes. A text in [20, 22] and [23, now] passes "until 20".
- **CHANGELOG text:** current unless edited, valid only at its release, so never stale and filtered by its one release.
- **The `hnsw.iterative_scan` setting** must not change dense, hybrid or rerank results; the pinned lines prove it.
- **A non-release number** ("a 1.5 second timeout"): the router names no release, so there's no window. The fake router is used in tests; there's no regex to fool.
- **The router API fails in `ask`:** the error is reported like a generation failure (exit 1, a message).
- **Old results folders:** no `route`, `current` or `release_windows` fields; they load, and their new summary fields are None.

#### Files in scope

- **New:**
  - `src/orgknow/retrieval/{router,temporal}.py`
  - `tests/unit/test_router.py`, `tests/unit/test_temporal.py`
  - an integration test of the filtered searches
  - `eval/question_routes/claude-opus-5-5.json`
- **Changed:**
  - Config: `Makefile` (`eval-routes`), `.env.example`
  - Code: `src/orgknow/settings.py`, `src/orgknow/db/{models,retrieval}.py`, `src/orgknow/retrieval/retrieve.py`, `src/orgknow/cli.py`, `src/orgknow/eval/{runner,metrics,table,__main__}.py`
  - Results: `eval/results/ablation.md` (regenerated)
  - Docs: `README.md`, `docs/{architecture,evaluation}.md`, `docs/learning/glossary.md`, `docs/backlog.md` (ticks)
  - Tests that build a `Hit`, a row, a summary or the table; `tests/integration/conftest.py` (#6)
- **Not touched:** `eval/golden_set/`, `eval/question_vectors/`, migrations and the schema (no migration: filters are queries only), chunking, ingestion, the generation prompt, every old results folder.

#### Proof map

| Task | Done when / rule | Proof | Expected values from |
|---|---|---|---|
| T2 | Windows | Unit: the 8 hand-worked examples above, plus `between 1.24 and 1.26` → 24–26, `between 1.26 and 1.24` → none, kind `none` → none, `start` empty with `end` "1.28" under `before` → until 27 | By hand from the releases table |
| T2 | Plan | Unit: CURRENT → current only; HISTORY until 20, slack 1 → until 21; HISTORY 28–28 → 27–29; HISTORY with no window, CHANGE, WHY → none | By hand |
| T2 | Router wiring | Unit with a fake `anthropic` client: the request carries `ROUTER_MODEL`, the effort and the prompt; the parsed `Route` comes back | By hand |
| T2 | Stored routes | Unit: a changed prompt hash → `EvalError`; a stored route is never re-requested | By hand |
| T2 | **Real router** | `make eval-routes` stores 43 routes (paid); `RETRIEVAL_MODE=temporal make eval-retrieval`: router accuracy ≥ 34 of 36, `Windows 7 of 9 (0 extra)`, `Plans: 10 current-only, 7 windowed, 19 unfiltered`, each question's plan as in the plan table | Sitting (Opus 35/36, windows 7/9) |
| T3 | Metrics | Unit on hand-built hits: 3 stale of 10 → 0.3; a CHANGELOG-like hit (current, window [24, 24]) isn't stale; a hit in [21, now] isn't in window "until 20" but one in [20, 22] is | By hand |
| T3 | Baselines | `make eval-retrieval` in dense, hybrid, rerank: the stale/temporal lines read 39/100 · 31/90, 39/100 · 30/90, 38/100 · 32/90; their other lines unchanged | Sitting probe (own SQL) |
| T3 | Table | `make eval-table`: the 9 old rows unchanged except 3 `n/a` cells each (diff) | Decision 6 |
| T4 | Filters | Integration on fixtures: CURRENT drops a text held only by a closed version; HISTORY "until 20" keeps a text held by versions [20, 22] and [23, now], and drops one held only by [23, now]; both searches; no filter → today's results | Hand-built fixtures |
| T4 | **Gate** | `RETRIEVAL_MODE=temporal make eval-retrieval` → `Recall@10 0.560  Hit@10 1.000  MRR 0.759  nDCG@10 0.535`, `Stale rate 0.000 (0 of 100 …)`, `Temporal accuracy 0.522 (47 of 90 …)` | Sitting prototype (variant C, exact SQL) |
| T4 | Old modes unchanged | dense → 0.384 / 0.944 / 0.614 / 0.369; hybrid → 0.382 / 0.944 / 0.675 / 0.385; rerank → 0.516 / 0.972 / 0.703 / 0.489 | S06 / S07 / S08 |
| T4 | Settings | Unit: `HISTORY_WINDOW_SLACK=6` → validation error; temporal mode without a route → `ValueError` | The contract |
| T4 | Crowding (S1) | The brief reports mean distinct sections in temporal vs. rerank (7.4) | Diagnostic |

If a stored route's plan differs from the plan table (LLM variance), the gate can't be checked as pinned: park the gate item, name the question, and keep the code.

#### Break-it rules

- T2: `before 1.N` → until N (off by one) → the "before 1.28 → until 27" test fails.
- T3: stale = "no window contains the latest release" → the CHANGELOG-like test fails.
- T4: match only the cited (newest) version against the window → the "[20, 22] and [23, now]" test fails.

#### Real-data demo

```bash
make eval-routes
RETRIEVAL_MODE=dense make eval-retrieval
RETRIEVAL_MODE=hybrid make eval-retrieval
RETRIEVAL_MODE=rerank make eval-retrieval
RETRIEVAL_MODE=temporal make eval-retrieval
RETRIEVAL_MODE=temporal uv run orgknow ask "Before v1.28, how many minor versions older than kube-apiserver could the kubelet be?"
RETRIEVAL_MODE=temporal uv run orgknow ask "pre-1.28 kubelet/apiserver skew: how many minors behind the apiserver could kubelet lag?"
```

At most 3 asks; the Langfuse trace links go in the brief.

#### Bundle-level check

1. `make check`.
2. `make test-int` (Postgres checked healthy at run start).
3. `make eval-retrieval` in all 4 modes: the pinned lines.
4. `make eval-table`: the 9 old rows unchanged except the 3 new `n/a` cells.
5. `git status --short`: only intended files.

#### PR plan

1 PR, above the ~800-line alarm by the developer's choice (decision 7). Greptile: 1 trigger (13/50 used before the run).

#### Paid calls allowed

- **Anthropic router:** ≤ 100 `claude-opus-5-5` calls at effort low (43 for `make eval-routes`, the rest for a re-fill or the demo).
- **Anthropic answers:** ≤ 3 demo asks.
- **Cap:** $1 for both.
- **Voyage:** ≤ 3 requests, for the demo asks only (the eval uses stored vectors).
- **Langfuse:** traces of the demo asks.
- **Hugging Face:** none (the reranker is cached).
- **Package installs:** none.
- No other network calls. No content reads on the corpus clones.

### Run S09-R2: authority, and the S09 eval run

- **Status:** planned
- **Branch:** `s09-r2-authority`
- **Tasks, in this order:** S09-T5 (gate stages) → S09-T6 (tiers per hit) → S09-T7 (`authority` mode and metric) → S09-T8 (the S09 eval run).
- **Closes the slice:** yes, once the retro (`/slice-retro`) follows.
- **Goal (plain words):**
  - Record each feature gate's stage at each release, as that release's own docs gave it.
  - Give every search result a trust tier (1 = official docs … 6 = blog). A KEP counts as shipped once one of its gates appears in the reference.
  - Add an `authority` mode: per question type, nudge trusted sources up and weak ones down, after the reranker; and score whether "now" questions put the most trusted correct source first.
  - Run the paid eval 3 times in the final mode, write the row, and set the S09 thresholds.

#### Sitting evidence (2026-10-10)

All free: saved pools from stored vectors and routes, the website clone, scratch scripts (not committed).

- **Gate stages at each release's own snapshot** (spike parser, the T5 rules below): 3,295 rows over 1.20–1.37, 3,260 high and 35 low; 0–5 gates per release give 2+ stages, 0–1 a typo stage; 94–229 per release no longer cover their release (ranges ended; removed after GA).
- **KEPs:** 113 current versions; 65 name a gate (70 have the key, 5 empty); 9 name several. 42 of 65 have no observation at 1.37 (gate removed after GA). Gates disagree in 25 of 1,918 KEP × release pairs. Claims differ from the observation in 119 of 442 pairs (claims run ahead of releases: S10's concern). 15 gate names in current KEPs match no reference name (typos such as `MixedProtocolLBSVC`, or never shipped). Two gates were renamed in their files (`APIServingWithRoute` → `APIServingWithRoutine` at 1.33; `ServiceAcccountNodeAudienceRestriction` → `ServiceAccountNodeAudienceRestriction` at 1.35): KEP-4412 matches only by the release's own name.
- **Weights prototype** (temporal pools: rerank order with scores; tiers and weights as below):

| Variant | Recall@10 | Hit@10 | MRR | nDCG@10 | Authority sel. | CURRENT MRR | Reorderings > 2 logits |
|---|---|---|---|---|---|---|---|
| temporal | 0.5596 | 1.0000 | 0.7586 | 0.5351 | 5 / 9 | 0.637 | — |
| **A: ×1.25 / ×0.8 on the probability (chosen)** | **0.5522** | **1.0000** | **0.8133** | **0.5348** | **9 / 9** | **0.783** | 66 of 228 |
| A at ×1.5 / ×0.67 | 0.5522 | 1.0000 | 0.8133 | 0.5365 | 9 / 9 | 0.783 | 76 of 254 |
| B: +2 / −2 on the raw score | 0.5568 | 1.0000 | 0.7832 | 0.5333 | 8 / 9 | 0.708 | 6 of 253 |
| C: after RRF (ADR-003 as written) | = temporal | | | | | | none: rerank re-sorts the pool |

  - By mode alone (A): CURRENT MRR +0.041, Recall −0.006; WHY MRR +0.014, Recall +0.002; CHANGE Recall −0.004 (q07, golden HISTORY, routed CHANGE).
  - Tiers by source type give the identical ranking to tiers that depend on validity, because D4's CURRENT boost needs "valid at the latest release" (q16's CHANGELOG-1.2x section, current but valid only at its release, isn't boosted).
  - Stale 0 of 100 and in-window 47 of 90 are unchanged by the weights.
- **Authority-selection baselines** (same tier rules, saved top 10s): dense 3/9 (CURRENT MRR 0.467), hybrid 2/9 (0.692), rerank 5/9 (0.588), temporal 5/9 (0.637), authority 9/9 (0.783). The old modes reproduced their pinned retrieval numbers and R1's stale and in-window counts exactly.
- **Flipped-tier check** (tier t → 7 − t in the tier function only): authority mode gives 6 of 9 (from 3 of 9 under flipped tiers) but CURRENT MRR 0.628 (from 0.637), Recall 0.5584, MRR 0.7702, nDCG 0.5236. Real tiers: CURRENT MRR 0.783. The metric leans toward the weights; CURRENT MRR doesn't.
- **Devil's advocates** (3, fresh context): weights act more like a cutoff than a nudge and were tuned on v0 (answered by B's row and the ×1.5 row); the metric grades itself (answered by the fixed denominator and the flipped-tier check); validity inside the tier adds nothing to the ranking (adopted: tiers by type).
- **Cost** of `make eval`: rerank's row is $0.031 per question, so 3 runs of 43 questions ≈ $4.

#### Decisions (made in the sitting, 2026-10-10)

| # | Choice | Rejected | Why |
|---|---|---|---|
| 1 | Bundle T5–T8 (T8 added by the developer). R1 parked items: drop #1, 3, 7, 9, 13, 14, 15; keep #2+4+16 ("R1 cleanup"), #6, #10, #11+12 (trace coverage), #17, #18 as proposed additions; fold #5 and #8 into T7. Drop "near-duplicate crowding" (temporal: 8.3 distinct sections per top 10) | T5–T7 only | T8's two open points became rules (decisions 5 and 10) |
| 2 | R1's questions: a future window ("in 1.40") keeps current text (the R1 edge-case line is corrected); "after 2010" starts at the first release (added to the pinned table); estimate tests at 1.5× the source | Make future windows empty | Only HISTORY routes get a window; a future-release question rarely reaches it |
| 3 | **Weights after the reranker, on its probability:** sort by sigmoid(score) × factor; boost ×1.25, demote ×0.8, in config (ADR-003 D4 change) | +2 on the raw score; after RRF | Best MRR (+0.055), clears the +0.03 bar; +2 gives +0.025; after RRF does nothing |
| 4 | **Authority-selection accuracy:** golden CURRENT questions whose labeled documents span 2+ tiers (fixed by the labels: 9 on v0); right when the first labeled top-10 hit has the best label tier; no tier = worst. CURRENT MRR printed beside it; the flipped-tier check is a T7 proof item | MRR only; a denominator taken from the hits | The spec names this metric; a label-fixed denominator can't shrink; MRR guards the lean |
| 5 | **Thresholds:** the final mode's result, loosened by one unit of its own count (1 hit or 1 question), rounded to 2 decimals toward the loose side; router keeps ≥ 0.90 (ADR-009). T8 writes them into the product spec; the merge confirms them | Approve in the morning; round targets now | Decided in the sitting; only arithmetic is left |
| 6 | *(rec.)* **Gate stages:** one row per gate × release; blank + low when unclear; a typo stage kept as written + low | A row per stage; raw ranges | One fact per gate per release; ≤ 5 unclear rows per release |
| 7 | *(rec.)* **The CHANGELOG as a stage source, and a claimed `disabled`, deferred to S10** (ADR-003 change) | Parse release notes now | Free text; only S10's conflict check needs it |
| 8 | *(rec.)* **Tiers by source type;** KEP tier 3 when shipped by the target release or implemented, else 5; withdrawn, rejected or replaced: "superseded proposal" (no tier). D4's CURRENT boost needs "valid at the latest release" (ADR-003 D3 change) | A tier that depends on validity | Same ranking; every citation gets a tier (AC1) |
| 9 | *(rec.)* **A new `authority` mode** (temporal + weights); every mode attaches tiers | A switch inside temporal | One mode per ablation stage; every stage prints the metric |
| 10 | *(rec.)* **T8:** a free gate before any paid call; T8 runs `authority` if its `make eval-retrieval` passes the improvement rule against `temporal` (authority selection +0.03, no retrieval metric −0.03), else `temporal` | — | No paid run on unverified code |
| 11 | **1 PR**, an explicit exception to the ~800-line alarm (estimate ~2,000). Paid calls as listed below | 2 stacked PRs split after T6 (recommended) | The developer's call |

**Claude's calls (overrulable):**

- **Layout:**
  - `db/migrations/versions/0006_observed_lifecycle.py`: the table below.
  - `ingestion/lifecycle.py`: pure functions (parse a table page's rows; turn a gate file's `stages` into ranges; the stage at a release), plus `main()` for `make lifecycle` (reads stored versions and the clone, writes the table).
  - `db/lifecycle.py`: replace all rows in one transaction; read a release's inputs; `observations(conn, gates, until_release)`; the newest version's tier inputs per document (for the labels).
  - `retrieval/authority.py`: pure functions `target_release`, `kep_stage`, `tier`, `factor`, `weigh`.
  - `db/models.py`: `Authority(target_release: int, tier: int | None, effective_stage: str | None, stage_confidence: Literal["high", "low"] | None)`; `Hit.authority: Authority | None = None` (set in every mode); `Hit.authority_score: float | None = None` (authority mode only). `tier` None means a superseded proposal.
  - Metric functions in `eval/metrics.py`, as pure functions.
- **Migration (pinned):**

  ```sql
  CREATE TABLE observed_lifecycle (
      gate              text NOT NULL,
      release           smallint NOT NULL,
      stage             text,
      status_confidence text NOT NULL,
      CONSTRAINT observed_lifecycle_pkey PRIMARY KEY (gate, release),
      CONSTRAINT observed_lifecycle_release_fkey FOREIGN KEY (release) REFERENCES releases (minor),
      CONSTRAINT observed_lifecycle_status_confidence_check
          CHECK (status_confidence IN ('high', 'low')),
      -- high: one stage from the vocabulary; low: no stage, or a value kept as written
      CONSTRAINT observed_lifecycle_high_check CHECK (
          status_confidence = 'low' OR stage IN ('alpha', 'beta', 'stable', 'deprecated'))
  )
  ```

- **T5 rules (pinned):**
  - **Release R's snapshot:** 1.20–1.28: the table rows of the `feature-gates` and `feature-gates-removed` page versions valid at R, read from the clone at their `snapshot_sha` (both pages' rows for a gate are joined). 1.29+: every `gate:` document's version valid at R (one per gate), named by its front-matter `title` at R, ranges from its `stages`.
  - **A table row** is a line `| \`Name\` | default | stage | from | until |` (the spike's pattern; `Since | Until` or `From | To`); an empty cell or `-` is an open end.
  - **A version** is a string `v?1.N(.P)?(-alpha|beta|rc.M)?`; its minor is N. Anything else, a YAML number included, is unparseable.
  - **The stage at R:** a range covers R when from-minor ≤ R ≤ to-minor (open end: open). Any range with an unparseable bound → blank, low. No covering range → no row. The covering ranges' distinct stages, after strip, lower case and `ga` → `stable`: one in {alpha, beta, stable, deprecated} → that stage, high; one outside → the cell as written (stripped), low; 2+ → blank, low.
  - **Writes:** delete every row, then insert, in one transaction; releases 1.20 to the latest in `releases`.
  - `make lifecycle` (`python -m orgknow.ingestion.lifecycle`) rebuilds the table; `make ingest` runs the same step after chunking, before its report. Output (pinned): `Observed lifecycle: 3295 rows over 18 releases (3260 high, 35 low).`
- **T6 rules (pinned):**
  - **Target release:** CURRENT → the latest release; HISTORY with a window → its `until_release`, capped at the latest (no `until` → the latest); CHANGE, WHY, HISTORY without a window, and dense, hybrid and rerank modes (no route) → the latest.
  - **KEP gates:** the `name`s in the cited version's `feature-gates` list (exact match, as written).
  - **Shipped by R:** one of its gates has a row (any stage, blank included) at a release ≤ R.
  - **Effective stage at R:** the gates' rows at R: if all are high and give one stage → that stage, high; else the version's `claimed_stage`, low; no claim → None (confidence None). Only KEPs get one.
  - **Tier:** `docs_page` and `feature_gate_reference` 1, `release_record` 2, `governance_doc` 4, `blog_post` 6. `kep`: `claimed_status` withdrawn, rejected or replaced → None (superseded proposal); shipped by R or `implemented` → 3; else 5.
  - `retrieve` attaches `authority` to the returned hits in dense, hybrid, rerank and temporal modes (one `observations` read per question), and to the whole pool in authority mode before the weights.
  - **The prompt (pinned):** each block's second line is `authority: tier N` or `authority: superseded proposal`. A KEP block's claim line is followed by `stage at 1.R: S (observed)` (high), `stage at 1.R: S (claimed, not observed)` (low) or `stage at 1.R: unknown`. The system prompt's paragraph becomes: "Each chunk starts with a line giving its id and the releases it was valid in ("now": still valid in the latest release), then its authority tier (1 = docs and feature-gate pages, 2 = release notes, 3 = shipped KEPs, 4 = governance docs, 5 = unshipped KEPs, 6 = blog posts). A KEP chunk adds the status and stage the KEP claimed, and its stage at the asked-about release."
  - **Citations:** `Evidence` gains `tier: int | None`, `superseded_proposal: bool`, `effective_stage: str | None` and `stage_confidence`. AC1's check also requires a tier, or `superseded_proposal`.
- **T7 rules (pinned):**
  - **Factor, by the routed mode.** Each hit gets one factor; the first matching rule wins:
    - CURRENT: tier 1 or 2 and some release window contains the latest release → boost; `blog_post` → demote.
    - CHANGE: `release_record` → boost.
    - WHY: a `kep` hit with a heading containing "motivation" or "alternatives" (case-insensitive) → boost; `blog_post` or `governance_doc` → boost; `feature_gate_reference` → demote.
    - HISTORY, or anything else: 1.
  - **Authority mode:** temporal's pool, reranked whole (rerank order), tiers attached, then sorted by `round(sigmoid(rerank_score) × factor, 4)` descending, ties keeping rerank order; the top RETRIEVAL_TOP_K. `authority_score` = the unrounded product. An empty pool → `[]`, no reranker call. It needs a route (`ValueError` without one), like temporal.
  - **The metric:** per golden CURRENT question, the label tiers (each label's document, newest version, at the latest release; None = worst) and its top-K hits' tiers. Counted when the label tiers hold 2+ distinct values; right when a top-K hit matches a label and the first one's tier equals the best label tier. Result (right, counted), or None when nothing counts or a counted question lacks tiers.
  - **CURRENT MRR:** the mean MRR over the golden CURRENT questions (printed only).
- **Settings:** `RETRIEVAL_MODE` gains `authority` (the default stays `rerank` until T8, which sets it to the final mode). `AUTHORITY_BOOST` (default 1.25, 1–4) and `AUTHORITY_DEMOTE` (default 0.8, > 0 and ≤ 1). `.env.example` lists both. Boost 1 and demote 1 give temporal's ranking exactly.
- **Eval files:** `run.json` settings gain `authority_boost` and `authority_demote` (None outside authority mode); authority mode records the router fields and routes as temporal does. Each hit gains `authority` (and `authority_score`); each row gains `label_tiers` (golden label order). All optional, so old folders load. Summary gains `authority: Rate | None`; the table gains `Authority sel.` after `Router acc.` (`n/a` for older rows).
- **`ask` in authority mode:** as temporal (live route, route line); citations carry the tier.
- **Trace:** the `retrieve` span records each hit's tier and, in authority mode, its factor and `authority_score` (not tested: the trace-coverage proposed addition).
- **R1 parked #5 and #8 (folded into T7):** the architecture doc's metrics row names all metric functions; `score_retrieval_only` returns a small named model instead of a tuple.
- **Docs:** ADR-003's S09-R2 change table (in this commit); `docs/architecture.md` (lifecycle, tiers, authority mode); README (`authority` mode, `make lifecycle`); `docs/evaluation.md` (the metric's definition and its lean, the side table's authority row and column, T8's write-up); the product spec's thresholds (T8); glossary: "authority tier" and "feature gate" if absent.

#### Pinned: output formats

`make eval-retrieval`, authority mode:

```
Mode: authority (candidates 20, k 60, width 100, model BAAI/bge-reranker-base@2cfc18c, max length 512, router claude-opus-5-5, slack 1, boost 1.25, demote 0.8). Answerable questions: 36.
Recall@10 0.552  Hit@10 1.000  MRR 0.813  nDCG@10 0.535
Stale rate 0.000 (0 of 100 CURRENT hits)  Temporal accuracy 0.522 (47 of 90 dated HISTORY hits)
Authority selection 1.000 (9 of 9 CURRENT questions)  CURRENT MRR 0.783
Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  Plans: 10 current-only, 7 windowed, 19 unfiltered
Retrieve time: p50 4.91 s, p95 6.14 s (36 questions). Reranker load 7.4 s.
```

- Times are examples. Every other mode adds the authority line after its stale/temporal line, and every other line stays as it is today:

| Mode | Authority line |
|---|---|
| dense | `Authority selection 0.333 (3 of 9 CURRENT questions)  CURRENT MRR 0.467` |
| hybrid | `Authority selection 0.222 (2 of 9 CURRENT questions)  CURRENT MRR 0.692` |
| rerank | `Authority selection 0.556 (5 of 9 CURRENT questions)  CURRENT MRR 0.588` |
| temporal | `Authority selection 0.556 (5 of 9 CURRENT questions)  CURRENT MRR 0.637` |

**Side table** in `docs/evaluation.md` ("Time scores by stage", renamed "Time and authority scores by stage"): gains the `Authority selection` and `CURRENT MRR` columns and an `authority` row (0.552, 0.813, 0.000, 0.522, 1.000, 0.783, the run's router value).

#### Pinned: T8

1. **Free gate:** `RETRIEVAL_MODE=authority make eval-retrieval` and `RETRIEVAL_MODE=temporal make eval-retrieval` print the pinned lines. Any difference → park T8 with $0 spent.
2. **Mode rule:** authority if, against temporal, authority selection rises ≥ 0.03 and no retrieval metric drops > 0.03 (the prototype: +0.444; Recall −0.007); else temporal. The brief states which, with the numbers.
3. **3 paid runs:** `RETRIEVAL_MODE=<final> make eval`, the usual results-folder names; then `make eval-table`.
4. **Write-up** in `docs/evaluation.md`: the S09 row against `rerank` under the improvement rule (stale, temporal and authority selection as the targets; Recall/MRR/nDCG/Hit within 0.03; AC1–AC3 and false refusals against the baseline's range), CURRENT MRR, cost per question, p95 latency, and the router's separate timing (R1).
5. **Thresholds** (decision 5) into the product spec's thresholds table. With the prototype's numbers: stale ≤ 0.01 (from 0 of 100), temporal ≥ 0.51 (from 47 of 90), authority ≥ 0.88 (from 9 of 9), router ≥ 0.90 (kept).
6. `RETRIEVAL_MODE`'s default becomes the final mode (settings, `.env.example`, README).

#### Handoffs between tasks

- T5 → T6: the table and `observations`.
- T6 → T7: `Hit.authority` in every mode, the target release, the label tier inputs.
- T7 → T8: the `authority` mode, the metric, the table column.
- If T5 parks, T6 still ships (KEPs fall back to their claims); its KEP examples and the 82 / 25 / 6 split park. If T6 parks, T7 parks. If T7 parks, T8 runs temporal, and the authority threshold parks.

#### Edge cases

- **A gate listed on both pre-1.29 pages:** its rows are joined (`DaemonSetUpdateSurge` at 1.27: stable, high, from the main page's open row; a known limit).
- **A renamed gate:** each release names it as its own file does; no aliasing.
- **Same stage over a patch boundary** (beta 1.35.0–1.35.3, beta 1.35.4–1.36): high. **A stage change at a patch:** 2 stages → blank, low.
- **A KEP with no gate, an unmatched gate name, or no claim:** tier by status; effective stage = the claim (low) or None.
- **A superseded proposal:** no tier, never boosted; AC1 accepts it.
- **A current CHANGELOG section of an older release:** tier 2, but not valid at the latest release, so CURRENT doesn't boost it.
- **Boost 1, demote 1:** temporal's ranking exactly.
- **Ties after rounding:** rerank order (a saturated probability, e.g. 0.9999, ties).
- **An empty pool or a filter that keeps nothing:** `[]`, no reranker call, `insufficient_evidence` in `ask`.
- **Old results folders:** no `authority` or `label_tiers`; they load, and the authority metric is None (`n/a`).

#### Files in scope

- **New:**
  - `src/orgknow/db/migrations/versions/0006_observed_lifecycle.py`
  - `src/orgknow/ingestion/lifecycle.py`, `src/orgknow/db/lifecycle.py`, `src/orgknow/retrieval/authority.py`
  - `tests/unit/test_lifecycle.py`, `tests/unit/test_authority.py`, an integration test of the table and `observations`, and a small table-page fixture in `tests/fixtures/`
  - T8's 3 results folders under `eval/results/`
- **Changed:**
  - Config: `Makefile` (`lifecycle`), `.env.example`
  - Code: `src/orgknow/settings.py`, `src/orgknow/db/models.py`, `src/orgknow/ingestion/ingest.py`, `src/orgknow/retrieval/retrieve.py`, `src/orgknow/generation/{prompt,schema}.py` and where `Evidence` is built, `src/orgknow/cli.py`, `src/orgknow/eval/{runner,metrics,checks,table,__main__}.py`
  - Results: `eval/results/ablation.md` (regenerated)
  - Docs: `README.md`, `docs/{architecture,evaluation,product-spec}.md`, `docs/learning/glossary.md`, `docs/backlog.md` (ticks)
  - Tests that build a `Hit`, `Evidence`, a row, a summary, the prompt or the table
- **Not touched:** `eval/golden_set/`, `eval/question_vectors/`, `eval/question_routes/`, earlier migrations, chunking, every older results folder.

#### Proof map

| Task | Done when / rule | Proof | Expected values from |
|---|---|---|---|
| T5 | Stage rules | Unit: alpha 1.22–1.22, beta 1.23–1.24, GA 1.25–1.27 → 22 alpha high, 25 stable high, 28 no row; alpha 1.14– and beta 1.17– at 20 → blank low; `True` 1.19– at 20 → `True` low; GA 1.22–`1,24` at 25 → blank low; beta 1.31.0–1.31.0 and deprecated 1.31.1– at 31 → blank low; beta 1.35.0–1.35.3 and beta 1.35.4–1.36 at 35 → beta high; a version given as a YAML number → unparseable; a table page fixture with `Since \| Until`, `From \| To`, `-` and empty cells | By hand |
| T5 | **Real table** | `make lifecycle` prints the pinned line; per release, rows (high / blank / typo): 20: 152 (147/4/1), 21: 170 (167/2/1), 22: 196 (192/3/1), 23: 216, 24: 224, 25: 144 (143/1/0), 26: 146 (145/1/0), 27: 147 (145/1/1), 28: 154 (153/1/0), 29: 159, 30: 159 (155/4/0), 31: 161 (160/1/0), 32: 172 (171/1/0), 33: 181 (180/1/0), 34: 201 (199/2/0), 35: 216 (214/2/0), 36: 238 (236/2/0), 37: 259 (254/5/0). Spot rows: PodSecurity 22 alpha high, 25 stable high, 28 none; EventedPLEG 29 beta high, 30 alpha high; CSIMigrationAWS 20 blank low; LegacyNodeRoleBehavior 20 `True` low; SetHostnameAsFQDN 25 blank low; APIServingWithRoutine 33 alpha high, APIServingWithRoute 33 none; DRADeviceTaints 37 blank low | Sitting probe |
| T5 | Repeatable | A second `make lifecycle` and a `make ingest`: the sha256 of the sorted rows is unchanged | — |
| T5 | Schema | Integration: a high row with stage `True` and a row for release 99 are rejected; the rebuild is all-or-nothing | The migration |
| T6 | Rules | Unit: each type's tier; KEP withdrawn → None, implementable with a gate seen at 25 only and target 37 → 3, implementable never seen → 5, implemented never seen → 3; effective stage: one high stage at R → it, high; 2 gates disagree → claim, low; nothing at R → claim, low; no claim → None; target release: CURRENT 37, HISTORY until 27 → 27, from 30 → 37, until 40 → 37, CHANGE → 37, no route → 37 | By hand |
| T6 | **Real KEPs** | KEP-2579 at 37: stable (claimed, low), tier 3; at 22: alpha (observed, high), tier 3. KEP-4858 at 37: beta (observed, high), claim stable, tier 3. KEP-2799 at 26: beta (claimed, low). KEP-4412 at 37: beta (observed, high). Current KEP versions at 37: 82 tier 3, 25 tier 5, 6 superseded | Sitting probe |
| T6 | Prompt and AC1 | Unit: the pinned lines in a KEP and a docs block; AC1 fails a citation with no tier that isn't a superseded proposal | The contract |
| T6 | Old modes unchanged | dense 0.384 / 0.944 / 0.614 / 0.369; hybrid 0.382 / 0.944 / 0.675 / 0.385; rerank 0.516 / 0.972 / 0.703 / 0.489; temporal 0.560 / 1.000 / 0.759 / 0.535; their stale/temporal lines as R1 | S06–S09-R1 |
| T7 | Weights | Unit: CURRENT, logits 2.0 (blog), 1.0 (docs, current), −1.0 (docs, current) → 0.8808 × 0.8 = 0.7046, 0.7311 × 1.25 = 0.9138, 0.2689 × 1.25 = 0.3362 → docs, blog, docs; equal products keep rerank order; each mode's factor table; boost 1 and demote 1 → the input order | By hand |
| T7 | Metric | Unit: label tiers {1, 6}, first labeled hit tier 6 → counted, wrong; {2, 4}, first 2 → right; one tier only → not counted; no labeled hit → counted, wrong; a None label tier is worst; a question whose labeled top-10 hits share one tier but whose labels span 2 → counted | By hand |
| T7 | **Gate** | `RETRIEVAL_MODE=authority make eval-retrieval` → the pinned lines (0.552 / 1.000 / 0.813 / 0.535; 0 of 100; 47 of 90; 9 of 9; CURRENT MRR 0.783); each other mode's authority line as pinned | Sitting prototype |
| T7 | Flipped tiers | The tier function returns 7 − t (None stays): authority mode → Recall 0.558, MRR 0.770, nDCG 0.524, authority 6 of 9, CURRENT MRR 0.628; restored, `git diff` clean | Sitting prototype |
| T7 | Settings and table | Unit: `AUTHORITY_BOOST=0.9` and `AUTHORITY_DEMOTE=1.1` → validation errors; authority mode without a route → `ValueError`. `make eval-table`: older rows unchanged except one `n/a` | The contract |
| T8 | Gate, row, write-up, thresholds | The free gate's output; 3 results folders; the table row and spread; the write-up's pass/fail; the spec's 4 thresholds by decision 5 | T7's gate; decision 5 |

If a pinned number differs, the task parks that item (with both numbers) and keeps the code, as in R1.

#### Break-it rules

- T5: take the first covering range instead of flagging 2+ stages → the "alpha 1.14– and beta 1.17–" test fails.
- T6: "shipped" = observed at the target release only → the "gate seen at 25 only, target 37 → 3" test fails.
- T7: multiply the raw score instead of the probability → the hand-worked ordering test fails (the blog ranks first).

#### Real-data demo

```bash
make lifecycle && make lifecycle
for m in dense hybrid rerank temporal authority; do RETRIEVAL_MODE=$m HF_HUB_OFFLINE=1 make eval-retrieval; done
RETRIEVAL_MODE=authority HF_HUB_OFFLINE=1 uv run orgknow ask "What enforces pod security standards in-tree?"
RETRIEVAL_MODE=authority HF_HUB_OFFLINE=1 uv run orgknow ask "Does the API server reject IP addresses with leading zeros by default?"
```

- The first ask's top citation should be a docs page (tier 1), where temporal ranked a blog first. The second should cite KEP-4858 with `stage at 1.37: beta (observed)` beside `claimed: implemented/stable`. The Langfuse trace links go in the brief.

#### Bundle-level check

1. `make check`.
2. `make test-int` (Postgres checked healthy at run start; the migration applied to the dev database with `make migrate` before T5's real-data steps).
3. `make eval-retrieval` in all 5 modes: the pinned lines.
4. `make eval-table`: older rows unchanged except the new `n/a` cell; the S09 row present.
5. `git status --short`: only intended files.

#### PR plan

1 PR, above the ~800-line alarm by the developer's choice (decision 11; estimate ~2,000 reviewable lines, plus results). Greptile: 1 trigger (14/50 used before the run).

#### Paid calls allowed

- **Anthropic answers:** T8's 3 × `make eval` (≤ 129 calls) and ≤ 2 demo asks.
- **Anthropic router:** ≤ 2 calls (the demo asks); the eval uses stored routes (≤ 43 more only if a route is missing).
- **Voyage:** ≤ 2 requests (the demo asks); the eval uses stored vectors.
- **Cap:** $7 for all of them.
- **Langfuse:** traces of the demo asks and the eval's asks.
- **Hugging Face:** none (`HF_HUB_OFFLINE=1`; the reranker is cached).
- **Package installs:** none.
- **Local reads** of the website clone (T5's 13 table files) are allowed; no other network calls.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S09-*.md`
