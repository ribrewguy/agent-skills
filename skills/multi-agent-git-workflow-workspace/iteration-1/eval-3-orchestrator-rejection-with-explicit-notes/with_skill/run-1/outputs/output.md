# Rejection notes — proj-42-w3 (source-ref enforcement + pre-commit hook)

**Decision: REJECTED.** Branch `feature/proj-42-w3_source-ref-enforcement` is not being merged into `integration/proj-42_staging-bringup` at this time. Bead `proj-42-w3` remains `in_progress` and stays assigned to you. Please address the issues below and re-hand-off the same branch.

This is not "requesting changes" or "small concerns." Two required gates fail and the implementation diverges from the bead design — those are mandatory rejection conditions. The branch goes back to you, not forward to integration.

---

## Failures

### Category: failing required gates

**1. Typecheck — 4 errors in `.github/workflows/ci-staging.yml.types.ts`**

The typed wrapper you added doesn't compile. 4 typecheck errors in that single file when I run the integrated typecheck. The integration target requires typecheck-clean; this blocks merge.

- File: `.github/workflows/ci-staging.yml.types.ts`
- Action: fix the type definitions so the wrapper compiles cleanly under the same typecheck config that gated your local feature branch. If the gate passed locally for you and fails for me, we have a config drift to investigate — please confirm which `tsconfig` your local typecheck used, and reproduce against the integration-branch config.

**2. Unit tests — 2 new tests fail (NODE_VERSION not set in CI)**

The existing suite passes, but the 2 new tests you added fail because they assume `process.env.NODE_VERSION` is set. It isn't, in CI, and we shouldn't make that an implicit precondition.

- Action: fix the tests, not the environment. Either (a) set `NODE_VERSION` explicitly in the test setup so the tests own their own preconditions, or (b) read it via a helper that has a sensible fallback for unset, and assert against the helper. Don't add a CI-side env mutation to paper over the test assumption.

### Category: design divergence (bead design / architecture)

**3. Pre-commit hook tooling: husky vs simple-git-hooks**

The branch adds an `.husky/` directory. The bead design (and the team's pre-commit hook policy) specifies **simple-git-hooks**, not husky. This is a design divergence, not a gate failure — and it's the load-bearing reason this can't be patched on the integration branch and waved through.

- Action: remove the `.husky/` directory entirely (no leftover config, no fallback). Implement the pre-commit hook configuration via simple-git-hooks per the bead design. If you believe simple-git-hooks is the wrong choice, raise that as a design question on the bead before changing tooling — don't ship the alternative tool and force a decision at integration.

---

## What I am not doing

- I am **not** fixing the typecheck errors on the integration branch. The wrapper is your slice — fix it on your branch.
- I am **not** patching the failing tests on the integration branch. Same reason.
- I am **not** swapping `.husky/` for simple-git-hooks myself. That would be silently absorbing a worker-owned design defect, which destroys the audit trail and erases your visibility into what was wrong.

If for any reason you can't pick this back up, the right move is explicit reassignment of `proj-42-w3` (so it formally becomes someone else's bead) or a new bead I own for the fix. Not a quiet edit on integration.

---

## What you do next

1. Pull the rejection notes onto `feature/proj-42-w3_source-ref-enforcement`.
2. Address the three items above on the same branch (don't fork the work into a new branch).
3. Re-run all gates locally — lint, typecheck, full unit test suite — green before re-handoff.
4. Update `proj-42-w3` with a progress note recording the rejection, what you changed, and the new head SHA.
5. Re-hand-off with an updated worker handoff summary noting the changes since the previous handoff.

The bead stays `in_progress` and assigned to you throughout. I'll re-attempt integration when you're ready.

---

## Audit trail note

I'll record this rejection on bead `proj-42-w3` with a pointer to these notes (gate failures + design divergence + re-handoff requested), so the bead history shows the round-trip rather than a silent re-merge.
