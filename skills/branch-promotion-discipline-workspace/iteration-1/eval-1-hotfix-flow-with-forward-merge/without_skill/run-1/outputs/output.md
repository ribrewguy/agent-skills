# Hotfix Path for the Null-Pointer 500

Quick fix, but you still want to push it through the proper flow so prod isn't a special case and so develop doesn't drift.

## TL;DR

```
hotfix/null-payload-fix  →  main  →  back-merge to develop and uat
```

Branch from `main`, fix, PR to `main`, then back-merge so the lower tiers don't lose the fix.

## Step-by-step

### 1. Branch from `main`

The bug is in production code, so you want to fix it relative to what's currently in `main` — not relative to `develop`, which may have unrelated work in flight.

```bash
git fetch origin
git checkout main
git pull --ff-only
git checkout -b hotfix/null-payload-fix
```

Naming convention: `hotfix/<short-description>` or `hotfix/<ticket-id>` if you have a ticketing system.

### 2. Make the fix and add a test

5-line fix is fine, but also add a unit test that hits the endpoint with the optional field omitted. The test prevents the bug coming back next quarter when someone refactors the handler.

Commit:
```bash
git add <files>
git commit -m "fix: handle missing optional field in <endpoint> payload"
git push origin hotfix/null-payload-fix
```

### 3. PR sequence

Open `hotfix/null-payload-fix` → `main` directly. This is the difference vs. a normal feature: hotfixes go straight to `main` because waiting for the develop → uat → main cycle is what we're trying to avoid.

Gate requirements on this PR:
- Lint, typecheck, unit tests, build — all required (same as any PR to `main`).
- Integration tests — required.
- E2E tests — required.
- Smoke tests against the prod-like environment — required.
- Required reviewers — same as any merge to `main` (typically 2). Don't shortcut this; the urgency makes mistakes more likely, not less.

Merge once green. Production deploy goes out automatically (or via your normal deploy pipeline).

### 4. Verify in production

After deploy, hit the endpoint with the offending payload and confirm it no longer 500s. Watch error rates for ~15 minutes.

### 5. Back-merge to `uat` and `develop`

This is the step that gets forgotten and causes the same bug to reappear two weeks later.

```bash
# back-merge into uat
git checkout uat
git pull --ff-only
git merge --no-ff main
git push origin uat

# back-merge into develop
git checkout develop
git pull --ff-only
git merge --no-ff main   # or merge uat into develop, equivalent here
git push origin develop
```

Do these as PRs if your branch protection requires it. The merges should be trivial — same commits, no conflicts unless someone else touched the same handler.

If you skip this step, develop and uat still have the bug. The next normal release cycle (develop → uat → main) will re-introduce the null pointer because develop's version of the handler hasn't been updated.

## Why branch from `main`, not `develop`?

`develop` may have other unmerged or in-progress work that's not ready for production. If you branch from `develop`, you'd have to cherry-pick or hold those changes back when promoting. Branching from `main` keeps the hotfix surgical: only the fix goes out.

## Things to put on the team's hotfix checklist

- [ ] Branch from `main`
- [ ] Add a regression test
- [ ] Same CI gates as a normal `main` PR — no skipping
- [ ] Required reviewers for `main` are met
- [ ] After deploy, verify in prod
- [ ] Back-merge `main` into `uat`
- [ ] Back-merge `main` into `develop`
- [ ] Update the incident log / changelog
