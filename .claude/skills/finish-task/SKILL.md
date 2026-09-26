---
name: finish-task
description: Finish the current backlog task. Verify with real commands, write the Explanation block, draft the PR description, and tick the backlog. Use when implementation of a task is complete.
---

# Finish task

1. **Verify.**
   - Run `make check`.
   - Also run `make test-int` if the DB, migrations or integration paths changed.
   - Report the actual output summary. If anything fails, fix it or report the failure. Never claim success without running the commands.
2. **Check "done when".** Compare the task's criteria with what exists, and list each criterion as met or unmet, with evidence.
3. **Check scope.** List the files changed. Flag anything outside the task's scope, any new dependency, and any change to `eval/golden_set/`.
4. **Write the Explanation block** exactly as specified in `CLAUDE.md` (15 lines or fewer; for `core` tasks, include "Read before merging"). Add any new terms to `docs/learning/glossary.md`.
5. **Draft the PR description** using `.github/pull_request_template.md`.
6. **Tick the task's checkbox** in `docs/backlog.md`. Don't change the slice status.
7. **Follow-ups.** List discovered work as *proposed* items for the backlog's "Proposed additions" section. Add them only if the developer agrees.
