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
docs/                         spec, ADRs, backlog, slices, learning notes, research
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
2. **Plan.** List the files to touch, the approach, the tests, and the risks. **Wait for approval** if the task is tagged `core`, touches the schema, or hits a stop-and-ask trigger. For `commodity` tasks, state the plan, then wait for the developer's "go" before editing.
3. **Tests first for deterministic logic:** hashing, normalization, validity windows, chunking, RRF, scoring, metrics.
4. **Implement** the smallest change that meets "done when".
5. **Verify.** Run `make check`, plus `make test-int` if the DB or integration paths changed. Report the actual result. Never claim a check passed without running it.
6. **Explain.** Write the Explanation block (below) and draft the PR description from `.github/pull_request_template.md`.
7. **Update the backlog.** Tick the task's checkbox in `docs/backlog.md` in the same change. Never change a slice's status; the developer does that.

Size guideline: about 300 changed lines of hand-written code per task at most. If a task needs more, propose a split before starting.

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
  - Explain in depth.
- **Commodity:** Docker, CI, Makefile, settings, logging, Alembic boilerplate, FastAPI plumbing, Streamlit, CLI. Keep it conventional and boring.

## Code conventions

- **Language and typing:** Python 3.12. Full type hints; `mypy --strict` on `src/`. Ruff for lint and format.
- **Contracts:** Pydantic models for cross-module contracts and API I/O.
- **Configuration:** all config comes from settings/env. Never hardcode secrets, URLs, model names, weights, or thresholds.
- **External services:** external APIs (embeddings, LLM) sit behind small interfaces with test fakes. Don't add an interface where only one implementation exists and no ADR requires swapping.
- **Determinism:** pin SHAs, fix seeds, and use no network in unit tests.
- **Naming:** use the ADR vocabulary (`canonical_id`, release window, `claimed_status`, `effective_stage`, authority tier).
- **TODOs:** none without a backlog entry.

## Explanation protocol (required at the end of every task)

The developer is a new-grad SWE who must explain this project in interviews. Teach; don't impress. Use plain language and define jargon on first use. End every task with a section headed **Explanation**, 15 lines or fewer:

- **What changed:** 1–2 lines.
- **Why this approach:** the reason, and the main alternative rejected.
- **Trade-offs:** what we gave up or deferred.
- **Concepts to know:** 1–3 terms, each with a one-line definition. Skip terms already in `docs/learning/glossary.md`, and add new ones there in the same change.
- **How verified:** the commands run and their results.
- **Interview question:** one question this code invites, with a 1–2 line answer sketch.
- **Read before merging** (`core` tasks only): pointers to the 2–4 most important functions (`file:function`).

## Definition of done (task)

- [ ] "Done when" criteria met; scope limited to the task.
- [ ] `make check` green (and `make test-int` where relevant), with the output reported.
- [ ] New logic has tests.
- [ ] Explanation block and PR description written.
- [ ] Backlog checkbox ticked. Docs updated if behavior or architecture changed. An ADR drafted if a decision was made.

## Skills (workflow shortcuts in `.claude/skills/`)

- `/start-task`: load context and propose a plan.
- `/finish-task`: verify, explain, and draft the PR.
- `/explain`: teach a file or concept.
- `/slice-retro`: close a slice.
