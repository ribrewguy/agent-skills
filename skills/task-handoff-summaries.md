---
title: task-handoff-summaries
parent: Skills
nav_order: 3
---

# task-handoff-summaries

Three rigorous structured report formats for the moments when work transitions between phases — implementation summary (before commit), worker handoff summary (multi-agent worker → orchestrator), closeout summary (after completion). Each format has a fixed field set and hard rules against using the summary to mask incomplete work.

## What makes this skill distinct

- **Three formats, one skill — the right format fires per trigger.** Implementation summary is the default for "I finished writing code, what's next?" Worker handoff is for the multi-agent worker handing off to an orchestrator. Closeout is for the final externally-visible record after merge/deploy. The skill picks based on context.
- **Every field is a commitment.** "Quality Gates: passed" without numbers is a smell; "Bead Scope: rp-c74" without confirming the bead exists is a smell. The reader should be able to verify every claim from the summary alone, or know exactly what's still unverified.
- **`No task was worked on.` is a valid value, not a missing field.** Lightweight processes (small fixes, drive-by changes) keep the same field structure — they just emit explicit "no task" / "not applicable" / "lightweight process" values. Format-as-accountability: the reader can see *that* a question was answered even when the answer is "nothing here."
- **Hard rules against using the summary to mask incomplete work.** If implementation is complete but closure is blocked (waiting on review, deploy gate, third party), the skill summarizes the implementation separately from the blocked governance step. Don't conflate them; don't elide them.
- **Bead-aware and multi-agent-aware.** Worker handoff vs. orchestrator closeout vs. single-agent closeout each have appropriate field sets — the worker doesn't write a user-facing implementation summary by default; the orchestrator incorporates accepted worker output into the user-facing closeout.
- **Don't cite the skill in the output.** The summary is a report for the reader (human reviewer, orchestrator agent, future-you reading the closeout record). The skill is the reference for the *author*; the audience for the output is whoever consumes the report.

## What it covers

### Format 1: Implementation summary (before commit)

Eight fields: Process Used, Execution Context, Task Scope, Implementation Outcome (with active branch + integration target), Behavioral Impact, Risks/Gaps, File Reference Summary, Governance Status. Used by single-agent or multi-agent orchestrator work; produced *before* commit so the reviewer can read it before the diff.

### Format 2: Worker handoff summary (multi-agent → orchestrator)

Six fields: Task, Branch (with Published yes/no + Commit handed off), Implementation Outcome (with intended integration target), Quality Gates, Risks/Gaps, Review Notes. More concise than Format 1 because the orchestrator only needs what it takes to accept-or-reject the branch.

### Format 3: Closeout summary (after completion)

Eight fields including Evidence (with concrete gate-by-gate results, UAT status, commit SHA, push status, branch status, promotion). The final externally-visible record of what shipped. Doesn't replace governance steps; summarizes them.

## Quick install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install task-handoff-summaries@ribrewguy-skills
```

For other tools, see [Install](../install).

## Composes with

- **[structured-code-review](structured-code-review)** — the implementation summary is *input* to the reviewer; the reviewer's findings come back in the structured-code-review format. Format consistency on both sides of the handoff makes the work-→-review-→-next-step flow legible at a glance.
- **(planned)** `cross-agent-adversarial-review` — when a second agent (different vendor) reviews the first agent's work, the implementation summary is the input package. With a critical caveat: the implementing agent's self-assessment ("LGTM", "all tests pass") should be **redacted** before the package goes to the reviewing agent, so the reviewer doesn't anchor on the implementer's confidence.
- **(planned)** `multi-agent-git-workflow` — provides the branch hierarchy and orchestrator/worker role vocabulary referenced in the format fields.

## Tooling and dependencies

- **Required:** none — the formats are tool-neutral
- **Strongly recommended:** a task tracker (Beads, GitHub Issues, Linear, Jira, Shortcut). Without one, every summary's `Task Scope:` is `No task was worked on.` and the skill falls back to lightweight-process closeouts.
- **Strongly recommended:** a version-controlled workflow with explicit branches and integration targets. The Branch / Integration Target / Governance Status fields assume a branch model where work flows through stages.
- **Adapter:** [Beads](https://github.com/gastownhall/beads) — the skill body has a section showing the literal mapping (`Bead Scope: rp-c74`, `bd show <id>` for the design data the summary needs). Other trackers substitute their own ID format.

## Source of truth

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/task-handoff-summaries/skills/task-handoff-summaries/SKILL.md)** — the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/task-handoff-summaries/skills/task-handoff-summaries/evals/evals.json)** — the four test cases used to verify the skill's behavior.

## Eval results

Iteration-1 benchmark: **100% pass rate with-skill vs. 76% baseline** (+24pp delta) across four test cases. Smaller delta than `structured-code-review` (+69pp) because baselines naturally produce reasonable summaries — they just label fields differently. The skill's value is in *standardizing* the field set so summaries scan consistently across many reports.

| Eval | What it probes |
|---|---|
| `single-agent-implementation-summary` | Does the skill emit all 8 implementation-summary fields in order, with Governance Status indicating pre-commit / awaiting review? |
| `multi-agent-worker-handoff` | Does the skill use Format 2 (concise, 6-field) for worker work and avoid claiming acceptance/merge? |
| `closeout-summary-with-evidence` | Does Evidence section have concrete numbers (gate results, commit SHA, branch status, promotion stage) — not vague claims? |
| `lightweight-no-task-closeout` | Does the skill emit explicit "No task was worked on." rather than eliding the field, on a no-bead trivial fix? |

Eval transcripts and benchmark JSON live alongside the skill source.

## Invocation examples

- "Write the implementation summary for the changes I just made."
- "I'm handing this branch to the orchestrator — produce a worker handoff summary."
- "Close out task rp-c74. Include all the gate results and the commit SHA."
- "Summarize what was done in this PR."
- "What's the closeout summary for this work?"
