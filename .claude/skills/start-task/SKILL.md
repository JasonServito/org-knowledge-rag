---
name: start-task
description: Start a backlog task. Load its context, restate the goal, propose a plan, and create the task branch before editing anything. Use when the user says "start task S0X-TY", "next task", or begins work on a backlog item.
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
3. Reply with:
   - **Task:** ID, title, and tag (`core` / `commodity` / `human`)
   - **Goal and done-when:** restated in 2–3 lines
   - **Plan:** files to create or change; the approach; tests to write first (for deterministic logic); verification commands
   - **Size check:** estimated changed lines. If it's over ~300, propose a split.
   - **Risks / questions:** anything unclear, and any stop-and-ask trigger from `CLAUDE.md` that the plan hits
   - **Concepts involved:** 1–3 terms the developer should understand, with one-line definitions
4. **Approval before editing:**
   - For `core` tasks, schema changes, or stop-and-ask triggers: wait for explicit approval.
   - For `commodity` tasks: proceed once the plan is stated.
   - For `human` tasks: help the developer do it (for example, draft the ADR), but the developer makes the decision.
5. **Branch before the first edit:** `git switch main && git pull --ff-only && git switch -c s0X-tY-<short-name>`. Never commit to `main`.
