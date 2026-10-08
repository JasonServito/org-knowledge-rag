# S06: Eval harness + golden set v0 + dense baseline

- **Status:** 🟨
- **Blueprint stage:** Stage 3 (§19: golden set, metrics, ablation table)
- **Started:** 2026-10-08
- **Finished:**

## Outcome

`make eval` scores a frozen golden set v0 (30–50 questions, verified by Claude and spot-checked by the developer: T5 decision 1) on today's pipeline (dense top-10 retrieval + one answer call), and the dense-baseline row is committed in the ablation table.

## Why now

- **Every later slice is measured against this row.** S07–S11 each add one stage and must show its delta against the dense baseline (AC7).
- **The corpus is final.** S05 fixed the chunk text and embedded all 21,552 texts; the baseline is measured on exactly that corpus.
- **The answer model freezes with the baseline** (ADR-006 D1): a later model change would make every later row incomparable.

## Exit checks

- [ ] ADR-007 (golden-set schema and labeling) is Accepted.
- [ ] Golden set v0: 30–50 questions, verified by Claude and spot-checked by the developer (T5 decision 1); every label matches at least one stored chunk; frozen.
- [ ] `make eval-smoke` (10–15 questions) and `make eval` (all) run end to end locally (AC8, second part).
- [ ] The dense-baseline row is committed in the ablation table, with its run-to-run spread.
- [ ] `docs/evaluation.md` defines each metric; the thresholds are recorded in the product spec.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| ADR-007: question file format, labels by document + heading path | Labels by chunk id (product spec: they must survive re-chunking) |
| Loader with a label check against the database | Editing `eval/golden_set/` by Claude (human-owned; Claude may propose candidates in a separate file) |
| Retrieval metrics: Recall@K, MRR, nDCG | Stale-result rate, temporal and authority accuracy, router accuracy (S09); conflict precision/recall (S10) |
| Answer checks AC1–AC3 | AC4–AC6 (S09, S10); an LLM judge for faithfulness (later, if a slice needs it) |
| Eval runner, results format, ablation-table generator, `make eval-smoke` / `make eval` | Streamlit inspector (S12 builds the dev UI; it would need a new dependency here) |
| The dense-baseline run, repeated to measure spread | Lexical search, RRF, reranking (S07, S08) |
| | Tiers on citations (S09, S04-R2 decision 5) |
| | Chunk-text changes; the 2 comment leftovers stay (S06 sitting, parked question 1) |

## Metric to move

n/a: S06 sets the baseline. It records Recall@10, MRR, nDCG@10, the AC1–AC3 pass rates, and cost and latency per question for the dense pipeline. Every later slice moves one of these.

## Tasks

These mirror `docs/backlog.md`; details live here.

### S06-T1: Golden-set format and loader `[core]`

- **Goal:** the question file format from ADR-007, read into typed models, with a check that every label exists in the database.
- **Done when:** a malformed file fails with the question id and field; a label matching 0 stored chunks is reported; hand-written fixtures cover each rule. A command lists a document's sections exactly as labels need them (S06-R1 decision 11).
- **Notes / pointers:** ADR-007; `db/models.py:Hit` (`canonical_id`, `heading_path`); aliases in `document_aliases`.
- **Deps:** ADR-007 decided in the sitting.

### S06-T2: Retrieval metrics `[core]`

- **Goal:** mark each retrieved hit relevant or not from the labels, then compute Recall@K, Hit@K, MRR, nDCG@K and the distinct-sections diagnostic (ADR-007 D3).
- **Done when:** each metric matches hand-calculated values on small hand-built rankings, including the edge cases (no relevant hit, all relevant, a question with no labels).
- **Notes / pointers:** pure functions; no database, no network.
- **Deps:** T1.

### S06-T3: Answer checks AC1–AC3 `[core]`

- **Goal:** per question, pass or fail on AC1 (citations present and resolved), AC2 (no citation outside the retrieved set) and AC3 (unanswerable → `insufficient_evidence` with a reason).
- **Done when:** each check passes and fails on hand-built answers.
- **Notes / pointers:** `generation/schema.py:Answer`, `Evidence`; `generation/validate.py` already rejects ids outside the retrieved set.
- **Deps:** T1.

### S06-T4: Eval runner and ablation table `[commodity]`

- **Goal:** `make eval-smoke` and `make eval` run every question through retrieval and answer, score it with T2 and T3, and write a results folder; a generator rebuilds the ablation table from all results.
- **Done when:** the contract's run on fixtures and a small real sample writes the pinned results format; a failed ask is a recorded row, not a crash.
- **Deps:** T2, T3.

### S06-T5: Write and verify golden set v0 `[human]`

- **Goal:** 30–50 questions from the 20 Appendix A seeds, with the blueprint §19.1 mix, labeled per ADR-007.
- **Done when:** the loader's label check passes on the file; Claude has verified every question against the stored text, and the developer has spot-checked a sample (1 per class plus 1 random). *(Reworded 2026-10-08, decision 1 below; was "the developer has verified every question".)*
- **Decisions (developer, 2026-10-08):**
  1. **Sign-off:** 3 independent Claude passes verify every question (the expected answer and each label against the stored chunk text); the developer spot-checks q40, q24, q18, q19, q48 and q21 (random, seed 20261008). Known limit: the other 37 questions have no human check.
  2. **Label breadth (A-primary):** label each fact's sources among the docs page (website or governance doc), the KEP, the gate file, the release's CHANGELOG section (`v1.X.Y >`, never alpha/beta/rc copies) and blog posts or sections about this topic. No pre-release copies, no passing mentions. Hit@K and MRR credit any labeled source; Recall@K reads as coverage of the primary sources. Rejected: every copy (A-strict: ~5–10 labels per question, Recall dominated by duplicates); one source per fact (B: good hits score 0); "any of" label groups (D: an ADR-007 change, moved to Proposed additions for v1).
  3. **Release range:** a source from outside `release_window` counts if it correctly describes the asked-about period (ADR-007: the window is what the question asks about); at least one source stored inside the range is labeled where one exists.
- **Candidates:** Claude's draft is `eval/candidates/v0-draft.yaml` (43 questions, 184 labels, label check passing); the developer copies it into `eval/golden_set/v0.yaml` after the spot-check.
- **Deps:** T1 (the format and the label check).

### S06-T6: Dense baseline `[commodity]`

- **Goal:** run `make eval` on the frozen v0, repeated to measure spread; commit the row; write `docs/evaluation.md`; record thresholds in the product spec.
- **Done when:** the row and its spread are committed; the spec lists a threshold per measured metric.
- **Notes / pointers:** paid (Anthropic); the model is confirmed in writing first (ADR-006 D1).
- **Deps:** T4, T5.

## Risks & unknowns

- **Labels by heading path match several chunks:** every version of a section, and every packed piece of a long one. Recall counts any of them; whether the right *version* was found is AC6's job (S09).
- **Run-to-run noise:** Voyage's question vector varies between calls (S04-T8: distances moved up to 0.0044, near-ties swapped), and the answer model reasons differently each run.
- **Some seed sources aren't in the corpus** (GitHub issues, PRs, a discussion, a source file). Labels can only name stored documents.
- **Labeling takes the developer hours**, and the run can't do it.

## Decisions expected (ADRs)

- ADR-007: golden-set schema and labeling. *(Accepted in the S06-R1 sitting.)*
- ADR-006 D1 revisit: confirm or switch the answer model before the baseline. *(Confirmed in the S06-R1 sitting: Opus 5.5 at medium; ADR-006 amendment 2026-10-08.)*

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S06-R1: eval harness

- **Status:** PR open
- **Branch:** `s06-r1-eval-harness`
- **Tasks, in this order:** S06-T1 (golden-set format and loader) → S06-T2 (retrieval metrics) → S06-T3 (answer checks AC1–AC3) → S06-T4 (eval runner and ablation table).
- **Closes the slice:** no. T5 (`[human]` labels) and T6 (the paid baseline) follow.
- **Goal (plain words):**
  - Read a question file with hand-written labels and check every label against the database.
  - Score each question's top 10 against its labels, and each answer against AC1–AC3.
  - One command runs a question file end to end and writes a results folder and the ablation table, ready for the developer's golden set.

#### Decisions (made in the sitting, 2026-10-08)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Triage of PR #30's 15 parked items: keep 4 (table-guard test, `counts_by_release` dead code, embed estimate order → Proposed additions; report snapshot → the S14 race entry); drop 3, 5, 6, 7, 8, 11; fix 12 and 13 in this commit; 1, 2 and 14 became the parked questions | Fixing each now | The dropped items have 0 real cases, are by design, or rest on a wrong premise (11: `make reset-corpus` keeps vectors, so a rebuild re-embeds only changed texts) |
| S2 | Parked question 1: the comment leftovers stay as known limits (5 texts mention `<!--`: 2 blocks in `changelog:1.22` and `kep:6283`, 2 inline comments, plus ~12 CHANGELOG lines without their PR-link tail) | Fix the CHANGELOG tails; fix all | ~20 of 21,552 texts (0.1%); a fix changes no heading, so labels are unaffected. Revisit if a golden question needs one of those lines |
| S3 | Parked question 2: the "no content reads on the corpus clones" rule is in the run-bundle builder brief and the `reviewer` agent; the memory entry is deleted | Block it in git config; keep it in memory | Subagents never see memory (S05-R3); config would break the fetch script |
| S4 | Slice doc approved; the Streamlit inspector is out of S06 (S12 has it); bundle T1–T4 | — | The harness on fixtures; labels and the paid baseline need the developer |
| 1 | ADR-007 D1: one YAML file; fields `id`, `question`, `mode` (optional when unanswerable), `answerable`, `expected_answer`, optional `release_window`, `smoke`, `labels` | `as_of` + `tags` (first draft); minimal fields | Devil's advocate: questions ask about ranges; S10 owns conflict cases; tags overlap `mode`. S09's fields are labeled once, while reading the sources |
| 2 | ADR-007 D2: a hit matches when its document is the label's (aliases resolved) and its heading path starts with the label's headings, compared heading by heading; no section = whole document; `""` = the intro only; duplicates and nested labels rejected; the check prints each label's match count | Exact sections; whole-document only for headingless documents; no alias lookup | One label per answer location; breadth is visible; a later KEP link needs no relabel. `""` added after drafting the demo labels (the PSA answer is in the page intro) |
| 3 | ADR-007 D3: binary relevance, each label credited once; Recall@10, Hit@10, MRR, nDCG@10; distinct sections as a diagnostic; averages over answerable questions | Every hit counts; graded labels; Hit@10 only | Near-duplicates can't inflate scores; both "any" and "all" views; S09's crowding fix stays measurable |
| 4 | AC1 is checked on source URL, release window and `source_type`; the spec notes tier joins citations in S09 | A base tier now | S04-R2 decision 5 moved tiers to S09 |
| 5 | The answer model is frozen: Opus 5.5 at medium (ADR-006 amendment) | Sonnet 5.5 | S04: $0.020–0.041 per ask, 0 reasoning tokens |
| 6 | `messages.parse` stays; a failed ask is a recorded row | `messages.create` (changes ADR-006 D2) | 0 cut-offs in S04 |
| 7 | Question vectors in a committed file, one per embedding model, keyed by the question text's sha256 | A DB table (migration, lost on reset); repeated runs | Retrieval becomes exactly repeatable |
| 8 | T6 runs `make eval` 3 times; the table shows the mean and min–max | 1 run | ADR-006 asks for the variance; retrieval is identical across runs by decision 7 |
| 9 | The tiny-section merge and Hugo shortcode experiments leave S06 (Proposed additions, post-baseline) | Before the baseline | Merging changes heading paths, so labels written now would need re-checking; S06 must freeze |
| 10 | Results: one folder per run (run settings, one row per question with each hit's document and section, a summary); `eval/results/ablation.md` rebuilt from the summaries | Summary only | A rule change means free re-scoring, not a paid re-run |
| 11 | A command lists a document's sections as labels need them | None | 1,830 heading paths hold backticks or shortcodes |
| 12 | **1 PR**; an explicit exception to the ~800-line size alarm (estimate ~1,400 reviewable lines) | 2 stacked PRs after T3 (recommended) | The developer's call in the sitting |
| 13 | The real-data demo uses `tests/fixtures/eval/demo.yaml` (seeds #6, #13, #10), labeled in the sitting and verified by the developer | Retrieval only; fakes only | The whole path proved on real data before the baseline |

ADR-007 D1–D3 each had a devil's advocate; their changes are folded in above and in the ADR.

**Claude's calls (overrulable):**
- **Layout:** `src/orgknow/eval/` with `golden.py` (models, YAML loading, the pure rules), `metrics.py`, `checks.py`, `runner.py`, `table.py`, and `__main__.py` (the commands). The label check's and section listing's SQL is in `src/orgknow/db/eval.py` (the only SQL).
- **Commands:** `python -m orgknow.eval run [--smoke] [--name NAME]` (default name `dense`), `check`, `sections CANONICAL_ID`, `table`; Make targets `eval-smoke`, `eval`, `eval-check`, `eval-sections DOC=…`, `eval-table`. `orgknow ask` is unchanged.
- **Settings:** `EVAL_GOLDEN_PATH` (default `eval/golden_set/v0.yaml`), `EVAL_RESULTS_DIR` (`eval/results`), `EVAL_VECTORS_DIR` (`eval/question_vectors`). A missing golden file is a one-line error, exit 1.
- **Run order:** load and validate the file → the label check (any 0-match label stops the run before any paid call) → embed the questions without a stored vector in one Voyage call and save the file → per question: retrieve, answer, score → write the folder → rebuild the ablation table.
- **Keys:** Anthropic is required; Voyage only when a vector is missing.
- **Errors:** an ask error (`cli.ASK_ERRORS`) becomes a row with `answer: null` and `error: "<Type>: <message>"`; the run continues and exits 0. An unanswerable question with an error fails AC3; an answerable one is n/a for AC1–AC3 and counted under errors.
- **False refusals:** each answerable question answered `insufficient_evidence` is flagged; the summary counts them (the Jev item's prerequisite; one boolean).
- **No Langfuse traces in eval runs:** the results folder is the record.
- **Docs:** `docs/architecture.md` (the eval module and its commands), README (commands), and the glossary if an interviewer would use a term (Recall@K, MRR, nDCG).

#### Pinned formats

**Golden-set file** (ADR-007 D1; the demo file is the example):

```yaml
version: v0
questions:
  - id: q06
    question: What enforces pod security standards in-tree?
    mode: CURRENT                # CURRENT | HISTORY | CHANGE | WHY; optional when answerable is false
    answerable: true
    expected_answer: PodSecurity admission, GA since v1.25.
    release_window: {until: "1.23"}   # optional; from/until inclusive, at least one
    smoke: true
    labels:
      - document: web:/docs/concepts/security/pod-security-admission/
        section: ""              # "" = intro; omitted = whole document; "A > B" = prefix
```

Validation errors name the question id and the field; unknown keys are errors.

**Label check output**, one line per label, then a total:

```
q06  web:/docs/concepts/security/pod-security-admission/  ""  4 texts
q13  gate:LegacyServiceAccountTokenCleanUp  (whole document)  3 texts
Labels: 4. Unmatched: 0.
```

**Section listing**, one line per distinct heading path in the document (any version), in order of first appearance (version date, then chunk ordinal), with its text count; the intro prints as `""`.

**Question vectors:** `<EVAL_VECTORS_DIR>/<embedding_model>.json` = `{"<sha256 hex of the question's UTF-8 text>": [1024 floats]}`, keys sorted, written with `json.dumps(..., sort_keys=True)`.

**Results folder** `<EVAL_RESULTS_DIR>/<name>-<YYYYMMDDTHHMMSSZ>/`:
- `run.json`: `name`, `started_at`, `finished_at` (UTC ISO), `git_sha`, `git_dirty`, `golden_path`, `golden_sha256` (of the file's bytes), `smoke`, `questions`, `settings` {`embedding_model`, `retrieval_top_k`, `generation_model`, `generation_effort`, `generation_max_tokens`}.
- `questions.jsonl`, one row per question in file order: `id`, `mode`, `answerable`, `hits` [{`rank`, `chunk_id`, `canonical_id`, `heading_path`, `distance`}], `answer` (the `ask` JSON, or null), `metrics` {`recall`, `hit`, `mrr`, `ndcg`, `distinct_sections`} (null when unanswerable), `checks` {`ac1`, `ac2`, `ac3`, `false_refusal`} (each true, false or null = n/a), `usage` {`input_tokens`, `output_tokens`, `thinking_tokens`} (or null), `latency_s`, `error`.
- `summary.json`: `name`, `golden_sha256`, `started_at`, `questions`, `answerable`, `errors`, the 5 metric means over answerable questions with metrics, `ac1` / `ac2` / `ac3` / `false_refusals` as {`pass` or `count`, `total`}, `input_tokens`, `output_tokens`, `latency_s_mean`.

**Metrics** (ADR-007 D3). K = `RETRIEVAL_TOP_K`. A hit matches at most one label (nested labels are rejected).

**Answer checks** (per question; null = n/a):
- AC1, when `answered`: ≥ 1 citation, and each has a non-empty `source_url`, `release_windows` and `source_type`.
- AC2, when there is an answer: every cited `chunk_id` is in the retrieved hits.
- AC3, when unanswerable: `insufficient_evidence` with a non-blank reason; an error row fails.
- False refusal, when answerable: `insufficient_evidence`.

**Ablation table** `eval/results/ablation.md`: a "generated, don't edit" line, then one row per (name, `golden_sha256`), in order of first run: Pipeline · Set (file name + first 8 hex of the hash) · Runs · Questions · Recall@10 · Hit@10 · MRR · nDCG@10 · AC1 · AC2 · AC3 · Errors. A value is the mean over runs to 3 decimals, with `(min–max)` when runs > 1; AC cells are pass rates. Folders without `summary.json` (e.g. `s04/`) are skipped.

#### Handoffs between tasks

- T1 → T2, T3, T4: `GoldenSet` / `Question` / `Label` models; `Label` holds the resolved `canonical_id` and the section as `None` (whole document), `[]` (intro) or a list of headings. Alias resolution happens in T1's database step, so T2 compares ids only.
- T2 and T3 are pure: (question, hits[, answer]) in, a record out. No database, no network.
- T4 owns all I/O: settings, the database, Voyage, Anthropic, files.

#### Edge cases

- A heading containing `->`, backticks or a shortcode: split only on `" > "` (0 headings contain it, measured 2026-10-08).
- A question with 0 hits (empty database): metrics all 0, distinct sections 0; `ask` returns `insufficient_evidence` without a model call.
- Fewer than K hits: the metrics use the hits returned; IDCG still uses min(labels, K).
- An unanswerable question with labels, or an answerable one without: a validation error.
- A label naming an alias whose document is also named by its `canonical_id` with the same section: a duplicate, rejected after resolution.
- A vector file missing or empty: treated as `{}`; a vector of the wrong length is an error.
- The golden file changes between runs: different `golden_sha256`, so a separate table row.

#### Files in scope

- New: `src/orgknow/eval/{__init__,__main__,golden,metrics,checks,runner,table}.py`, `src/orgknow/db/eval.py`, `tests/unit/test_eval_{golden,metrics,checks,table}.py`, `tests/integration/test_eval.py`, small fixtures under `tests/fixtures/eval/` (not `demo.yaml`, which is the sitting's), `eval/question_vectors/voyage-4-large.json` (the demo's 3 vectors).
- Changed: `src/orgknow/settings.py`, `Makefile`, `README.md`, `docs/architecture.md`, `docs/learning/glossary.md` (if needed), `docs/backlog.md` (ticks).
- Not touched: `eval/golden_set/`, `tests/fixtures/eval/demo.yaml`, chunking, retrieval and generation code.

#### Proof map

| Task | Done when / rule | Proof | Expected values from |
|---|---|---|---|
| T1 | Malformed files fail with id + field | Unit tests, one hand-written file per rule: missing field, unknown key, duplicate id, `mode` missing when answerable, labels on an unanswerable question, no labels on an answerable one, bad `release_window` (`from` > `until`, no key, not `1.N`), nested labels, a whole-document label next to a section label | Hand-written files |
| T1 | Section parsing | Unit: `"A > B"` → `["A","B"]`; `""` → `[]`; omitted → whole document; `"Beta -> GA > Test plan"` → 2 headings | ADR-007 D2 |
| T1 | 0-match labels reported; aliases resolved; duplicates after resolution rejected | Integration on a tiny hand-built test database | Rows inserted by the test |
| T1 | Demo label counts | `EVAL_GOLDEN_PATH=tests/fixtures/eval/demo.yaml make eval-check` | SQL in the sitting: q06 PSA intro 4, q06 blog intro 2, q13 changelog section 5, q13 gate 3 texts; `Unmatched: 0` |
| T1 | Section listing | `make eval-sections DOC=gate:LegacyServiceAccountTokenCleanUp` | SQL in the sitting: 1 section, `""` |
| T2 | Metrics | Unit, a seed-#8-shaped ranking: label A matched at ranks 5 and 8, label B never | By hand: Recall@10 0.5, Hit@10 1, MRR 0.2, nDCG@10 = (1/log₂6) ÷ (1 + 1/log₂3) = 0.38685 ÷ 1.63093 = **0.23720** |
| T2 | Edge cases | Unit: no hits → all 0; both labels at ranks 1 and 2 → all 1.0; one label at rank 1 only → Recall 0.5, nDCG 1/1.63093 = 0.61315; whole-heading compare: label `Install` vs hit `Installation` → no match | By hand |
| T2 | Distinct sections | Unit: 10 hits over 6 (document, section) pairs → 6 | Hand-built hits |
| T3 | Each check passes and fails | Unit, hand-built `Answer`s: answered with 0 citations (AC1 fail); a citation with an empty `source_url` or no windows (AC1 fail); a cited id outside the hits (AC2 fail); unanswerable answered (AC3 fail); `insufficient_evidence` with a blank reason (AC3 fail); an error row on an unanswerable question (AC3 fail); the passing case of each | Hand-built |
| T4 | Pinned results format | Integration with a call-counting fake embedder and a fake generator on the test database: `run.json`, `questions.jsonl`, `summary.json` keys and values | Fixture rows and fake outputs |
| T4 | A failed ask is a row | Integration: the fake generator raises `GenerationError` for one question | The fake's error text |
| T4 | Second run 0 Voyage requests | Integration: the fake's call count is 1, then 0 | — |
| T4 | Ablation table | Unit: 3 hand-made summaries (2 runs of one set, 1 of another) → the table text | Hand-calculated means and ranges |

#### Break-it rules

- T1: compare sections as raw strings (`startswith`) → the `Install` / `Installation` test fails.
- T1: drop the nested-label rule → its test fails.
- T2: credit every matching hit → the seed-#8 nDCG test fails (it becomes 0.38685 + 1/log₂9 over 1.63093).
- T3: skip the AC2 membership test → its failing case passes, so the test fails.
- T4: delete 1 stored vector → exactly 1 Voyage request on the next run.

#### Real-data demo

```bash
EVAL_GOLDEN_PATH=tests/fixtures/eval/demo.yaml make eval-check
make eval-sections DOC=gate:LegacyServiceAccountTokenCleanUp
EVAL_GOLDEN_PATH=tests/fixtures/eval/demo.yaml EVAL_RESULTS_DIR=<scratch>/demo make eval-smoke   # twice
```

The demo's results folders are not committed (they'd add a demo row to the ablation table); the brief quotes them. The 3 question vectors are committed.

#### Bundle-level check

1. `make check`
2. `make test-int` (Postgres checked healthy at run start)
3. The demo above: the check prints `Unmatched: 0` with the 4 sitting counts; 2 smoke runs → the second makes 0 Voyage requests, and its `hits` and `metrics` equal the first's (`diff` of the extracted fields)
4. `git status --short`: only intended files

#### PR plan

1 PR, above the ~800-line alarm by the developer's choice (decision 12). Greptile: 1 trigger (10/50 used before the run).

#### Paid calls allowed

- **Voyage** (free tier): ≤ 20 requests, for the demo's question vectors and the break-it.
- **Anthropic:** ≤ 15 asks (~$0.60 at most), for the demo smoke runs only. Nothing else.
- No other network calls. No content reads on the corpus clones.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S06-*.md`
