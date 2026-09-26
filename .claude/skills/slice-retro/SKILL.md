---
name: slice-retro
description: Close out a slice. Verify exit checks, summarize results with numbers, update docs, and generate interview questions for the developer's learning note. Use when all tasks in the active slice are done.
---

# Slice retro

1. **Exit checks.** Go through each exit check in the slice doc and report met or unmet, with evidence (command output, metrics). If any are unmet, stop and report; the slice isn't done.
2. **Results.**
   - Summarize what shipped, with numbers (counts, metrics, latency, cost).
   - From S06 onward, run or cite the eval and add the ablation row, **including negative results**.
3. **Doc updates (propose; the developer confirms):**
   - the slice doc's Retro section, drafted from facts only
   - `docs/architecture.md`, if the architecture changed
   - ADR statuses to change
   - glossary gaps
4. **Learning note support.** Create `docs/learning/SNN-<name>.md` from the template, with:
   - the "Decisions and trade-offs" table pre-filled from facts and ADRs
   - 5 interview questions about this slice
   - **the answer fields and "In my own words" left blank.** The developer writes those.
5. **Next slice.** Recommend whether the next backlog slice is ready to start, and list any blocking open questions. Don't change slice statuses; the developer does.
