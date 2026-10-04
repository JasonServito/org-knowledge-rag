---
name: finish-task
description: Finish the current interactive task. Verify with real commands, complete the review pass and the evidence pack, write the two-layer PR brief, tick the backlog, then commit, push, and open the PR with gh. Use when implementation of a task is complete.
---

# Finish task

1. **Verify.**
   - Run `make check`.
   - Also run `make test-int` if the DB, migrations or integration paths changed.
   - Copy the output; never retype it. If anything fails, fix it or report the failure. Never claim success without running the commands.
2. **Review pass.** If the per-task loop's review hasn't happened yet, start a `reviewer` subagent on the diff. Fix the must-fix items once, then repeat step 1. Park the rest.
3. **Evidence pack** (`CLAUDE.md`, "Evidence pack"):
   - the proof map: each "done when" → proof → result
   - where the expected values came from
   - red → green for tests written first; the break-it results, with `git diff` showing the code was restored
   - the real-data demo command and a short output excerpt, if the task touches data
   - the "Not verified" list
4. **Check scope.** List the files changed. Flag anything outside the task's scope, any new dependency, and any change to `eval/golden_set/`.
5. **Write the PR brief** from `.github/pull_request_template.md`, following "Writing for the developer" in `CLAUDE.md`.
   - The top section fits on one screen and has no file paths.
   - It ends with "Next steps for you".
   - Key code, Claude's calls, interview talking points and the size line go in Details.
   - Add a term to `docs/learning/glossary.md` only if an interviewer would plausibly use it.
6. **Tick the task's checkbox** in `docs/backlog.md`.
7. **Ship.**
   - Commit on the task branch: `SNN-TY: <what>`.
   - Push: `git push -u origin <branch>`.
   - Open the PR with `gh pr create --base main` and the brief as the body.
8. **CI and Greptile.**
   - Wait for CI with `gh pr checks <N> --watch`, then add the CI link to the brief (`gh pr edit <N> --body-file <file>`).
   - Greptile only if the developer asked for it in the plan. Handle its comments as in `/run-bundle` ("End of run", step 6).
9. **Report and stop.** Print the brief's top section with the PR link, ending with "Next steps for you". Never push to `main`.
10. **Merge only on request.** When the developer says "merge", confirm CI is green and every review thread is resolved. Then run `gh pr merge <N> --merge --delete-branch`, which asks for approval.
11. **Follow-ups.** List discovered work as *proposed* items for the backlog's "Proposed additions" section. Add them only if the developer agrees.
