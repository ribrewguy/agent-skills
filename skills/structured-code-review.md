---
title: structured-code-review
parent: Skills
nav_order: 2
---

# structured-code-review

A rigorous, review-only output format for code reviews. Domain skills bring opinions about *what* to flag; this skill brings the discipline of *how* to present findings so the author can triage at a glance and the reviewer can be held accountable to a named source of truth.

## What makes this skill distinct

- **Reviews are review-only by default.** The reviewer's job is to surface, name severity, cite source-of-truth, and propose alignment — not to apply fixes. Don't edit files unless the user explicitly asks.
- **`Findings:` header + 8-field preamble.** Every review starts the same way: `Findings:` on its own line, then `Review Scope:`, `Process Context:`, `Execution Context:`, `Integration Target:`, `Design Reference:`, `Architecture Reference:`, `Feature Specification Reference:`, `PRD Reference:` — in that order, even on a one-line change.
- **Severity tags in backticks**, ordered highest first. `` `High` ``, `` `Medium` ``, `` `Low` ``. The author scans severities down the left margin and triages in seconds. Domain skills MAY add `` `Critical` `` for production-blocker class issues (see [Severity ladder](../concepts/severity-ladder)).
- **No-findings format is identical to findings format.** Even on a clean change, the preamble emits and `Residual Risks / Gaps:` is mandatory. This is what proves the review actually happened versus an unaccountable "looks good."
- **Per-finding `Source of truth:` discipline.** Every finding names what it's checking against — task design, architecture spec, feature specification, PRD, lightweight task context, or general code quality. Reviews that don't name a source of truth aren't reviews; they're opinions.
- **Don't cite the skill in the output.** The skill is a reference for the reviewer; the audience for the output is the PR author. Reviews argue from first principles, not from the skill's rulebook.

## What it covers

- Required preparation before writing findings
- Eight-field preamble with `None applicable` / `Unable to determine` / `No task identified` as valid values
- Per-finding format: severity tag in backticks, file:line citation, Problem/Why/Source of truth/Proposed fix structure
- Three-tier severity ladder (`High` / `Medium` / `Low`), with optional `Critical` for domain skills
- No-findings case (preamble still emitted, plus `Residual Risks / Gaps:`)
- Hard rules against summary-before-findings, fabricated tasks, silent source-of-truth skips, applying fixes when only review was requested

## Quick install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install structured-code-review@ribrewguy-skills
```

For other tools, see [Install](../install).

## Composes with

- **[rest-api-design](rest-api-design)** — domain review opinions for HTTP REST APIs. Pair with this skill: rest-api-design identifies the violations; structured-code-review structures the output.
- **(planned)** `multi-agent-git-workflow` — branch and role vocabulary used in `Execution Context:` and `Integration Target:` preamble fields.
- **(planned)** `task-handoff-summaries` — the report format that sits *upstream* of code review (the implementation summary the author hands you before you review).

## Tooling and dependencies

- **Required:** none — the format is tool-neutral
- **Strongly recommended:** a task / issue tracker (Beads, GitHub Issues, Linear, Jira, Shortcut). Without one, every review's `Review Scope:` is `No task identified` and the skill falls back to lightweight-process review.
- **Strongly recommended:** source-of-truth artifacts — design docs, architecture specs, feature specifications, PRDs. Reviews are stronger when they can name what they're checking against.
- **Adapter:** [Beads](https://github.com/gastownhall/beads) — the skill body has a dedicated section showing the literal mapping (`Review Scope: Bead rp-c74`, `bd show <id>` for source-of-truth lookups). Other trackers substitute their own ID format.

## Source of truth

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/structured-code-review/skills/structured-code-review/SKILL.md)** — the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/structured-code-review/skills/structured-code-review/evals/evals.json)** — the four test cases used to verify the skill's behavior.

## Eval results

Iteration-1 benchmark: **100% pass rate with-skill vs. 31% baseline** across four test cases (+69pp delta — the largest skill effect we've measured in this collection):

| Eval | What it probes |
|---|---|
| `mixed-severity-pr-review` | Does the skill produce the eight-field preamble, sort findings by severity, identify a realistic mix of issues across security and convention? |
| `no-findings-clean-change` | Does the skill emit the preamble + `No findings.` + `Residual Risks / Gaps:` even when there are zero findings? |
| `no-task-no-design-fallback` | Does the skill correctly emit `Review Scope: No task identified` and review against lightweight-process context without fabricating a task? |
| `rest-domain-composition` | Does the skill compose with rest-api-design — applying the format to REST domain findings? |

Eval transcripts and benchmark JSON live alongside the skill source.

## Invocation examples

- "Review this PR using structured-code-review's format."
- "Audit this implementation against the design at `docs/specs/auth-flow.md`. Tag findings with severity."
- "Code review the changes on this branch — what doesn't match the PRD?"
- "Is this PR ready to merge?"
- "Use rest-api-design + structured-code-review to review the new endpoint."
