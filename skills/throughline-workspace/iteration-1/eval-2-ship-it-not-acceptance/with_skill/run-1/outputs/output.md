Got it — I'll take tf-42 through close-out now. One thing up front so there are no surprises when you're back from your meeting: **"ship it" starts the completion process, but it isn't the merge approval.** Nothing lands on `develop` without your explicit yes — and there's one other question below that needs your answer. Everything else I can do right now.

Here's the full sequence, in order:

## Phase A — Branch completion (I do this now)

**1. Re-run the full quality gates.**
The green run from an hour ago predates your "couple of small cleanups," so it's stale evidence — I won't ship on it. I'll re-run lint, typecheck, and the full test suite on the current tip of `feature/tf-42_csv-export` and report concrete pass/fail results. If anything fails, I stop here, report it, and the task stays open until it's fixed.

**2. UAT question — needs your answer.**
CSV export on the reports page is an externally visible change, so before I commit I need one of:

- **(a)** you (or I, via the browser) exercise the export once and confirm the file looks right, or
- **(b)** you explicitly waive UAT for this change.

A one-liner when you're out of the meeting is fine. No commit, push, or merge happens until then.

**3. Commit on the working branch** (after gates pass and UAT is answered).
A Conventional Commit on `feature/tf-42_csv-export` — e.g. `feat(reports): add CSV export to reports page (tf-42)` — with a real multi-paragraph body covering what changed and why, the task id, and the agent co-author trailer.

**4. Publish decision.**
You're working solo on a single-agent feature branch, so it stays local by default; I'll only push it if you want remote visibility or a PR-based merge. Either way I'll emit the pre-integration evidence block:

```
Branch: feature/tf-42_csv-export
Local SHA:  <hash>
Remote SHA: <hash or "not published">
Gates:      lint=PASS typecheck=PASS tests=PASS
git status: clean
```

**5. Implementation summary.**
I'll write up what was built, how it maps to the task's acceptance criteria, files touched, test coverage added, and any decisions worth flagging. It ends at **"ready to merge, awaiting your acceptance"** — and that's where I stop.

## Phase B — Integration (waits for you)

**6. Merge only on your explicit acceptance.**
Passing gates aren't acceptance, and "ship it" on your way to a meeting isn't either — it's what kicked off this checklist. When you're back, read the summary and gate results; on your explicit yes I fast-forward/merge `feature/tf-42_csv-export` → `develop`. That's the full extent of the merge — promotion beyond `develop` (uat/main) is a separate approved flow, not part of closing this task.

## Phase C — Closure and cleanup (immediately after the merge lands)

**7. Close tf-42 in the tracker** — only after the branch has actually reached `develop`, never before.

**8. Clean the workspace in this same close-out**, in this order:
   1. Remove the worktree for the branch, if one exists (this must precede branch deletion — git refuses to delete a branch a worktree has checked out);
   2. Delete the local `feature/tf-42_csv-export` branch;
   3. Delete the remote branch, if step 4 published one.

**9. Closeout summary.**
A short record of what shipped, the merge commit on `develop`, verification results, and cleanup confirmation — plus any learnings worth recording for future work (e.g. anything the CSV export surfaced about the reports page).

---

**So while you're in the meeting:** I'll run the gates and prepare the commit message and implementation summary. **When you're out, I need two things:** your UAT answer (exercise it or waive it) and your explicit yes to merge. From there, steps 3–9 take a couple of minutes and I'll hand you the closeout summary with the workspace already clean.
