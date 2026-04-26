---
title: Evaluations
nav_order: 4
has_children: true
permalink: /evals/
---

# Evaluations

Every skill in this collection is measured before it ships. This section publishes the receipts.

## What the numbers mean

For each skill, four test prompts are written that probe the skill's distinct opinions. Each prompt is run twice: once with the skill loaded into the AI tool, once without (the **baseline**). Both outputs go to a grader that checks each output against per-assertion pass/fail criteria. The "pass rate" is the fraction of assertions met across all evals.

The point isn't to prove the skill makes the AI smarter. It's to prove the skill is *load-bearing*: that without it, the AI would have shipped output that fails one or more of the rules the skill encodes.

A small delta on a strong baseline still matters if it's catching a specific failure mode (an idempotency trap, a missed PATCH conversion, a worker silently merging its own branch). A large delta on a weak baseline tells you the skill is doing real work.

## Headline results

| Skill | With Skill | Baseline | Δ | Notes |
|---|---|---|---|---|
| [rest-api-design](rest-api-design) | 100% | 36% | **+64pp** | Idempotency trap eval is +100pp by itself: untrained models cheerfully ship money-moving POSTs without an Idempotency-Key. |
| [multi-agent-git-workflow](multi-agent-git-workflow) | 100% | 38% | **+62pp** | Worker-close-out eval +75pp: untrained models routinely tell the worker to merge their own branch into integration. |
| [structured-code-review](structured-code-review) | 100% | 45% | **+55pp** | "No findings, still formal" eval is the strongest delta (+78pp). Untrained models drop to "LGTM" the moment there's nothing wrong. |
| [cross-agent-review](cross-agent-review) | 100% | 84% | **+16pp** | The redaction-discipline eval (+50pp) is the load-bearing one; baseline does fine on the other three. |
| [task-handoff-summaries](task-handoff-summaries) | 100% | 88% | **+12pp** | Three of four evals had a strong baseline because the format is intuitive. The implementation-summary eval (+27pp) is the discriminator. |
| [branch-promotion-discipline](branch-promotion-discipline) | 100% | 84% | **+15pp** | The hotfix-with-forward-merge eval (+62pp) is the discriminator. Three other evals non-discriminating in iteration-1 because the prompts give away the framing; flagged for sharpening. |

Numbers are pass rate across four evals, one run per configuration.

## Methodology and caveats

- **One run per (eval, configuration)** in this iteration. Aspirational target is 3 runs each for stddev. Iteration-2 will tighten this.
- **Grading is reasoned, not regex'd.** A single grader reads each output and decides per-assertion pass/fail with a short evidence citation. Cited evidence is in `grading.json` per run for anyone who wants to recheck.
- **Baseline arms ran in the same agent context as with-skill arms** for this iteration (sub-subagent dispatch wasn't available in the run environment). The orchestrator was instructed to avoid consulting the SKILL.md when producing baseline output. This isn't as clean as separate fresh agent contexts. Iteration-2 will run baselines as fully isolated agents.
- **Time and token budgets are estimates** for the same reason: the orchestrator generated arms inline rather than dispatching them as separate timed tasks. The pass-rate columns are the load-bearing data; treat the time/token columns as advisory.

## How to dig deeper

Each per-skill page below has:

- The headline pass rate
- A per-eval breakdown showing which assertions the skill helped on
- A link to the **interactive review** (a side-by-side viewer with the with-skill output, the baseline output, and per-assertion grading evidence inline)
- A link to the **eval definitions** (the prompts and assertions, in `evals.json`)
- A link to the raw model outputs and `grading.json` files in the workspace

## Skills evaluated

- [rest-api-design evaluations](rest-api-design)
- [structured-code-review evaluations](structured-code-review)
- [task-handoff-summaries evaluations](task-handoff-summaries)
- [cross-agent-review evaluations](cross-agent-review)
- [multi-agent-git-workflow evaluations](multi-agent-git-workflow)
- [branch-promotion-discipline evaluations](branch-promotion-discipline)

## Why republish so much detail

The intent is transparency. Anyone can read the prompts, run them in their own tool, regrade the outputs, and decide whether the skill earns its keep in their stack. Headline pass rates are easy to game; per-assertion evidence and raw outputs are what let an external reader verify the claim.
