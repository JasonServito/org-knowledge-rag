---
name: plan-run
description: Run a sitting for slice SNN. Plan a bundle of 2-5 tasks with the developer, make every decision with the decision protocol, and write the run contract into the slice doc on a new run branch. Only when the developer types /plan-run.
argument-hint: SNN
disable-model-invocation: true
---

# Plan run (sitting)

Slice: `$ARGUMENTS`. The developer is here, and every decision for the run is made now. Follow `CLAUDE.md` ("Decisions", "Writing for the developer") and `docs/ai-workflow.md` section 4. Wait for answers.

1. **Load context.** Read `CLAUDE.md`, the slice's entry in `docs/backlog.md`, its slice doc and earlier run contracts (if any), the ADRs it references, and the last run's brief. Count Greptile credits (`CLAUDE.md`, "Greptile").
2. **Step 0, scope check.**
   - Triage parked items one by one: keep (→ Proposed additions) or drop.
   - Propose the bundle: 2–5 unchecked tasks (usually 3–4) in backlog order, with no `[human]` tasks. Flag any task that isn't in the slice doc.
   - Ask any parked questions.
3. **Step 1, big picture.** The pipeline map, then before / after / why.
   - First sitting of a slice: open with a one-screen primer on that RAG stage (what it does, why RAG needs it, one example from the corpus).
   - No slice doc yet: draft it from `docs/slices/_template.md` first, and get it approved.
4. **Step 2, the bundle as a whole.** The tasks, what each hands to the next, and what later tasks assume about earlier ones.
5. **Step 3, pre-mortem.** "Imagine the run failed. Why?" List edge cases per task and across tasks. Check them against real data where possible, showing the command and its output.
6. **Step 4, decisions.** One at a time, with the decision protocol.
   - For an ADR-level decision, start a `devils-advocate` subagent with the question, the options and your recommendation. Show its case before the developer decides.
   - If nothing needs deciding, say "No decisions needed".
7. **Step 5, verification plan.** Per task: the proof map ("done when" → proof → source of expected values), 1–3 break-it rules, and the real-data demo command. Then the bundle-level check. Expected values never come from the code under test.
8. **Step 6, PR plan.** Is there a natural seam? 1 or 2 PRs. Paid calls allowed: none unless the developer lists them.
9. **Step 7, teach-back.** Ask the developer to explain the bundle in 2–3 sentences. Fix any gaps in at most 3 bullets.
10. **Step 8, read-back and go.**
    - List every decision ("Here's what you decided") and get confirmation.
    - Branch: `git switch main && git pull --ff-only && git switch -c sNN-rN-<name>`, where N is the next run number in this slice.
    - Write the contract into the slice doc's "Run contracts" section (template in `docs/slices/_template.md`), with Status "planned". Write ADRs decided here as Accepted on the same branch.
    - Commit `SNN-RN: run contract`, then `git push -u origin <branch>`.
    - Wait for the developer to say "go".
11. **Hand-off.** End with "Next steps for you": the run-night checklist (`docs/ai-workflow.md` section 7), then `/run-bundle` in a new session started with `claude --permission-mode auto`.
