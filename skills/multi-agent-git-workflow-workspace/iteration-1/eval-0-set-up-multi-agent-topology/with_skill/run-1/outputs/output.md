# Multi-agent topology for proj-42 (staging branch + 3-tier deploy flow)

## Beads

One parent bead, three child beads — one child per worker slice. Never reuse a single bead across slices.

- **Parent (you, the orchestrator):** `proj-42` — Add staging branch and 3-tier deploy flow
- **Child W1:** `proj-42-w1` — Policy doc updates and renames
- **Child W2:** `proj-42-w2` — CI workflow YAMLs (ci-develop / ci-staging / ci-main)
- **Child W3:** `proj-42-w3` — Source-ref enforcement workflow + pre-commit hook config

Assign each child bead to exactly one worker. Don't fold two slices into the same bead — atomic claim and audit trail depend on 1:1.

## Branches

- **Integration branch (you own this):** `integration/proj-42_staging-bringup`
- **Worker feature branches (one per child bead, one per worker):**
  - W1 → `feature/proj-42-w1_policy-docs`
  - W2 → `feature/proj-42-w2_ci-workflows`
  - W3 → `feature/proj-42-w3_source-ref-enforcement`

Each feature branch maps 1:1 to a single child bead. Don't reuse a feature branch for unrelated tasks.

## Worktrees

Multi-agent work mandates one Git worktree per agent. No agent runs in the same checkout as another. Suggested layout (sibling worktrees, outside the main checkout and outside generated output):

- Orchestrator: main repo checkout, with `integration/proj-42_staging-bringup` checked out in its own worktree, e.g. `../<repo>-proj-42-integration/`
- W1: `../<repo>-proj-42-w1/` checked out to `feature/proj-42-w1_policy-docs`
- W2: `../<repo>-proj-42-w2/` checked out to `feature/proj-42-w2_ci-workflows`
- W3: `../<repo>-proj-42-w3/` checked out to `feature/proj-42-w3_source-ref-enforcement`

Create them with:

```bash
git worktree add ../<repo>-proj-42-integration -b integration/proj-42_staging-bringup develop
git worktree add ../<repo>-proj-42-w1 -b feature/proj-42-w1_policy-docs integration/proj-42_staging-bringup
git worktree add ../<repo>-proj-42-w2 -b feature/proj-42-w2_ci-workflows integration/proj-42_staging-bringup
git worktree add ../<repo>-proj-42-w3 -b feature/proj-42-w3_source-ref-enforcement integration/proj-42_staging-bringup
```

## Integration target

- Worker feature branches → merge into `integration/proj-42_staging-bringup` (orchestrator-only).
- After all workers are accepted and integrated gates pass on the integration branch → merge `integration/proj-42_staging-bringup` into **`develop`**.
- The further promotion to a staging branch and main is out of scope for this skill — handled by branch-promotion-discipline.

## Worker responsibilities and MUST NOTs

### Each worker (W1, W2, W3) is responsible for

- Implementing exactly the slice scoped to their child bead, on their dedicated `feature/*` branch in their dedicated worktree.
- Keeping all gates green (lint, typecheck, unit tests, anything else the bead design requires) before handoff.
- Producing a worker handoff summary for you when their slice is ready: what changed, what was tested, the branch name and head SHA, any deviations from the bead design with rationale.
- Updating their child bead with progress notes; leaving the bead `in_progress` at handoff.

### Each worker MUST NOT

- **Merge their own `feature/*` branch** into another worker branch, into `integration/proj-42_staging-bringup`, into `develop`, or into `main`. Workers don't merge themselves; that's an orchestrator-coordinated decision.
- **Fix things outside their slice.** If W2 notices something broken in the policy docs (W1's lane), they raise it to you, not patch it on their own branch.
- **Close their own child bead.** The bead stays `in_progress` until you accept their branch into the integration target.
- **Push the feature branch by default.** Worker `feature/*` branches stay local unless one of these applies: you need remote access, CI is required on the branch, the user explicitly wants it published, or a remote recovery point is needed before integration. Then publish, not before.
- **Reuse the feature branch for follow-up work.** If a second slice emerges, that's a new bead and a new branch.

## Orchestrator responsibilities and MUST NOTs

### You (orchestrator on `proj-42`) are responsible for

- Owning the parent bead `proj-42` and the integration branch `integration/proj-42_staging-bringup`.
- Publishing `integration/proj-42_staging-bringup` to remote — it's the shared integration target across workers, so it must be published.
- Reviewing each worker's handoff: attempting the merge, resolving integration order across the three workers, running required integrated gates on the integration branch, verifying alignment with the bead design and PRD scope.
- Either **accepting** a worker branch (merging it into `integration/proj-42_staging-bringup`) or **rejecting** it back to the worker with explicit, structured notes.
- Resolving conflicts that arise from integration order (true integration-only changes — not implementing worker-scoped functionality).
- Closing each child bead after you merge it. Closing the parent bead `proj-42` after the integration branch is merged into `develop` and gates pass there.
- Branch cleanup after acceptance: deleting accepted local feature branches (and remote copies if they were ever published), removing dead worktrees.

### You MUST NOT

- **Implement worker-scoped functionality on the integration branch.** If W2's CI YAMLs are wrong, the answer is to reject the branch back to W2 — not to patch the YAML on `integration/proj-42_staging-bringup`. Two valid alternatives if the worker is unavailable: explicitly reassign the slice to yourself (the bead now belongs to you), or create a new bead that you own for the fix. Either way, the audit trail stays clean.
- **Silently fix worker defects.** Even small ones. The temptation ("I could just fix this typo on integration") is exactly when the orchestrator/worker boundary breaks down. Always: explicit reassignment, new bead, or rejection notes back to the worker.
- **Skip mandatory rejection.** Reject a worker branch when integration fails on merge conflicts, failing required gates (typecheck, tests, lint, build), or divergence from the bead design / architecture / PRD. These are not negotiable.
- **Merge the integration branch directly to `main`**, or merge any worker `feature/*` directly to `develop` or `main`. Worker branches go through the integration branch; the integration branch goes through `develop`.
- **Merge to `develop` without all required integrated gates passing on the integration branch.**
- **Bypass the UAT-gate ceremony** for any change that affects externally visible behavior — ask the user before any commit on the integration branch in that case.

## Commit format reminder for everyone (workers and you)

Every commit on every branch:

- Conventional Commits subject: `<type>(<scope>): <description>`
- Multi-paragraph body explaining what changed and why
- Task ID reference: bead ID inline in the subject or `Refs: <bead-id>` line in the body
- `Co-authored-by: <Model name and version> <vendor-email>` trailer for AI-assisted commits
- No silent amends — if a hook fails, the commit didn't happen; fix and create a new commit.
- Merge commits MAY use the default Git message (only exception).

## Suggested kickoff order

1. Create the four beads (`proj-42`, `proj-42-w1/w2/w3`) with assignees and DESIGN sections that scope each slice precisely.
2. Create `integration/proj-42_staging-bringup` from `develop` and publish it.
3. For each worker, create their worktree branched from the integration branch.
4. Hand each worker their bead ID, branch, and worktree path. Tell them: stay in your slice, gates green before handoff, handoff summary on completion, don't merge yourself, don't close your own bead.
