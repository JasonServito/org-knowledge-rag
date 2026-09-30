# AI-Assisted Development Workflow

This is how the project is built with AI assistance. `CLAUDE.md` holds the agent's rules; this doc is **for you**, the developer.

**The goal is validated progress you can explain, not maximum code.**

## 1. Principles

1. **Outcome-driven.** Every slice ends with something observable: a command that works, or a metric that moved.
2. **Scope-disciplined.** The backlog decides what's next. New ideas go to "Proposed additions", never straight into the active slice.
3. **Verify, don't trust.** Nothing is done until a check you can see has passed.
4. **Small units.** One task is one PR of about 300 hand-written lines at most, reviewable in 15 minutes.
5. **You own the thinking.** The AI drafts and opens PRs; you decide, review, and merge.

## 2. Roles

| Who | Does | Doesn't |
|---|---|---|
| **You** | Approve plans for `core` tasks, schema changes and stop-and-ask triggers; own acceptance criteria, golden-set labels and ADR acceptance; review PRs and merge them once CI is green; approve slice status changes by merging the retro PR | Rubber-stamp diffs you can't explain; re-run checks that CI already ran |
| **Chat assistant** (Claude project) | Architecture and trade-off discussion, slice docs, ADR drafts, debugging your reasoning, teaching, follow-up questions on slice briefs | Write large amounts of code |
| **Coding agent** (Claude Code) | Implement one bounded task per branch; run checks; commit, push and open the PR with the brief; tick the backlog; write the slice brief and open the retro PR, including the slice status flip | Merge PRs, push to `main`, make decisions, add dependencies, touch the golden set, change scope |

## 3. The slice loop (days)

```
Define ─► Decompose ─► Task loop ×N ─► Verify slice ─► Retro PR
```

1. **Define (in chat).** Turn the backlog entry into `docs/slices/SNN-*.md` using `_template.md`. It should state:
   - the outcome in one sentence
   - the exit checks
   - what's in and out of scope
   - the metric that should move
2. **Decompose.** Split the slice into 3–8 tasks, each with a "done when". Mirror them in the backlog.
3. **Task loop** (section 4), once per task.
4. **Verify the slice.** Run the exit checks. From S06 onward, run the eval and record the ablation row, including when the technique didn't help. A negative result is still a result.
5. **Retro.** Run `/slice-retro`. The agent checks the exit criteria, writes the slice brief `docs/learning/SNN-*.md`, updates `docs/architecture.md` if needed, flips the slice to ✅ and the next one to 🟨 in the backlog, and opens the retro PR. It proposes ADR status changes; you accept ADRs. Read the brief, then merge the PR to approve the status change. Then sync the claude.ai project (section 9).

## 4. The task loop (hours)

```
Context ─► Plan ─► Branch ─► (Tests) ─► Implement ─► Verify ─► PR ─► CI green ─► You merge
```

1. **Start a fresh agent session per task.** Long sessions drift and accumulate stale context.
2. Run `/start-task S0X-TY`. The agent restates the goal and proposes a plan.
3. **Review the plan against the spec, ADRs and non-goals.** Push back here; it's the cheapest point to correct course. The agent waits for your approval on `core` tasks, schema changes and stop-and-ask triggers. On `commodity` tasks it proceeds once it has stated the plan, so interrupt if the plan is wrong. Before its first edit, it creates the branch `s0X-tY-<name>` from `main`.
4. **For deterministic logic, tests come first.** Read the tests before the implementation, and ask whether they check the "done when" or just mirror the code.
5. The agent implements, then runs `/finish-task`: `make check` (plus `make test-int` if the DB or integration paths changed), PR brief, backlog tick, commit `S0X-TY: <what>`, push, and `gh pr create` with the check output pasted in.
6. **Review the PR:** the brief first, then the diff. The required CI checks (`check`, `integration`) replace re-running anything locally.
7. **You merge** once CI is green. The agent never merges, never pushes to `main`, and changes slice status only in the retro PR.

### 4.1 Batch mode

Say "work through S0X" to run a slice's tasks in backlog order, one task per branch and PR.

- The agent still stops at every `core` plan, every stop-and-ask trigger, and every `human` task.
- After opening each PR it stops. Merge the PR, then tell it to continue. It confirms the merge and branches the next task from the updated `main`.

## 5. Core vs. commodity: what you must own

| Core: you can whiteboard it | Commodity: you review lightly |
|---|---|
| Versioning, hashing, validity windows, identity (ADR-002) | Docker, CI, Makefile |
| Chunking | Settings, logging, CLI |
| Retrieval SQL, RRF, reranking integration | Alembic boilerplate, FastAPI plumbing |
| Temporal/authority scoring (ADR-003) | Streamlit |
| Conflict detection | Terraform (medium: learn the AWS concepts) |
| Eval metrics and harness; LangGraph design; output schema | |

For core code, read the brief's decisions and `Key code` line, then the tests, before merging. `/explain` is available if you want more depth; it's optional.

**Golden-set rule:** the AI may *propose* questions. You verify every expected answer and source against the corpus yourself. If the model grades against labels it wrote, the eval is circular. This is the same reason the blueprint rejected a synthetic corpus.

## 6. Feedback loops (time budgets)

| Loop | Target time | How |
|---|---|---|
| `make check` | ≤ 1 min | Unit tests only: no network, no DB |
| `make test-int` | ≤ 3 min | Compose Postgres plus small real fixture files |
| `make eval-smoke` | ≤ 5 min | 10–15 questions, embeddings cached by content hash |
| `make eval` | per slice | Full golden set; costs money, so run it deliberately |

If a loop gets slower than its budget, fix that before adding features.

## 7. Learning system

| Where | What | Who writes it |
|---|---|---|
| Chat, as you go | Trade-offs and concepts behind each decision | Chat assistant (see the project instructions below) |
| PR brief, per task | What changed, decisions (choice → alternative rejected → why), how verified, interview-relevant points; `Key code` for core tasks | Coding agent |
| `docs/learning/glossary.md` | Terms an interviewer would plausibly use, one line each | Agent appends; you edit |
| `docs/learning/SNN-*.md` (slice brief) | Per slice: what was built, decisions table, interview Q&A with answers, numbers to remember | Coding agent, via `/slice-retro`; you read it before merging the retro PR |
| `docs/decisions/` | The "why" for each decision | Agent drafts, you accept |

The slice briefs are your interview prep. For anything still unclear, ask in chat or run `/explain`.

## 8. Prompts

### 8.1 Claude project instructions (paste once into the chat project)

```
This project is my portfolio RAG system (see project files). I'm a new-grad SWE.
For every design decision or recommendation: state the trade-off, the main
alternative rejected, and the concepts I need to defend it in an interview.
Define jargon on first use. Respect docs/backlog.md scope and the ADRs; flag
scope creep. Distinguish facts, assumptions, and opinions. Don't write large
amounts of code in chat. Implementation happens in Claude Code, one backlog task at a time.
```

### 8.2 Start a slice (chat)

```
Slice SNN (<name>) is next. Using docs/backlog.md, the product spec and relevant
ADRs, draft docs/slices/SNN-<name>.md from the template: outcome, exit checks,
in/out scope, metric to move, 3–8 tasks with "done when", risks, ADRs needed.
Challenge anything that looks like scope creep.
```

### 8.3 Start a task (Claude Code)

```
/start-task S0X-TY
```

Or, for a whole slice (batch mode, section 4.1):

```
Work through S0X.
```

### 8.4 Review a diff (Claude Code or chat)

```
Review this diff as a strict senior engineer against the task's "done when",
CLAUDE.md rules, and ADRs. List: correctness risks, missing tests, scope
violations, simpler alternatives. Don't rewrite. Just list findings by severity.
```

### 8.5 Slice retro

```
/slice-retro SNN
```

## 9. Session hygiene

- One task per agent session. Clear or restart between tasks. Batch mode is the exception: one session per slice.
- Point the agent at the specific files; don't say "read the docs".
- When the agent goes off-plan, stop it and re-plan. Don't let it "fix forward" through scope creep.
- One task per PR. Small PRs make reverting cheap.
- Sync the claude.ai project files only at slice boundaries or before starting a new chat.
- Project rules live in the repo (`CLAUDE.md`, ADRs, docs). Claude Code's auto-memory is only for machine or tool quirks, and `/slice-retro` reviews it at every retro.

## 10. Anti-patterns to catch early

| Anti-pattern | Symptom | Fix |
|---|---|---|
| Mega-task | "Implement ingestion" in one go; a 1,500-line diff | Split before starting |
| Mirror tests | Tests restate the implementation and pass trivially | Derive tests from "done when" and edge cases |
| Unverified "done" | "Should work now" with no command output | The Definition of Done requires pasted results |
| Speculative scaffolding | Empty modules or interfaces "for later" | Delete; build only when a slice needs it |
| Silent decisions | A new library or pattern appears in a diff | Stop-and-ask trigger; write an ADR |
| AI-labelled eval | Golden answers written by the model | The golden set is human-owned |

## 11. Which doc to update when

| Event | Update |
|---|---|
| A decision is made | New ADR (draft → you accept) |
| A task is finished | Backlog checkbox and PR brief, in the task's PR; glossary if an interview-relevant term appears |
| A slice starts or ends | Slice doc; at the end, the retro PR (slice brief, backlog status flip, `architecture.md`); then sync the claude.ai project |
| Behavior or contracts change | The relevant doc (`domain-model.md`, `interfaces.md`, `evaluation.md`) |
| Scope question | Product spec (non-goals) or backlog "Proposed additions" |
