---
name: finish-task
description: Finish the current backlog task. Verify with real commands, write the PR brief, tick the backlog, then commit, push, and open the PR with gh. Use when implementation of a task is complete.
---

# Finish task

1. **Verify.**
   - Run `make check`.
   - Also run `make test-int` if the DB, migrations or integration paths changed.
   - Report the actual output summary, and keep the output for the PR. If anything fails, fix it or report the failure. Never claim success without running the commands.
2. **Check "done when".** Compare the task's criteria with what exists, and list each criterion as met or unmet, with evidence.
3. **Check scope.** List the files changed. Flag anything outside the task's scope, any new dependency, and any change to `eval/golden_set/`.
4. **Write the PR brief** exactly as specified in `CLAUDE.md`: 8 lines or fewer, and `core` tasks may add one optional `Key code` line. Add a term to `docs/learning/glossary.md` only if an interviewer would plausibly use it.
5. **Tick the task's checkbox** in `docs/backlog.md`.
6. **Ship.**
   - Commit on the task branch: `S0X-TY: <what>`.
   - Push: `git push -u origin <branch>`.
   - Open the PR with `gh pr create --base main`. Fill the body from `.github/pull_request_template.md`: the brief, the pasted check output, and the checklist.
   - Report the PR URL, then stop. **Never merge and never push to `main`.** The developer merges after the required CI checks are green.
7. **Follow-ups.** List discovered work as *proposed* items for the backlog's "Proposed additions" section. Add them only if the developer agrees.
