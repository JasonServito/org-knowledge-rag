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

### 🟨 S07 Hybrid retrieval *(Stage 4)*

- **Outcome:** lexical + dense retrieval fused with RRF, and an ablation row showing the delta.
- **Slice doc:** `docs/slices/S07-hybrid-retrieval.md`
- **Metric to move:** MRR (≥ +0.03 over the dense baseline, per the product spec's improvement rule).

Tasks:

- [ ] **S07-T1 `[core]` Lexical search.**
  - A migration adds the `search_vector` column + GIN index; a query returns the top N distinct texts by full-text rank.
  - Done when: integration tests on fixtures: an exact term ranks its text first; a text in several chunks appears once; no match → empty.
- [ ] **S07-T2 `[core]` RRF.**
  - A pure function: ranked id lists in, one fused ranking with scores out.
  - Done when: unit tests match hand-calculated scores, including an id in one list only, ties and empty lists.
- [ ] **S07-T3 `[core]` Hybrid retrieval and config.**
  - Dense N + lexical N → RRF → top K; mode, N, k and the HNSW search width in settings; `ask` and the eval use and record the mode; `make eval-retrieval` scores retrieval for free.
  - Done when: hybrid on fixtures returns the hand-predicted order; dense mode reproduces the baseline's retrieval scores.
  - Deps: T1, T2.
- [ ] **S07-T4 `[commodity]` Hybrid eval run.**
  - Two eval fixes (dirty check, smoke rows), then 3 paid runs of `make eval` in hybrid mode; the row and the write-up.
  - Done when: the row and its spread are committed; `docs/evaluation.md` states pass or fail against the improvement rule with numbers.
  - Deps: T3.

### ⬜ S08 Reranking *(Stage 5)*

- **Outcome:** a local BGE cross-encoder rerank stage, with an ablation row and the CPU p95 latency recorded.
- **Candidate tasks:**
  - ADR-008: reranker model and candidate count
  - reranker module
  - latency benchmark
  - instance-sizing note for S15
  - p95 latency and cost per question in `summary.json` and the ablation table (moved from Proposed additions in the S07 sitting; S08 must record p95)

### ⬜ S09 Temporal and authority-aware retrieval *(Stage 6)*

- **Outcome:** query modes plus validity filtering plus ADR-003 authority adjustments.
- **Metrics:** stale-result rate, temporal accuracy, authority-selection accuracy, router accuracy. Plus an ablation row.
- **Candidate tasks:**
  - ADR-009: routing approach (rules first vs. LLM)
  - time expression → release window resolver
  - `observed_lifecycle` ingestion from CHANGELOG and the feature-gates page
  - `effective_stage`
  - authority multipliers in config
  - mode-specific retrieval plans

### ⬜ S10 Conflict detection *(Stage 7)*

- **Outcome:** `conflicts[]` populated from deterministic sources (`claim_mismatch`, supersession) plus a cross-document check.
- **Metrics:** conflict precision/recall on the 4 seed conflict cases and more. AC4 passes.
- **Candidate tasks:**
  - ADR-010: conflict detection method
  - deterministic detectors
  - LLM pairwise check (top-N)
  - output wiring
  - conflict test set

### ⬜ S11 Corrective agentic retrieval *(Stage 8)*

- **Outcome:** a bounded LangGraph workflow (router → retrieve → grade → retry ≤ 3 → generate).
- **Exit:** kept only if the ablation shows benefit on hard queries worth the extra latency and cost; trajectory metrics recorded.

### ⬜ S12 Phase 1 closeout

- **Outcome:** the product spec's AC1–AC8 are verified and M1 is declared.
- **Candidate tasks:**
  - FastAPI `POST /query`
  - Langfuse on the API path
  - Streamlit dev UI
  - README ablation table and results narrative
  - `docs/architecture.md` update
  - slice-brief consolidation

---

## Milestone M2: Whole project

| Slice | Stage | Outcome |
|---|---|---|
| ⬜ **S13 Phase 2 provenance MVP** | Stage 9 | One decision chain reconstructed end to end. Linked issues/PRs are ingested for that chain only; `decisions`/`decision_evidence` tables; decision-chain completeness metric. |
| ⬜ **S14 Backend hardening + async ingestion** | Stage 10 | `docs/interfaces.md` (contracts, error shapes, idempotency); ingestion job model; a local queue abstraction shaped like SQS; idempotent worker; request IDs; structured logs; timeouts and retries. |
| ⬜ **S15 AWS deployment** | Stage 11 | **First task:** a risk/security/cost review (blueprint gap #6). Then ADR-011 (deployment topology) and Terraform for EC2, RDS, S3, SQS, ECR, IAM, CloudWatch, and SSM. Budget alarm, a teardown runbook, and cost of $50/month or less. |
| ⬜ **S16 CI/CD** | Stage 12 | ECR build/push, deploy to EC2, smoke eval in CI. |
| ⬜ **S17 Next.js UI** | Stage 13 | Answer with citations, authority/version badges, a conflict panel, a timeline, and provenance views. |
| ⬜ **S18 Final evaluation + portfolio assets** | Stage 14 | Full benchmark, architecture docs, README, demo video, resume bullets backed by measured results. |

---

## ADR queue

ADRs are decided when their slice starts, not earlier.

| ADR | Topic | Slice |
|---|---|---|
| 004 | Toolchain | S01 (Accepted) |
| 005 | Data access approach | S03 (Accepted) |
| 006 | Generation model, structured output, tracing | S04 (Accepted) |
| 007 | Golden-set schema and labeling | S06 |
| 008 | Reranker model and candidate count | S08 |
| 009 | Query-mode routing | S09 |
| 010 | Conflict detection method | S10 |
| 011 | Deployment topology | S15 |

## Proposed additions (triage by the developer)

*(Agents append items here with a one-line reason. They are not scheduled until moved into a slice.)*

- **Evaluate Jev (TypeSafe) as a query-mode router (ADR-009) and evidence grader (S11); candidate only.** Reason: a fast typed-decision model might beat rules at mode routing and an LLM at sufficiency grading. Adopt only on ablation evidence. (Researched 2026-09-27; Jev is early access, v1.13.)
  - **S06 prerequisites:** met in the S06-R1 sitting: ADR-007's `mode` is the human-labeled expected mode, and the harness records the false-refusal rate.
  - **S09:** ADR-009 compares rules / LLM / Jev. Build rules first; try Jev only if rules miss the router-accuracy threshold.
  - **S11:** compare an LLM grader with a Jev Noul grader on AC3 and false-refusal rate.
  - **If adopted:** new ADR (dependency); small interface + test fake; pinned version (never `jev-latest`); threshold in config.
  - **Out of bounds:** citation validation (AC2 stays deterministic), date/release resolution, "needs retrieval?" routing.
- **Community SIG annual reports as WHY-evidence source (deferred).** Reason: `community/sig-{release,auth,network}/annual-report-*.md` (2020–2025) explain SIG priorities and rationale; left out of manifest v0 to keep governance scope to README/charter. (Found in S02-T1.)
- **Post-baseline experiment (moved out of S06 in the S06-R1 sitting, decision 9): merge a section under 64 tokens into its first subsection.** Merging changes heading paths, so labels must be re-checked (ADR-007 label check), and the row is compared with the frozen baseline. The same applies to stripping Hugo shortcodes (`{{< glossary_tooltip … >}}`, `{{< feature-state … >}}`) from chunk text (S04 slice doc). Reason: 14% of sections on the S04 scope (30–32% on the full corpus) are under 64 tokens. Measure the effect on Recall@K with the S06 harness before adopting it. Related: greedy packing can end a chunk on an intro and start the next with its list (Pod Security Admission "Exemptions": "…current policy level:"). (Found in S02-T3b; S04-R1 sitting decision 5 kept chunking without merging; packing note from S04-R1, PR #22.)
- **Playwright end-to-end tests + screenshots for the S17 Next.js UI.** Reason: verify UI behavior once a UI exists. Evaluate in the S17 sitting. (Workflow review 2026-10-04.)
- **Cloud runs test (`claude --cloud`).** Reason: lets the laptop stay off on run nights. Check Docker Postgres, the corpus cache, and that the merge gate still holds. Trigger: keeping the laptop on becomes a burden. (Workflow review 2026-10-04.)
- **Make R3 race-free before a second writer exists (S14 at the latest).** Reason: R3's cross-table part (no alias equals a `canonical_id`) is a check-then-insert in `create_document` and `add_alias`. Two concurrent writers can each miss the other's uncommitted row and both commit the same identifier. Options: a transaction-level advisory lock in both functions, or one shared identifiers table with a single UNIQUE. Safe today: one writer. Same class: two `make embed` runs at once both pay for the same texts, and the second aborts on the primary key. Also: `make ingest-report` reads in several queries, so a report taken during an ingest could mix moments; a REPEATABLE READ read-only snapshot in its two entry points fixes it (Greptile on PR #30). (Found by Greptile on PRs #19, #20 and #22.)
- **S14: keep past `head` SHAs in the lock.** (Moved from S05 in the S05 sitting, 2026-10-07: it matters only when the lock is refreshed; S05 keeps the 2026-09-30 lock.) Reason: earlier `head` snapshots aren't kept, so a doc edited on `main` after the first ingest gives a history mismatch. (S04-R1, PR #21 parked 2.) The 18 CHANGELOG versions too: a lock refresh re-dates them and gives a history mismatch (S05-R2, PR #29 parked 17).
- **S09: near-duplicate crowding in the top 10.** Reason: versions of one section that differ by a line each take a slot; seeds #6 and #8 had 6 distinct sections in 10 hits, and #8 missed the docs chunk stating "stable since v1.25" (a hypothesis: only the top 10 is stored). Candidates: the release filter, or one hit per section. (S04-T8, PR #25.)
- **Link the 25 old single-file KEPs to their later KEP folders by exact title (S10 sitting at the latest, before S06 labels if wanted sooner).** Reason: 24 of 25 match a 1.21 folder's `kep.yaml` title exactly (e.g. `0014-dynamic-audit-configuration.md` → `600-dynamic-audit-configuration/`), so one history per KEP is possible. Needs an ADR-002 amendment (the known limit) and a one-time link rule. No relabel is needed if the link stores each old id as an alias: ADR-007 D2 resolves labels through aliases (S06-R1 sitting, decision 2). (S05-R2 sitting, decision 3, option C.)
- **S10: check KEP Implementation History dates against the `releases` table.** Reason: seed #8 repeated KEP-2579's "2021-11-03: v1.23 Beta version released" as fact; 1.23 shipped 2021-12-07. The model never sees release dates. (S04-T8, PR #25; Appendix A conflict case.)
- **Golden set v1: "any of" label groups (ADR-007 amendment).** Reason: v0's A-primary rule leaves equally good copies (CHANGELOG pre-release sections, passing mentions) unlabeled, so a hit on one scores 0, while labeling them all would fill Recall's denominator with duplicates. A group credited once when any member is hit fixes both. Needs an ADR-007 amendment, loader and metric changes, and a relabel into v1 (re-baselined). (S06-T5 decision 2, 2026-10-08.)
- **S10 conflict-set candidates found while labeling v0.** `versioning.md` (1.36+) says 4 minor releases are supported vs. 3 in the version-skew page; legacy apt/yum repos deprecated Aug 31 (deprecation blog) vs. Sep 13, 2023 (1.29 upcoming-changes blog); `gate:ServiceTopology` "Deprecated 1.20" vs. alpha in the v1.20 docs; release page "currently four times per year" stale in v1.21–v1.23. (S06-T5, 2026-10-08.)
- **Chunker: a test for the HTML-table half of the "never cut" guard.** Reason: removing it fails no test today. (S05-R3, PR #30 parked 4; kept in the S06-R1 sitting.)
- **Report: remove `counts_by_release`'s unprinted per-type values and 1 duplicate fingerprint test case.** Reason: dead code. (S05-R3, PR #30 parked 9; kept in the S06-R1 sitting.)
- **`make embed`: print the estimate before the requests.** Reason: the R3 contract said "before"; the refusal above the cap already runs first. (S05-R3, PR #30 parked 10; kept in the S06-R1 sitting.)
- **BM25 ranking for the lexical search (Postgres extension, e.g. pg_search or VectorChord-bm25).** Reason: Postgres `ts_rank`/`ts_rank_cd` have no IDF, so a common word ("kubernetes") weighs as much as a rare one ("PodSecurity"). S07 uses AND matching, which matches 0 texts for 23 of 36 v0 questions; OR matching added noise (Recall@20 0.603 → 0.540). Needs an ADR (new dependency, custom DB image). Try it if S08/S09 show lexical recall is the bottleneck. (S07 sitting, decision 1, 2026-10-08.)
