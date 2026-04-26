---
title: branch-promotion-discipline
parent: Skills
nav_order: 6
---

# branch-promotion-discipline

The discipline for the long-lived environment branches above feature work: `develop`, `uat`, and `main`. Code lands in `develop` from feature branches (handled by `multi-agent-git-workflow`), gets promoted to `uat` for stakeholder acceptance, then to `main` for production. Promotion is one-way and tier-respecting; the per-tier CI gate matrix is what makes each tier actually mean something different.

This is the layer above multi-agent-git-workflow. That skill ends when feature work lands in `develop`. This one starts there.

## What makes this skill distinct

- **One-way promotion only.** develop to uat to main, never skipping a tier, never reversing. The single allowed reverse motion is the post-hotfix forward-merge from uat back to develop.
- **Source-ref enforcement on every PR.** A PR targeting `uat` MUST have source ref `develop` or `hotfix/*`. A PR targeting `main` MUST have source ref `uat`. The check is its own CI workflow that fails the PR before any other gate runs. Discipline plus tooling.
- **Per-tier CI gate matrix.** Each tier requires at least one gate the previous tier doesn't. A typical shape: develop runs lint/typecheck/unit, uat adds integration/e2e/UAT-environment smoke, main adds production-environment smoke + change-management metadata. Adding a gate to an upper tier doesn't automatically add it to a lower tier; the matrix is explicit.
- **Hotfix flow ends at the forward-merge.** A hotfix that lands in main without forward-merging uat back to develop is incomplete; the next normal promotion cycle reintroduces the bug. The forward-merge is the load-bearing step that prevents this drift.
- **Branch protection escalates with tier.** Develop tolerates a single approver and a faster pace. Main requires two approvers, dismissal of stale approvals on push, linear history, admin-only push. The cost of a mistake increases per tier; the protection ruleset reflects that.
- **Pre-commit hooks stay fast.** Format check, cached lint on changed files, scoped typecheck, optional secret-shape guard. Anything taking more than a couple of seconds belongs in CI, not in a pre-commit hook. Slow pre-commit hooks train people to use `--no-verify`, which defeats the gate.
- **Don't cite the skill in the output.** Branch protection settings, CI workflow files, hotfix runbooks, adoption plans go to the team. The reasoning lives in the artifact directly, not behind a "per-policy" reference.

## What it covers

- **The branch hierarchy**: `develop` (integration), `uat` (long-lived stakeholder acceptance environment), `main` (production). Naming substitutions (`staging` for `uat`) only with strong reason.
- **One-way promotion direction** and the explicit list of forbidden motions (develop to main skipping uat, main to uat as a normal flow, feature/* directly to uat or main).
- **Source-ref enforcement** as a CI workflow that runs at the target branch's gate set.
- **CI gate matrix** as a default starting point with rationale for each gate's tier placement, plus accommodations for repos that don't yet have e2e tests, fast e2e teams, etc.
- **Hotfix flow** including the rare regression-only exception (branch from main when the bug exists only on main).
- **Branch protection settings** as a per-tier table covering required PR / status checks / approvers / stale-approval dismissal / linear history / admin-only push / no-force-push / no-deletions.
- **Pre-commit hooks**: what to run, what NOT to run, simple-git-hooks vs husky tradeoff, adoption-as-non-blocking-first sequencing.
- **Adoption from a single-main repo**: the cutover sequence and the cultural-change reality.
- **Common failure modes** the skill is designed to catch: develop-to-main skipping, hotfix without forward-merge, direct uat pushes, monolithic gate matrix, pre-commit-hook bypass adoption.

## Quick install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install branch-promotion-discipline@ribrewguy-skills
```

Other tools: see [Install](../install).

## Composes with

- **[multi-agent-git-workflow](multi-agent-git-workflow)**: the layer below this one. Per-task git topology and commit format. Feature work ends at the develop boundary, then enters this skill's flow.
- **[structured-code-review](structured-code-review)**: promotion PRs (develop to uat, uat to main) are reviewed in that format, often with promotion-specific risk findings (e.g., "this PR includes a schema migration; have the rollback plan reviewed").
- **[task-handoff-summaries](task-handoff-summaries)**: closeout summaries record which tier the work reached. This skill defines what "promoted to uat" or "released to main" actually means in artifact terms.

## Tooling and dependencies

- **Required**: Git with branch protection on the host (GitHub branch protection / rulesets, GitLab protected branches, Bitbucket merge checks).
- **Required**: A CI system (GitHub Actions, GitLab CI, CircleCI, Buildkite, etc.) that supports per-branch workflow files or per-branch gate configuration.
- **Strongly recommended**: A pre-commit hook runner. [simple-git-hooks](https://github.com/toplenboren/simple-git-hooks) is preferred (zero-runtime-deps); [husky](https://github.com/typicode/husky) also works.
- **Strongly recommended**: A code-hosting platform with PR review so promotions are PR-driven, not direct merges.

## Source of truth

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/branch-promotion-discipline/skills/branch-promotion-discipline/SKILL.md)**: the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/branch-promotion-discipline/skills/branch-promotion-discipline/evals/evals.json)**: the four test cases used to verify the skill's behavior.

## Eval results

Full per-eval breakdown, interactive review viewer, and links to raw model outputs: **[branch-promotion-discipline evaluations](../evals/branch-promotion-discipline)**.

## Invocation examples

- "Set up the branch flow for this new repo: 3-tier, develop/uat/main."
- "We need to ship a hotfix to production. What's the flow?"
- "A PR is open from develop to main, skipping uat. What do I do?"
- "What CI gates should run on uat that don't run on develop?"
- "Configure pre-commit hooks for this repo."
- "Adopt 3-tier promotion for a repo currently merging features to main."
