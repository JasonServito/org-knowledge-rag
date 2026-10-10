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
| `observed_lifecycle` from the feature-gate reference; `effective_stage`; tiers | The CHANGELOG as a stage observation (decided in the R2 sitting; S10 candidate) |
| Authority multipliers in config | Learned weights; tuning beyond a small sitting prototype |
| The S09 eval run and its row | Golden set changes (v0 is frozen); BM25 (proposed addition); conflicts (S10) |

## Metric to move

- **Stale-result rate** (CURRENT, lower is better) and **temporal accuracy** (HISTORY with a window, higher is better): the temporal stage's targets.
- **Authority-selection accuracy:** the authority stage's target (defined in the R2 sitting).
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
- **Done when:** decided in the R2 sitting.
- **Deps:** none.

### S09-T6: `effective_stage` and authority tier per hit `[core]`

- **Goal:** each hit carries its tier (ADR-003 D3) for the question's target release; KEPs use `effective_stage` through their `kep.yaml` feature gates (70 of 113 current KEP versions list gates); the tier reaches the prompt and citations (AC1).
- **Done when:** decided in the R2 sitting.
- **Deps:** T5.

### S09-T7: Authority multipliers and authority-selection accuracy `[core]`

- **Goal:** ADR-003 D4's boost and demote columns, from config, applied per mode; the authority-selection metric.
- **Done when:** decided in the R2 sitting.
- **Deps:** T4, T6.

### S09-T8: S09 eval run `[commodity]`

- **Goal:** 3 paid runs of `make eval` in the final S09 mode; the row; the write-up; thresholds for the 4 S09 metrics in the product spec.
- **Done when:** the row and its spread are committed; `docs/evaluation.md` states pass or fail against the improvement rule with numbers.
- **Deps:** T7.

## Risks & unknowns

- **Later documents describe the past.** For HISTORY questions with a window, 7 of 41 labeled sources have no text within ±1 release of it (e.g. the 2021 cadence blog for "before 2021"). The ±1 filter still scored best (S09-R1 decision 2).
- **AC6 conflicts with the labels.** AC6 says cited evidence must be valid within the window, but v0 labels later documents as primary sources for HISTORY questions. Its definition is for the R2 sitting.
- **A hit cites the newest copy of its text,** even for a HISTORY question whose window holds an older copy. Its windows list shows both; AC6 must allow for it.
- **Router latency is unmeasured.** Opus at effort low adds one call to each live ask; the run measures it once (ADR-009).
- **Multipliers after RRF do nothing in rerank mode.** ADR-003 D4 applies them after RRF, but rerank re-sorts the whole pool by its own score. Their place needs an ADR-003 change (R2 sitting).
- **Tuning on the test set.** The filters are ADR-003's, chosen before any data, but v0 confirmed them; the router prompt was written from definitions, and checked on a blind rewording. v1 is the clean test.
- **CHANGELOG release records are valid only at their own release.** 26 of 105 non-HISTORY labels have no text valid at 1.37, so staleness is defined by replacement, not by release (S09-R1 decision 1).

## Decisions expected (ADRs)

- **ADR-009:** query-mode routing. Accepted in the S09-R1 sitting.
- **ADR-003 changes:** dated CHANGE retrieval deferred (R1, done); where multipliers apply and the CHANGELOG as an observation (R2 sitting).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S09-R1: route and filter by time

- **Status:** PR open
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
| after | from N + 1 | from the release in effect on (Y + 1)-01-01 |
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
- **A window outside the corpus** ("before 1.15", "in 1.40"): kept as numbers, so the filter matches nothing → `[]`.
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

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S09-*.md`
