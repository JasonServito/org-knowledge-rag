# Backlog

This is the ordered list of slices and tasks. It is the single source for **what to do next**.

## Rules

| Rule | Detail |
|---|---|
| Slice status | ⬜ todo · 🟨 active · ✅ done. **Only the developer approves slice status changes (by merging the retro PR).** Exactly one slice is 🟨 at a time. |
| Task selection | The agent works on the first unchecked task in the 🟨 slice whose dependencies are done. The agent ticks `[x]` in the same PR that completes the task. |
| Task tags | `[core]`: the developer must deeply understand it, and the plan needs approval. `[commodity]`: boilerplate; the agent proceeds once it has stated the plan. `[human]`: the developer does or decides it. |
| Git and PRs | One task per branch and PR. The agent creates the branch (`s0X-tY-name`), commits (`S0X-TY: <what>`), pushes, and opens the PR with `gh`. The developer merges after the required CI checks are green; the agent never merges or pushes to `main`. |
| Batch mode | "Work through S0X" runs the slice's tasks in order, one PR each. The agent stops at every `core` plan, stop-and-ask trigger and `[human]` task, and waits for each PR to be merged before starting the next task. |
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

### 🟨 S02 Corpus spike *(validates ADR-002 and ADR-003)*

- **Outcome:** measured corpus numbers, with ADR-002 and ADR-003 accepted or amended on evidence.
- **Slice doc:** `docs/slices/S02-corpus-spike.md`

Tasks:

- [x] **S02-T1 `[core]` Manifest v0.**
  - `config/corpus_manifest.yaml`: repos, release range, SIG → path allowlists (Release/Auth/Network), the 4 traced KEPs, blog/CHANGELOG/governance sources.
  - Done when: the developer has reviewed it against ADR-002 D6.
- [ ] **S02-T2 `[commodity]` Fetch script.**
  - `spikes/fetch.py` makes partial clones into `CORPUS_CACHE_DIR` (outside the repo) and records the SHAs.
  - Done when: SHAs are written to the spike report.
  - Deps: T1.
- [ ] **S02-T3 `[core]` Measurement.**
  - Per release: in-scope files; distinct versions after ADR-002 normalization and hashing; estimated tokens and chunks; estimated embedding cost at current Voyage pricing (look it up).
  - Done when: there is a table in the spike report.
  - Deps: T2.
- [ ] **S02-T4 `[core]` Rename check.**
  - Run `git diff --find-renames` between adjacent release branches, on at least one known move in the Auth or Network docs.
  - Done when: the report records precision on sampled renames and lists unmatched add/delete pairs.
  - Deps: T2.
- [ ] **S02-T5 `[core]` Format checks.**
  - Latest release number; feature-gates page structure (stage per version?); blog front-matter dates and in-place edit history; CHANGELOG section structure; `kep.yaml` status typos.
  - Done when: each has a yes/no plus an example in the report.
  - Deps: T2.
- [ ] **S02-T6 `[human]` Decide.**
  - Write `docs/research/corpus-spike-report.md`; amend ADR-002 and ADR-003 if needed; set them to Accepted.
  - Done when: both ADRs are Accepted and the cost estimate fits the budget.
  - Deps: T3–T5.

### ⬜ S03 Domain model + migrations *(blueprint gap #3)*

- **Outcome:** a schema that encodes ADR-002/003 invariants, enforced by the DB or by tested code.

Tasks:

- [ ] **S03-T1 `[human]` ADR-005: data access approach.**
  - SQLAlchemy Core vs. psycopg with raw SQL. Discuss in chat first.
  - Deps: S02.
- [ ] **S03-T2 `[core]` Write `docs/domain-model.md`.**
  - Entities, keys, constraints, and validity-window invariants. For example: at most one current version per `canonical_id`; windows of the same document don't overlap.
  - Done when: the developer has approved it.
  - Deps: T1.
- [ ] **S03-T3 `[core]` Migration `0002`.**
  - Tables: `releases`, `documents`, `document_aliases`, `document_versions`, `chunks`, `embeddings` (keyed by model).
  - Done when: it migrates up and down cleanly.
  - Deps: T2.
- [ ] **S03-T4 `[core]` Data-access layer.**
  - Done when: integration tests prove every invariant in the domain model (for example, an overlapping window is rejected).
  - Deps: T3.
- [ ] **S03-T5 `[commodity]` Seed the `releases` table.**
  - Loaded from the manifest (version, release date, end-of-life).
  - Done when: re-running the seed is idempotent.
  - Deps: T3.
- **Not in this slice:** the `search_vector` column (S07), `observed_lifecycle` (S09), and the relationships/decisions tables (S13).

### ⬜ S04 First vertical slice: PSP → PSA *(Stage 2, narrowed)*

- **Outcome:** `orgknow ask "<question>"` returns a cited, structured answer over SIG Auth docs at v1.24 and the latest release, plus KEP-2579.
- **Tests:** seeds #6–#10 (golden seeds in `docs/research/corpus_validation_gate.md` Appendix A).

Tasks:

- [ ] **S04-T1 `[human]` ADR-006: generation model/provider and tracing.**
  - Covers the LLM for generation, structured-output method, and Langfuse Cloud setup.
- [ ] **S04-T2 `[core]` Slice-scope ingestion.**
  - Snapshots → normalize/hash → versions with windows → stored.
  - Done when: a re-run creates 0 new versions (idempotent).
  - Deps: S03.
- [ ] **S04-T3 `[core]` Markdown chunker.**
  - Structure-aware (heading path), with a deterministic metadata header.
  - Done when: unit tests pass on fixtures, including table and code-block preservation.
- [ ] **S04-T4 `[commodity]` Embedding interface.**
  - Voyage provider, content-hash cache, and a fake for tests.
  - Done when: a second run makes 0 API calls.
- [ ] **S04-T5 `[core]` Dense retrieval.**
  - pgvector cosine search with an HNSW index; returns chunks with version/window/tier metadata.
  - Done when: an integration test on fixtures passes.
  - Deps: T2–T4.
- [ ] **S04-T6 `[core]` Generation.**
  - Structured output (`answer`, `answer_status`, `evidence[]`, `insufficient_evidence_reason`) plus a citation validator.
  - Done when: a citation outside the retrieved set is rejected in tests.
  - Deps: T1, T5.
- [ ] **S04-T7 `[commodity]` CLI `ask` command + Langfuse trace per query.**
  - Deps: T6.
- [ ] **S04-T8 `[human]` Run seeds #6–#10.**
  - Save the outputs to `eval/results/s04/` and write failure notes. Temporal confusion is expected; that's the motivation for S09.
  - Deps: T7.

---

## Milestone M1: Phase 1 complete (product spec AC1–AC8)

### ⬜ S05 Stage 1 subset ingestion *(Stage 2)*

- **Outcome:** the full manifest is ingested: 3 SIGs × v1.20 → latest, the 4 KEPs, CHANGELOG, blog, and governance docs.
- **Exit:** re-ingesting yields identical counts and hashes (AC8, first part); counts match the spike within an explained tolerance.
- **Candidate tasks:**
  - release-range snapshot loop
  - date-scoped sources (true commit dates)
  - blog in-place versions
  - CHANGELOG patch-section chunks
  - alias/rename handling
  - ingestion report command

### ⬜ S06 Eval harness + golden set v0 + dense baseline *(Stage 3)*

- **Outcome:** a frozen golden set v0 (30–50 questions, human-verified) and a committed dense-baseline row in the ablation table.
- **Exit:** `make eval-smoke` and `make eval` work; `docs/evaluation.md` is written; thresholds are recorded in the product spec.
- **Candidate tasks:**
  - ADR-007: golden-set schema and labeling (document + heading-path labels)
  - loader and label → chunk mapping
  - Recall@K, MRR, nDCG
  - AC1–AC3 schema checks
  - results format and ablation-table generator
  - `[human]` write and verify the questions
  - optional Streamlit inspector

### ⬜ S07 Hybrid retrieval *(Stage 4)*

- **Outcome:** lexical + dense retrieval fused with RRF, and an ablation row showing the delta.
- **Candidate tasks:**
  - `search_vector` column + GIN index (migration)
  - lexical query
  - RRF as a pure function with unit tests
  - config for k and candidate counts
  - eval run

### ⬜ S08 Reranking *(Stage 5)*

- **Outcome:** a local BGE cross-encoder rerank stage, with an ablation row and the CPU p95 latency recorded.
- **Candidate tasks:**
  - ADR-008: reranker model and candidate count
  - reranker module
  - latency benchmark
  - instance-sizing note for S15

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
| 005 | Data access approach | S03 |
| 006 | Generation model, structured output, tracing | S04 |
| 007 | Golden-set schema and labeling | S06 |
| 008 | Reranker model and candidate count | S08 |
| 009 | Query-mode routing | S09 |
| 010 | Conflict detection method | S10 |
| 011 | Deployment topology | S15 |

## Proposed additions (triage by the developer)

*(Agents append items here with a one-line reason. They are not scheduled until moved into a slice.)*

- **Evaluate Jev (TypeSafe) as a query-mode router (ADR-009) and evidence grader (S11); candidate only.** Reason: a fast typed-decision model might beat rules at mode routing and an LLM at sufficiency grading. Adopt only on ablation evidence. (Researched 2026-09-27; Jev is early access, v1.13.)
  - **S06 prerequisites:** the ADR-007 golden-set schema includes a human-labeled `expected_mode` per question; add false-refusal rate to the metrics in `docs/evaluation.md`.
  - **S09:** ADR-009 compares rules / LLM / Jev. Build rules first; try Jev only if rules miss the router-accuracy threshold.
  - **S11:** compare an LLM grader with a Jev Noul grader on AC3 and false-refusal rate.
  - **If adopted:** new ADR (dependency); small interface + test fake; pinned version (never `jev-latest`); threshold in config.
  - **Out of bounds:** citation validation (AC2 stays deterministic), date/release resolution, "needs retrieval?" routing.
- **Community SIG annual reports as WHY-evidence source (deferred).** Reason: `community/sig-{release,auth,network}/annual-report-*.md` (2020–2025) explain SIG priorities and rationale; left out of manifest v0 to keep governance scope to README/charter. (Found in S02-T1.)
