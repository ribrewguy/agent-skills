Got it — enjoy the meeting. Here's exactly what I'll do, in order. One thing up front: the last green test run predates the cleanups I made since, so step 1 is re-verifying before anything merges. "Ship it" gets a fresh green run first, not the hour-old one.

## 1. Re-verify the branch as it stands now

- `git status` / `git diff` — review the post-cleanup working tree so I know exactly what's about to ship and nothing stray is included.
- Run the **full test suite** again, plus lint/typecheck if the project has them. The cleanups since the last run are unverified until this passes.
- **Gate:** if anything fails, I stop here — no merge, no push. I'll leave the branch intact with a note on what failed and wait for you rather than shipping red or "fixing" my way onto trunk unsupervised.

## 2. Commit the remaining cleanups

- Stage and commit the small cleanups on `feature/tf-42_csv-export` with a message referencing the task, e.g. `tf-42: cleanup pass on CSV export (naming, dead code)`.
- Confirm `git status` is clean — nothing uncommitted left behind.

## 3. Sync with trunk

- `git fetch origin`
- Rebase the branch onto `origin/develop` (solo branch, so rebase is safe): `git rebase origin/develop`.
- If the rebase pulled in any upstream changes, **re-run the test suite once more** — the merged combination is what actually ships, and it's never been tested until now. If develop hasn't moved, this is a no-op and I skip the re-run.
- Any non-trivial conflict: I stop and leave it for when you're back rather than guessing.

## 4. Merge to develop and push

- `git checkout develop && git pull --ff-only origin develop`
- `git merge --no-ff feature/tf-42_csv-export` — the merge commit keeps the feature's history grouped (I'll follow fast-forward instead if that's the repo's established convention).
- `git push origin develop`
- If CI runs on develop, I'll confirm the pipeline goes green before calling it shipped; if it fails, I'll tell you immediately rather than closing the task.

## 5. Close the task

- Mark **tf-42** closed in the tracker with a short closing note: what shipped (CSV export on the reports page), the merge commit hash on `develop`, and that the full suite passed at ship time.

## 6. Clean up the workspace

- `git branch -d feature/tf-42_csv-export` (`-d`, not `-D` — it only deletes if the merge really landed, a free safety check).
- Delete the remote branch if one was pushed: `git push origin --delete feature/tf-42_csv-export`.
- `git remote prune origin` and a final `git status` on `develop` to confirm a clean tree.

## What you'll find when you're back

Either: tf-42 closed, CSV export merged to `develop` and pushed, branch deleted, clean workspace — with the merge commit hash in the task note. Or, if any gate failed (tests, rebase conflict, CI): everything left exactly where it was, branch untouched, with a clear summary of what blocked the ship so we can pick it up together.
