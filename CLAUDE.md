# CLAUDE.md: Agent Guide

This project is an Organizational Knowledge & Decision Intelligence RAG system over the public Kubernetes corpus. It models versions, source authority, and conflicts explicitly instead of leaving them to the LLM.

It is a **portfolio project by a new-grad SWE**. Code must be simple, verified, and explainable. The developer must be able to defend every core design choice in an interview. Optimize for validated progress, not for volume of code.

## Read first (source-of-truth order; earlier wins on conflict)

1. `docs/decisions/`: ADRs. *Accepted* ADRs are binding; *Proposed* ADRs are the current plan.
2. `docs/product-spec.md`: Phase 1 scope, non-goals, acceptance criteria.
3. `docs/backlog.md`: what to work on, in order.
4. The active slice doc in `docs/slices/`.
5. `docs/reference/blueprint-v2.pdf`: background only. Items 1–3 override it where they differ.

Don't read the whole `docs/` tree every session. Read the task, its slice doc, and the ADRs the slice references.

## Current focus

The active slice is the one marked 🟨 in `docs/backlog.md`. Work only on tasks from that slice. The next task is the first unchecked task whose dependencies are done.

## Commands

These targets are created in S01. Until a target exists, say so; never pretend it ran.

| Command | Purpose |
|---|---|
| `make up` / `make down` | Start/stop local Postgres + pgvector |
| `make migrate` | Apply Alembic migrations |
| `make fmt` | Auto-format |
| `make check` | Format-check + lint + typecheck + unit tests. **Required before any task is done.** |
| `make test-int` | Integration tests (needs `make up`) |
| `make eval-smoke` | 10–15 question eval (from S06) |
| `make eval` | Full golden-set eval (from S06). Costs money; run only when asked. |

## Repo map

Create directories only when a task needs them. Don't pre-scaffold empty modules.

```
config/corpus_manifest.yaml   corpus scope; the manifest defines the subset, not code
docs/                         spec, ADRs, backlog, slices, slice briefs, research
src/orgknow/
  settings.py                 env-based config (pydantic-settings)
  db/                         migrations + data access; the ONLY place with SQL
  ingestion/                  manifest → snapshots → normalize/hash → versions → chunks
  embeddings/                 embedding interface, provider, content-hash cache
  retrieval/                  dense, lexical, fusion, rerank, temporal/authority scoring
  generation/                 prompts, structured output, citation validation
  agent/                      LangGraph workflow (S11)
  eval/                       golden-set loader, metrics, runners
  api/                        FastAPI app; thin, no business logic
  cli.py
spikes/                       throwaway exploration (S02); never imported by src/
tests/unit/                   no network, no DB
tests/integration/            real Postgres via compose
tests/fixtures/               small real corpus files, pinned
eval/golden_set/              HUMAN-OWNED labels
eval/results/                 committed eval outputs
```

## Target pipeline (built incrementally per the backlog)

1. Manifest → snapshot reader → normalize + hash → document versions with release/date validity windows (ADR-002).
2. Structure-aware chunks with deterministic metadata headers → embeddings (cached by content hash) → Postgres (pgvector + full-text search).
3. Retrieval, built up one stage at a time: dense → + lexical/RRF → + cross-encoder rerank → + temporal/authority adjustment (ADR-003).
4. Conflict detection → bounded LangGraph corrective loop → structured answer with citations, or `insufficient_evidence`.

## How to work (every task)

1. **Load context.** Read the task in the backlog and its slice doc. Restate the goal and "done when" in 2–3 lines.
2. **Plan.** List the files to touch, the approach, the tests, and the risks. **Wait for approval** if the task is tagged `core`, touches the schema, or hits a stop-and-ask trigger. For `commodity` tasks, state the plan, then proceed.
3. **Branch.** Create the task branch from an up-to-date `main` before the first edit (see Git and PRs).
4. **Tests first for deterministic logic:** hashing, normalization, validity windows, chunking, RRF, scoring, metrics.
5. **Implement** the smallest change that meets "done when".
6. **Verify before pushing.** Run `make check`, plus `make test-int` if the DB or integration paths changed. Report the actual result and paste the output in the PR. Never claim a check passed without running it.
7. **Brief and backlog.** Write the PR brief (below) and tick the task's checkbox in `docs/backlog.md` in the same change.
8. **Ship.** Commit, push, and open the PR with `gh`. Then stop; the developer merges.

Size guideline: about 300 changed lines of hand-written code per task at most. If a task needs more, propose a split before starting.

## Git and PRs

- One task per branch and per PR. Branch: `s0X-tY-<short-name>`. Commit: `S0X-TY: <what>`.
- Claude Code creates the branch, commits, pushes (`git push -u origin <branch>`), and opens the PR with `gh pr create`, using `.github/pull_request_template.md` for the body.
- Claude Code **never** merges a PR and never pushes to `main`. The developer merges after the required CI checks (`check`, `integration`) are green.
- Slice status changes only in the retro PR (`/slice-retro`). The developer approves them by merging that PR.

## Batch mode

"Work through S0X" means: do the slice's tasks in backlog order, one task per branch and PR.

- Stop for approval at every `core` plan and every stop-and-ask trigger. At a `human` task, stop and hand over.
- After opening a PR, stop. Start the next task only after the previous PR is merged (confirm with `gh pr view <number> --json state`), branching from the updated `main`.

## Stop and ask before…

- adding any dependency, service, or architectural pattern (this needs an ADR)
- changing the DB schema beyond what the task specifies
- creating or editing anything in `eval/golden_set/`. Labels are human-owned. You may propose candidates in a separate file.
- changing retrieval scoring, weights, or thresholds not specified by the task
- deviating from an ADR or the product spec, or editing files unrelated to the task
- spending money beyond the task's needs, e.g. embedding the full corpus or running the full eval. Default to fixtures and caches.

## Non-goals (don't build them, and don't scaffold them "for later")

- Multi-agent or supervisor architectures; Neo4j; a separate vector DB; Elasticsearch/OpenSearch; Kafka or microservices; Kubernetes deployment.
- Fine-tuning or custom embedding training; multi-region deployment; RBAC or complex auth.
- LLM chunk enrichment (unless a backlog experiment asks for it); non-English docs; SIGs outside the manifest.
- AWS, Next.js, or async queues before their slice. Phase 2 work before M1.

## Core vs. commodity

- **Core** (the developer must understand it deeply): versioning/validity/identity, chunking, retrieval SQL, fusion, scoring, conflict logic, eval metrics, agent graph, output schema.
  - Prefer plain, readable code over clever abstractions.
  - Put pure functions in the logic modules and keep I/O at the edges.
  - Name the key functions in the PR brief's `Key code` line.
- **Commodity:** Docker, CI, Makefile, settings, logging, Alembic boilerplate, FastAPI plumbing, Streamlit, CLI. Keep it conventional and boring.

## Code conventions

- **Language and typing:** Python 3.12. Full type hints; `mypy --strict` on `src/`. Ruff for lint and format.
- **Contracts:** Pydantic models for cross-module contracts and API I/O.
- **Configuration:** all config comes from settings/env. Never hardcode secrets, URLs, model names, weights, or thresholds.
- **Settings instances:** no module-level `Settings()`; pass settings in (e.g. `create_app(settings=None)` builds one only when none is given). Unit tests use `Settings(_env_file=None)` so a local `.env` can't leak in.
- **External services:** external APIs (embeddings, LLM) sit behind small interfaces with test fakes. Don't add an interface where only one implementation exists and no ADR requires swapping.
- **Determinism:** pin SHAs, fix seeds, and use no network in unit tests.
- **Naming:** use the ADR vocabulary (`canonical_id`, release window, `claimed_status`, `effective_stage`, authority tier).
- **TODOs:** none without a backlog entry.

## PR brief (required for every task)

The **Brief** section of the PR description: 8 lines or fewer, in plain language, with jargon defined on first use.

- **What changed:** 1–2 lines.
- **Decisions:** choice → alternative rejected → why, or "none".
- **How verified:** the commands run and their results. The full output goes below the brief.
- **Interview-relevant:** 0–2 bullets, or "none".
- **Key code** (`core` tasks only, optional, one line): `file:function`, …

Add a term to `docs/learning/glossary.md` only if an interviewer would plausibly use it.

## Definition of done (task)

- [ ] "Done when" criteria met; scope limited to the task.
- [ ] `make check` green (and `make test-int` where relevant) before pushing, with the output pasted in the PR.
- [ ] New logic has tests.
- [ ] PR brief written; backlog checkbox ticked.
- [ ] Docs updated if behavior or architecture changed. An ADR drafted if a decision was made.
- [ ] Branch pushed and PR opened with `gh`; not merged.

## Skills (workflow shortcuts in `.claude/skills/`)

- `/start-task`: load context, propose a plan, and create the branch.
- `/finish-task`: verify, write the PR brief, commit, push, and open the PR.
- `/explain`: teach a file or concept (optional).
- `/slice-retro`: close a slice: verify exit checks, write the slice brief, and open the retro PR.
