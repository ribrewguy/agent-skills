# CI Gate Matrix for develop / uat / main

The shape: each tier requires at least one gate the tier below doesn't. Promotion has to *mean* something different at each step, otherwise it's just a rubber stamp.

## The matrix

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
| Source-ref check | optional | required | required |
| Change-management metadata | n/a | n/a | required |

## Why each gate runs where it runs

### Lint — required at all three tiers

Cheap, fast, deterministic. The cost of running it everywhere is negligible and a lint failure on `main` would be embarrassing. No reason to skip at any tier.

### Typecheck — required at all three tiers

Same reasoning. Runs in seconds-to-minutes, catches real bugs, and the cost of letting an untyped change through to a higher tier is much greater than the marginal CI cost of running it again. Type errors on `main` are silly.

### Unit tests — required at all three tiers

Fast, isolated, and the safety net that should always have caught the obvious regressions. Required everywhere. If unit tests are slow enough that you'd want to skip them at `develop`, fix the unit tests — they're not actually unit tests anymore.

### Build artifact — required at all three tiers

The build has to succeed everywhere. The artifact is what actually gets deployed; you don't want to discover at the `uat` boundary that something on `develop` doesn't build. Also: the build cache often makes downstream builds nearly free.

### Integration tests — optional on develop, required at uat and main

This is where the matrix starts to differentiate.

- A typical `develop` tip sees many merges per day. Running the integration suite per-merge is expensive and noisy — most failures get fixed by the next merge anyway, and the genuinely-broken merges usually have unit-test failures too.
- At the `uat` boundary you're saying "we think this is ready to show stakeholders." Integration tests *must* pass before you make that claim.
- Required at `main` for the same reason any uat-required gate is required at main: main is strictly stricter than uat.

If your team has fast integration tests (under a few minutes total) and budget to run them per-merge, promote it to required on develop. The matrix accommodates that. The reason for "optional" rather than "required" on develop is the cost-benefit, not the principle.

### End-to-end tests — optional on develop, required at uat and main

Same reasoning, more so. E2e tests are slow (often 15+ minutes), historically the flakiest in the suite, and the cost of running them per-develop-merge is high while the signal at that point is usually low. Most e2e failures on a develop tip get fixed by an unrelated subsequent merge before anyone investigates.

Gating e2e at the `uat` boundary is where the cost-benefit lands for most teams: you only pay the e2e cost when you're actually trying to promote, and you only block promotions that have a real risk of regressing user-visible flows.

If your e2e suite is fast (under 5 minutes) and stable, promote it to required on develop. Otherwise leave it at the uat boundary.

### UAT environment smoke tests — required at uat and main, n/a on develop

Smoke tests against the deployed UAT environment can only run *after* the deploy has happened. They live at the uat boundary by definition. They run again as a gate on the uat -> main promotion to confirm nothing has drifted between when the uat PR merged and when the main PR is opened.

`develop` doesn't have a deployed environment to smoke against (there's no "develop environment" in this flow — develop is integration, not a deployment target).

### Production environment smoke tests — required at main only

Same shape, but against production. They run after the main deploy. The reason this row is `n/a` for the lower tiers is obvious: there's no production environment for develop or uat to smoke against, by definition.

### Source-ref check — optional on develop, required at uat and main

This is the gate that enforces one-way promotion at the tooling level rather than just policy.

- A PR targeting `uat` MUST have source ref `develop` or `hotfix/*`.
- A PR targeting `main` MUST have source ref `uat`.

If you mention source-ref enforcement on `develop` at all, it should accept `feature/*` and `integration/*` as valid sources and reject `uat` or `main`. (Feature work can't legally come from upstream tiers.) On many repos the `develop` source-ref check is left optional because the lower tiers' protection rules already prevent direct push and feature branches naturally have correct prefixes. The strict enforcement matters most where the cost of a wrong-direction merge is highest, i.e., at `uat` and `main`.

A wrong source-ref fails the check and cannot be merged regardless of the rest of the gates.

### Change-management metadata — required at main only

Release notes, on-call notification, link to a change ticket if your org has one. Lower tiers don't need this overhead; production deploys do.

## Per-tier list (alternate view)

If you prefer a per-tier reading rather than the table:

**develop**
- Required: lint, typecheck, unit, build
- Optional: integration, e2e
- Optional but recommended: source-ref check (rejects `uat`/`main` as sources)

**uat** (everything in develop, plus:)
- Required: integration, e2e, source-ref check
- Required after deploy: UAT environment smoke tests
- Source-ref check accepts `develop` and `hotfix/*`

**main** (everything in uat, plus:)
- Required after deploy: production environment smoke tests
- Required: change-management metadata
- Source-ref check accepts only `uat`
- (Branch protection adds: 2 approvers, admins-only push, etc., though that's protection rather than CI gates)

## The principle

Each tier strictly stricter than the last. Each promotion crosses a gate the prior tier didn't have. This is what makes "promoted to uat" and "released to main" mean different things in a verifiable, tooling-enforced way — not just a label in the team chat.
