---
title: task-handoff-summaries
parent: Evaluations
nav_order: 5
---

# task-handoff-summaries evaluations

The smallest headline in the collection (+12pp). Three of four evals had a strong baseline: the formats are intuitive enough that an unprompted model gets close. The implementation-summary eval (+27pp) is the discriminator, mostly on the "every field is a commitment" rule.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 88% | **+12pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `single-agent-implementation-summary` | Implementation summary before commit: scope, decisions, test results, behavior-impact, what's NOT in scope. | 100% | 73% | +27pp |
| `multi-agent-worker-handoff` | Worker handoff to orchestrator: branch + commit SHA, gate status, ready-for-acceptance signal, no self-merge. | 100% | 90% | +10pp |
| `closeout-summary-with-evidence` | Closeout: completed criteria, evidence per criterion, follow-ups, no glossing over incomplete items. | 100% | 91% | +9pp |
| `lightweight-no-task-closeout` | When there's no formal task, the format degrades gracefully to change + why + verification, without inventing a fake task ID. | 100% | 100% | 0pp |

The implementation-summary eval is the load-bearing one. The hard rule the skill encodes is "every field is a commitment". `Quality Gates: passed` without numbers is a smell. Untrained models cheerfully write `Tests: passing` and leave it at that; with the skill, they cite the actual count.

The lightweight-no-task eval is non-discriminating in iteration-1. Sharpen for iteration-2.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/task-handoff-summaries-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/task-handoff-summaries/skills/task-handoff-summaries/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/task-handoff-summaries-workspace/iteration-1)**: raw `output.md`, `grading.json`, `timing.json` per run.

## Back to skill

[task-handoff-summaries skill page](../skills/task-handoff-summaries)
