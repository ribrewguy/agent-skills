# Hotfix path for the null-pointer 500

A 5-line fix to a production endpoint. Run it through the hotfix flow — not a develop-to-main shortcut.

## Step 1: Branch from `uat` (not `main`)

```
git fetch origin
git checkout uat
git pull --ff-only
git checkout -b hotfix/<task_id>_null-payload-guard
```

Why `uat`, not `main`:

- The fix still needs to pass through stakeholder acceptance — that's what `uat` exists for. A hotfix isn't a license to bypass the tier.
- Branching from `uat` ensures the fix is testable in the UAT environment before it touches prod.

**Regression-only exception**: if the bug exists *only* on `main` (i.e., it was introduced by the most recent uat-to-main promotion and is not present on `uat`), branching from `main` is acceptable, but only with explicit user/stakeholder approval to skip the UAT acceptance step. In your case — a null-pointer on an optional field — the bug almost certainly predates the last release and exists on `uat` and `develop` too, so branch from `uat`.

## Step 2: Implement the fix on the hotfix branch

5 lines of null guard. Add a unit test that exercises the missing-field case so the regression has a fence around it. Commit, push.

## Step 3: PR `hotfix/*` -> `uat`

Open the PR with `uat` as target. The source-ref check on `uat` accepts `hotfix/*` (alongside `develop`) as a valid source ref, so this PR is allowed.

**Gate requirements at this step are the same as a normal develop -> uat promotion.** Urgency does not skip gates:

- Lint — required
- Typecheck — required
- Unit tests — required (including the new regression test)
- Build artifact — required
- Integration tests — required
- End-to-end tests — required
- UAT environment smoke tests — required (after deploy)
- Source-ref check — required

Once green, merge. UAT deploys. Stakeholders smoke the affected endpoint in the UAT environment.

## Step 4: PR `uat` -> `main`

After UAT acceptance, open the promotion PR `uat -> main`. Source-ref check on `main` requires source = `uat`; this PR satisfies that.

**Gate requirements are the same as a normal uat -> main promotion**:

- Lint, typecheck, unit, build artifact — required
- Integration, e2e — required
- UAT smoke + production smoke — required
- Source-ref check — required
- Change-management metadata (release notes, on-call awareness) — required

Required approvers on `main` is 2 (escalated vs. lower tiers because the cost of a `main` mistake is the highest). Get them. Merge. Deploy lands the fix on production.

## Step 5: Forward-merge `uat` -> `develop`

This is the load-bearing step and the most commonly skipped one.

```
git checkout develop
git pull --ff-only
git merge --no-ff uat
# resolve any conflicts; usually trivial right after a hotfix
git push origin develop
```

(Alternatively, do this as a PR if branch protection on `develop` requires it — `uat -> develop` is the explicitly-permitted reverse motion in the post-hotfix case, so the source-ref check on `develop` should allow `uat` as a source for *this* one path. If your check is strict feature/integration-only, do the merge as a feature-style PR titled "forward-merge hotfix `<id>` from uat".)

### Why the forward-merge matters

Without it: `main` is fixed, `uat` is fixed, but `develop` still has the bug. The next normal `develop -> uat -> main` promotion cycle will re-introduce the null pointer to `uat` and then to `main`. This is the single most common failure mode of 3-tier flows — the team thinks they're done after the hotfix lands in production, the fix gets quietly overwritten on the next release, and the bug appears to "come back from the dead."

The hotfix flow ends at the forward-merge, not at the production deploy.

## Summary of the path

```
hotfix/<id>  -->  uat  -->  main
                          \
                           +--> (forward-merge) develop
```

- Branch from: `uat`
- PR sequence: `hotfix/* -> uat`, then `uat -> main`
- Gates: full per-tier matrix at each step, no shortcuts for urgency
- After main: forward-merge `uat -> develop` to keep them in sync

## What NOT to do

- Don't branch from `main` directly (skips UAT acceptance) unless this is a regression introduced by the most recent uat-to-main promotion AND you have explicit approval.
- Don't open a PR `hotfix/* -> main`. The source-ref check on `main` only accepts `uat` as a source.
- Don't skip the forward-merge. Add it to the hotfix PR template as a checklist item if your team forgets it.
- Don't drop gates because "it's just 5 lines and we're in a hurry." The gate matrix exists to protect each tier; urgency makes mistakes more likely, not less.
