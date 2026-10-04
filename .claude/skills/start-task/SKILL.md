---
name: start-task
description: Start a backlog task as an interactive task. Load its context, restate the goal, plan it as a mini-sitting (decision protocol and proof map), create the task branch, then build it with the per-task loop. Use when the user says "start task SNN-TY", "next task", or begins work on a backlog item.
---

# Start task

1. Identify the task:
   - If the user gave a task ID, use it.
   - Otherwise, pick the first unchecked task in the 🟨 slice of `docs/backlog.md` whose dependencies are done, and confirm it with the user.
2. Read only what's needed:
   - `CLAUDE.md` rules
   - the task entry in `docs/backlog.md`
   - its slice doc in `docs/slices/`
   - the ADR sections the slice references
   - the existing files you'll touch
3. Reply with the plan, following "Writing for the developer" in `CLAUDE.md`:
   - **Task:** ID, title, and tag (`core` / `commodity` / `human`)
   - **Where this fits:** the pipeline map, with the stage in bold
   - **Goal and done-when:** restated in 2–3 lines
   - **Plan:** files to create or change; the approach; tests to write first; verification commands
   - **Proof map:** each "done when" → the test or command that proves it → the source of its expected values (never the code under test). Add 1–3 break-it rules and, if the task touches data, the real-data demo command.
   - **Risks / questions:** anything unclear, and any stop-and-ask trigger the plan hits
   - **Concepts involved:** 1–3 terms the developer should understand, with one-line definitions
   - **Greptile:** none by default. Ask if this PR should get a review.
4. **Decisions (mini-sitting).** Run the decision protocol in `CLAUDE.md` for each "ask the developer" item, one at a time. Use a `devils-advocate` subagent for ADR-level ones. Then do the read-back. If there's nothing to decide, say "No decisions needed". List Claude's calls.
5. **Approval before editing:**
   - For `core` tasks, schema changes, or stop-and-ask triggers: wait for explicit approval.
   - For `commodity` tasks: proceed once the plan is stated.
   - For `human` tasks: help the developer do it (for example, draft the ADR), but the developer makes the decision.
   - After approval, switching to auto mode is fine.
6. **Branch before the first edit:** `git switch main && git pull --ff-only && git switch -c sNN-tY-<short-name>`. Never commit to `main`.
7. **Build with the per-task loop** (`CLAUDE.md`):
   1. Write the tests first and show red → green.
   2. Fix until `make check` (plus `make test-int` if the DB is touched) and the proof tests pass. If the same failure survives 3 fix attempts, stop and tell the developer.
   3. Start a `reviewer` subagent on the diff, once.
   4. Fix the must-fix items, once, and re-run the checks. Park the rest.
   5. Then run `/finish-task`.
