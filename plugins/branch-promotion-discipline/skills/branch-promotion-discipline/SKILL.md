---
name: branch-promotion-discipline
description: "Use when designing or operating a multi-tier git branch flow, develop / uat / main long-lived environment branches with one-way promotion (develop to uat to main), per-tier CI gate matrices, source-ref enforcement (no skipping tiers, no backflow), hotfix flow (hotfix to uat with forward-merge to develop), branch protection ruleset, pre-commit hook setup. Layer above multi-agent-git-workflow: that skill governs feature work landing in develop; this one governs everything from develop upward. Symptoms, develop merged direct to main skipping uat, main hotfixes not forward-merged into develop causing drift, uat receiving direct pushes that bypass develop, one CI gate matrix used for every tier, no enforcement that PR source ref matches the expected previous tier."
---

# Branch Promotion Discipline

## Overview

The discipline for the long-lived environment branches above feature work: `develop`, `uat`, and `main`. Code lands in `develop` from feature branches (handled by `multi-agent-git-workflow`), gets promoted to `uat` for stakeholder acceptance, then to `main` for production. Promotion is one-way and tier-respecting; the per-tier CI gate matrix is what makes each tier mean something different.

This skill stays in the long-lived-branches lane. The per-task topology (worktrees, orchestrator/worker roles, commit format, per-commit UAT gate ceremony) is in `multi-agent-git-workflow`. Skills that need both should compose them.

## Tooling and dependencies

### Required

- **Git** with branch protection support on the host (GitHub branch protection / rulesets, GitLab protected branches, Bitbucket merge checks).
- **A CI system** (GitHub Actions, GitLab CI, CircleCI, Buildkite, etc.) that supports per-branch workflow files or per-branch gate configuration.

### Strongly recommended

- **A pre-commit hook runner.** [simple-git-hooks](https://github.com/toplenboren/simple-git-hooks) is preferred for its zero-runtime-deps profile; [husky](https://github.com/typicode/husky) also works.
- **A code-hosting platform with PR review** so promotions are PR-driven, not direct merges.

### Composes with

- [`multi-agent-git-workflow`](../../../multi-agent-git-workflow/skills/multi-agent-git-workflow/SKILL.md), this skill picks up where that one ends. The handoff is at the `develop` boundary.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md), promotion PRs (develop to uat, uat to main) get reviewed in this format, often with promotion-specific risk findings.
- [`task-handoff-summaries`](../../../task-handoff-summaries/skills/task-handoff-summaries/SKILL.md), the closeout summary records which tier the work reached. This skill defines what "promoted to uat" or "released to main" actually means in artifact terms.

## When to use

- Designing a new repo's branch flow and need to decide what the long-lived branches are and how code moves between them.
- Adopting 3-tier promotion in a repo that currently merges feature branches directly to `main`.
- A hotfix is needed in production and the team isn't sure where to branch from or how to keep `develop` from drifting after.
- A PR is open from `feature/*` to `main` (which would skip `uat`) and the question is whether to allow it.
- Setting up the CI gate matrix per branch and choosing which gates run where.
- Setting up branch protection rules for `develop`, `uat`, `main`.
- Configuring pre-commit hooks for the repo.

## The branch hierarchy

Three long-lived branches, in promotion order:

1. **`develop`**, integration of accepted feature work. The "ready for stakeholder eyes" surface. Updated by feature-branch merges (per `multi-agent-git-workflow`).
2. **`uat`**, long-lived stakeholder acceptance environment. Deployed to a UAT environment that mirrors production as closely as practical. Updated only by promotion from `develop` (or by hotfix from `main` direction, see below).
3. **`main`**, production. Updated only by promotion from `uat`.

`uat` and `main` are *long-lived environment branches*. They are not periodic release branches that get cut and abandoned. Each branch corresponds 1:1 with a deployed environment that lives indefinitely.

### Naming

The names above are the canonical defaults. Substitute equivalents (`staging` for `uat`, `production` or `release` for `main`) only with strong reason; consistency across the codebase is more valuable than name aesthetics.

## One-way promotion

Code moves in exactly one direction:

```
feature/* --> develop --> uat --> main
```

Forbidden:

- **`develop` to `main`** (skipping `uat`). The whole point of `uat` is stakeholder acceptance; bypassing it defeats the tier.
- **`main` to `uat`** as a normal flow (backflow). `main` only flows back to other branches via hotfix forward-merge, never as a promotion direction.
- **`uat` to `develop`** as a normal flow. The exception is the post-hotfix forward-merge, which goes from `uat` (after the hotfix lands) back to `develop` to keep them in sync.
- **`feature/*` directly to `uat` or `main`**. Feature branches always go to `develop` first.

The single allowed reverse motion is the **post-hotfix forward-merge** (see Hotfix flow).

## Source-ref enforcement

The one-way rule has to be enforced by tooling, not just discipline. CI on each long-lived branch checks the PR's source ref:

- A PR targeting `uat` MUST have source ref `develop` (or `hotfix/*`, see below).
- A PR targeting `main` MUST have source ref `uat`.
- A PR targeting `develop` MUST have source ref `feature/*` or `integration/*` (not `uat`, not `main`).

The CI workflow that does this check belongs at the *target branch's* gate set. A PR with a wrong source ref fails the source-ref check and cannot be merged regardless of the rest of the gates.

## CI gate matrix

Each tier has its own CI workflow with its own gate set. Adding a gate to an upper tier doesn't automatically add it to a lower tier; the matrix is explicit.

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

The matrix above is a default. Repos that don't have e2e tests yet defer the e2e row across the board until the tests exist; the matrix is a target shape, not a Day-1 requirement. The important property is that *each tier has gates the lower tier doesn't*, so promotion is a real promotion and not a rubber stamp.

### Why integration / e2e are optional on develop

A typical develop tip has tens of merges per day. Running a slow e2e suite per-merge on develop is expensive and usually low-signal because most regressions don't reach a deployable state until promotion. Gating e2e at the `uat` boundary is where the cost-benefit lands for most teams.

If the team has fast e2e (under 5 min) and budget to run it per-merge, promote it to required on `develop` too. The matrix accommodates that.

## Hotfix flow

When a production bug needs a fix faster than the normal `develop` to `uat` to `main` cadence:

1. Branch from `uat` (NOT from `main`): `git checkout -b hotfix/<task_id>_<short_name> uat`.
   - Why uat: hotfixes still need stakeholder acceptance before production. Branching from `uat` ensures the fix is testable in the UAT environment.
   - If the bug only exists on `main` (e.g., a regression introduced in the most recent uat-to-main promotion), branch from `main` instead and skip the uat acceptance step with explicit user / stakeholder approval.
2. Implement the fix on the hotfix branch.
3. PR `hotfix/*` to `uat`. Source-ref check accepts `hotfix/*` as a valid source for `uat`.
4. After acceptance, PR `uat` to `main`. Hotfix reaches production.
5. **Forward-merge `uat` to `develop`** to keep them in sync. Otherwise `develop` will reintroduce the bug at the next promotion.

The forward-merge is the load-bearing step. Skipping it produces drift: `main` is fixed, `develop` still has the bug, the next `develop` to `uat` to `main` cycle reintroduces the bug. This pattern is the most common failure mode of 3-tier flows.

## Branch protection rules

Strict on top, lenient on bottom:

| Setting | develop | uat | main |
|---|---|---|---|
| Require PR before merge | yes | yes | yes |
| Require status checks to pass | yes | yes | yes |
| Require source-ref check | yes | yes | yes |
| Required approvers | 1 | 1 | 2 |
| Dismiss stale approvals on push | optional | yes | yes |
| Require linear history | optional | yes | yes |
| Restrict who can push (admins-only) | no | no | yes |
| Disallow force pushes | yes | yes | yes |
| Disallow deletions | yes | yes | yes |

The escalating approver count and admin-only push on `main` exist because the cost of a mistake increases with each tier. Develop tolerates a one-approver pace because incidents land in `uat` first; main does not.

If the host's branch protection tier doesn't support all the rows above (e.g., GitHub's free tier on private repos doesn't expose ruleset enforcement), document the gaps. The rules become discipline-binding rather than tooling-binding until the plan tier is upgraded.

## Pre-commit hooks

Pre-commit hooks run on the developer's machine before a commit is created. They are the cheapest layer of feedback in the matrix.

### What to run pre-commit

Fast checks only. Anything that takes more than a few seconds belongs in CI, not in a pre-commit hook.

- Format check (e.g., prettier --check)
- Lint with `--cache` so only changed files run
- Typecheck only on changed files (most type checkers support this)
- Optional: a quick "did you commit a `.env` or other secret-shaped file" guard

Avoid running unit tests in a pre-commit hook unless they finish in under 2 seconds total. A 30-second pre-commit hook trains people to use `--no-verify`, which defeats the gate.

### Tooling choice

Prefer [simple-git-hooks](https://github.com/toplenboren/simple-git-hooks):

- Single-file install via package.json `simple-git-hooks` field.
- No runtime dependency in node_modules; just a Git hook script.
- Easy to read and audit.

Use [husky](https://github.com/typicode/husky) only when an existing project is already on it; greenfield repos should start with simple-git-hooks.

### Adoption sequencing

When adopting pre-commit hooks on a repo that has been operating without them:

1. Get the hooks installed and running, but configured to be **non-blocking** for the first week (warn on failure, don't fail). This catches the surface area of unexpected failures.
2. After a week of warnings, audit which checks are actually catching things vs. which are just noisy.
3. Promote stable, low-noise checks to blocking. Leave noisy ones in warning mode until they're tuned.

Going straight to blocking on day 1 produces immediate `--no-verify` adoption and the hooks become decorative.

## Adoption from a single-`main` repo

If the repo currently merges feature branches directly to `main`:

1. Create `develop` from `main` tip.
2. Create `uat` from `main` tip.
3. Update branch protection so `main` accepts PRs only from `uat`.
4. Update CI workflows to add the per-tier gate matrix.
5. Wire source-ref enforcement on PRs to `uat` and `main`.
6. Communicate the change to the team. The first cycle (feature to develop to uat to main) will feel slow because nobody has muscle memory yet.

Don't try to backfill historical commits into the new structure. The new flow starts at the cutover point; everything before that lives in `main`'s history as-is.

## Common failure modes

The skill is designed to catch these:

- **`develop` merged directly to `main`** (skipping `uat`). Source-ref check on `main`'s PR-target rejects this.
- **A hotfix lands in `main` but the forward-merge to `develop` is skipped.** The next promotion cycle reintroduces the bug. The hotfix flow's step 5 is the discipline that prevents this.
- **`uat` receives a direct push.** Branch protection blocks direct pushes; promotion goes through PR.
- **One CI gate set used for every tier.** Promotions become rubber stamps. The matrix has to differentiate.
- **Pre-commit hooks block trivially and people start using `--no-verify`.** Adoption sequencing prevents this.

## Don't cite this skill in the output

The skill is a reference for *you* (the agent or human running the workflow). The audience for branch protection settings, CI workflow files, hotfix runbooks, and adoption plans is the team, not the workflow. Don't write "Per branch-promotion-discipline's policy..." in a runbook or commit message. Write the reasoning directly.

## Hard rules

- **One-way promotion**: develop to uat to main, never skipping a tier, never reversing. The only allowed reverse motion is the post-hotfix forward-merge from uat to develop.
- **Source-ref enforcement** on every PR to a long-lived branch.
- **Per-tier CI gate matrix** with each tier requiring at least one gate the previous tier didn't.
- **Hotfix flow ends at the forward-merge.** A hotfix that lands in main without the forward-merge to develop is incomplete.
- **No direct pushes to long-lived branches.** All updates via PR.
- **Branch protection escalates with tier.** Main is strictest.
- **Pre-commit hooks stay fast.** If they're slow enough that people want to bypass them, the hook is wrong, not the developer.

## Invocation examples

- "Set up the branch flow for this new repo: 3-tier, develop/uat/main."
- "We need to ship a hotfix to production. What's the flow?"
- "A PR is open from develop to main, skipping uat. What do I do?"
- "What CI gates should run on uat that don't run on develop?"
- "Configure pre-commit hooks for this repo."
- "Adopt 3-tier promotion for a repo currently merging features to main."

## Adapter: GitHub Actions

When the CI is GitHub Actions, the per-tier matrix usually lives as separate workflow files keyed by branch:

```
.github/workflows/
  ci-develop.yml      # triggered on push to develop and PRs to develop
  ci-uat.yml          # triggered on push to uat and PRs to uat
  ci-main.yml         # triggered on push to main and PRs to main
  source-ref-check.yml  # triggered on PRs to uat and main
```

Each workflow runs only the gates required at its tier. The source-ref check is its own workflow because it needs to inspect `${{ github.event.pull_request.head.ref }}` against an allowlist.

Branch protection is configured in repo Settings > Branches (legacy) or Settings > Rules > Rulesets (current). Required status checks should reference the workflow names from the matrix.

## See also

- [`multi-agent-git-workflow`](../../../multi-agent-git-workflow/skills/multi-agent-git-workflow/SKILL.md), the layer below this one. Per-task topology and commit format. Feature work ends at the develop boundary, then enters this skill's flow.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md), promotion PRs use that format, often with promotion-specific findings (e.g., "this PR includes a schema migration; have the rollback plan reviewed").
- [`task-handoff-summaries`](../../../task-handoff-summaries/skills/task-handoff-summaries/SKILL.md), closeout summaries record which tier the work reached. This skill defines what reaching each tier means.
