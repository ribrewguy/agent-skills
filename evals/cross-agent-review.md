---
title: cross-agent-review
parent: Evaluations
nav_order: 4
---

# cross-agent-review evaluations

Smaller headline (+16pp) because three of four evals had a strong baseline. The redaction-discipline eval (+50pp) is the load-bearing result: without the skill, handoff packages routinely include "all tests pass" or the implementer's reasoning trace, anchoring the reviewer toward rubber-stamping.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 84% | **+16pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `build-handoff-package-with-redaction` | Package includes diff + design + acceptance criteria. REDACTS self-assessment, framing, reasoning trace, gate-passed claims. | 100% | 50% | +50pp |
| `perform-cold-review-no-anchoring` | Reviewer treats the work cold; catches load-bearing issues (timing attack, signing-key misuse, missing malformed/expired handling). | 100% | 88% | +12pp |
| `write-disagreement-summary` | Even-handed disagreement summary in the prescribed 6-section format with named human escalation. | 100% | 100% | 0pp |
| `skip-cross-agent-for-trivial-work` | Correctly skips for typos, applies for high-value triggers. | 100% | 100% | 0pp |

The two non-discriminating evals are flagged for redesign in iteration-2. The current prompts contain enough policy framing that the baseline gets there too.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/cross-agent-review-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/cross-agent-review/skills/cross-agent-review/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/cross-agent-review-workspace/iteration-1)**: raw `output.md`, `grading.json`, `timing.json` per run.

## Back to skill

[cross-agent-review skill page](../skills/cross-agent-review)
