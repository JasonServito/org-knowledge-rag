# Workflow v2 handoff

- **Date:** 2026-10-04
- **For:** Claude Code, as **one interactive docs/config task** (not a run)
- **Source:** workflow review in the claude.ai project (items 1–9), decided by the developer
- **After merge:** this file is a historical record. The rules live in `CLAUDE.md` and `docs/ai-workflow.md`.

## 0. How to implement this handoff

1. Start in **Manual mode** (`claude --permission-mode default`). Read this file, `CLAUDE.md`, `docs/ai-workflow.md`, the Rules section of `docs/backlog.md`, and every file listed in §4.
2. **Plan first, then wait for approval.** List every file you will change, with one line each. Flag anything here that conflicts with an ADR, the product spec, or itself.
3. Create the branch `workflow-v2` from an up-to-date `main`. One PR. Group commits by area (`workflow-v2: CLAUDE.md`, `workflow-v2: skills`, …).
4. **Docs and config only.** Don't touch `src/`, `tests/`, `config/`, migrations, or any ADR's decision content.
5. **Check current syntax before writing tool config** (Claude Code permissions, skills and subagents; Greptile config). Where a key or pattern suggested here differs from the official docs, follow the docs and note it in the PR.
6. Keep every doc short and plain. They are read by a developer who is new to RAG, and by agents.
7. Write the PR brief in the **new format** (§5.1), and pass the acceptance checks (§7).
8. **Skip Greptile** for this PR, because it is docs/config only.
9. The developer merges this PR **by hand on GitHub**. The new merge gate only exists after it merges.

## 1. Goal

Speed up and simplify development while keeping scope tight, results verifiable, the design simple, and the context easy to maintain. The developer is a new grad and new to RAG. Every output must be plain-language, verifiable, and end with next steps.

## 2. Decision log

| # | Topic | Decision |
|---|---|---|
| 1 | Merge gate | Keep the `protect-main` ruleset as it is. Claude merges a PR **only** after the developer approves a permission prompt (an `ask` rule on `gh pr merge`). |
| — | Size cap | Remove the ~300-line task cap. Runs have no time or line limits. |
| 2 | Working model | **Plan together, run alone:** a detailed sitting with the developer, then an unattended run of a task bundle, then a review. |
| 2a | Check-ins | Printed in the Claude Code session: at the start, after each task, after each park, and at the end. No draft PRs. |
| 2b | No-progress rule | The same failure after 3 fix attempts → park that piece. |
| 2c | Permission modes | Runs: auto mode. Sittings: Manual mode. |
| 3 | Loops | A bounded loop per task: build → fix until green → one review pass → one fix round → verify. **Loops fix or simplify, never add.** |
| 4 | PRs | **S1+:** one PR per run; split into 2 at a task boundary only on a natural seam or a size alarm. Merge commits. Greptile on the Base tier, triggered manually, used mindfully, hard max 50 credits. |
| 5 | Verifiability | An evidence pack per task, reported briefly. Playwright later (S17). |
| 6 | PR brief | A two-layer brief: a plain top section and collapsed details. Short interview notes. A fixed check-in format. |
| 7 | Decisions | A decision protocol. **Decisions stay in the sitting.** |
| 8 | Tools | Claude Code is the single workspace. claude.ai is for learning, interview prep and workflow reviews. A one-screen primer (first sitting of a slice) and a teach-back (every sitting). |
| 9 | Coordination | No new tools. Each run proposes the next bundle. Cloud runs go to Proposed additions. |
| + | Next steps | Every output that hands something to the developer ends with **Next steps for you** (1–3 items). |

## 3. Terms (define these in `docs/ai-workflow.md`)

| Term | Meaning |
|---|---|
| Bundle | 2–5 tasks planned together, usually 3–4. Human tasks are never in a bundle. |
| Sitting | An interactive Claude Code session (Manual mode) where the developer and Claude plan a bundle and make every decision. |
| Run contract | The sitting's written output, stored in the slice doc: everything the run needs. |
| Run | An unattended Claude Code session (auto mode) that builds a bundle from its contract. |
| Park | Set a piece of work or a question aside, record it, and continue with independent work. |
| Check-in | A short status message printed in the session during a run. |
| Evidence pack | The proof that a task is done (§4.1, "Evidence pack"). |
| Claude's calls | Small, reversible decisions Claude made itself, listed so the developer can overrule them. |

## 4. Changes by file

### 4.1 `CLAUDE.md`

**Remove**

- The size guideline (about 300 changed lines per task).
- The "Batch mode" section.
- "One task per branch and per PR" as a universal rule, and "Claude Code never merges a PR" (both replaced below).
- The old 8-line PR brief section (replaced by §5.1).

**Add a principle**

*Implementation simplicity:* solve each task in the simplest reliable way, with minimal code, dependencies, abstractions and moving parts. With no size cap, this is the main guard against bloat.

**Add "Two working modes"**

| Mode | How to start | Use for |
|---|---|---|
| Interactive task | `claude --permission-mode default`, then `/start-task SNN-TY` | One-off tasks, fixes, docs |
| Sitting → run | Sitting: `claude --permission-mode default`, then `/plan-run SNN`. Run: a new session with `claude --permission-mode auto`, then `/run` | Bundles of slice tasks |

In an interactive task, the plan step works as a mini-sitting: the same decision protocol and the same evidence pack. Switching to auto mode after the plan is approved is fine.

**Add "Runs"**

- The run contract lives in the slice doc and is the run branch's first commit.
- One session per run, one fresh subagent per task. Each subagent first reads `CLAUDE.md` and the contract, not the earlier subagents' output.
- Each task follows the per-task loop (below). After each task, the **main session re-runs the checks itself**, then commits (`SNN-TY: <what>`) and pushes the branch. This is the checkpoint.
- No merges and no PRs mid-run. PRs open at the end (see "Git and PRs").
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
- **Resume:** `/run` continues from the first unfinished task in the contract.
- **End of run:**
  1. bundle-level check
  2. open the PR(s)
  3. Greptile (policy below)
  4. fix must-fix items
  5. re-run the checks
  6. final check-in with the PR link(s), the next-bundle proposal, and next steps

**Add "Per-task loop"**

| Step | Repeats? | What happens | Ends when |
|---|---|---|---|
| 1. Build | No | Implement to the contract. Tests come first for "done when" items and deterministic logic | The code is written |
| 2. Fix until green | **Yes** | `make check`, plus `make test-int` if the DB is touched, plus this task's proof tests | All pass, or the no-progress rule parks it |
| 3. Review | Once | A fresh reviewer subagent checks the diff against the rubric below | Findings are sorted |
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

**Add "Decisions"**

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
- **ADR-level decisions:** a devil's-advocate subagent (fresh context) argues against the recommendation before the developer decides.
- **Read-back:** list every decision made ("Here's what you decided"), get confirmation, then record it in the contract, ADR or slice doc. Nothing is decided only in chat.
- If nothing needs deciding, say "No decisions needed" and move on.

**Add "Evidence pack" (part of the Definition of done)**

Every task produces the following, briefly:

1. **Proof map:** each "done when" item → the test or command that proves it → the result.
2. **Independent expected values:** taken from the spec, a hand calculation, or real data checked in the sitting. Never computed by the code under test.
3. **Proof the tests can fail:**
   - Red → green for tests written first.
   - A break-it check for the 1–3 most important rules named in the contract: break the code that enforces the rule, show the test fails, restore it, and confirm with `git diff`.
4. **Real-data demo** (when the task touches data): one reproducible command on a small real sample, with a short output excerpt. From S04 on, include the Langfuse trace for sample queries.
5. **Honesty rules:**
   - outputs are copied from the tools, never retyped
   - every claim has a command that reproduces it
   - a "Not verified" list
   - the CI link

**Replace "Git and PRs"**

- **Interactive tasks:** branch `sNN-tY-<name>`, one PR per task (unchanged).
- **Runs:** branch `sNN-rN-<name>`. The first commit is the run contract, then one commit per task (`SNN-TY: <what>`).
- **S1+:** one PR per run by default. Split into 2 PRs, at a task boundary, only on one of these triggers:
  - **Natural seam:** the bundle has two distinct purposes (decided in the sitting).
  - **Size alarm** (checked when opening the PR): more than ~30 changed files, or more than ~800 reviewable lines. Reviewable lines exclude lockfiles, generated files, fixtures, and docs already approved in the sitting.
- **Limits and size record:**
  - At most 2 PRs per run. A third needs the developer's OK in the sitting.
  - Record the PR size (files, reviewable lines) in every brief.
- **Stacked PRs:** when a run is split, PR 2's base is PR 1's branch (`sNN-rNb-<name>`).
- **Merging:**
  - Claude merges only with `gh pr merge <N> --merge --delete-branch`, which triggers the developer's approval prompt.
  - Merge commits only: no squash, no rebase.
- **After a stacked PR 1 merges:** GitHub retargets PR 2 to `main`. Run `gh pr update-branch <N>` (merge, not rebase), wait for CI, then ask to merge.
- Never push to `main`. Never force-push.
- **Slice status** still changes only in the retro PR. The retro can be the last commit of a slice's final run.
- **ADRs:** decided in the sitting and committed as Accepted in the run PR. The developer's merge confirms them.

**Add "Greptile"**

- **Trigger:** manual only. Comment `@greptileai` once, after the PR opens. The tier is pinned to Base. No re-review on push.
- **Sorting comments:** use the reviewer rubric. Fix must-fix items, park the rest, and dismiss false alarms with a reason. React 👍/👎 to each comment.
- **Re-review:** at most one per PR, only if the must-fix fixes changed behavior and fewer than 40 credits have been used.
- **Skip** Greptile on docs-only PRs.
- **Counting:** count `@greptileai` triggers since the billing cycle started (day **DD** of each month, which the developer fills in). Show `Greptile: N/50` in check-ins and briefs.

| Credits used | Mindset |
|---|---|
| 0–40 | Normal use |
| 41–49 | Mindful: say "running low", and prefer skipping re-reviews and docs/config-only PRs |
| 50 | Hard max: no more triggers until the reset |

**Add "Writing for the developer"** (applies to briefs, check-ins, sittings, slice briefs and any other output)

- Write for someone new to RAG. Define each term in a few words on first use, or avoid it.
- No paragraph longer than 2 lines. Bullets are one line where possible.
- Use numbers instead of adjectives.
- No file paths or function names in a brief's top section.
- **End every output that hands something to the developer with "Next steps for you":** 1–3 concrete actions (what, where, roughly how long).

**Add the pipeline map** (used in every brief)

`Sources → Ingest → Store → Chunk → Embed → Retrieve → Answer`

Non-pipeline work is labeled `Supporting: tooling / evaluation / deployment`.

**Also update**

- "Stop and ask before…": add "In a run, these park instead of stopping."
- The skills list (§4.7).
- The Definition of done: evidence pack, review pass done, must-fix items resolved, parked items listed, next steps.

### 4.2 `docs/ai-workflow.md`

Rewrite it to match. Keep it short, and link to `CLAUDE.md` for rules instead of repeating them.

1. **How it works:** decide in sittings, build in runs, review in the morning. The developer approves merges through the prompt.
2. **Roles**

| Who / tool | Does | Doesn't |
|---|---|---|
| Developer | Decides in sittings; reviews briefs; approves merges; owns golden-set labels; triages parked items | Run git or make by hand; carry prompts between tools |
| Claude Code: sitting (Manual) | Plans bundles, explains, runs the decision protocol, drafts slice docs, ADRs and contracts | Build unattended |
| Claude Code: run (auto) | Builds, tests, reviews, opens PRs, merges after approval | Make decisions |
| claude.ai project | Learning, interview prep, workflow reviews, an outside opinion when the developer wants one | Required steps |
| GitHub | CI (`check`, `integration`); the ruleset protects `main` | — |
| Greptile | One outside review per run PR | — |

3. **Sitting agenda** (`/plan-run`)
   - **Step 0, scope check:**
     - triage parked items one by one (keep → Proposed additions, or drop)
     - flag bundle items that aren't in the slice doc
     - ask any parked questions
   - **Step 1, big picture:** the pipeline map, then before / after / why.
     - In the first sitting of a slice, open with a one-screen primer on that RAG stage: what it does, why RAG needs it, and one example from the corpus.
     - If the slice has no doc yet, draft it first.
   - **Step 2, the bundle as a whole:** the tasks, what each hands to the next, and what later tasks assume about earlier ones.
   - **Step 3, pre-mortem:** "Imagine the run failed. Why?" Edge cases per task and across tasks, checked against real data where possible.
   - **Step 4, decisions:** one at a time, using the decision protocol. Devil's advocate for ADR-level decisions.
   - **Step 5, verification plan:** the proof map, the sources of expected values, the break-it rules, the demo command, and the bundle-level check.
   - **Step 6, PR plan:** is there a natural seam? 1 or 2 PRs.
   - **Step 7, teach-back:** the developer explains the bundle in 2–3 sentences, and Claude fixes any gaps in at most 3 bullets.
   - **Step 8, read-back and go:** confirm the decisions, write the contract into the slice doc, commit it on the run branch. The developer says "go".
4. **Run loop** (`/run`): a summary of §4.1 "Runs".
5. **Morning review (about 5 minutes):**
   1. the proof map is all ✅
   2. CI is green
   3. read the "Not verified" list
   4. read the break-it result for the most important rule
   5. optionally, re-run one demo command
   6. approve the merge prompt
6. **Run-night checklist** (the developer's tested setup):
   - **Before:**
     1. No pending Windows restart.
     2. Laptop plugged in, lid open, somewhere with airflow.
     3. Claude Desktop open with "Keep computer awake" on.
     4. Start Docker. In Ubuntu, run `tmux new -s run`, `cd` into the repo, and `make up` until it reports healthy.
     5. Check `/usage`.
     6. Run `claude --permission-mode auto`, then `/run`.
     7. **Confirm the start check-in appears.**
     8. Detach (Ctrl-b, then d). Closing the window is fine. Lock the screen (Win+L).
   - **During:** `tmux attach -t run` to read check-ins.
   - **After:** turn "Keep computer awake" off, exit Claude, run `make down`, quit Docker, then `tmux kill-session -t run`.
7. **Interactive task loop** (`/start-task`): updated to the per-task loop, the evidence pack, and the new brief.
8. **Closing a slice:** `/slice-retro`, which can be the last commit of the final run.
9. **Session hygiene:**
   - one run per session
   - a fresh subagent per task
   - sittings and runs are separate sessions
10. **claude.ai chats:** for learning, interview prep and workflow reviews. Sync the project at slice boundaries.
    - Keep guide prompts 1 (sync check), 5 (understand a decision; optional), 7 (after the retro) and 8 (mock interview).
    - Retire prompts 2, 3, 4 and 6.
11. **Principles:** replace "small units (~300 lines)" with implementation simplicity.

### 4.3 `docs/backlog.md`

**Rules table**

- *Git and PRs:* interactive tasks keep one task per PR; runs use S1+ (see `CLAUDE.md`). Claude merges only after the developer approves the prompt.
- *Batch mode* becomes *Runs:* a sitting (`/plan-run`), then a run (`/run`). See `CLAUDE.md`.
- *Task tags:* `[core]` means the plan is approved per task (interactive) or in the sitting (runs).
- *Slice status:* unchanged.

**Proposed additions** (append)

- **Playwright end-to-end tests + screenshots for the S17 Next.js UI.** Reason: verify UI behavior once a UI exists. Evaluate in the S17 sitting. (Workflow review 2026-10-04.)
- **Cloud runs test (`claude --cloud`).** Reason: lets the laptop stay off on run nights. Check Docker Postgres, the corpus cache, and that the merge gate still holds. Trigger: keeping the laptop on becomes a burden. (Workflow review 2026-10-04.)

### 4.4 `docs/decisions/README.md`

Replace "Only the developer sets the status to Accepted" with: "The developer decides in the sitting. Claude commits the ADR as Accepted in the run PR, and the developer's merge confirms it."

### 4.5 Templates

- `docs/slices/_template.md`: add a **Run contracts** section:

  ```
  ### Run SNN-RN: <name>
  - Status: planned / running / PR open / merged
  - Tasks: …
  - Goal (plain words): …
  - Decisions: choice → rejected → why
  - Handoffs between tasks: …
  - Edge cases: …
  - Files in scope: …
  - Proof map: "done when" → proof → source of expected values
  - Break-it rules (1–3 per task): …
  - Real-data demo: <command>
  - Bundle-level check: <command(s)>
  - PR plan: 1 PR (or 2: split after TN because …)
  - Paid calls allowed: none / list
  ```

- `.github/pull_request_template.md`: the §5.1 layout.
- `docs/learning/_template.md`: apply the writing rules. Interview questions use talking points, not scripts.

### 4.6 `.claude/settings.json`

Keep the existing allow list. Add the following, checking the exact pattern syntax in the current Claude Code docs:

- **deny:** pushes to `main`, force pushes, `sudo`, and edits under `eval/golden_set/`.
- **ask:** `gh pr merge`, with any arguments.

Don't set `defaultMode` to auto in project settings, because Claude Code ignores it there. Runs start with `--permission-mode auto`.

### 4.7 Skills (`.claude/skills/`) and subagents

| Item | Change |
|---|---|
| `/plan-run SNN` (new) | Runs the sitting agenda (§4.2, item 3) and writes the contract |
| `/run` (new) | Starts or resumes a run (§4.1, "Runs") and prints check-ins (§5.2) |
| `/start-task` | The plan step becomes a mini-sitting (decision protocol); adds the per-task loop and the evidence pack |
| `/finish-task` | New brief format, evidence pack, next steps |
| `/slice-retro` | Writing rules; can run as the last step of a slice's final run; next steps |
| `/explain` | Unchanged |
| Reviewer subagent (new) | Fresh-context review using the rubric (§4.1) |
| Devil's-advocate subagent (new) | Argues against a recommendation for ADR-level decisions |

Use the current Claude Code format for skills and subagents (check the docs). The builder is a general-purpose subagent instructed by `/run`. Don't define any agents beyond these two.

### 4.8 `.greptile/config.json` (new)

Check the current key names in Greptile's docs. The intent:

- review tier: **base**
- automatic reviews: **off** (manual `@greptileai` only), with no review on push or rebase
- PR description updates: **off**, so Greptile can't overwrite the brief
- context files: `CLAUDE.md`, `docs/architecture.md`, `docs/decisions/`

Greptile reads its config from the PR's source branch, so this takes effect for runs branched after this PR merges.

## 5. Formats

### 5.1 PR brief (two layers)

```markdown
**Where this fits:** Sources → Ingest → **Store** → Chunk → Embed → Retrieve → Answer
**Before:** Currently the project can …
**After:** Now it can … (specifically: …)
**Why:** This matters because …

**Proof**
✅ <"done when" in plain words>: <proof>
✅ Checks: format/lint/types · N unit · N integration · CI <link>
✅ Break-it: <rule> broken → test failed → restored
✅ Real data: <one-line result>
⚠️ Not verified: <list, or "nothing">

**Needs your attention**
Parked (N): <one line each>
Greptile: N comments → N fixed, N parked, N dismissed · N/50 credits
Questions for you: <list, or "none">

**Next steps for you**
1. …

<details><summary>Details</summary>

- Per task: what changed (1 line) · Key code `file:function` · commit
- Decisions: choice → rejected → why
- Claude's calls: reversible choices you can overrule
- Interview notes: 2–3 likely questions ("How does…?", "Why X over Y?", "How do you know it works?", a likely follow-up), each with 1–2 one-line talking points. Not scripts.
- Size: N files · ~N reviewable lines · split: no / yes (why)
- Commands to reproduce, with trimmed outputs

</details>
```

The top section fits on one screen (about 20 lines), uses plain language, and has no file paths.

### 5.2 Check-ins (in the run session)

```
[Check-in HH:MM] Task 2 of 3 done: <plain name>
✅ checks green · N parked · N blockers · Greptile N/50
Next: <next task>
```

- **Start:** the run name, its tasks, and "Started".
- **End:**
  - the PR link(s) and a one-line summary
  - the **next-bundle proposal**: its tasks and the decisions the developer will face
  - **Next steps for you**

## 6. Developer's manual setup

Claude Code lists these as next steps in this PR's brief.

1. **GitHub → Settings → General → Pull Requests:** allow merge commits, and turn on "Automatically delete head branches".
2. **Ruleset `protect-main`:**
   - the bypass list is empty
   - "Require linear history" is off
   - the required checks and "up to date" setting are unchanged
3. **Greptile dashboard:**
   - the repo is connected
   - tier set to Base
   - automatic reviews off
   - PR description updates off
   - note the billing-cycle start day and fill it in under "Greptile" in `CLAUDE.md`
4. **claude.ai project:** update the project instructions to the new roles and the "Next steps for you" rule. Sync after the merge.
5. **Workflow guide PDF:** regenerate it from the new `docs/ai-workflow.md`, or retire it.

## 7. Acceptance checks for this PR (proof map)

| Check | Proof |
|---|---|
| Old rules removed | `grep` for "300", "Batch mode", "one task per", "never merges" across `CLAUDE.md` and `docs/`. Any match left is intentional and explained in the PR |
| New sections exist | `CLAUDE.md` has: Two working modes, Runs, Per-task loop, Decisions, Evidence pack, Git and PRs, Greptile, Writing for the developer, the pipeline map |
| Config is valid | `python3 -m json.tool` succeeds on `.claude/settings.json` and `.greptile/config.json`; `/permissions` shows the deny and ask rules |
| Skills and agents exist | `/plan-run`, `/run`, the reviewer and the devil's advocate exist; `/start-task`, `/finish-task` and `/slice-retro` are updated |
| Templates updated | The slice template has Run contracts; the PR template has the §5.1 layout |
| Backlog updated | Proposed additions include Playwright (S17) and cloud runs |
| Nothing else touched | `git diff --stat main` lists only `CLAUDE.md`, `docs/`, `.claude/`, `.github/` and `.greptile/` |
| Still green | `make check` passes |

## 8. Assumptions to test on the first run (S03)

- One subagent per task keeps the context fresh and follows the contract.
- Check-ins are readable through `tmux attach`.
- Auto mode respects the deny and ask rules.
- Reading Greptile's inline comments with `gh` works. Greptile reviews a stacked PR (only matters if a run splits).
- Usage limits allow a full run, and the laptop stays awake all night.
- Real PR sizes: calibrate the ~800-line alarm after 2–3 runs.

After the first run, do a 10-minute tune-up. Small fixes go in a small docs PR.

## 9. Out of scope

Product code; ADR decisions; Playwright; cloud runs; routines; Cowork; parallel runs; coverage or mutation-testing tools; new dependencies.
