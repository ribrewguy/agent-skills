---
title: structured-code-review
parent: Evaluations
nav_order: 2
---

# structured-code-review evaluations

The "no findings, still formal" eval is the strongest single delta in the collection (+78pp). Untrained models drop to "LGTM" the moment there's nothing to flag. With the skill, the model produces a formal preamble, an explicit zero-findings count, and the gates-passed confirmation.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 45% | **+55pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `mixed-severity-pr-review` | Severity tags, file:line citations, source-of-truth references, structured finding format. The PR has a hardcoded API key, SQL injection, and routing-as-verb violations. | 100% | 54% | +46pp |
| `no-findings-clean-change` | A trivial-clean variable rename. Does the review still produce the formal structure (preamble, zero findings, gates confirmation), or drop to "looks good"? | 100% | 22% | +78pp |
| `no-task-no-design-fallback` | No task spec, no design doc. Does the review fall back to public-API and architecture rationale instead of inventing a phantom design? | 100% | 44% | +56pp |
| `rest-domain-composition` | Composes with `rest-api-design`. Catches missing Idempotency-Key on a POST that creates a task, plus a status-by-POST-body violation. | 100% | 60% | +40pp |

`no-findings-clean-change` is the canary. A code-review system that emits "looks good" when there's nothing wrong is indistinguishable from a system that just wasn't paying attention. The format-discipline this skill enforces removes that ambiguity.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/structured-code-review-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/structured-code-review/skills/structured-code-review/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/structured-code-review-workspace/iteration-1)**: raw `output.md`, `grading.json`, `timing.json` per run.

## Back to skill

[structured-code-review skill page](../skills/structured-code-review)
