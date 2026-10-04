# AI-Assisted Development Workflow

This is how the project is built with AI assistance. It's **for you**, the developer. The rules themselves live in `CLAUDE.md`; this doc links there instead of repeating them.

**The goal is validated progress you can explain, not maximum code.**

## 1. How it works

- **Decide in sittings.** You and Claude plan a bundle of tasks together and make every decision (Manual mode).
- **Build in runs.** Claude builds the bundle unattended, usually overnight (auto mode), checking each task as it goes.
- **Review in the morning.** About 5 minutes per run PR. Then you say "merge" and approve the prompt.
- One-off tasks, fixes and docs use an interactive task instead (section 8).

## 2. Terms

| Term | Meaning |
|---|---|
| Bundle | 2–5 tasks planned together, usually 3–4. Human tasks are never in a bundle. |
| Sitting | An interactive Claude Code session (Manual mode) where you and Claude plan a bundle and make every decision. |
| Run contract | The sitting's written output, stored in the slice doc: everything the run needs. |
| Run | An unattended Claude Code session (auto mode) that builds a bundle from its contract. |
| Park | Set a piece of work or a question aside, record it, and continue with independent work. |
| Check-in | A short status message printed in the session during a run. |
| Evidence pack | The proof that a task is done (`CLAUDE.md`, "Evidence pack"). |
| Claude's calls | Small, reversible decisions Claude made itself, listed so you can overrule them. |

## 3. Roles

| Who / tool | Does | Doesn't |
|---|---|---|
| **You** | Decide in sittings; review briefs; approve merges; own golden-set labels; triage parked items | Run git or make by hand (except the run-night setup); carry prompts between tools |
| **Claude Code: sitting** (Manual) | Plans bundles, explains, runs the decision protocol, drafts slice docs, ADRs and contracts | Build unattended |
| **Claude Code: run** (auto) | Builds, tests, reviews, opens PRs; merges when you say "merge" and approve the prompt | Make decisions (it parks them) |
| **claude.ai project** | Learning, interview prep, workflow reviews, an outside opinion when you want one | Required steps |
| **GitHub** | CI (`check`, `integration`); the `protect-main` ruleset protects `main` | — |
| **Greptile** | One outside review per run PR | — |

## 4. Sitting agenda (`/plan-run SNN`)

- **Step 0, scope check:**
  - triage parked items one by one (keep → Proposed additions, or drop)
  - flag bundle items that aren't in the slice doc
  - ask any parked questions
- **Step 1, big picture:** the pipeline map, then before / after / why.
  - In the first sitting of a slice, open with a one-screen primer on that RAG stage: what it does, why RAG needs it, and one example from the corpus.
  - If the slice has no doc yet, draft it first.
- **Step 2, the bundle as a whole:** the tasks, what each hands to the next, and what later tasks assume about earlier ones.
- **Step 3, pre-mortem:** "Imagine the run failed. Why?" Edge cases per task and across tasks, checked against real data where possible.
- **Step 4, decisions:** one at a time, using the decision protocol (`CLAUDE.md`, "Decisions"). Devil's advocate for ADR-level decisions.
- **Step 5, verification plan:** the proof map, the sources of expected values, the break-it rules, the demo command, and the bundle-level check.
- **Step 6, PR plan:** is there a natural seam? 1 or 2 PRs.
- **Step 7, teach-back:** you explain the bundle in 2–3 sentences, and Claude fixes any gaps in at most 3 bullets.
- **Step 8, read-back and go:** confirm the decisions, write the contract into the slice doc, commit it on the run branch. You say "go".

## 5. Run loop (`/run-bundle`)

The full rules are in `CLAUDE.md` ("Runs" and "Per-task loop"). In short:

1. A start check-in names the run and its tasks.
2. Per task: a fresh builder subagent builds and fixes until green, a `reviewer` subagent reviews once, the builder fixes must-fix items once, and the main session re-runs the checks. Then commit, push, check-in.
3. Anything that hits a stop condition is parked; the run continues with independent work.
4. End of run: bundle-level check → PR(s) → Greptile → must-fix fixes → checks again → final check-in with the PR link(s), the next-bundle proposal, and next steps for you.

A check-in looks like this:

```
[Check-in 02:14] Task 2 of 3 done: store document versions
✅ checks green · 1 parked · 0 blockers · Greptile 3/50
Next: seed the releases table
```

## 6. Morning review (about 5 minutes)

1. The proof map is all ✅.
2. CI is green.
3. Read the "Not verified" list.
4. Read the break-it result for the most important rule.
5. Optionally, re-run one demo command.
6. Say "merge" in the run session, then approve the prompt.

## 7. Run-night checklist

Your tested setup.

- **Before:**
  1. No pending Windows restart.
  2. Laptop plugged in, lid open, somewhere with airflow.
  3. Claude Desktop open with "Keep computer awake" on.
  4. Start Docker. In Ubuntu, run `tmux new -s run`, `cd` into the repo, and `make up` until it reports healthy.
  5. Check `/usage`.
  6. Run `claude --permission-mode auto`, then `/run-bundle`.
  7. **Confirm the start check-in appears.**
  8. Detach (Ctrl-b, then d). Closing the window is fine. Lock the screen (Win+L).
- **During:** `tmux attach -t run` to read check-ins.
- **After:** turn "Keep computer awake" off, exit Claude, run `make down`, quit Docker, then `tmux kill-session -t run`.

## 8. Interactive task loop (`/start-task SNN-TY`)

1. Start a fresh session in Manual mode and run `/start-task SNN-TY`.
2. The plan is a mini-sitting: the decision protocol and a proof map. You approve plans for `core` tasks, schema changes and stop-and-ask triggers. Switching to auto mode after approval is fine.
3. Claude branches (`sNN-tY-<name>`), builds with the per-task loop, then runs `/finish-task`: evidence pack, brief, PR.
4. Greptile runs only if you asked for it in the plan.
5. Review the brief, say "merge", and approve the prompt.

## 9. Closing a slice

- Run `/slice-retro SNN`, or let it be the last commit of the slice's final run.
- It checks the exit criteria, writes the slice brief (`docs/learning/SNN-*.md`), flips the slice status, and updates `docs/architecture.md` if needed.
- The slice briefs are your interview prep. Read the brief before you say "merge".
- Then sync the claude.ai project and use prompt 7 (section 11).

## 10. Session hygiene

- One run per session.
- A fresh subagent per task.
- Sittings and runs are separate sessions.
- Point Claude at specific files; don't say "read the docs".
- Project rules live in the repo (`CLAUDE.md`, ADRs, docs). Claude Code's auto-memory is only for machine or tool quirks, and `/slice-retro` reviews it at every retro.

## 11. claude.ai chats

Use the claude.ai project for learning, interview prep and workflow reviews. Sync its files at slice boundaries.

**Project instructions** (paste once into the project):

```
This project is my portfolio RAG system (see project files). I'm a new-grad SWE,
new to RAG. Claude Code builds it: I decide in sittings, Claude Code builds in
unattended runs, and I review and approve merges. Here you help me learn,
prepare for interviews, review the workflow, and give an outside opinion when
I ask. For every design decision: state the trade-off, the main alternative
rejected, and what I need to defend it in an interview. Define jargon on first
use. Respect docs/backlog.md scope and the ADRs; flag scope creep. Separate
facts, assumptions and opinions. Don't write large amounts of code. End every
answer that hands me something to do with "Next steps for you" (1–3 items).
```

**Prompt 1** (sync check, starting a new claude.ai chat):

```
Starting the <SNN> chat. From the project docs only: what's the active slice, the next unchecked task, and any open ADRs relevant to it? Flag anything in the docs that looks inconsistent.
```

**Prompt 5** (understand a decision; optional):

```
The brief for <S0X-TY or S0X-RN> says: "<decision line>". Explain in ≤5 sentences: what the choice is, the alternative rejected, why, and what an interviewer would ask about it.
```

**Prompt 7** (after the retro):

```
I read the <SNN> slice brief. These parts are unclear: <list>. Explain each briefly, and tell me if anything in the brief looks wrong against the merged code/docs.
```

**Prompt 8** (mock interview; before applying, not every slice):

```
Act as an interviewer for a new-grad backend/ML-infra role. Using the slice briefs and ADRs, ask me one question at a time about this project, follow up on weak answers, and at the end list the 3 topics I should review.
```

Prompts 2, 3, 4 and 6 from the old workflow guide are retired: sittings, skills and the `reviewer` agent do that work now.

## 12. Principles

1. **Outcome-driven.** Every slice ends with something observable: a command that works, or a metric that moved.
2. **Scope-disciplined.** The backlog decides what's next. New ideas go to "Proposed additions", never straight into the active slice.
3. **Verify, don't trust.** Nothing is done until its evidence pack shows proof you can re-run.
4. **Implementation simplicity.** Solve each task in the simplest reliable way, with minimal code, dependencies, abstractions and moving parts. There's no size cap, so this is the main guard against bloat.
5. **You own the thinking.** You decide in sittings; Claude builds and opens PRs; you approve merges.
6. **The golden set is yours.** The AI may *propose* questions. You verify every expected answer and source against the corpus. If the model grades against labels it wrote, the eval is circular.
7. **Fast feedback.** `make check` ≤ 1 min, `make test-int` ≤ 3 min, `make eval-smoke` ≤ 5 min. If a loop gets slower, fix that before adding features.

## 13. First-run checks (S03)

Assumptions to test on the first run:

- One subagent per task keeps the context fresh and follows the contract.
- Check-ins are readable through `tmux attach`.
- Auto mode respects the deny and ask rules.
- Reading Greptile's inline comments with `gh` works. Greptile reviews a stacked PR (only matters if a run splits).
- Does Greptile answer Claude's thread replies, and do those answers use credits?
- Greptile skips automatic reviews once its config is on `main` and the dashboard says Never. On PR #18 it reviewed automatically, with the config only on the PR's branch.
- Usage limits allow a full run, and the laptop stays awake all night.
- Real PR sizes: calibrate the ~800-line alarm after 2–3 runs.

After the first run, do a 10-minute tune-up. Small fixes go in a small docs PR.

## 14. Which doc to update when

| Event | Update |
|---|---|
| A decision is made | The run contract, an ADR or the slice doc (never only in chat) |
| A task is finished | Backlog checkbox and PR brief, in the same PR; glossary if an interview-relevant term appears |
| A slice starts or ends | Slice doc; at the end, the retro (slice brief, backlog status flip, `architecture.md`); then sync the claude.ai project |
| Behavior or contracts change | The relevant doc (`domain-model.md`, `interfaces.md`, `evaluation.md`) |
| Scope question | Product spec (non-goals) or backlog "Proposed additions" |
