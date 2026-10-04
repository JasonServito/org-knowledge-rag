---
name: run-bundle
description: Start or resume an unattended run. Build the tasks in the slice doc's run contract one at a time with the per-task loop, print check-ins, then open the PR(s), handle Greptile and print the final check-in. Only when the developer types /run-bundle.
argument-hint: "[SNN-RN]"
disable-model-invocation: true
---

# Run bundle

You are the main session of a run. The developer is away, so never wait for an answer: park instead. Follow `CLAUDE.md` ("Runs", "Per-task loop", "Evidence pack", "Git and PRs", "Greptile", "Writing for the developer").

## Start or resume

1. Find the contract: the run `$ARGUMENTS` if given, otherwise the run named by the current branch (`sNN-rN-*`). Read its block under "Run contracts" in the slice doc. If there's no contract, stop and say so.
2. `git switch <run branch> && git pull --ff-only`. Check that `make up` reports healthy; the end-of-run check always runs `make test-int`.
3. Tasks with a `SNN-TY:` commit on the branch are done or parked. Start at the first task with no commit.
4. Count Greptile credits, then print the start check-in:

   ```
   [Check-in HH:MM] Run SNN-RN: <name>. Started
   Tasks: 1) <plain name> 2) … 3) …
   Greptile N/50
   ```

## Per task

1. **Build and fix until green** (loop steps 1–2). Start a fresh general-purpose subagent. Give it:
   - the task ID, and "first read `CLAUDE.md` and the run contract in `<slice doc>`"
   - the task's contract lines: done when, proof map, break-it rules, demo command, files in scope
   - "Follow per-task loop steps 1–2: tests first, show red → green, apply the no-progress rule. Don't commit. Report the files changed, the commands run with copied output, the break-it results, and anything parked."

   Don't pass it earlier subagents' output.
2. **Review** (step 3). Start a `reviewer` subagent with the task's contract block and the diff: `git diff HEAD` (staged and unstaged) plus the untracked files in `git status --short`. It returns must-fix and park lists.
3. **Fix must-fix** (step 4), once. Send only the must-fix list to the builder, or to a fresh builder if it's gone. Then repeat step 2 of the loop (checks until green).
   - If it's still red or a must-fix item remains, park the task (below).

**To park a task** (no-progress rule, a stop condition, or must-fix left):

1. Keep its work: `git stash push -u -m "parked SNN-TY: <reason>"`.
2. Add `Parked: SNN-TY: <reason> (stash "parked SNN-TY")` to the contract block.
3. Commit `SNN-TY: parked (<reason>)` and push, so a resumed run skips it.
4. Skip later tasks that depend on it, parking them the same way.
4. **Verify** (step 5). Run `make check` yourself, plus `make test-int` if the DB is touched and the task's proof tests. Confirm each must-fix item was addressed. Raise no new findings.
5. **Checkpoint.** Tick the task in `docs/backlog.md`, commit `SNN-TY: <what>`, and `git push -u origin <branch>`.
6. **Check-in:**

   ```
   [Check-in HH:MM] Task 2 of 3 done: <plain name>
   ✅ checks green · N parked · N blockers · Greptile N/50
   Next: <next task>
   ```

   For a parked task, write "parked: <reason in one line>" instead of "done".

Keep running lists for the brief: each task's evidence pack, parked items, Claude's calls.

## End of run

1. **Bundle-level check** from the contract, plus `make check` and `make test-int`.
2. **Size check.** Count changed files and reviewable lines against `main`. Split only on the contract's seam or the size alarm (`CLAUDE.md`, "Git and PRs").
3. **Retro.** If the contract says this run closes the slice, follow `/slice-retro` now; it becomes the run's last commit.
4. **Open the PR(s).** Set the contract's Status to "PR open", commit and push. Then `gh pr create --base main` with the body from `.github/pull_request_template.md`.
   - To split after task TN: `git branch sNN-rNa-<name> <TN's last commit>` and push it. Open PR 1 from that branch (`--base main`), then PR 2 from the run branch (`--base sNN-rNa-<name>`). No commits move, so nothing is force-pushed.
5. **CI.** `gh pr checks <N> --watch`. Add the CI link to the brief with `gh pr edit <N> --body-file <file>`.
6. **Greptile** (`CLAUDE.md`, "Greptile"). Skip it for docs-only or config-only PRs, or at 50 credits. Otherwise:
   - Trigger: `gh pr comment <N> --body "@greptileai"`. Wait for its review, checking every few minutes for up to 30 minutes. If none arrives, list that under "Not verified".
   - Read the inline comments: `gh api repos/{owner}/{repo}/pulls/<N>/comments`.
   - Sort each with the reviewer rubric. Have a builder subagent fix the must-fix items, then re-run the checks, commit and push.
   - For each comment:
     - react: `gh api -X POST repos/{owner}/{repo}/pulls/comments/<id>/reactions -f content=+1` (or `-1`)
     - reply: `gh api -X POST repos/{owner}/{repo}/pulls/<N>/comments/<id>/replies -f body="Fixed in <sha>"` (or "Parked: …" / "Dismissed: …")
     - resolve the thread, **only if Greptile started it** (the first comment's author is `greptile-apps`). Never resolve anyone else's thread. Get thread IDs with `gh api graphql -F owner='{owner}' -F name='{repo}' -F n=<N> -f query='query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved comments(first:1){nodes{databaseId author{login}}}}}}}}'`. Then resolve each one with `gh api graphql -F id=<threadId> -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}'`.
   - Replies never mention `@greptileai`. Re-review at most once, under the rule in `CLAUDE.md`.
7. **Checks again** after any fixes; wait for CI to go green.
8. **Finish the brief:** Proof, Needs your attention (parked items, the Greptile tally, questions), Next steps for you, and Details.
9. **Final check-in**, then stop. Don't merge.

   ```
   [Check-in HH:MM] Run SNN-RN done: <one-line summary>
   PR: <link(s)> · CI green · N parked · Greptile N/50
   Next bundle (proposal): <tasks> · decisions you'll face: <list>
   Next steps for you:
   1. Morning review (~5 min): read the brief, then say "merge"
   ```

## Merging (only when the developer says "merge")

Confirm CI is green and every review thread is resolved. Then run `gh pr merge <N> --merge --delete-branch`, which asks the developer for approval. For a stacked PR 2, after PR 1 merges: `gh pr update-branch <N>`, wait for CI, then ask to merge.
