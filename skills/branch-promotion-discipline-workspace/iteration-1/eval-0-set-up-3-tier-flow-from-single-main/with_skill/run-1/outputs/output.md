# 3-Tier Branch Flow Design

## Long-lived branches

Three, in promotion order:

1. **`develop`** — integration of accepted feature work. Updated by feature-branch merges.
2. **`uat`** — long-lived stakeholder acceptance environment. Deployed to a UAT environment that mirrors production. Updated only by promotion from `develop` (or by `hotfix/*` from main-direction emergencies).
3. **`main`** — production. Updated only by promotion from `uat`.

`uat` and `main` are *long-lived environment branches* — each maps 1:1 to a deployed environment that lives indefinitely. They are not periodic release branches.

## How code moves

```
feature/* --> develop --> uat --> main
```

One-way only. The following are forbidden:

- **`develop` to `main`** (skipping `uat`). The whole point of `uat` is stakeholder acceptance; bypassing it defeats the tier.
- **`main` to `uat`** as a normal flow (backflow). `main` only flows back to other branches via the post-hotfix forward-merge, never as a promotion direction.
- **`uat` to `develop`** as a normal flow. The single exception is the **post-hotfix forward-merge** from `uat` to `develop` to keep them in sync after a hotfix lands.
- **`feature/*` directly to `uat` or `main`**. Feature branches always go to `develop` first.

### Source-ref enforcement

Each long-lived branch's CI runs a source-ref check on incoming PRs. This is enforcement, not just documentation:

- A PR targeting `uat` MUST have source ref `develop` or `hotfix/*`.
- A PR targeting `main` MUST have source ref `uat`.
- A PR targeting `develop` MUST have source ref `feature/*` or `integration/*` (never `uat`, never `main`).

A wrong source ref fails the source-ref check and cannot be merged regardless of the rest of the gates.

## Per-tier CI gate matrix

Each tier has its own workflow. Adding a gate to an upper tier does not automatically add it to a lower tier.

| Gate | develop | uat | main |
|---|---|---|---|
| Lint | required | required | required |
| Typecheck | required | required | required |
| Unit tests | required | required | required |
| Build artifact | required | required | required |
| Integration tests | optional | required | required |
| End-to-end tests | optional | required | required |
| UAT environment smoke tests | n/a | required | required |
| Production environment smoke tests | n/a | n/a | required |
| Source-ref check | required | required | required |
| Change-management metadata | n/a | n/a | required |

### Why integration / e2e are optional on develop

A typical develop tip sees many merges per day. Running a slow e2e suite on every merge is expensive and usually low-signal because most regressions don't reach a deployable state until promotion. Gating e2e at the `uat` boundary is where the cost-benefit lands. If e2e is fast (under ~5 min) and budget allows, promote it to required on develop too.

### Why the matrix differentiates

Each tier requires at least one gate the previous tier doesn't. Otherwise promotion becomes a rubber stamp — the tiers wouldn't *mean* anything different.

## Branch protection rules

Strict on top, lenient on bottom. The cost of a mistake escalates with each tier.

| Setting | develop | uat | main |
|---|---|---|---|
| Require PR before merge | yes | yes | yes |
| Require status checks to pass | yes | yes | yes |
| Require source-ref check | yes | yes | yes |
| Required approvers | 1 | 1 | 2 |
| Dismiss stale approvals on push | optional | yes | yes |
| Require linear history | optional | yes | yes |
| Restrict push to admins | no | no | yes |
| Disallow force pushes | yes | yes | yes |
| Disallow deletions | yes | yes | yes |

If the host's plan tier doesn't expose all of these (e.g., GitHub free on private repos), document the gaps and treat them as discipline-binding until the plan is upgraded.

## Adoption sequence (team of ~6)

This is a culture change, not just a config change. Sequence it:

1. **Create the branches.** From current `main` tip, branch `develop` and `uat`. They start identical to `main` — no history backfill.
2. **Update branch protection.** Configure the rule rows above on all three branches. `main` accepts PRs only from `uat`; `uat` accepts only from `develop` or `hotfix/*`; `develop` accepts only from `feature/*` or `integration/*`.
3. **Wire source-ref enforcement.** Add the source-ref check workflow on PRs to `uat` and `main`. Optionally on `develop` to catch malformed feature branches early.
4. **Split the CI workflows per tier** so each branch runs its own gate set per the matrix above. The most common mistake is one workflow firing on all three; the matrix has to differentiate.
5. **Provision the UAT environment.** `uat` only earns the name if there's a real deployed environment for stakeholders to look at. Wire the deploy step on every push to `uat`.
6. **Communicate with the team.** A 6-person team needs a 30-minute walkthrough: what each branch means, where to open PRs, why a feature branch can't go straight to main anymore, what to do for a hotfix. The first cycle (feature to develop to uat to main) will feel slow because nobody has muscle memory yet — that's expected.
7. **First production release through the new flow.** Pick a low-risk piece of work to push through develop -> uat -> main as the proof. Take notes on friction and tighten the docs.
8. **Don't backfill history.** Everything before the cutover lives in `main`'s history as-is. The new flow starts at the cutover.

## Hotfix flow (for completeness)

When a production bug needs fixing faster than develop -> uat -> main cadence:

1. Branch from `uat`: `git checkout -b hotfix/<id>_<name> uat`. (Hotfixes still need stakeholder acceptance.) Exception: if the bug exists only on `main` because it was introduced by the most recent uat-to-main promotion, branching from `main` is acceptable with explicit stakeholder approval.
2. Implement the fix.
3. PR `hotfix/*` to `uat`. Source-ref check accepts `hotfix/*`.
4. After acceptance, PR `uat` to `main`. Hotfix reaches production.
5. **Forward-merge `uat` to `develop`**. Without this, `develop` still has the bug, and the next develop-to-uat-to-main cycle reintroduces it. The forward-merge is the load-bearing step of the hotfix flow.

## Common failure modes to watch for

- `develop` merged direct to `main`, skipping `uat`. The source-ref check rejects this.
- A hotfix lands in `main` but the forward-merge to `develop` is skipped — next promotion cycle reintroduces the bug.
- One CI gate set used for every tier; promotions become rubber stamps.
- Pre-commit / CI gates so slow people start using `--no-verify`. Keep pre-commit fast (format, lint --cache, typecheck on changed files only).
