# Moving from Single-Main to a 3-Tier Branch Flow

Here's a workable design for the transition. It's modeled on the classic Git Flow / GitHub Flow hybrid that most teams settle on once they need a stakeholder acceptance step.

## 1. Long-lived branches

Three permanent branches:

- **`develop`** — integration branch. All feature work merges here first.
- **`staging`** — stakeholder/UAT environment. Deployed to a staging environment that mirrors prod.
- **`main`** — production. What's live for customers.

I'm using `staging` rather than `uat` only because it's a slightly more common name in modern repos; either works. Pick one and be consistent.

Short-lived branches:
- `feature/<ticket>-<slug>` — feature work, branched from and merged into `develop`.
- `hotfix/<ticket>-<slug>` — emergency fixes (more on this below).
- `release/<version>` — optional, used if you want a stabilization window before promoting to staging.

## 2. How code moves

```
feature/* ──► develop ──► staging ──► main
```

Promotion is one direction. A few rules:

- Features always start from `develop` and merge back into `develop` via PR.
- When `develop` is "ready for stakeholder testing", open a PR `develop -> staging`. Merge after CI passes.
- Once stakeholders sign off in staging, open a PR `staging -> main` for production release.
- **No skipping**: a feature should never go directly from `develop` to `main`, and definitely not from a feature branch straight into `main`. The whole point of the staging tier is that stakeholders see the change before customers do.
- **No backflow**: changes don't move from `main` back into `staging` or `develop` as a normal pattern. The only sanctioned reverse motion is the post-hotfix forward-merge described below.

### Hotfix flow

When prod has a bug that can't wait for the next normal release cycle:

1. Branch from `staging` (so the fix gets stakeholder validation): `git checkout -b hotfix/XYZ staging`.
2. Implement the fix.
3. PR `hotfix/XYZ -> staging`. Validate.
4. PR `staging -> main`. Ship.
5. **Forward-merge `staging` back into `develop`** so the fix doesn't get lost on the next promotion.

The forward-merge step is the one that gets skipped most often and causes pain — the same bug reappears on the next normal release because `develop` never received the fix.

## 3. Per-tier CI gate matrix

Each tier runs progressively more checks. Faster feedback at the bottom, more thorough validation at the top.

| Gate | develop | staging | main |
|------|---------|---------|------|
| Lint | required | required | required |
| Typecheck | required | required | required |
| Unit tests | required | required | required |
| Build artifact | required | required | required |
| Integration tests | optional | required | required |
| End-to-end tests | optional | required | required |
| Smoke test in staging env | — | required | required |
| Smoke test in prod env | — | — | required |
| Security scan / SCA | optional | required | required |
| Source-branch check (correct source ref) | optional | required | required |

Why this shape:

- **Lint / typecheck / unit / build** are cheap and fast. Run everywhere. Devs get immediate feedback on a feature PR.
- **Integration & e2e** are slower and flakier. Running them on every feature PR is expensive and noisy. Gate them at the staging boundary, where the cost-benefit is right: you only run them when you're actually trying to promote.
- **Smoke tests against the deployed environment** can only run *after* the deploy, so they live at the staging->main and post-main steps.
- **Source-branch check** validates that PRs to staging come from `develop` or `hotfix/*` and PRs to `main` come from `staging`. This is what enforces the one-way flow at the tooling level.

## 4. Branch protection rules

Get stricter as you go up.

| Setting | develop | staging | main |
|---------|---------|---------|------|
| Require PR for merges | yes | yes | yes |
| Require passing status checks | yes | yes | yes |
| Required approvers | 1 | 1 | 2 |
| Restrict who can merge | maintainers+ | maintainers+ | admins only |
| Dismiss stale approvals on new commits | yes | yes | yes |
| Require linear history | optional | yes | yes |
| Forbid force pushes | yes | yes | yes |
| Forbid branch deletion | yes | yes | yes |
| Restrict source branches (via the source-ref CI check) | n/a | from `develop` or `hotfix/*` only | from `staging` only |

The escalation matters: a mistake on `develop` is an inconvenience; a mistake on `main` is a customer incident.

## 5. Adoption sequence (team of 6)

This is a culture change, not just a config change. Sequence:

### Week 0 — prep
- Discuss and ratify the flow with the whole team. Show them this doc; collect objections.
- Make sure a staging environment actually exists and is wired to deploy from a `staging` branch. If it doesn't, build that first — the tier means nothing without a real environment.

### Week 1 — set up branches and CI
- Cut `develop` from `main`'s tip.
- Cut `staging` from `main`'s tip.
- Don't try to backfill the existing `main` history into `develop` — start fresh from the cutover point.
- Add the per-tier CI workflows. Most CI systems support per-branch workflow files; configure them according to the matrix above.
- Add the source-ref check job for PRs to `staging` and `main`.

### Week 2 — branch protection
- Apply the protection rules. Start *strict*, not lenient — it's easier to relax than tighten.
- Document the new flow in the repo's `CONTRIBUTING.md` with a diagram.

### Week 3 — first cycle
- Pick a small, low-risk feature and put it through the full feature -> develop -> staging -> main cycle as a learning exercise. Have the whole team observe at least one promotion.
- Expect the first cycle to feel slow. Nobody has muscle memory yet.

### Week 4+ — stabilize
- Run a retro. What's friction? Are gates too slow? Is anyone using `--no-verify` on hooks? Are PRs getting stuck waiting for approvals?
- Tune the gates based on what you observe. Don't tune them based on what feels nice in the abstract.

### Things to communicate explicitly

- "Feature branches go to `develop`, not `main`." Repeat this. Several times.
- "If you need a hotfix, branch from `staging`, not `main`." Easy to forget.
- "After a hotfix lands in `main`, somebody owns the forward-merge to `develop`." Assign this; don't leave it to "whoever notices."
- "Demo deadlines don't override the tier flow." If a demo is tomorrow, you ship through staging tonight, not through a develop->main shortcut.

## 6. Common pitfalls to avoid

- **One CI workflow used for all three branches.** Defeats the matrix; each tier has to mean something different.
- **Hotfix forward-merge skipped.** Next release reintroduces the bug. Make this a checklist item on the hotfix PR template.
- **Stale `develop`** if `staging`/`main` get hotfixes and nobody merges them back. Same as above.
- **Direct pushes to `staging` or `main`.** Branch protection blocks this; verify it's actually configured, not just declared.
- **"Just this once" exceptions.** The flow only works if the team treats it as load-bearing. Demo deadlines, exec asks, end-of-quarter pushes — none of those are reasons to skip a tier.
