# Worker close-out for proj-42-w2 (CI workflow YAMLs)

You're at the right point. Gates green, branch ready. Here's what close-out looks like for you as a worker — and, importantly, what is **not** part of your close-out.

## What you do

### 1. Hand off to the orchestrator — do not merge yourself

Workers do not merge their own `feature/*` branches. That means you **MUST NOT**:

- Merge `feature/proj-42-w2_ci-workflows` into `integration/proj-42_staging-bringup`
- Merge it into `develop`
- Merge it into `main`
- Merge it into another worker's branch

The merge into `integration/proj-42_staging-bringup` is the orchestrator's call, not yours. They need to coordinate the merge order across workers, run integrated gates, and confirm alignment with the bead design and PRD before any of the three slices land.

### 2. Decide whether to publish the branch

Worker `feature/*` branches stay **local by default**. Publish `feature/proj-42-w2_ci-workflows` only if one of these applies:

- The orchestrator can't access your local worktree and needs remote access to review/integrate
- CI must run on the branch (branch-level gating) before acceptance
- The user explicitly wants remote visibility / auditability for this slice
- The team wants a remote recovery point before integration

If none of those apply, leave it local. If publishing, push with the explicit upstream:

```bash
git push -u origin feature/proj-42-w2_ci-workflows
```

### 3. Write the worker handoff summary

Produce a structured handoff summary for the orchestrator (the format from the worker handoff skill). At minimum:

- **Bead:** `proj-42-w2 — CI workflow YAMLs`
- **Branch:** `feature/proj-42-w2_ci-workflows` (local-only; publish status as decided above)
- **Head SHA at handoff:** `7a3f9b1`
- **Intended integration target:** `integration/proj-42_staging-bringup`
- **Gates:** lint clean, typecheck clean, 142/142 unit tests pass
- **What changed:** the three CI workflow YAMLs (ci-develop / ci-staging / ci-main), with a one-line summary of what each runs
- **What was tested:** which gates were exercised, how, where
- **Deviations from the bead design:** any (if none, say "none")
- **Open questions / risks:** anything the orchestrator should know before merging
- **Known follow-ups:** anything explicitly out of scope for this slice but worth tracking elsewhere

### 4. Update your bead with progress notes — do not close it

Add a note on `proj-42-w2` recording:

- Slice complete, gates green, branch ready for orchestrator review
- Head SHA `7a3f9b1`
- Reference to the handoff summary

The bead stays `in_progress`. **You do not close your own bead.** It closes when the orchestrator accepts the branch into `integration/proj-42_staging-bringup`. If the orchestrator rejects the branch instead, the bead stays open and you address the rejection notes and re-hand-off.

## What is NOT part of your close-out

- Merging anywhere — `integration/*`, `develop`, `main`. None of it. The orchestrator does that.
- Deleting your branch or removing your worktree. Cleanup happens after the orchestrator accepts and merges. They are responsible for deleting accepted feature branches (locally and remotely if published).
- Closing the parent bead `proj-42`. That's the orchestrator's call after the integration branch lands in `develop` and gates pass.
- Touching anything outside your slice. If you noticed an issue in W1 or W3 territory, raise it to the orchestrator separately — don't fold it in.

## Summary in one breath

Write the handoff summary, log a progress note on `proj-42-w2`, decide whether to publish the branch (local by default, publish only if the orchestrator-access / CI / user-asks / recovery-point conditions apply), hand off to the orchestrator, and wait. You're done at handoff; close-out for you ends at the orchestrator's acceptance, not before and not after.
