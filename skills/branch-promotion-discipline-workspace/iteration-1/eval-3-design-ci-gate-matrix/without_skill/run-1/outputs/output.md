# CI Gate Matrix for a 3-Tier Flow

The general principle: faster, cheaper checks run everywhere; slower or more expensive checks gate promotion to the next tier. Each tier should add at least one new check that the tier below didn't run, otherwise the tier isn't really doing anything.

## Matrix

| Gate | develop | uat | main |
|---|---|---|---|
| Lint | required | required | required |
| Typecheck | required | required | required |
| Unit tests | required | required | required |
| Build artifact | required | required | required |
| Integration tests | optional / advisory | required | required |
| End-to-end tests | optional / advisory | required | required |
| Smoke tests against UAT env | — | required (post-deploy) | required (regression check) |
| Smoke tests against prod env | — | — | required (post-deploy) |
| Security / dependency scan | optional | required | required |
| Source-ref check | optional | required | required |

## Per-tier rationale

### develop — fast feedback, low cost per merge

Develop is the integration branch. Many merges per day, often small. Devs need feedback in minutes, not hours.

- **Lint** — required. Trivially cheap, catches the silliest mistakes, and you don't want lint debt accumulating on develop.
- **Typecheck** — required. Same logic. A type error reaching uat would be embarrassing and the check is cheap.
- **Unit tests** — required. They're supposed to be fast, isolated, and reliable. If they're not, fix the tests, don't skip them. Required everywhere.
- **Build artifact** — required. If the code doesn't build, nothing else matters. Catch this at the lowest tier.
- **Integration tests** — optional. This is the first tradeoff. Integration tests are slower and flakier. Running them on every develop merge produces a lot of CI cost and a lot of "rerun the flaky test" noise. Recommend running them on a schedule (every push, or every N minutes) rather than as a hard gate per merge.
- **End-to-end tests** — optional, similar reasoning. E2e is the slowest, flakiest tier. Gating develop merges on e2e turns "ship a small fix" into a 30-minute wait. Most teams settle on running e2e nightly or pre-promotion, not per-merge.
- **Source-ref check** — optional, but if you do enforce one on develop, it should accept feature/* and integration/* as sources and reject any source from a higher tier (uat, main) since feature work shouldn't be flowing backward.

### uat — pre-prod confidence

Uat is where you say "we believe this is ready to be seen by stakeholders." The gate set should produce that confidence.

- Everything from develop is still required.
- **Integration tests** — required. The whole point of integration tests is to catch the things unit tests can't. Promotion to uat is the latest reasonable point to require them.
- **End-to-end tests** — required. Stakeholders are about to look at this. If a critical user flow is broken, you want to know now, not when the PM hits it during acceptance.
- **Smoke tests against UAT environment** — required, post-deploy. After the merge to uat triggers a deploy, run a small set of smoke tests against the actual UAT environment URL. This is the first time you're testing the *deployment*, not just the artifact.
- **Security / dependency scan** — required. SCA, secret scanning, license check. These are slow enough to be annoying on every develop merge but cheap enough to require at the uat boundary.
- **Source-ref check** — required. A PR to uat should have a source ref of `develop` or `hotfix/*` and nothing else. Enforce this in CI; it's the one-way-flow guardrail.

### main — production guarantees

Main is what's live. Be paranoid.

- Everything from uat is still required.
- **Smoke tests against UAT environment** — required as a *regression* check before promotion (to catch drift between the uat-merge time and the main-merge time).
- **Smoke tests against production environment** — required, post-deploy. After the main merge triggers the prod deploy, run a smoke suite against production URLs. If it fails, page on-call and roll back.
- **Source-ref check** — required, and stricter: a PR to main should have source ref of `uat` only. No `develop -> main` shortcuts, no `hotfix/* -> main`.
- **Change management metadata** — depending on your org: release notes, change ticket link, on-call notified, version tag. Make these part of the PR template and require them.

## Why slower gates live at the higher tiers

The big tradeoff is e2e (and to a lesser extent integration tests). Some teams want to run them on every develop merge to "fail fast." It usually doesn't work out for a few reasons:

- Develop sees many merges per day. Running 20 minutes of e2e per merge is real money in CI minutes.
- Most e2e failures on develop are caused by unrelated, recently-merged changes, not by the PR being tested. The signal-to-noise ratio is poor pre-promotion.
- Slow gates trained on develop pressure people into "rerun the flaky test until it passes" rather than fixing root causes — a worse outcome than not running them per-merge.

By gating e2e at the uat boundary instead, you only pay the e2e cost when promotion is actually being attempted, and you have a clear "this is the point where everything has to be green" expectation.

If the team has a *fast* e2e suite (under 5 minutes, low flake rate), promoting it to required on develop is fine — the matrix is a default, not a law.

## Source-ref check details

The source-ref check is a small CI job that inspects the PR's head ref against an allowlist for the target branch:

- PRs to `develop`: head must match `feature/*` or `integration/*` (rejects `uat`, `main`, anything else).
- PRs to `uat`: head must be `develop` or `hotfix/*`.
- PRs to `main`: head must be `uat`.

This is the difference between "we have a 3-tier flow as a convention" and "we have a 3-tier flow as enforced policy." Without the check, somebody will eventually open a `develop -> main` PR under deadline pressure and merge it before anyone reviews the base branch.

## Quick summary

```
develop:  fast checks (lint, typecheck, unit, build) — give devs sub-10-min feedback
uat:      add slower checks (integration, e2e, env smoke, source-ref) — confidence for acceptance
main:     add prod-specific checks (prod smoke, change mgmt, source-ref strict) — confidence for release
```

Each step adds something the prior step didn't, so promotion is a real promotion.
