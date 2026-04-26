---
name: task-handoff-summaries
description: Use when finishing a task and reporting status — implementation complete, multi-agent worker handing off to orchestrator, task closeout feeding the PR description. Produces one of three structured formats: implementation summary (before commit), worker handoff summary (worker → orchestrator), closeout summary (after completion). Each has a fixed field set, hard rules against claiming completion that didn't happen, task-tracker-aware vocabulary. Symptoms — vague "I made some changes" reports, completion claims that hide failed gates, summaries implying commit/push happened when they didn't, no governance status.
---

# Task Handoff Summaries

## Overview

Three structured report formats for the moments when work transitions between phases:

- **Implementation summary** — produced before commit, after implementation is complete. The author hands this to the reviewer (human or another agent) so the reviewer can understand what changed before reading the diff.
- **Worker handoff summary** — concise variant for multi-agent worker work, handed to an orchestrator. The orchestrator reads it before accepting the worker's branch into the integration target.
- **Closeout summary** — produced after completion, when the work has reached its integration target and any required cleanup is done. This is the final externally-visible record of what shipped.

The formats share a discipline: every field is a commitment. "Quality Gates: passed" without numbers is a smell; "Bead Scope: proj-42" without confirming the bead actually exists is a smell. The reader should be able to verify every claim from the summary alone, or know exactly what's still unverified.

## Tooling and dependencies

### Required

Nothing. The formats are tool-neutral.

### Strongly recommended

- **A task / issue tracker** — every format has a "Task Scope" / "Bead Scope" field. Without a tracker the field falls back to `No task was worked on.` Examples: [Beads](https://github.com/gastownhall/beads), GitHub Issues, Linear, Jira, Shortcut.
- **A version-controlled workflow** with explicit branches and integration targets. The "Integration Target" / "Branch" / "Governance Status" fields assume a branch model where work flows through stages (e.g., `feature/*` → `develop` → `uat` → `main`).
- **`structured-code-review`** — when the summary's reader is *another agent doing a review*, the reviewer's output uses that format. Format consistency between summary input and review output makes hand-off → review → next-step legible at a glance.

### Optional adapters

- [Beads](https://github.com/gastownhall/beads) for tracking — see the **Adapter: Beads** section for the literal mapping.

### Composes with

- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md) — the implementation summary is *input* to the reviewer; the reviewer's findings are output in the structured-code-review format.
- *(planned)* `multi-agent-git-workflow` — provides the branch hierarchy and orchestrator/worker role vocabulary referenced in `Process Used`, `Branch`, `Integration Target`, `Governance Status` fields.
- *(planned)* `cross-agent-adversarial-review` — when a second agent (different vendor) reviews the first agent's work, the handoff summary is the input package. With a critical caveat: the implementing agent's self-assessment ("LGTM", "all tests pass") should be **redacted** before the package goes to the reviewing agent, so the reviewer doesn't anchor on the implementer's confidence.

## When to use

Three triggers, one per format:

| Trigger | Format |
|---|---|
| Implementation complete, ready to hand off to reviewer (single-agent or orchestrator) | Implementation summary |
| Multi-agent worker finished their branch and hands it to the orchestrator | Worker handoff summary |
| Work has reached its integration target, cleanup done, ready for the final externally-visible record | Closeout summary |

If you're unsure which fires: implementation summary is the right default for "I just finished writing code, what's next?" Worker handoff is the right default when you're the worker in a multi-agent topology. Closeout is for after merge/deploy/whatever the project's "done" state is.

## Format 1: Implementation summary

Produced before commit, after implementation is complete. Single-agent work or multi-agent orchestrator work both use this format. (Workers use Format 2 instead.)

```
## Implementation Summary

Process Used: <Full process | Lightweight process>
Execution Context: <Single-agent | Multi-agent orchestrator>

Task Scope:
  <task ID + brief restatement of scope, OR "No task was worked on.">

Implementation Outcome:
  <what was implemented or changed, in concrete terms>
  Active branch: <branch name, if used>
  Integration target: <branch name, when one exists>

Behavioral Impact:
  <user-visible or system-visible effect of the change>
  <any migrations, config changes, or operational effects>

Risks / Gaps:
  <known limitations, follow-up work, edge cases not covered, unresolved concerns>
  <or "No known implementation gaps at handoff.">

File Reference Summary:
  <primary files changed; not a full changelog — just the files most relevant to review>

Governance Status:
  <which completion steps are still pending>
  <e.g., "awaiting code review", "awaiting orchestrator acceptance",
   "awaiting merge to develop", "awaiting approved PR from develop to uat">
```

The summary is written *before* commit and push. Don't claim those steps happened until they have.

## Format 2: Worker handoff summary

Produced by a multi-agent worker handing their branch to an orchestrator for integration review. More concise than Format 1 because the orchestrator only needs what it takes to accept-or-reject the branch.

```
## Worker Handoff Summary

Task: <worker bead/task ID>

Branch: <worker branch name>
  Published: <yes | no>
  Commit handed off: <SHA>

Implementation Outcome:
  <what changed, concretely>
  Intended integration target: <branch name>

Quality Gates:
  <gates run, pass/fail status — concrete numbers/names, not "all passed">

Risks / Gaps:
  <known issues, follow-ups, unresolved concerns for integration>

Review Notes:
  <anything the orchestrator should pay attention to during integration —
   non-obvious decisions, areas where the worker is uncertain, hot spots>
```

A user-facing implementation summary is **not required** for worker work by default. The orchestrator-facing handoff summary is the worker's required artifact. If the user explicitly asks to review the worker slice directly, produce Format 1 in addition.

## Format 3: Closeout summary

Produced after completion — when the work has reached its integration target and any required cleanup is done. This is the final externally-visible record. It does **not** replace governance steps, evidence blocks, quality gates, UAT gates, commit/push requirements, or task state transitions; it summarizes them.

```
## Closeout Summary

Process Used: <Full process | Lightweight process>
Execution Context: <Single-agent | Multi-agent orchestrator>

Task Scope:
  <task ID + brief restatement of scope, OR "No task was worked on.">

Closeout Outcome:
  <what was delivered and closed out, concretely>
  Active branch: <branch name>
  Integration target reached: <branch name at closeout>

Evidence:
  Quality gate results: <gate-by-gate, exactly as executed; numbers, not adjectives>
  UAT: <offered | requested | performed | deferred | not applicable>
  Commit: <SHA>
  Push status: <yes | no | skipped, with reason>
  Branch status: <e.g., "merged to develop, local + remote deleted">
  Promotion: <e.g., "stopped at orchestrator handoff", "reached develop",
              "reached uat", "PR open from uat to main">

Behavioral Impact:
  <user-visible or system-visible effect>
  <any migrations, config changes, operational effects, rollout concerns>

Risks / Gaps:
  <known limitations, follow-up work, edge cases not covered>
  <or "No known remaining gaps at closeout.">

File Reference Summary:
  <primary files changed; not a full changelog>
```

If a step required by the project's process didn't happen, say so plainly in the relevant Evidence line. **Don't omit; admit.**

## Hard rules (apply to all three formats)

- **Don't claim completion without matching evidence.** A summary that says "Quality Gates: passed" without naming the gates and their results is a smell. Either list the gates with concrete results, or state which gates were skipped and why.
- **Don't use the summary to hide failed checks, skipped steps, or unresolved governance requirements.** If the summary feels like it's trying to make incomplete work look complete, the format isn't doing its job.
- **Don't mark work "done" if the closeout step list isn't actually complete.** If implementation is complete but closure is blocked (waiting on review, on a deploy gate, on a third party), summarize the implementation separately from the blocked governance step. Don't conflate them.
- **Don't omit Process Used, Task Scope, or Execution Context.** "No task was worked on." is a valid value; *missing* is not. Same for Process Used.
- **Factual, concise, externally legible.** No motivational language ("we crushed it"), no self-congratulation ("solid work"), no vague claims ("looks good"). Optimize for fast verification by the reader.

## Don't cite this skill in the output

The summary is a report for the reader (human reviewer, orchestrator agent, future-you reading the closeout record). The skill is the reference for the *author*. Don't write "Per task-handoff-summaries..." or "This skill requires..." — just produce the report. The format speaks for itself.

## Adapter: Beads

If the project uses [Beads](https://github.com/gastownhall/beads) as its task tracker, the literal mappings:

- `Task Scope:` → `Bead Scope:` (e.g., `Bead Scope: proj-42 — Add staging branch and 3-tier deploy flow`)
- `Task:` (in Format 2) → `Bead:` (e.g., `Bead: proj-42-w2`)
- "task design" / "task scope" in prose → "bead design" / "bead scope"
- The Beads CLI gives you the data the summary needs:
  ```bash
  bd show <id>          # bead design + acceptance criteria for the Task Scope restatement
  bd children <parent>  # for orchestrator close-out across worker beads
  ```

Beads also has a `bd close` flow that's required *after* the closeout summary is delivered (the summary documents that closeout is happening; `bd close` is the actual state transition). Don't conflate the two — the summary precedes the close.

Other trackers work the same way — substitute the issue ID format and adjust the field labels per your team's vocabulary:

- **GitHub Issues:** `Task Scope: Issue #123` (or `Closeout Outcome: closes #123`)
- **Linear:** `Task Scope: ENG-123`
- **Jira:** `Task Scope: PROJ-1234`

## Invocation examples

- "Write the implementation summary for the changes I just made."
- "I'm handing this branch to the orchestrator — produce a worker handoff summary."
- "Close out task proj-42. Include all the gate results and the commit SHA."
- "Summarize what was done in this PR using task-handoff-summaries' implementation format."
- "What's the closeout summary for this work?"

## See also

- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md) — the reviewer reads this skill's output and produces structured-code-review format. Format consistency on both sides of the handoff makes the work-→-review-→-next-step flow legible.
- *(planned)* `cross-agent-adversarial-review` — uses the implementation summary as input to a second agent's review (with self-assessment redacted to prevent anchoring).
- *(planned)* `multi-agent-git-workflow` — provides the branch hierarchy and orchestrator/worker role vocabulary referenced in the format fields.
