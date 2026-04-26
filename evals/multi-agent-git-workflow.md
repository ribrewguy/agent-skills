---
title: multi-agent-git-workflow
parent: Evaluations
nav_order: 3
---

# multi-agent-git-workflow evaluations

The strongest delta on a workflow skill (+62pp). The worker-close-out eval is the canary: untrained models routinely tell the worker to merge their own branch into integration, which is the single failure mode multi-agent topology exists to prevent.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 38% | **+62pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `set-up-multi-agent-topology` | Names parent + child beads, worker feature branches, integration branch, role MUST/MUST-NOT lists, worktree-per-agent rule. | 100% | 33% | +67pp |
| `worker-finished-close-out` | Tells the worker to hand off (NOT self-merge). Bead stays `in_progress` until orchestrator accepts. | 100% | 25% | +75pp |
| `write-commit-message-with-task-id-and-coauthor` | Conventional Commits subject (`feat(scope): ...`), task ID reference, multi-paragraph body explaining why, co-author line. | 100% | 50% | +50pp |
| `orchestrator-rejection-with-explicit-notes` | Rejects rather than silently fixes. Tags failures by category. Tells the worker to fix and re-hand-off. | 100% | 44% | +56pp |

The worker-close-out eval is the load-bearing one. Without the skill, the model's default suggestion is "merge your branch to develop" or similar, blowing past the orchestrator role entirely. With the skill, the model produces the handoff package and explicitly tells the worker not to merge.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/multi-agent-git-workflow-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/multi-agent-git-workflow/skills/multi-agent-git-workflow/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/multi-agent-git-workflow-workspace/iteration-1)**: raw `output.md`, `grading.json`, `timing.json` per run.

## Back to skill

[multi-agent-git-workflow skill page](../skills/multi-agent-git-workflow)
