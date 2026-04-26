---
title: rest-api-design
parent: Evaluations
nav_order: 1
---

# rest-api-design evaluations

The strongest delta in the collection (+64pp). The eval that drives the headline is `payments-post-idempotency-trap` at +100pp: untrained models cheerfully ship a money-moving POST without an Idempotency-Key, and don't catch the omission when prompted to review.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 36% | **+64pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `design-task-api-from-scratch` | Full task API: state transitions via PATCH (not POST verbs), error envelope, idempotency, content-type, typed contracts. | 100% | 25% | +75pp |
| `pr-audit-multiple-violations` | Audits a PR with sub-resource verbs, opaque error codes, deep nesting. Catches GET-as-destructive, snake_case in JSON, bespoke envelope. | 100% | 58% | +42pp |
| `payments-post-idempotency-trap` | Money-moving POST is missing an Idempotency-Key. Does the review catch it? | 100% | 0% | +100pp |
| `bounded-notifications-not-a-list` | Endpoint returns top-N notifications, no pagination needed. Does the design correctly recognize a bounded collection isn't a paginated list? | 100% | 60% | +40pp |

The idempotency trap is the canary. If a skill claims to teach REST design and a model armed with that skill misses an obvious idempotency hole on a money-moving POST, the skill is broken.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/rest-api-design-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/rest-api-design/skills/rest-api-design/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/rest-api-design-workspace/iteration-1)**: raw `output.md`, `grading.json`, `timing.json` per run.

## Back to skill

[rest-api-design skill page](../skills/rest-api-design)
