---
name: slice-retro
description: Close out a slice. Verify exit checks, summarize results with numbers, write the slice brief, flip the slice status in the backlog, and open the retro PR. Use when all tasks in the active slice are done.
---

# Slice retro

1. **Exit checks.** Go through each exit check in the slice doc and report met or unmet, with evidence (command output, metrics). If any are unmet, stop and report; the slice isn't done.
2. **Results.**
   - Summarize what shipped, with numbers (counts, metrics, latency, cost).
   - From S06 onward, run or cite the eval and add the ablation row, **including negative results**.
3. **Branch:** `git switch main && git pull --ff-only && git switch -c sNN-retro`.
4. **Doc updates:**
   - the slice doc's Retro section, drafted from facts only; set its Status to ✅ and fill in Finished
   - `docs/architecture.md`, if the architecture changed
   - glossary gaps: only terms an interviewer would plausibly use
   - ADR status changes: propose them only. The developer accepts ADRs.
5. **Slice brief.** Write `docs/learning/SNN-<name>.md` from `docs/learning/_template.md`, complete:
   - what was built (3–5 sentences)
   - the decisions table (decision / alternative rejected / why / cost), from facts and ADRs
   - 3–5 likely interview questions, with answers
   - numbers to remember

   No quizzes, blank answer fields, or grading.
6. **Status flip.** In `docs/backlog.md`, mark this slice ✅ and the next slice 🟨. If the next slice's doc exists, set its Status to 🟨. The developer approves the change by merging the retro PR.
7. **Ship.** Commit `SNN: retro`, push, and open the PR with `gh pr create --base main`. Put the exit-check evidence and results in the body. Stop there; **never merge.**
8. **Next slice.** Say whether the next slice is ready to start, and list any blocking open questions. Remind the developer to sync the claude.ai project after merging.
