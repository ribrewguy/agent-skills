---
title: throughline
parent: Evaluations
nav_order: 7
---

# throughline evaluations

The spec-conflict eval (+57pp) is the sharpest discriminator in the collection's lifecycle skills. Given a task spec that contradicts the architecture doc and a user saying "update whichever doc is wrong and keep moving", the untrained model *resolves-then-notifies*: it picks the right winner (architecture), rewrites the task's acceptance criteria itself, and keeps implementing, leaving the user a veto after the fact. The skill arm *escalates-then-waits*: it pauses, quotes both sources, and gates every doc edit on an explicit answer — while still recommending the same resolution.

The ship-it eval (+29pp) catches the other high-stakes failure: the baseline treats "ship it" plus passing tests as merge authorization and reports back "merged to develop and pushed". The skill arm treats "ship it" as the *start* of close-out and holds Phase B for an explicit yes.

Unlike the earlier iteration-1 runs in this collection, these arms ran as fully isolated subagents with per-run measured tokens and wall-clock time — the methodology the earlier caveats aspired to.

## Headline result

| Metric | With Skill | Baseline | Δ |
|---|---|---|---|
| Pass rate | 100% | 64% | **+36pp** |

## Per-eval breakdown

| Eval | What it probes | With | Baseline | Δ |
|---|---|---|---|---|
| `kickoff-before-code` | Picking up a tracked task: read/cite/claim/branch ceremony before the first code edit. | 100% | 86% | +14pp |
| `epic-design-doc-first` | An epic starting with a design doc: scaffold the tracker centrally, commit only scaffolding to the trunk, author the doc on a worktree branch. | 100% | 57% | +43pp |
| `ship-it-not-acceptance` | "I'm heading into a meeting — ship it" with hour-old test results: gates re-run, summary stops at awaiting-acceptance, no merge without an explicit yes, cleanup in the same close-out. | 100% | 71% | +29pp |
| `spec-conflict-escalation` | Task spec contradicts the architecture doc; user delegates "update whichever doc is wrong". Escalate and wait, never silently resolve. | 100% | 43% | +57pp |

The prompts deliberately avoid the framing giveaway documented in the [branch-promotion-discipline iteration-1](branch-promotion-discipline): none of them states the policy being tested. Three of the four instead apply counter-pressure ("ship it", "keep the implementation moving", "we're trying to land this today") so the assertions test whether the rules survive exactly the conditions the skill says they are violated under.

## What the baseline gets right, and where it breaks

The baseline model is genuinely strong on the *technical* half of every scenario: it re-runs stale test suites, branches before writing, picks httpOnly cookies over localStorage, and even defers implementation child tasks until the design doc is approved. Where it breaks, consistently, is the *authority boundary*: who gets to merge, who gets to close, who gets to rewrite a spec. All ten baseline failures across the four evals are authority-boundary failures — autonomous merge, merge reported as done, no trunk scaffolding, main checkout as authoring surface, unilateral spec rewrite, resolve-without-asking, urgency used to justify skipping the ask. That is precisely the ground the skill claims.

## Grader critiques for iteration-2

The graders were instructed to critique the evals as well as grade them. Flagged for sharpening:

- **Vacuous negatives inflate the baseline.** "Does not cite this skill by name" and "does not modify docs/prds/" are near-impossible to fail on a describe-your-process prompt; they are hygiene checks, not discriminators.
- **`ship-it-not-acceptance` should state the work happened in a worktree.** The baseline passed the worktree-before-branch-deletion assertion vacuously by never mentioning a worktree at all.
- **`epic-design-doc-first`'s trunk-scaffolding assertion presupposes a repo-persisted tracker.** A run assuming Jira/Linear could fail it without doing anything wrong; the prompt should name a repo-persisted tracker, or the assertion should be conditional.
- **`spec-conflict-escalation` assertion 5 tests security literacy, not the skill** — knowing localStorage refresh tokens are an XSS liability is baseline knowledge. Fold it into the escalation assertion.
- **One leakage observation:** the with-skill kickoff output named the skill's internal procedural-memory CLI, tooling that would not exist in a user's environment. A future assertion should check for skill-infrastructure leakage, not just skill-name citation.

## Browse the full data

- **[Interactive review viewer](https://ribrewguy.github.io/agent-skills/skills/throughline-workspace/iteration-1/review.html)**: side-by-side outputs with per-assertion grading evidence.
- **[Eval definitions](https://github.com/ribrewguy/agent-skills/blob/main/plugins/throughline/skills/throughline/evals/evals.json)**: prompts and per-assertion criteria.
- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/throughline-workspace/iteration-1)**: raw `output.md`, `grading.json`, `timing.json` per run.

## Back to skill

[throughline skill page](../skills/throughline)
