---
name: post-merge-cleanup
description: After a PR is merged on GitHub, sync main, delete the merged feature branch locally and on the remote, prune stale refs, and verify the repo is healthy. Use when the user says they merged a PR and wants dead branches removed and cleanup done.
---

# Post-merge cleanup

The user merged a PR on GitHub (the PR number may be given as an argument, e.g. `/post-merge-cleanup 14`). Bring the local repo in sync and remove everything the merge made obsolete.

## Steps

1. **Identify the merged branch.** If a PR number was given, get its head branch and confirm it is merged:
   `gh pr view <number> --json headRefName,state,mergeCommit`
   If no number was given, infer the branch: the current non-main branch, or the most recently merged PR (`gh pr list --state merged --limit 1 --json number,headRefName`). If the PR is not actually merged, stop and tell the user — do not delete anything.

2. **Sync main.**
   `git checkout main && git pull`
   The merge commit for the PR should now be at or behind `HEAD`.

3. **Delete the local feature branch.**
   `git branch -d <branch>` — if git refuses because the PR was squash- or rebase-merged (branch "not fully merged"), verify via `gh pr view` that the PR state is MERGED, then use `git branch -D <branch>`. Never force-delete a branch whose PR is not merged.

4. **Delete the remote branch.**
   `git push origin --delete <branch>` — run this as a standalone command (a hook blocks compound git commands that look like pushes to main). If GitHub already auto-deleted the branch, this errors harmlessly; note it and move on.

5. **Prune stale remote refs.**
   `git fetch --prune`, then `git branch -a` to confirm only expected branches remain. Also delete any other local branches whose PRs are merged (check with `gh pr list --state merged`) — but ask before deleting branches with unpushed work.

6. **Verify the repo is healthy on merged main.**
   `uv run pytest -q` — the offline suite must pass. Report the result.

7. **Other cleanup as necessary.** Check `git status --short` for leftovers from the branch's work (scratch files, stale artifacts) and remove only things this session created; leave the user's untracked files alone. If a SQLite WAL file has grown, checkpoint it: `sqlite3 data/fundamentals.db "PRAGMA wal_checkpoint(TRUNCATE);"`. If a plan document tracked the merged work, mark it completed with the PR number and merge commit.

## Report

Summarize: branch deleted (local + remote), main's new HEAD, test result, and any extra cleanup performed.
