# CLAUDE.md: Agent Guide

This project is an Organizational Knowledge & Decision Intelligence RAG system over the public Kubernetes corpus. It models versions, source authority, and conflicts explicitly instead of leaving them to the LLM.

It is a **portfolio project by a new-grad SWE** who is new to RAG. Code must be simple, verified, and explainable. The developer must be able to defend every core design choice in an interview. Optimize for validated progress, not for volume of code.

**Implementation simplicity:** solve each task in the simplest reliable way, with minimal code, dependencies, abstractions and moving parts. There is no size cap, so this is the main guard against bloat.

## Read first (source-of-truth order; earlier wins on conflict)

1. `docs/decisions/`: ADRs. *Accepted* ADRs are binding; *Proposed* ADRs are the current plan.
2. `docs/product-spec.md`: Phase 1 scope, non-goals, acceptance criteria.
3. `docs/backlog.md`: what to work on, in order.
4. The active slice doc in `docs/slices/`, including its run contracts.
5. `docs/reference/blueprint-v2.pdf`: background only. Items 1–3 override it where they differ.

Don't read the whole `docs/` tree every session. Read the task, its slice doc, and the ADRs the slice references.

## Current focus

The active slice is the one marked 🟨 in `docs/backlog.md`. Work only on tasks from that slice. The next task is the first unchecked task whose dependencies are done. A run builds only the tasks in its contract.

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

**Pipeline map**, used in every brief to show where the work fits (bold the stage it touches):

`Sources → Ingest → Store → Chunk → Embed → Retrieve → Answer`

Work outside the pipeline is labeled `Supporting: tooling`, `Supporting: evaluation` or `Supporting: deployment`.

## Two working modes

| Mode | How to start | Use for |
|---|---|---|
| Interactive task | `claude --permission-mode default`, then `/start-task SNN-TY` | One-off tasks, fixes, docs |
| Sitting → run | Sitting: `claude --permission-mode default`, then `/plan-run SNN`. Run: a new session with `claude --permission-mode auto`, then `/run-bundle` | Bundles of slice tasks |

- A **bundle** is 2–5 tasks planned together. `[human]` tasks are never in a bundle.
- A **sitting** is the interactive session where the developer and Claude plan a bundle and make every decision.
- The **run contract** is the sitting's written output, stored in the slice doc.
- A **run** builds the bundle unattended from its contract.
- To **park** is to record a piece of work or a question, set it aside, and continue with independent work.

In an interactive task, the plan step works as a mini-sitting: the same decision protocol and the same evidence pack. Switching to auto mode after the plan is approved is fine.

## Interactive task (every step)

1. **Load context.** Read the task in the backlog and its slice doc. Restate the goal and "done when" in 2–3 lines.
2. **Plan (mini-sitting).** List the files to touch, the approach, the tests, the proof map and the risks. Run the decision protocol for anything on the "ask" side of Decisions. **Wait for approval** if the task is tagged `core`, touches the schema, or hits a stop-and-ask trigger. For `commodity` tasks, state the plan, then proceed.
3. **Branch.** Create the task branch from an up-to-date `main` before the first edit (see Git and PRs).
4. **Build with the per-task loop** (below). Tests come first for deterministic logic: hashing, normalization, validity windows, chunking, RRF, scoring, metrics.
5. **Evidence pack, brief and backlog.** Write the evidence pack into the PR brief and tick the task's checkbox in `docs/backlog.md` in the same change.
6. **Ship.** Commit, push, and open the PR with `gh`. Merge only when the developer says "merge" (see Git and PRs).

## Runs

- The run contract lives in the slice doc and is the run branch's first commit.
- One session per run, one fresh subagent per task. Each subagent first reads `CLAUDE.md` and the contract, not earlier subagents' output.
- Each task follows the per-task loop. After each task, the **main session re-runs the checks itself**, then commits (`SNN-TY: <what>`) and pushes the branch. This is the checkpoint.
- No merges and no PRs mid-run. PRs open at the end.
- **Park, don't wait.** When a stop condition hits, record it, skip that piece, and continue with independent tasks. End the run if nothing is left.
- **Stop conditions:**
  - paid API calls not listed in the contract
  - a new dependency
  - a schema change beyond the contract
  - departing from an ADR, the spec or a contract decision
  - anything in `eval/golden_set/`
  - the no-progress rule
- **No-progress rule:** the same failure after 3 fix attempts → park.
- If an earlier task's tests break and fixing them would change an approved decision → park.
- If the usage limit stops the run, the last check-in shows where it was.
- **Resume:** `/run-bundle` continues from the first unfinished task in the contract.
- **End of run:**
  1. bundle-level check
  2. open the PR(s)
  3. Greptile (see Greptile)
  4. fix must-fix items
  5. re-run the checks
  6. final check-in with the PR link(s), the next-bundle proposal, and next steps
- The run doesn't merge. In the morning the developer reviews, says "merge", and approves the prompt.

## Per-task loop

| Step | Repeats? | What happens | Ends when |
|---|---|---|---|
| 1. Build | No | Implement to the contract. Tests come first for "done when" items and deterministic logic | The code is written |
| 2. Fix until green | **Yes** | `make check`, plus `make test-int` if the DB is touched, plus this task's proof tests | All pass, or the no-progress rule parks it |
| 3. Review | Once | A fresh `reviewer` subagent checks the diff against the rubric below | Findings are sorted |
| 4. Fix must-fix | Once, then back to step 2 | Only must-fix items | Fixed and green. Otherwise, park the task |
| 5. Verify | No | The main session re-runs the checks and confirms each must-fix item was addressed. It raises no new findings | Commit and push |

**Reviewer rubric.** Loops fix or simplify, never add.

| Must-fix | Park (goes on the developer's list) |
|---|---|
| A "done when" item that isn't met, or has no proof | Refactors and "cleaner" designs |
| Expected test values computed by the code under test | Extra features or options |
| A bug or correctness risk | Tests beyond the plan |
| Work outside the contract's scope, or a break of an ADR or `CLAUDE.md` rule | Style beyond what the linter enforces |
| Complexity the task didn't need (a dependency, abstraction or file): remove it | |

## Decisions

| Ask the developer | Decide yourself, and list it under "Claude's calls" |
|---|---|
| Hard to undo: schema, data formats, interfaces between components | Easy to undo: names, helpers, layout inside a file |
| Anything on the stop-and-ask list | Anything already settled by an ADR, the contract or the conventions |
| Scope changes (anything parked) | How tests are organized; test data |
| Core design choices the developer would be asked "why?" about | Routine commodity details |
| Conflicts between project docs | |

- **Rule of thumb:** if it must be defended in an interview, or is costly to undo, ask.
- **Decisions stay in the sitting.** Outside a sitting, park the question for the next one unless truly blocked.
- **Format, one decision at a time:**
  1. "Decision N of M:" the question in plain words
  2. why it matters (1 line)
  3. an options table: what each means, its upside, its downside
  4. a recommendation, and what would change it
  5. wait for the answer before the next decision
- **ADR-level decisions:** a `devils-advocate` subagent (fresh context) argues against the recommendation before the developer decides.
- **Read-back:** list every decision made ("Here's what you decided"), get confirmation, then record it in the contract, ADR or slice doc. Nothing is decided only in chat.
- If nothing needs deciding, say "No decisions needed" and move on.

## Evidence pack

Every task produces the following, briefly. It goes in the PR brief.

1. **Proof map:** each "done when" item → the test or command that proves it → the result.
2. **Independent expected values:** taken from the spec, a hand calculation, or real data checked in the sitting. Never computed by the code under test.
3. **Proof the tests can fail:**
   - Red → green for tests written first.
   - A break-it check for the 1–3 most important rules named in the contract: break the code that enforces the rule, show the test fails, restore it, and confirm with `git diff`.
4. **Real-data demo** (when the task touches data): one reproducible command on a small real sample, with a short output excerpt. Once tracing exists (S04-T7), include the Langfuse trace for sample queries.
5. **Honesty rules:**
   - outputs are copied from the tools, never retyped
   - every claim has a command that reproduces it
   - a "Not verified" list
   - the CI link

## Git and PRs

- **Interactive tasks:** branch `sNN-tY-<name>`, one PR per task. Commit: `SNN-TY: <what>`.
- **Runs:** branch `sNN-rN-<name>`. The first commit is the run contract, then one commit per task (`SNN-TY: <what>`).
- **One PR per run** by default. Split into 2 PRs, at a task boundary, only on one of these triggers:
  - **Natural seam:** the bundle has two distinct purposes (decided in the sitting).
  - **Size alarm** (checked when opening the PR): more than ~30 changed files, or more than ~800 reviewable lines. Reviewable lines exclude lockfiles, generated files, fixtures, and docs already approved in the sitting.
- **Limits and size record:**
  - At most 2 PRs per run. A third needs the developer's OK in the sitting.
  - Record the PR size (files, reviewable lines) in every brief.
- **Stacked PRs:** when a run is split after task TN, PR 1 gets a new branch (`sNN-rNa-<name>`) cut at TN's last commit. PR 2 is the run branch, with PR 1's branch as its base. No commits move, so nothing is force-pushed.
- **Opening:** `git push -u origin <branch>`, then `gh pr create` with the body from `.github/pull_request_template.md`.
- **Merging:**
  - Only after the developer says "merge" and the required CI checks (`check`, `integration`) are green.
  - Use only `gh pr merge <N> --merge --delete-branch`, which triggers the developer's approval prompt.
  - Merge commits only: no squash, no rebase.
- **After a stacked PR 1 merges:** GitHub retargets PR 2 to `main`. Run `gh pr update-branch <N>` (merge, not rebase), wait for CI, then ask to merge.
- Never push to `main`. Never force-push.
- **Slice status** still changes only in the retro PR (`/slice-retro`). The retro can be the last commit of a slice's final run.
- **ADRs:** decided in the sitting and committed as Accepted in the run PR. The developer's merge confirms them.

## Greptile

Greptile is an AI code reviewer that comments on GitHub PRs. Its config is in `.greptile/`.

- **When:** run PRs. Interactive-task PRs only when the developer asks for it in the plan. **Skip** Greptile on docs-only and config-only PRs.
- **Trigger:** manual only. Comment `@greptileai` once, after the PR opens. The tier is pinned to Base (1 credit per review). No re-review on push.
- **Sorting comments:** use the reviewer rubric. Fix must-fix items, park the rest, and dismiss false alarms with a reason. For each comment:
  1. react 👍 (useful) or 👎 (not useful)
  2. reply with the outcome: "Fixed in `<sha>`", "Parked: <why>" or "Dismissed: <why>"
  3. resolve the thread, because `protect-main` blocks merges while threads are open
- **Replies never mention `@greptileai`**, because a mention can start a new, paid review.
- **Re-review:** at most one per PR, only if the must-fix fixes changed behavior and fewer than 40 credits have been used.
- **Counting:** count `@greptileai` triggers since the billing cycle started (day **4** of each month). Show `Greptile: N/50` in check-ins and briefs. Count with (set the date to the latest 4th):

  ```bash
  gh api "repos/{owner}/{repo}/issues/comments?since=YYYY-MM-04T00:00:00Z" --paginate \
    --jq '.[] | select(.user.type == "User" and (.body | test("@greptile"))) | .id' | wc -l
  ```

  Automatic reviews also cost credits, and this command misses them. Add any by hand (there should be none once the dashboard is set to Never).

| Credits used | Mindset |
|---|---|
| 0–40 | Normal use |
| 41–49 | Mindful: say "running low", and prefer skipping re-reviews and docs/config-only PRs |
| 50 | Hard max: no more triggers until the reset |

## Writing for the developer

Applies to briefs, check-ins, sittings, slice briefs and any other output.

- Write for someone new to RAG. Define each term in a few words on first use, or avoid it.
- No paragraph longer than 2 lines. Bullets are one line where possible.
- Use numbers instead of adjectives.
- No file paths or function names in a brief's top section.
- **End every output that hands something to the developer with "Next steps for you":** 1–3 concrete actions (what, where, roughly how long).

## PR brief

Every PR body follows `.github/pull_request_template.md`: a plain top section that fits on one screen, then collapsed details. Interactive tasks and runs use the same format. Add a term to `docs/learning/glossary.md` only if an interviewer would plausibly use it.

## Stop and ask before…

In a run, these park instead of stopping.

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
  - Name the key functions under `Key code` in the brief's details.
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

## Definition of done (task)

- [ ] "Done when" criteria met; scope limited to the task.
- [ ] `make check` green (and `make test-int` where relevant), re-run by the main session before pushing.
- [ ] New logic has tests.
- [ ] Evidence pack in the brief: the proof map is all ✅, or each gap is on the "Not verified" list.
- [ ] Review pass done; must-fix items resolved.
- [ ] Parked items listed in the brief.
- [ ] PR brief written, ending with "Next steps for you"; backlog checkbox ticked.
- [ ] Docs updated if behavior or architecture changed. An ADR drafted if a decision was made.
- [ ] Branch pushed and PR opened with `gh` (in a run, at the end of the run).

## Skills and agents

Skills are in `.claude/skills/`, agents in `.claude/agents/`.

- `/start-task SNN-TY`: interactive task: load context, plan as a mini-sitting, and create the branch.
- `/finish-task`: verify, write the evidence pack and brief, commit, push, and open the PR.
- `/plan-run SNN`: the sitting: plan a bundle with the developer and write its run contract.
- `/run-bundle`: start or resume a run from its contract, and print check-ins.
- `/slice-retro`: close a slice: verify exit checks, write the slice brief, and open the retro PR (or add it as a run's last commit).
- `/explain`: teach a file or concept (optional).
- `reviewer` agent: fresh-context review of a diff against the rubric.
- `devils-advocate` agent: argues against a recommendation for ADR-level decisions.

Only the developer starts `/plan-run` and `/run-bundle`. The builder is a general-purpose subagent started by `/run-bundle`; define no other agents.
