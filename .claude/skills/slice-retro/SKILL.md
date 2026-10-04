---
name: slice-retro
description: Close out a slice. Verify exit checks, summarize results with numbers, write the slice brief, flip the slice status in the backlog, and open the retro PR (or add the retro as the last commit of the slice's final run). Use when all tasks in the active slice are done.
---

# Slice retro

Follow "Writing for the developer" in `CLAUDE.md` throughout.

1. **Exit checks.** Go through each exit check in the slice doc and report met or unmet, with evidence (command output, metrics). If any are unmet, stop and report (in a run: park the retro); the slice isn't done.
2. **Results.**
   - Summarize what shipped, with numbers (counts, metrics, latency, cost).
   - From S06 onward, run or cite the eval and add the ablation row, **including negative results**.
3. **Branch.**
   - As the last step of a slice's final run: stay on the run branch. The retro is the run's last commit.
   - Otherwise: `git switch main && git pull --ff-only && git switch -c sNN-retro`.
4. **Doc updates:**
   - the slice doc's Retro section, drafted from facts only; set its Status to ✅ and fill in Finished
   - `docs/architecture.md`, if the architecture changed
   - glossary gaps: only terms an interviewer would plausibly use
   - ADR status changes: decided by the developer in a sitting or with the decision protocol, then committed as Accepted. The merge confirms them.
5. **Auto-memory review.** Read Claude Code's auto-memory for this project: `MEMORY.md` and every note it indexes, in `~/.claude/projects/<repo key>/memory/`. The key is the repo's absolute path with each `/` replaced by `-`, e.g. `-home-jservito-code-org-knowledge-rag`. In the PR body, list each entry as:
   - **keep:** a machine or tool quirk
   - **move-to-repo:** a project rule; name the target file
   - **delete:** stale, or already recorded in the repo

   Report only. Don't edit memory or move content without the developer's approval.
6. **Slice brief.** Write `docs/learning/SNN-<name>.md` from `docs/learning/_template.md`, complete:
   - where it fits on the pipeline map
   - what was built (3–5 one-line bullets)
   - the decisions table (decision / alternative rejected / why / cost), from facts and ADRs
   - 3–5 likely interview questions, each with 1–2 one-line talking points (not scripted answers)
   - numbers to remember

   No quizzes, blank fields, or grading.
7. **Status flip.** In `docs/backlog.md`, mark this slice ✅ and the next slice 🟨. If the next slice's doc exists, set its Status to 🟨. The developer approves the change by approving the merge.
8. **Ship.** Commit `SNN: retro` and push.
   - In a run, the run's PR carries the retro; put the exit-check evidence, the results and the auto-memory review in its Details.
   - Otherwise, open the PR with `gh pr create --base main`, with the same content.
   - Stop there. Merge only when the developer says "merge" (`gh pr merge <N> --merge --delete-branch`, which asks for approval).
9. **Next slice.** Say whether the next slice is ready to start, and list any blocking open questions. End with "Next steps for you", including: sync the claude.ai project after the merge, and use prompt 7 (`docs/ai-workflow.md`, section 11).
