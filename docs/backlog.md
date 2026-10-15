# Backlog

This is the ordered list of slices and tasks. It is the single source for **what to do next**.

## Rules

| Rule | Detail |
|---|---|
| Slice status | ⬜ todo · 🟨 active · ✅ done. **Only the developer approves slice status changes (by merging the retro PR).** Exactly one slice is 🟨 at a time. |
| Task selection | The agent works on the first unchecked task in the 🟨 slice whose dependencies are done. The agent ticks `[x]` in the same PR that completes the task. |
| Task tags | `[core]`: the developer must deeply understand it, and the plan is approved per task (interactive) or in the sitting (runs). `[commodity]`: boilerplate; the agent proceeds once it has stated the plan. `[human]`: the developer does or decides it; never part of a run. |
| Git and PRs | Interactive tasks keep one task per branch and PR (`sNN-tY-name`). Runs use one PR per run (`sNN-rN-name`); see `CLAUDE.md`. Commits are `SNN-TY: <what>`. Claude merges only after the developer says "merge" and approves the prompt, and never pushes to `main`. |
| Runs | A sitting (`/plan-run SNN`) plans a bundle of tasks and writes its run contract; a run (`/run-bundle`) builds it unattended. See `CLAUDE.md`. |
| Detail level | Slices S01–S04 are detailed. Later slices have outcomes, exit criteria, and candidate tasks; they are refined into a slice doc (`docs/slices/`) when they become 🟨. |
| New work | Discovered work goes to **Proposed additions** at the bottom. The developer triages it; it never goes straight into the active slice. |
| Exit criteria | Every slice ends with its exit criteria met and a retro PR (`/slice-retro`) containing the slice brief and the status flip. |

**Stage mapping:** blueprint §29 stages are noted per slice. Stage 2 is split across S04 and S05, and Stage 3 happens in S06.

---

## Milestone M0: Foundation

### ✅ S01 Repo foundation *(Stage 1)*

- **Outcome:** a fresh clone runs `make up && make migrate && make check && make test-int` green locally and in CI.
- **Slice doc:** `docs/slices/S01-repo-foundation.md`

Tasks:

- [x] **S01-T1 `[human]` Accept ADR-004 (toolchain).**
  - Done when: ADR-004 status is Accepted, or amended and accepted.
- [x] **S01-T2 `[commodity]` Project scaffold.**
  - Contents: uv project, `src/orgknow/`, `pyproject.toml` (ruff, mypy strict, pytest), `.gitignore`, `.gitattributes`, `.python-version` (3.12), `.env.example`, one smoke unit test.
  - Done when: `uv run pytest` passes and `import orgknow` works.
  - Deps: T1.
- [x] **S01-T3 `[commodity]` Makefile + pre-commit.**
  - Targets: `fmt`, `check`, `test-int`, `up`, `down`, `migrate`. Pre-commit runs ruff.
  - Done when: `make check` is green.
  - Deps: T2.
- [x] **S01-T4 `[commodity]` Local Postgres.**
  - Docker Compose with a pinned pgvector image, healthcheck, and named volume. Settings module reads the DB URL from env.
  - Done when: `make up` reports healthy.
  - Deps: T3.
- [x] **S01-T5 `[commodity]` Alembic.**
  - Migration `0001` enables the `vector` extension. No domain tables yet.
  - Done when: `make migrate` is idempotent, and an integration test asserts the extension exists.
  - Deps: T4.
- [x] **S01-T6 `[commodity]` FastAPI skeleton.**
  - App factory, `GET /health` (liveness), `GET /ready` (DB ping).
  - Done when: integration tests cover both endpoints, and `/ready` returns 503 when the DB is down.
  - Deps: T5.
- [x] **S01-T7 `[commodity]` CI.**
  - GitHub Actions: `check` job, plus an `integration` job with a pgvector service container.
  - Done when: both jobs are green on a PR.
  - Deps: T6.
- [x] **S01-T8 `[human]` Docs + license.**
  - README quickstart verified from a fresh clone; pick the code license (MIT or Apache-2.0); stub `docs/architecture.md` describing the current state; write learning note S01.
  - Done when: a fresh clone following the README works.
  - Deps: T7.

### ✅ S02 Corpus spike *(validates ADR-002 and ADR-003)*

- **Outcome:** measured corpus numbers, with ADR-002 and ADR-003 accepted or amended on evidence.
- **Slice doc:** `docs/slices/S02-corpus-spike.md`

Tasks:

- [x] **S02-T1 `[core]` Manifest v0.**
  - `config/corpus_manifest.yaml`: repos, release range, SIG → path allowlists (Release/Auth/Network), the 4 traced KEPs, blog/CHANGELOG/governance sources.
  - Done when: the developer has reviewed it against ADR-002 D6.
- [x] **S02-T2 `[commodity]` Fetch script.**
  - `spikes/fetch.py` makes partial clones into `CORPUS_CACHE_DIR` (outside the repo) and records the SHAs.
  - Done when: SHAs are written to the spike report.
  - Deps: T1.
- [x] **S02-T3a `[core]` Versions.**
  - Per release: in-scope files and distinct versions after ADR-002 normalization and hashing, plus a `head` row for the date-scoped sources.
  - Done when: the per-release and per-source tables are in the spike report, and the hand checks match.
  - Deps: T2.
- [x] **S02-T3b `[core]` Tokens, chunks, cost.**
  - Estimated tokens and chunks (upper and lower bound, chunk-size sensitivity); embedding cost at current Voyage pricing (look it up); vector storage.
  - Done when: there is a cost table in the spike report.
  - Deps: T3a.
- [x] **S02-T4a `[core]` Renames.**
  - Run `git diff --find-renames` between adjacent release branches, on at least one known move in the Auth or Network docs. Grade every rename with an oracle: redirects or aliases for docs, the title for feature gates.
  - Done when: the report records precision (census plus hand-read sample), lists and classifies the unmatched add/delete pairs, and recommends a similarity threshold.
  - Deps: T2.
- [x] **S02-T4b `[core]` Blog identity.**
  - Break down the front-matter blog id changes by cause and by before/after publication. Score two identity rules: the latest date and slug applied backwards, and the Hugo URL from the permalink config.
  - Done when: the report has the breakdown, both rules' scores, and a `valid_from` note for T6.
  - Deps: T2.
- [x] **S02-T5a `[core]` Feature gates and latest release.**
  - Latest release number and branch (hand check); feature-gates page structure (stage per version?), and whether the pre-1.29 tables agree with the 1.29+ `stages:` ranges.
  - Done when: each has a yes/no plus an example in the report, with the agreement counts.
  - Deps: T2.
- [x] **S02-T5b `[core]` CHANGELOG, KEP and blog formats.**
  - Blog front-matter dates and in-place edit history; CHANGELOG section structure, plus one sampled immutability check; `kep.yaml` status typos.
  - Done when: each has a yes/no plus an example in the report.
  - Deps: T2.
- [x] **S02-T6 `[human]` Decide.**
  - Write `docs/research/corpus-spike-report.md`; amend ADR-002 and ADR-003 if needed; set them to Accepted.
  - Done when: both ADRs are Accepted and the cost estimate fits the budget.
  - Deps: T3a, T3b, T4a, T4b, T5a, T5b.

### ✅ S03 Domain model + migrations *(blueprint gap #3)*

- **Outcome:** a schema that encodes ADR-002/003 invariants, enforced by the DB or by tested code.
- **Slice doc:** `docs/slices/S03-domain-model.md`

Tasks:

- [x] **S03-T1 `[human]` ADR-005: data access approach.**
  - SQLAlchemy Core vs. psycopg with raw SQL. Discuss in chat first.
  - Deps: S02.
- [x] **S03-T2 `[core]` Write `docs/domain-model.md`.**
  - Entities, keys, constraints, and validity-window invariants. For example: at most one current version per `canonical_id`; windows of the same document don't overlap.
  - Done when: the developer has approved it.
  - Question from S02-T3b: store one vector per chunk row, or one per unique content hash that chunks reference?
    - **Per chunk row:** storage follows the spike's upper bound (229 MB at 512-token chunks, 1024 dimensions), and filtering by release or validity window stays on the chunk row.
    - **Per content hash:** storage follows the lower bound (109 MB). But one nearest-neighbour hit maps to several versions, so temporal filtering needs a join after the search.

    See `docs/research/corpus-spike-report.md` §3.
  - Deps: T1.
- [x] **S03-T3 `[core]` Migration `0002`.**
  - Tables: `releases`, `documents`, `document_aliases`, `document_versions`, `chunks`, `embeddings` (keyed by model).
  - Done when: it migrates up and down cleanly.
  - Deps: T2.
- [x] **S03-T4 `[core]` Data-access layer.**
  - Done when: integration tests prove every invariant in the domain model (for example, an overlapping window is rejected).
  - Deps: T3.
- [x] **S03-T5 `[commodity]` Seed the `releases` table.**
  - Loaded from the manifest (version, release date, end-of-life).
  - Done when: re-running the seed is idempotent.
  - Deps: T3.
- **Not in this slice:** the `search_vector` column (S07), `observed_lifecycle` (S09), and the relationships/decisions tables (S13).

### ✅ S04 First vertical slice: PSP → PSA *(Stage 2, narrowed)*

- **Outcome:** `orgknow ask "<question>"` returns a cited, structured answer over SIG Auth docs at every release from v1.24 to the latest (v1.37), plus KEP-2579. (Range widened from "v1.24 and the latest" in the S04-R1 sitting, so every stored window is exact; 1.20–1.23 need rename handling, S05.)
- **Slice doc:** `docs/slices/S04-first-vertical-slice.md`
- **Tests:** seeds #6–#10 (golden seeds in `docs/research/corpus_validation_gate.md` Appendix A).

Tasks:

- [x] **S04-T1 `[human]` ADR-006: generation model/provider and tracing.**
  - Covers the LLM for generation, structured-output method, and Langfuse Cloud setup.
  - Decided in the S04-R2 sitting (2026-10-06); committed as Accepted in the run PR.
- [x] **S04-T2 `[core]` Slice-scope ingestion.**
  - Snapshots → normalize/hash → versions with windows → stored.
  - Done when: a re-run creates 0 new versions (idempotent).
  - Deps: S03.
- [x] **S04-T3 `[core]` Markdown chunker.**
  - Structure-aware (heading path), with a deterministic metadata header.
  - Done when: unit tests pass on fixtures, including table and code-block preservation.
- [x] **S04-T4 `[commodity]` Embedding interface.**
  - Voyage provider, content-hash cache, and a fake for tests.
  - Done when: a second run makes 0 API calls.
- [x] **S04-T5 `[core]` Dense retrieval.**
  - pgvector cosine search with an HNSW index; returns chunks with version/window/tier metadata.
  - Done when: an integration test on fixtures passes.
  - Deps: T2–T4.
- [x] **S04-T6 `[core]` Generation.**
  - Structured output (`answer`, `answer_status`, `evidence[]`, `insufficient_evidence_reason`) plus a citation validator.
  - Done when: a citation outside the retrieved set is rejected in tests.
  - Deps: T1, T5.
- [x] **S04-T7 `[commodity]` CLI `ask` command + Langfuse trace per query.**
  - Deps: T6.
- [x] **S04-T8 `[human]` Run seeds #6–#10.**
  - Save the outputs to `eval/results/s04/` and write failure notes. Temporal confusion is expected; that's the motivation for S09.
  - Deps: T7.

---

## Milestone M1: Phase 1 complete (product spec AC1–AC8)

### ✅ S05 Stage 1 subset ingestion *(Stage 2)*

- **Outcome:** the full manifest is ingested and embedded: 3 SIGs × v1.20 → latest, the website release records, the feature gates, every KEP in the 3 SIG folders, CHANGELOG, blog, and governance docs. (Wording fixed in the S05 sitting, 2026-10-07: all KEPs, not 4; feature gates in; the embed is S05's last task.)
- **Exit:** re-ingesting yields identical counts and hashes (AC8, first part); counts match the spike within an explained tolerance.
- **Slice doc:** `docs/slices/S05-stage1-subset-ingestion.md`

Tasks:

- [x] **S05-T1 `[core]` Release-scoped website sources from 1.20.**
  - Docs pages of the 3 SIGs and the website release records, every release 1.20 → 1.37; `make reset-corpus`.
  - Done when: a re-run adds 0 versions, and the counts are explained against the spike.
- [x] **S05-T2 `[core]` Renames and aliases (ADR-002 D4).**
  - Done when: the 6 known moves are one document each.
  - Deps: T1.
- [x] **S05-T3 `[core]` Feature gates.**
  - Done when: the 1.32 file renames create no new documents.
  - Deps: T1, T2.
- [x] **S05-T4 `[core]` KEPs and governance docs (date-scoped, merge-time dating).**
  - Done when: a re-run adds 0 versions; KEP-2579's versions start at their merge times.
  - Deps: T1.
- [x] **S05-T5 `[core]` Blog posts.**
  - Done when: a re-run adds 0 versions; the counts are explained against the spike.
  - Deps: T1.
- [x] **S05-T6 `[core]` CHANGELOG.**
  - Done when: 18 documents, 371 patch sections; no sha512 rows in chunks; a set release `until` can't change.
  - Deps: T1.
- [x] **S05-T7 `[core]` Chunker fixes.**
  - Covers `{#id}` anchors, HTML tables with a blank line in a cell, the scanner re-check, and the oversize-block decision.
  - Done when: 0 heading paths contain `{#`; the RBAC page's 30 cut HTML tables are whole; the scanner matches markdown-it, or each difference is explained. (S05-R3 sitting: also cut oversize lists and tables, drop HTML comment blocks, and the "Downloads for" rule on every source.)
  - Deps: T1–T6.
- [x] **S05-T8 `[commodity]` Ingestion report with a fingerprint.**
  - Done when: two from-empty ingests print identical reports.
  - Deps: T1–T6.
- [x] **S05-T9 `[commodity]` Embed the full corpus.**
  - Done when: a second run makes 0 requests.
  - Deps: T7, T8.

### ✅ S06 Eval harness + golden set v0 + dense baseline *(Stage 3)*

- **Outcome:** a frozen golden set v0 (30–50 questions, verified by Claude and spot-checked by the developer) and a committed dense-baseline row in the ablation table.
- **Exit:** `make eval-smoke` and `make eval` work; `docs/evaluation.md` is written; thresholds are recorded in the product spec.
- **Slice doc:** `docs/slices/S06-eval-harness.md`. ADR-007 Accepted in the S06-R1 sitting.
- [x] **S06-T1 `[core]` Golden-set format and loader.**
  - Done when: a malformed file fails with the question id and field; a label matching 0 stored chunks is reported; hand-written fixtures cover each ADR-007 rule.
  - Deps: ADR-007.
- [x] **S06-T2 `[core]` Retrieval metrics.**
  - Done when: Recall@K, Hit@K, MRR, nDCG@K and distinct sections match hand-calculated values, edge cases included.
  - Deps: T1.
- [x] **S06-T3 `[core]` Answer checks AC1–AC3.**
  - Done when: each check passes and fails on hand-built answers.
  - Deps: T1.
- [x] **S06-T4 `[commodity]` Eval runner and ablation table.**
  - Done when: `make eval-smoke` writes the pinned results format; a failed ask is a recorded row; a second run makes 0 Voyage requests.
  - Deps: T2, T3.
- [x] **S06-T5 `[human]` Write and verify golden set v0.**
  - Done when: the label check passes, Claude has verified every question, and the developer has spot-checked a sample (reworded 2026-10-08; see the slice doc).
  - Deps: T1.
- [x] **S06-T6 `[commodity]` Dense baseline.**
  - Done when: 3 runs of `make eval` on the frozen v0 are committed with their spread; `docs/evaluation.md` is written; thresholds are in the product spec.
  - Deps: T4, T5.

### ✅ S07 Hybrid retrieval *(Stage 4)*

- **Outcome:** lexical + dense retrieval fused with RRF, and an ablation row showing the delta.
- **Slice doc:** `docs/slices/S07-hybrid-retrieval.md`
- **Metric to move:** MRR (≥ +0.03 over the dense baseline, per the product spec's improvement rule).

Tasks:

- [x] **S07-T1 `[core]` Lexical search.**
  - A migration adds the `search_vector` column + GIN index; a query returns the top N distinct texts by full-text rank.
  - Done when: integration tests on fixtures: an exact term ranks its text first; a text in several chunks appears once; no match → empty.
- [x] **S07-T2 `[core]` RRF.**
  - A pure function: ranked id lists in, one fused ranking with scores out.
  - Done when: unit tests match hand-calculated scores, including an id in one list only, ties and empty lists.
- [x] **S07-T3 `[core]` Hybrid retrieval and config.**
  - Dense N + lexical N → RRF → top K; mode, N, k and the HNSW search width in settings; `ask` and the eval use and record the mode; `make eval-retrieval` scores retrieval for free.
  - Done when: hybrid on fixtures returns the hand-predicted order; dense mode reproduces the baseline's retrieval scores.
  - Deps: T1, T2.
- [x] **S07-T4 `[commodity]` Hybrid eval run.**
  - Two eval fixes (dirty check, smoke rows), then 3 paid runs of `make eval` in hybrid mode; the row and the write-up.
  - Done when: the row and its spread are committed; `docs/evaluation.md` states pass or fail against the improvement rule with numbers.
  - Deps: T3.

### ✅ S08 Reranking *(Stage 5)*

- **Outcome:** a local BGE cross-encoder rerank stage, with an ablation row and the CPU p95 latency recorded.
- **Phase 1 gaps carried from S07** (developer, S07 retro): hybrid is at MRR 0.675 vs ≥ 0.69, and Recall@10 0.382 vs ≥ 0.46.
- **Slice doc:** `docs/slices/S08-reranking.md`
- **Metric to move:** Recall@10 (≥ +0.03 over hybrid, per the product spec's improvement rule; S08-R1 decision 4), with mean p95 ≤ 23 s.

Tasks:

- [x] **S08-T1 `[core]` ADR-008: reranker model, runtime and candidate count.**
  - Decided in the S08-R1 sitting (2026-10-09) from a measured prototype; committed as Accepted in the run PR.
- [x] **S08-T2 `[core]` Reranker module and `rerank` mode.**
  - A `Reranker` interface, the local cross-encoder and a fake; `rerank` mode reranks hybrid's whole pool and keeps the top K.
  - Done when: unit tests give the hand-predicted order; `make eval-retrieval` in rerank mode prints the sitting's numbers; dense and hybrid print theirs.
  - Deps: T1.
- [x] **S08-T3 `[commodity]` p95 latency and cost in the summary and table.**
  - `summary.json` gains p95 latency, retrieval-only p95 and cost per question; the 6 existing folders are refilled; the table shows them.
  - Done when: hand-calculated unit tests pass; the table shows dense 10.7 s / $0.029 and hybrid 12.9 s / $0.030.
- [x] **S08-T4 `[commodity]` Rerank latency benchmark and S15 sizing note.**
  - `make eval-retrieval` prints retrieval p50/p95 and the model's load time; the sizing note covers 11 threads and 2 CPUs, plus peak RAM.
  - Done when: the line prints and the note is in `docs/evaluation.md`.
  - Deps: T2.
- [x] **S08-T5 `[commodity]` Rerank eval run.**
  - 3 paid runs of `make eval` in rerank mode; the row and the write-up; the default mode set by decision 4.
  - Done when: the row and its spread are committed; `docs/evaluation.md` states pass or fail per condition with numbers.
  - Deps: T2, T3.

### ✅ S09 Temporal and authority-aware retrieval *(Stage 6)*

- **Outcome:** query modes plus validity filtering plus ADR-003 authority adjustments.
- **Slice doc:** `docs/slices/S09-temporal-authority.md`
- **Metrics to move:** stale-result rate and temporal accuracy (temporal stage), authority-selection accuracy (authority stage); router accuracy ≥ 0.90 (ADR-009). Plus an ablation row.

Tasks:

- [x] **S09-T1 `[core]` ADR-009: query-mode routing.**
  - Decided in the S09-R1 sitting (2026-10-09): an LLM router; committed as Accepted in the run PR.
- [x] **S09-T2 `[core]` Router and time scope → release window.**
  - The `Router` interface, the Claude router and a fake; time scope → window through the `releases` table; stored routes and `make eval-routes`.
  - Done when: hand-worked unit tests pass; temporal-mode `make eval-retrieval` prints router accuracy ≥ 34 of 36 and 7 of 9 windows.
  - Deps: T1.
- [x] **S09-T3 `[core]` S09 metrics in the eval.**
  - Stale-result rate, temporal accuracy, router accuracy: printed, stored in the summary, in the table.
  - Done when: hand-computed unit tests pass; dense, hybrid and rerank print the sitting's baselines.
- [x] **S09-T4 `[core]` Temporal retrieval mode.**
  - Route, resolve, then ADR-003 D4's filters inside both searches, on top of rerank.
  - Done when: fixture integration tests pass; temporal-mode `make eval-retrieval` prints the sitting's prototype numbers.
  - Deps: T2.
- [x] **S09-T5 `[core]` `observed_lifecycle` from the feature-gate reference.**
  - Per gate × release, from that release's own snapshot; `make lifecycle`, also run by `make ingest`.
  - Done when: hand-worked unit tests pass; the sitting's 3,295 rows; a re-run stores identical rows.
- [x] **S09-T6 `[core]` `effective_stage` and authority tier per hit.**
  - Tiers by source type (KEPs: shipped or implemented → 3); in every mode, the prompt and citations (AC1).
  - Done when: hand-worked unit tests pass; the sitting's KEP examples; old modes unchanged.
  - Deps: T5.
- [x] **S09-T7 `[core]` Authority multipliers and authority-selection accuracy.**
  - An `authority` mode: ×1.25 / ×0.8 on the reranker's probability, per ADR-003 D4; the metric with CURRENT MRR beside it.
  - Done when: hand-worked unit tests pass; `make eval-retrieval` prints the sitting's numbers in all 5 modes; the flipped-tier check matches.
  - Deps: T4, T6.
- [x] **S09-T8 `[commodity]` S09 eval run.** A free gate first, then 3 paid runs, the row, the write-up, the S09 metric thresholds (by the R2 sitting's rule). Deps: T7.

### ✅ S10 Conflict detection *(Stage 7)*

- **Outcome:** every answer carries `conflicts[]`: claimed vs. observed, old vs. new text, and contradictions, each resolved by an ADR-003 D6 rule or marked unresolved.
- **Slice doc:** `docs/slices/S10-conflict-detection.md`
- **Metrics to move:** conflict precision and recall on conflict set v0 (thresholds set in T8); AC4 reported per seed, end to end (S10-R2 decision 3: a seed that search misses is "not retrieved", for S11). Retrieval metrics unchanged. Plus an ablation row.

- [x] **S10-T1 `[core]` ADR-010: conflict detection method.** Decided in the S10-R1 sitting (2026-10-11).
- [x] **S10-T2 `[core]` KEP metadata conflicts.**
  - `claim_mismatch` (the claim of the KEP version valid at the target release vs. its observed stage) and `history_date` (a KEP "v1.N … released" line vs. the `releases` table), on each question's hits.
  - Done when: hand-worked unit tests pass; `make eval-retrieval` prints the sitting's rule-conflict line.
- [x] **S10-T3 `[core]` Kind and resolution of a pair.**
  - A pure function: same section → supersession, else contradiction; the winner by ADR-003 D6, or unresolved.
  - Done when: hand-worked unit tests pass, including the sitting's 2 real pairs.
- [x] **S10-T4 `[core]` Conflicts in the answer.**
  - `conflicts[]` on the answer and the eval rows, on every path; the rule-found block in the prompt; `ask` JSON; the trace.
  - Done when: hand-worked unit tests pass; retrieval prints S09's numbers; a demo `ask` shows KEP-4858's conflict.
  - Deps: T2.
- [x] **S10-T5 `[core]` Model-found conflicts.**
  - The answer model lists chunk pairs that disagree; ids checked on their own; kind and resolution by T3; D6 and the KEP milestone line in the prompt; the losing-side flag in the eval.
  - Done when: hand-worked unit tests pass; the smoke run keeps AC1–AC3 at 100%.
  - Deps: T3, T4.
- [x] **S10-T5b `[core]` The release to settle conflicts at.**
  - "Settle conflicts at release 1.N." in the prompt, so the answer text and the code's list settle at the same release (S10-R2 decision 4).
  - Done when: hand-worked unit tests pass; T8's run 1 keeps AC1–AC3 at 100%.
  - Deps: T5.
- [x] **S10-T5c `[core]` A KEP's future milestone stays out of the prompt.**
  - The claim line and the rule-found summary show a KEP's latest milestone only when it is older than the target release (decided after T8's run 1 answered unanswerable q48 from "latest milestone v1.38"; ADR-010 D1 amended).
  - Done when: hand-worked unit tests pass; q48 asked 3 times after the change gives `insufficient_evidence` 3 of 3.
  - Deps: T5.
- [x] **S10-T6 `[core]` Conflict set format, loader and metrics.**
  - ADR-007 D4's format and label check; precision, recall and AC4 per seed in the eval, the summary and the table; `make eval-conflicts` (free).
  - Done when: hand-worked unit tests pass; `make eval-conflicts` on the demo sample prints the R2 contract's lines.
  - Deps: T4.
- [x] **S10-T7a `[core]` Draft conflict set v0.**
  - Every disagreement among the 10 results of each golden question and the 2 new questions, plus the 4 seeds; 3 independent passes; the spot-check sheet.
  - Done when: the loader's check passes on the draft; the split rate is reported.
  - Deps: T6.
- [x] **S10-T7 `[human]` Verify conflict set v0.** The sheet (seeds, 1 per kind, 1 random, every disputed one, 1 whole question), then the file in `eval/golden_set/`. Deps: T7a.
- [x] **S10-T8 `[commodity]` S10 eval run.** A free gate, 3 paid runs, the row, the write-up, the conflict thresholds. Deps: T5b, T5c, T7.

### ✅ S11 Corrective agentic retrieval *(Stage 8)*

- **Outcome:** corrective retrieval is tested and not adopted (ADR-011): the S11-R1 sitting's probes found no grader that tells thin evidence from enough, and no second-search design that passes the keep rule fixed before its test.
- **Slice doc:** `docs/slices/S11-corrective-retrieval.md`
- **Metrics to move:** none adopted (ADR-011).

- [x] **S11-T1 `[core]` ADR-011: corrective retrieval.** Decided in the S11-R1 sitting (2026-10-12): not adopted.
- [x] **S11-T2 `[commodity]` The S11 write-up.**
  - `docs/evaluation.md`'s "Corrective retrieval (S11)" section from `summarize.py`'s output; the spec's must-have 8 and AC7 notes; ADR-006 and ADR-010 amendments; the ADR index; the Greptile list; glossary terms.
  - Done when: every number in the section matches `summarize.py`'s output; `make check` is green.
  - Deps: T1.
- [x] **S11-T3 `[commodity]` The backlog after S11.**
  - S11's tasks; S12's two AC4 items; the ADR queue (011 corrective retrieval, 012 deployment); the proposed additions from the sitting.
  - Done when: each item in the run contract's list is in the backlog; `make check` is green.
  - Deps: T1.
- [x] **S11-T4 `[commodity]` The S11 retro.**
  - `/slice-retro S11` as the run's last commit: the slice brief, S11 ✅ and S12 🟨, `docs/architecture.md`, the memory review.
  - Done when: the retro's exit checks pass.
  - Deps: T2, T3.

### ✅ S12 Phase 1 closeout

- **Outcome:** Phase 1 closes (M1) with 3 stated exceptions (AC4 1 of 4, AC5 8 of 10, AC6 8 of 9), each with its measured cause, in `docs/m1-report.md`. `POST /query` answers through the same pipeline as `orgknow ask`, with one Langfuse trace per request.
- **Metrics to move:** none by design; AC5 and AC6 are now measured on every saved run.
- **The candidate tasks, as the S12-R1 sitting decided them:**
  - ADR-010 D4's fallbacks: the separate detector was probed in the sitting and not adopted (judged precision 0.690 < 0.90); the stale-KEP rule isn't built (ADR-010, amendment 2026-10-12).
  - AC4's q08 and c01: AC4 closes at 1 of 4 as a stated exception (decision 2); S11's c01 lead was a false match.
  - FastAPI `POST /query` and Langfuse on the API path: T2.
  - Streamlit dev UI: not built; FastAPI's `/docs` page instead (a proposed addition for S17's sitting).
  - README table and narrative, `docs/architecture.md`, slice-brief consolidation (the M1 report's slice table): T3.
- **Slice doc:** `docs/slices/S12-phase1-closeout.md`

- [x] **S12-T1 `[core]` AC5 and AC6 answer-side checks.** Scored from saved eval rows, in the summary and the ablation table. Deps: none.
- [x] **S12-T2 `[commodity]` `POST /query` with Langfuse.** The `ask` pipeline over HTTP; the reranker loaded once per process; one trace per request. Deps: none.
- [x] **S12-T3 `[commodity]` Closeout docs and the M1 report.** Deps: T1, T2.
- [x] **S12-T4 `[commodity]` The S12 retro.** Deps: T3.

---

## Milestone M2: Whole project

| Slice | Stage | Outcome |
|---|---|---|
| ✅ **S13 Phase 2 provenance MVP** | Stage 9 | One decision chain reconstructed end to end. Linked issues/PRs are ingested for that chain only; `decisions`/`decision_evidence` tables; decision-chain completeness metric. |
| ✅ **S14 Backend hardening + async ingestion** | Stage 10 | `docs/interfaces.md` (contracts, error shapes, idempotency); ingestion job model; the jobs table as the queue (no SQS, ADR-013); idempotent worker; request IDs; structured logs; timeouts and retries. |
| 🟨 **S15 AWS deployment** | Stage 11 | **First task:** a risk/security/cost review (blueprint gap #6). Then ADR-014 (deployment topology) and Terraform for EC2, RDS, S3, ECR, IAM, CloudWatch, and SSM (no SQS: ADR-013 D1). Budget alarm, a teardown runbook, and cost of $50/month or less. |
| ⬜ **S16 CI/CD** | Stage 12 | ECR build/push, deploy to EC2, smoke eval in CI. |
| ⬜ **S17 Next.js UI** | Stage 13 | Answer with citations, authority/version badges, a conflict panel, a timeline, and provenance views. |
| ⬜ **S18 Final evaluation + portfolio assets** | Stage 14 | Full benchmark, architecture docs, README, demo video, resume bullets backed by measured results. |

### 🟨 S15 AWS deployment

- **Outcome:** one `terraform apply` creates the AWS environment (EC2, RDS, S3, ECR, IAM, CloudWatch, SSM, a budget alarm); the API and the worker run there from one image and restart after a crash; the deployed API answers a live question with citations, RDS's fingerprint equals the laptop's, the forecast cost is ≤ US$50/month, and one runbook command removes it all (ADR-014).
- **Metrics to move:** none (deployment). Guards: Phase 1 retrieval metrics and the ingestion fingerprint stay exactly the same; cost ≤ US$50/month. Live latency is recorded, not gated.
- **Slice doc:** `docs/slices/S15-aws-deployment.md` (run contract S15-R1)

- [x] **S15-T1 `[core]` Risk, security and cost review (`docs/security-review.md`).** Blueprint gap #6's 6 topics; S17's exposure controls designed, marked Proposed; the cost table; a disposition for each carried item. Deps: the contract.
- [x] **S15-T2 `[core]` ADR-014: deployment topology.** Decided in the S15-R1 sitting (2026-10-15): no inbound ports (Session Manager), t3a.medium with the local reranker, an own VPC with private database subnets; committed as Accepted with the run contract.
- [x] **S15-T3 `[commodity]` Container image (`make image`).** One image, API and worker; proven on the laptop (a job, the fingerprint, the retrieval eval's lines, a restart). Deps: the contract.
- [ ] **S15-T4 `[commodity]` Terraform (`infra/`, `make tf-check`).** Offline tests pin no public database, no internet route from its subnets, no inbound ports, the budget. Deps: the contract.
- [ ] **S15-T5 `[commodity]` Deploy and teardown runbook (`docs/deployment.md`).** Deps: T3, T4.
- [ ] **S15-T6 `[human]` First deploy and measurements.** With the developer (paid AWS): apply, load, RDS checks, the retrieval eval in the cloud, a live ask, connections, cost, teardown proof. Deps: T5.
- [ ] **S15-T7 `[commodity]` Docs and the S15 retro.** Deps: T6.

### ✅ S14 Backend hardening + async ingestion

- **Outcome:** every API response carries a request ID that also appears in one-line JSON logs, with one error shape and explicit timeouts and bounded retries on every external call (R1). `POST /ingestion-jobs` queues a job that `make worker` runs to completion with per-step progress; the same job run twice or a killed worker leaves the same ingestion fingerprint (R2).
- **Metrics to move:** none (backend). Guard: Phase 1 retrieval metrics and the ingestion fingerprint stay exactly the same.
- **Slice doc:** `docs/slices/S14-backend-hardening.md` (run contract S14-R1; R2 has its own sitting)

- [x] **S14-T1 `[commodity]` Interface contracts (`docs/interfaces.md`).** Every endpoint, the error envelope, request IDs, logs, each dependency's timeout and retries; a test keeps routes and doc in step. Deps: none.
- [x] **S14-T2 `[commodity]` Request IDs, JSON logs, one error handler.** Deps: T1.
- [x] **S14-T3 `[commodity]` Timeouts, retries, autocommit API connections, API mode tests.** Deps: T2.
- [x] **S14-T4 `[core]` Job table, corpus-writer lock, snapshot reads.** The jobs table is the queue (ADR-013). Deps: T1–T3.
- [x] **S14-T5 `[core]` The worker (`make worker`).** Deps: T4.
- [x] **S14-T6 `[commodity]` Job endpoints.** Deps: T4, T5.
- [x] **S14-T7 `[commodity]` Docs and the S14 retro.** Deps: T6.

### ✅ S13 Phase 2 provenance MVP

- **Outcome:** `orgknow chain kep:2572` prints the release-cadence decision as 6 dated steps, each citing a stored text, built by rules from recorded links and dates (ADR-012). Decision-chain completeness is scored on 2 gold chains (release cadence and a random held-out KEP), beside a like-for-like plain-search control.
- **Metrics to move:** decision-chain completeness (new); Phase 1's retrieval metrics hold within ±0.03.
- **Slice doc:** `docs/slices/S13-provenance-mvp.md` (run contract S13-R1)

- [x] **S13-T1 `[core]` Ingest the chains' GitHub items.** `discussion` documents (tier 7), fetched into the cache and pinned by hash; migration; embeddings; the chain label check. Deps: none.
- [x] **S13-T2 `[human]` Gold chains v0.** Both chains' steps and the held-out chain's WHY question, before any system output; drafted by Claude at the developer's request, signed off by the developer in the S13-R1 sitting. Deps: the contract.
- [x] **S13-T3 `[core]` Decision tables and the chain builder.** `decisions`, `decision_evidence`; `make chains`; `orgknow chain`. Deps: T1.
- [x] **S13-T4 `[core]` Decision-chain completeness.** `make eval-chain`: both numbers per chain, and the control. Deps: T2, T3.
- [x] **S13-T5 `[commodity]` `GET /decisions/{canonical_id}`.** Deps: T3.
- [x] **S13-T6 `[commodity]` Docs and the S13 retro.** Deps: T4, T5.

---

## ADR queue

ADRs are decided when their slice starts, not earlier.

| ADR | Topic | Slice |
|---|---|---|
| 004 | Toolchain | S01 (Accepted) |
| 005 | Data access approach | S03 (Accepted) |
| 006 | Generation model, structured output, tracing | S04 (Accepted) |
| 007 | Golden-set schema and labeling | S06 |
| 008 | Reranker model and candidate count | S08 (Accepted) |
| 009 | Query-mode routing | S09 (Accepted) |
| 010 | Conflict detection method | S10 (Accepted) |
| 011 | Corrective retrieval | S11 (Accepted) |
| 012 | Decision provenance | S13 (Accepted) |
| 013 | Async ingestion (job model, queue, idempotency) | S14 (Accepted) |
| 014 | Deployment topology | S15 (Accepted) |

## Proposed additions (triage by the developer)

*(Agents append items here with a one-line reason. They are not scheduled until moved into a slice.)*

- **Evaluate Jev (TypeSafe) as a query-mode router (ADR-009) and evidence grader (S11); candidate only.** Reason: a fast typed-decision model might beat rules at mode routing and an LLM at sufficiency grading. Adopt only on ablation evidence. (Researched 2026-09-27; Jev is early access, v1.13.)
  - **S06 prerequisites:** met in the S06-R1 sitting: ADR-007's `mode` is the human-labeled expected mode, and the harness records the false-refusal rate.
  - **S09:** done without Jev. The S09-R1 sitting chose an LLM router (ADR-009): rules scored 12 of 36 on a blind rewording, Opus 35 of 36.
  - **S11:** dropped in the S11-R1 sitting; no grader adopted (ADR-011).
  - **If adopted:** new ADR (dependency); small interface + test fake; pinned version (never `jev-latest`); threshold in config.
  - **Out of bounds:** citation validation (AC2 stays deterministic), date/release resolution, "needs retrieval?" routing.
- **Community SIG annual reports as WHY-evidence source (deferred).** Reason: `community/sig-{release,auth,network}/annual-report-*.md` (2020–2025) explain SIG priorities and rationale; left out of manifest v0 to keep governance scope to README/charter. (Found in S02-T1.)
- **Post-baseline experiment (moved out of S06 in the S06-R1 sitting, decision 9): merge a section under 64 tokens into its first subsection.** Merging changes heading paths, so labels must be re-checked (ADR-007 label check), and the row is compared with the frozen baseline. The same applies to stripping Hugo shortcodes (`{{< glossary_tooltip … >}}`, `{{< feature-state … >}}`) from chunk text (S04 slice doc). Reason: 14% of sections on the S04 scope (30–32% on the full corpus) are under 64 tokens. Measure the effect on Recall@K with the S06 harness before adopting it. Related: greedy packing can end a chunk on an intro and start the next with its list (Pod Security Admission "Exemptions": "…current policy level:"). (Found in S02-T3b; S04-R1 sitting decision 5 kept chunking without merging; packing note from S04-R1, PR #22.)
- **Playwright end-to-end tests + screenshots for the S17 Next.js UI.** Reason: verify UI behavior once a UI exists. Evaluate in the S17 sitting. (Workflow review 2026-10-04.)
- **Cloud runs test (`claude --cloud`).** Reason: lets the laptop stay off on run nights. Check Docker Postgres, the corpus cache, and that the merge gate still holds. Trigger: keeping the laptop on becomes a burden. (Workflow review 2026-10-04.)
- **Make R3 race-free before a second writer exists (S14 at the latest).** Reason: R3's cross-table part (no alias equals a `canonical_id`) is a check-then-insert in `create_document` and `add_alias`. Two concurrent writers can each miss the other's uncommitted row and both commit the same identifier. Options: a transaction-level advisory lock in both functions, or one shared identifiers table with a single UNIQUE. Safe today: one writer. Same class: two `make embed` runs at once both pay for the same texts, and the second aborts on the primary key. Also: `make ingest-report` reads in several queries, so a report taken during an ingest could mix moments; a REPEATABLE READ read-only snapshot in its two entry points fixes it (Greptile on PR #30). (Found by Greptile on PRs #19, #20 and #22.) Same class: a chain read during `make chains` can return 0 steps (2 reads, no shared snapshot; Greptile on PR #48). **Scheduled for S14-T4 (S14-R1 sitting). Done in S14-T4 (S14-R2): one corpus-writer lock taken by all 6 writers (ADR-013 D3); `make ingest-report` and `stored_decision` each read in one REPEATABLE READ snapshot.**
- **Lock refresh (out of S14, S14-R1 sitting K2).** Three parts. (1) Keep past `head` SHAs in the lock (moved from S05 in the S05 sitting, 2026-10-07: it matters only when the lock is refreshed; S05 keeps the 2026-09-30 lock.) Reason: earlier `head` snapshots aren't kept, so a doc edited on `main` after the first ingest gives a history mismatch. (S04-R1, PR #21 parked 2.) The 18 CHANGELOG versions too: a lock refresh re-dates them and gives a history mismatch (S05-R2, PR #29 parked 17). (2) A re-fetched GitHub thread with new posts stops `make ingest`: only the latest snapshot is kept, so its history mismatches (PR #47 parked; PR #48 question 2); decide how GitHub items get new versions before any re-fetch. (3) The spike's `--relock` drops the lock's GitHub section (PR #47 parked). S14's jobs run at the current lock.
- **Golden set v1: "any of" label groups (ADR-007 amendment).** Reason: v0's A-primary rule leaves equally good copies (CHANGELOG pre-release sections, passing mentions) unlabeled, so a hit on one scores 0, while labeling them all would fill Recall's denominator with duplicates. A group credited once when any member is hit fixes both. Needs an ADR-007 amendment, loader and metric changes, and a relabel into v1 (re-baselined). (S06-T5 decision 2, 2026-10-08.)
- **S10 conflict-set candidates found while labeling v0 (input to S10-T7a; kept in the S10-R1 sitting; S10-R2 labels them where a question's results hold both sides: q21, q25).** `versioning.md` (1.36+) says 4 minor releases are supported vs. 3 in the version-skew page; legacy apt/yum repos deprecated Aug 31 (deprecation blog) vs. Sep 13, 2023 (1.29 upcoming-changes blog); `gate:ServiceTopology` "Deprecated 1.20" vs. alpha in the v1.20 docs; release page "currently four times per year" stale in v1.21–v1.23. (S06-T5, 2026-10-08.)
- **Chunker: a test for the HTML-table half of the "never cut" guard.** Reason: removing it fails no test today. (S05-R3, PR #30 parked 4; kept in the S06-R1 sitting.)
- **Report: remove `counts_by_release`'s unprinted per-type values and 1 duplicate fingerprint test case.** Reason: dead code. (S05-R3, PR #30 parked 9; kept in the S06-R1 sitting.)
- **`make embed`: print the estimate before the requests.** Reason: the R3 contract said "before"; the refusal above the cap already runs first. (S05-R3, PR #30 parked 10; kept in the S06-R1 sitting.)
- **BM25 ranking for the lexical search (Postgres extension, e.g. pg_search or VectorChord-bm25).** Reason: Postgres `ts_rank`/`ts_rank_cd` have no IDF, so a common word ("kubernetes") weighs as much as a rare one ("PodSecurity"). S07 uses AND matching, which matches 0 texts for 23 of 36 v0 questions; OR matching added noise (Recall@20 0.603 → 0.540). Needs an ADR (new dependency, custom DB image). Try it if S08/S09 show lexical recall is the bottleneck. (S07 sitting, decision 1, 2026-10-08.)
- **S07 parked test gaps (PR #34).** Reason: 3 small gaps the reviewers parked as beyond the plan. (1) No test that the `retrieve` trace records the mode, RRF score and ranks; it was checked once on a demo trace. (2) No lexical test for a question with flags (`--service-account-issuer`); it was checked by hand. (3) The autocommit width test proves the width doesn't leak, not that it applied during the query. (S07-R1, 2026-10-08.)
- **CI: cache mypy between runs.** Reason: since torch and transformers (S08), CI's `check` job takes 91 s instead of 33 s, mostly mypy reading both packages from cold. Options: cache `.mypy_cache` in the workflow, or stop mypy following torch's imports. (S08-R1, PR #37 question 2.)
- **S15: the reranker's 2-CPU numbers.** Reason: pinned to 2 CPUs, rerank takes 11.5 s per question at p50, and the projected answer p95 is 22.3–24.2 s, over the 23 s ceiling in 2 of 3 runs (`docs/evaluation.md`, "Reranker timing and S15 sizing"). The levers: a bigger instance, the hosted Voyage fallback, ONNX quantization (ADR-008). (S08-T4/T5.) **Decided in the S15-R1 sitting (ADR-014 D2): t3a.medium with the local reranker; S15-T6 measures; a retrieve p95 above 15 s goes to the next sitting.**
- **S08 parked items (PR #37).** Reason: gaps the reviewers and Greptile parked as beyond the plan. (1) The prices aren't recorded in `run.json` or `summary.json`, so `make eval-resummarize` after a price change would reprice old runs. (2) The real-model test checks only that the weights file is cached; a partial cache would download the rest instead of skipping. (3) No test that the `retrieve` trace records `rerank_score`, that dense and hybrid never import torch, or that they never call the reranker; each was checked by hand. (4) ADR-008 and the cross-encoder docstring give the model-only load (3 s); a process pays about 7.5 s with imports. (5) 3 comments still say "both modes" (`.env.example`, `settings.py`). (6) The integration `settings` fixture reads `.env`, so a local `RETRIEVAL_MODE` would change the mode of tests that don't pin it. (S08-R1, 2026-10-09.) **(5) and (6) moved into S09-T4 in the S09-R1 sitting.**
- **Dated CHANGE questions: retrieve per window end, then merge (ADR-003 D4, deferred).** Reason: none of v0's 9 CHANGE questions names a release or year, so the plan can't be measured; CHANGE gets no filter until a golden question needs it. (S09-R1 sitting, decision 3.)
- **Golden set v1: a router check set.** Reason: the S09-R1 sitting's blind rewording of v0's 36 answerable questions (Slack style, same meaning) exposed fitted router rules (36/36 → 12/36); it's in `eval/candidates/router-rewording-v0.yaml`. A reworded set, spot-checked by the developer, would test the router and retrieval on wording the system wasn't tuned on. (S09-R1 sitting, 2026-10-09.)
  - **S11-R1:** the developer spot-checked 5 of 36 (all match) and Claude read all 36; the set was the sitting's hard set.
- **S09-R1 cleanup (PR #39 parked 2, 4, 16).** Reason: `Mode` is defined twice (`retrieval/router.py`, `eval/golden.py`); `golden_window` re-implements `golden._minor`; `route_line` uses an `assert` in production code. (Kept in the S09-R2 sitting.) Also a third copy of the "1.N" → N parse (PR #45 parked 4; kept in the S13-R1 sitting).
- **Test: pin "stale" to dates, not releases (PR #39 parked 6).** Reason: switching `current` to "open end release" breaks no test; only the real baselines catch it. (Kept in the S09-R2 sitting.)
- **Golden set v1: count an unanswerable row the same way in `summarize` and `score_retrieval_only` (PR #39 parked 10).** Reason: `summarize` would count an unanswerable row with a mode or window; `score_retrieval_only` wouldn't. No effect on v0. (Kept in the S09-R2 sitting.)
- **Trace coverage.** Reason: no test checks the `retrieve` span's route, window and filter (PR #39 parked 11), there is no router span, so a live ask's router latency isn't traced (parked 12), and the S07 (1) and S08 (3) trace gaps above. One task could cover them. (Kept in the S09-R2 sitting.)
- **Record the router effort in the routes file (PR #39, Greptile).** Reason: after a `ROUTER_EFFORT` change the eval reuses old routes while `run.json` shows the new effort. (Kept in the S09-R2 sitting.)
- **Atomic saves for the routes and question-vector files (PR #39, Greptile).** Reason: a plain overwrite interrupted midway could lose them (worst case: re-pay ~$0.18). (Kept in the S09-R2 sitting.)
- **Query rewriting for informal wording (S11-R1 sitting lead).** A second search on every question with a Haiku-written query, RRF with the first 10. Rephrased Recall@10 0.427 → 0.468 and MRR 0.607 → 0.671, v0 neutral; 1 run, the best of 4 designs, v0's routes reused; ~5.5 s more per question; it would run on unanswerable questions too (q48). Test it on golden v1's verified rephrased set with ADR-011 D2's rule.
- **Conflict set v1 candidates (S10-T8; parked in the S11-R1 sitting).** q18 `gate:StrictIPCIDRValidation` 10419 vs. 10420; q34 `gate:KMSv2` 9930 vs. 9931; q35 the v1.28 blog 41925 vs. 42160 (borderline).
- **Detector A for conflict recall (S12-R1 sitting).** Reason: a separate Haiku call with the neutral wording raised recall 0.33 → 0.55 on conflict set v0 (raw precision 0.707, judged precision unknown), but failed q01's summary check (`eval/results/s12-sitting/`). Test it on conflict set v1, with ADR-010's revisit rule (judged precision ≥ 0.90).
- **q08's reranker regression (S12-R1 sitting).** Reason: KEP-2579's Implementation History (seed k03) is rank 10 in hybrid mode and rank 20 after the reranker (`probe_ranks.log`), one of AC4's 3 causes. Look at it on golden v1, not by tuning on v0.
- **c01's search miss (S12-R1 sitting).** Reason: as routed (HISTORY, 1.30), none of seed k04's `versioning.md` texts is among c01's 20 candidates; only kep:1498 (a second side) is (`probe_ranks.log`). S11's "no window" lead matched the "every four months" versions, not the seed's text.
- **Freeze the AC5 and AC6 rules for golden set v1 (S12-R1 sitting).** Reason: both rules were chosen on the runs they score (decisions 3 and 4), with a negative control as the only guard. Fix them, and v1's AC4 wording (product spec), before any v1 result.
- **Streamlit dev UI: a note for S17's sitting (S12-R1 sitting).** Reason: S12 used FastAPI's `/docs` page, the CLI and Langfuse instead (0 lines, 0 dependencies); S17 builds the real UI, so decide there whether a Streamlit step is worth it.
- **Phase 1 text corrections (S12-R1, PRs #45 and #46; kept in the S13-R1 sitting).** Reason: 12 factual errors in docs, docstrings and interview prep. Stale docstrings: "the CLI" (`generation/schema.py`, `generation/generator.py`), "only caller of Langfuse" (`pipeline.py`), `summarize`'s when only `latest` is given. `CLAUDE.md`'s Core list names "agent graph". `docs/evaluation.md` cites `graph.py:76` for a cast the committed spike doesn't have, and says "row 4 rescues only q02" (for dense it rescues q02 and q24). The S11 docs call k04 "reachable" with no pointer to S12's correction. The "every three months" text is in chunk 36369 too, not only 36362. The M1 report's `probe_ranks.py` command needs `HF_HUB_OFFLINE=1`. `docs/architecture.md` says "both routes" (there are 3). The S12 slice brief calls the reranker load "the slow step" (7.5 s of an 11–12 s request); the S12 retro says "the router call isn't in the trace" (the route is on the retrieve span; only its usage is missing). Also (S13-R1, PR #48 parked; S14-R1 sitting K5): the per-question comparison's baseline is S10-T8's run 3, called "S12's final run"; 3 Known-limits bullets repeat the section above them; `docs/architecture.md`'s "6 tables" and "Both routes"; the README's provenance lines use "KEP" and "Prow" undefined. Also (S15-R1 sitting): PR #51's 9 doc nits (settings comments on the statement timeout and Anthropic retries; 2 stale `.env.example` comments; 3 "per address"/"only spaces" nits; "make serve only" in the logs module and the architecture doc; the domain model lacks the jobs table; the architecture doc's Tests table lacks S14's tests; the Logs section doesn't say worker lines carry the job's request ID; "the worker holds the lock only during a job") and PR #52's 3 (2 code spans with a trailing space; the chain builder's docstring lists 3 of 4 error cases). About 45–60 minutes as one interactive docs task.
- **Eval: read the latest release before the paid question loop (PR #45 parked 1; kept in the S13-R1 sitting).** Reason: `run` reads it after the paid loop, so a bad database read at the end fails a run that has already been paid for.
- **S14 inputs from S12-R1 (PR #45 parked 8, PR #46 parked 2; kept in the S13-R1 sitting).** Reason: no API test covers temporal or authority mode; `/query` opens 1 database connection per request with no pool, though ADR-005 expects one. **Moved into S14-T3 (S14-R1 sitting): the mode tests are built; the pool is decided against (ADR-005 amendment 2026-10-13: autocommit connections, revisit in S15).**
- **S17: attach the stored chain to WHY answers (S13-R1 decision 6).** Reason: when a WHY answer cites a text from a stored chain, the reply could carry that chain's timeline without touching the LLM (~100–150 lines). Not built in S13 to keep the run inside one PR; S17's sitting decides how answers and chains meet.
- **Chain rules: read bare `#N` references (S13-R1, the held-out draw).** Reason: KEP-3015's tracking issue names its merged KEP PR as a bare `#5140`, which GitHub renders as a link but the frozen rule (full URLs only) ignores, so the held-out chain's decision step is missing. Test the fix on a fresh held-out chain, never on KEP-3015.
  - **Chain rules v1, more cases (S13-R1, PRs #47 and #48; S14-R1 sitting K3):** `/approve cancel` counts as an approval (question 3); a merged PR with no stored text (empty description, only bot comments) crashes `make chains`: reuse `not_ingested` or add a reason (a migration; question 5, Greptile); an `/approve` posted on merge day after the merge is cited (post times are stored by day); a stored discussion with no comment reads as missing `no_link`; `git.k8s.io` redirect links read as `not_public`; a post with an unclosed code fence swallows later posts' headings. Same test rule: a fresh held-out chain.
- **`CLAUDE.md`: the golden-set copy step in the desktop app (S13-R1 sitting).** Reason: "type it in the Claude Code prompt with a `!` prefix" doesn't run in the desktop app's Code tab (the message arrives as text); the developer used the Ubuntu terminal. Update "Getting a file in", step 2: an Ubuntu (WSL) terminal, or the app's Run button on a `bash` block.
- **S13 cleanup (S13-R1, PRs #47 and #48; S14-R1 sitting K4).** Reason: small gaps and repeats the reviewers parked. Code: 4 unused chain model fields; the citation-URL helper repeats one in `generation/validate.py`; chain seeds re-read the manifest YAML; the gold loader repeats the golden-set loader's read block; the chain label check reads the YAML unvalidated. Gaps: `orgknow chain` with the database down prints a traceback; the gold loader accepts fewer than 6 steps or empty `texts`; the control credits a `none` gold step (no effect on v0); `make eval-chain` embeds a new question before checking the chains exist; the control's top 10 follows `RETRIEVAL_TOP_K` (pinned 10); a missing gold file gives a traceback. Tests: 1 duplicate assertion; 1 expected value taken from a pinned helper.
- **S15 security review inputs from S14-R1 (PRs #49 and #50; kept in the S14-R2 sitting).** Reason: gaps that matter once the API is public. (1) Logs: the reranker's library (transformers) writes plain-text lines under `make serve`; a failed traced ask's log line has no `trace_id`; a 502 or 503 logs no cause (PR #49 parked 1, 3, 4). (2) Anthropic's SDK waits as long as a `retry-after` header says, with no cap, so a 429 can stall a request past the documented 612 s worst case (PR #49 parked 2). (3) A 502's message can carry a provider's text, any `RuntimeError`/`ValueError` in the ask is a 502, and a validation message can include the input (PR #49 question 3). (4) `VOYAGE_MAX_RETRIES` has no upper bound and its wait doubles without a cap; the API connection helper's `options` replaces any `options` in `DATABASE_URL` (e.g. a `search_path` on RDS) (PR #50 parked 3, 4). **Scheduled for S15-T1 (S15-R1 sitting): the review rates each, with PR #51 parked 3 (a file path in a job's error) and the misleading "step failed" line on a lost connection. Rated in S15-T1 (`docs/security-review.md`, section 8): all 6 low with no inbound ports, none must-fix, no code changed; each goes to S17's sitting (with (1) and (3) together: a fixed 502 text and the cause in the log; (2): a deadline per ask).**
- **GitHub texts in CURRENT ("now") questions (S13-R1, PR #48 question 1; S14-R1 sitting K6).** Reason: discussion windows never close, so their comments pass CURRENT's filter; q01 lost all 4 labeled hits to Discussion #1290's comments (Phase 1 MRR 0.813 → 0.781). Options: leave, demote (an authority weight) or filter them in CURRENT mode. Also the answer prompt explains tiers 1–6, not tier 7 (Greptile, PR #47). A scoring change: measure on golden set v1, not v0.
- **S17: public exposure controls (S15-T1 security review, section 7; ADR-014 D1).** Reason: the API has no authentication and `POST /query` costs ~US$0.03 per ask; S15 is safe only because it has no inbound ports. Build before anything is public: HTTPS (or only the UI public), an API key (`ui`, `admin`), a per-key daily spending cap, rate limits on `POST /query` and `POST /ingestion-jobs`, a question length cap, model text shown as plain text, and a prompt line saying evidence is data, not instructions (measure it on golden set v1). Starting values are in the review.
- **S17: hardening from the S15 security review (2.4, 4.6, 4.7).** Reason: each is low with no inbound ports. A least-privilege database role for the app, the master user only for migrations and restore (contract call c2); outbound traffic limited to TCP 443, plus 5432 to the database (c3); write-only SSM values, so Terraform's state never holds the API keys.
- **S16: act on the image scan (S15 security review, 5.5).** Reason: ECR scans each pushed image but only reports, and no step reads it. Fail the deploy pipeline on critical findings; refresh `uv.lock` and the base-image digests monthly.
