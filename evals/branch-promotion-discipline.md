---
title: branch-promotion-discipline
parent: Evaluations
nav_order: 6
---

# branch-promotion-discipline evaluations

The hotfix-with-forward-merge eval (+62pp) is the load-bearing one. Untrained models routinely propose hotfixing from `main` and skipping the post-hotfix forward-merge to `develop`, which produces the most common silent-bug-reintroduction failure mode of 3-tier flows.

The other three evals are non-discriminating in iteration-1: the prompts contain enough policy framing (e.g., "the repo's flow is develop / uat / main with one-way promotion") that even baseline models match the assertions. Iteration-2 will sharpen those prompts.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 84% | **+15pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `set-up-3-tier-flow-from-single-main` | Designing the flow for a new repo: long-lived branches, promotion direction, CI gate matrix, branch protection, adoption sequence. | 100% | 100% | 0pp |
| `hotfix-flow-with-forward-merge` | Production hotfix: branch from `uat` not `main`, PR sequence, regression-only exception, post-hotfix forward-merge to `develop`. | 100% | 38% | +62pp |
| `reject-pr-skipping-uat` | A PR is open from develop direct to main with "urgent" framing. Reject and propose the correct path. | 100% | 100% | 0pp |
| `design-ci-gate-matrix` | Per-tier CI gates with rationale. Each tier strictly stricter than the previous. | 100% | 100% | 0pp |

The hotfix eval is the discriminator. The forward-merge step is a non-obvious "off the happy path" detail that untrained models miss systematically. Without the forward-merge, `develop` reintroduces the bug at the next normal promotion cycle. The skill encodes this as a hard rule because the failure mode is silent and recurring.

## A note on the non-discriminating evals

Three of four prompts contain enough policy framing in the prompt itself that the baseline matches the assertions. For example, the `reject-pr-skipping-uat` prompt opens with "the repo's flow is develop / uat / main with one-way promotion", which is itself most of the answer. A baseline model parrots that framing back without needing the skill.

This is a design issue with the eval prompts, not the skill. Iteration-2 should:

- Drop the policy-statement framing from those prompts. Phrase them as "we have these branches, what should we do?" without explaining what one-way promotion means.
- Add a more diagnostic eval, e.g., a scenario where the team has been running 3-tier for a year but a hotfix-without-forward-merge is causing repeated reintroductions and the question is "what's going wrong?". The skill's forward-merge rule should be the load-bearing answer.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/branch-promotion-discipline-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/branch-promotion-discipline/skills/branch-promotion-discipline/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/branch-promotion-discipline-workspace/iteration-1)**: raw `output.md`, `grading.json`, `timing.json` per run.

## Back to skill

[branch-promotion-discipline skill page](../skills/branch-promotion-discipline)
