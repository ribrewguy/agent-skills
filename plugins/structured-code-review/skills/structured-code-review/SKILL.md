---
name: structured-code-review
description: Use when conducting code reviews, PRs, audits, evaluations against design. Produces rigorous review-only output: names source of truth per finding (task/design/architecture/feature spec/PRD/lightweight context), tags severity (High/Medium/Low), cites file:line, emits structured no-findings preamble. Composes with domain-review skills like rest-api-design. Symptoms, flat issue lists, severity terms used inconsistently (Critical/High/Major/P1 mixed), "looks good" responses not naming what was reviewed against, reviews drifting into applying fixes when only review was requested.
---

# Structured Code Review

## Overview

A rigorous output format for code reviews. Domain skills bring opinions about *what* to flag; this skill brings the discipline of *how* to present findings so the author can triage at a glance and the reviewer can be held accountable to a named source of truth.

Reviews are review-only by default, don't apply fixes unless the user explicitly asks. The reviewer's job is to **surface, name severity, cite source-of-truth, and propose alignment**, not to do the work.

## Tooling and dependencies

### Required

- Nothing. The output format is tool-neutral.

### Strongly recommended

- **A task / issue tracker**, review scope is materially clearer when each change maps to a tracked task. The skill names a task ID in the preamble. Examples: [Beads](https://github.com/gastownhall/beads), GitHub Issues, Linear, Jira, Shortcut. If the work has no tracked task, the skill emits `Review Scope: No task identified` and reviews against the highest available source of truth.
- **Source-of-truth artifacts**, design docs, architecture specs, feature specifications, PRDs. Reviews are stronger when they can name what they're checking against. Without them, reviews fall back to lightweight-process context (general code quality, repo conventions).

### Optional

- A domain-specific review skill (e.g., `rest-api-design`) for the *what to flag*. This skill governs *how to present*.

### Composes with

- [`rest-api-design`](../../../rest-api-design/skills/rest-api-design/SKILL.md), domain opinions for HTTP REST APIs. Use both: domain skill identifies the violations; this skill structures the output.
- *(planned)* `multi-agent-git-workflow`, branch and role vocabulary used in `Execution Context:` and `Integration Target:`.
- *(planned)* `task-handoff-summaries`, the report format that sits *upstream* of the code review (the implementation summary the author hands you before you review).

## When to use

- The user asks to review a PR, audit a change, evaluate an implementation against design intent
- A task is being closed out and the implementation needs verification before merge
- A teammate asks "is this ready?", the answer should always be a structured review, never an unaccountable "looks good"
- Symptoms calling for this skill: flat issue lists with no severity, reviews that don't name what they checked against, "approval" responses that hide unverified governance

## Required preparation

Before writing findings, determine and state these facts. Each maps to a preamble field below.

- **Whether the review is tied to a tracked task**, a task tracker issue ID, a ticket reference, or "no task identified."
- **Process type**, full process (PRD → architecture → feature spec → task with design) vs. lightweight process (small change, no formal task) vs. unable to determine.
- **Execution topology**, single-agent vs. multi-agent worker vs. multi-agent orchestrator. Skip this distinction if the project doesn't use multi-agent workflows; emit `Execution Context: Single-agent` or `Unable to determine` as appropriate.
- **Integration target**, which branch will this merge into, if determinable.
- **Governing documents consulted vs. unavailable vs. not applicable**, design, architecture, feature spec, PRD.

If a task is identified, name the task ID and review against the task's scope and design (if a design exists). If no task is identified, state that explicitly, don't invent one, and review against the best available governing sources.

## Required output format

Every code review response must start with **exactly** this header on its own line:

```
Findings:
```

Then emit these eight preamble fields, in this order, one per line:

1. `Review Scope: Task <id>` or `Review Scope: No task identified`
2. `Process Context: Full process` or `Process Context: Lightweight process` or `Process Context: Unable to determine`
3. `Execution Context: Single-agent` or `Execution Context: Multi-agent worker` or `Execution Context: Multi-agent orchestrator` or `Execution Context: Unable to determine`
4. `Integration Target: <branch name>` or `Integration Target: Unable to determine`
5. `Design Reference: <one-line summary of the design referenced>` or `Design Reference: None found` or `Design Reference: No task identified`
6. `Architecture Reference: <file path + section>` or `Architecture Reference: None applicable`
7. `Feature Specification Reference: <file path + section>` or `Feature Specification Reference: None applicable`
8. `PRD Reference: <file path + section>` or `PRD Reference: None applicable`

Then list findings, ordered by severity (highest first).

### Each finding

Each finding must:

- Start with a severity tag in backticks: `` `High` ``, `` `Medium` ``, or `` `Low` ``
- State the issue in one sentence
- Explain why it violates or risks violating the scoped source of truth
- Include precise file references with line numbers
- Name the source of truth used for the finding
- Propose a fix that would align the implementation

Format each finding like this:

```
- `High` [path/to/file.ext:line]
  Problem: <what is wrong, in one sentence>
  Why it matters: <behavioral, governance, architectural, or product impact>
  Source of truth: <task / design / architecture / feature specification / PRD / lightweight task context>
  Proposed fix: <what needs to change to align with the source of truth>
```

Order strictly by severity: all `High` findings, then all `Medium`, then all `Low`. Within a severity, group by file when possible so the author can scan changes by location.

### Severity ladder

| Severity | Criterion |
|---|---|
| `High` | Correctness or contract violation. Will cause wrong behavior, break consumers, fail security/compliance, or fail the source-of-truth check materially. The author cannot ship until this is addressed. |
| `Medium` | Design or convention deviation. Doesn't break the build but creates debt, inconsistency, missing convention, or scope drift from the design. The author should fix before merge unless they have a specific reason to defer. |
| `Low` | Polish. Naming nit, minor clarity issue, "nice to have" addition. Optional. |

When reviewing in a domain that has genuine production-blocker class issues (e.g., REST design with destructive `GET` endpoints, payments without idempotency), domain review skills MAY add a `Critical` tier above `High` and document it in their own skill body. The default scale used by this skill is the three-tier `High` / `Medium` / `Low`.

### No-findings case

If no findings are discovered, the format does **not** change, emit the full preamble. This is what proves the review actually happened versus an unaccountable "looks good."

```
Findings:
Review Scope: <...>
Process Context: <...>
Execution Context: <...>
Integration Target: <...>
Design Reference: <...>
Architecture Reference: <...>
Feature Specification Reference: <...>
PRD Reference: <...>

No findings.

Residual Risks / Gaps: <tests not run, unclear assumptions, missing docs, or "None noted">
```

The `Residual Risks / Gaps:` line is mandatory in the no-findings case, it forces the reviewer to surface the things they couldn't verify.

## Hard rules

- **Findings before summaries.** The findings list comes before any change overview, "what changed" summary, or general commentary. The author should be able to read severity tags down the left margin and know what blocks merge before reading anything else.
- **Don't invent a task.** If no task ID is associated with the work, emit `Review Scope: No task identified`. Do not fabricate one.
- **Don't omit the preamble.** Even on a one-line change, all eight preamble fields appear. "None applicable" / "No task identified" / "Unable to determine" are valid values; *missing* is not.
- **Don't silently skip source-of-truth checks.** If architecture, feature spec, or PRD wasn't consulted, the corresponding line says `None applicable` or `Unable to determine`, never just absent.
- **If required sources are missing, surface it.** A review that couldn't find the design is a review with a gap; that gap goes in `Residual Risks / Gaps:`, not buried in prose.
- **Review-only by default.** Don't apply fixes unless the user explicitly asks. "Propose a fix" is text in the finding; don't edit the file.

## Don't cite this skill in the output

Explain reasoning directly. A reviewer argues from the underlying issue ("this `POST` returns `200` for a created resource, clients reading the spec will treat it as 'existing resource fetched' and skip the `Location` header lookup"); they don't cite a rulebook ("Listed in structured-code-review: 'severity tags must be in backticks'").

The skill is a reference for *you*; the audience for your output is the PR author. Avoid:

- *"Per structured-code-review..."*
- *"This skill requires..."*
- *"Listed as a hard rule"*

Write the reasoning directly. The format speaks for itself; you don't need to cite where it came from.

## Adapter: Beads

If the project uses [Beads](https://github.com/gastownhall/beads) as its task tracker, the literal mappings:

- `Review Scope: Task <id>` → `Review Scope: Bead <id>` (e.g., `Bead proj-42`)
- `Process Context: Full process` → `Process Context: Full bead process`
- "task scope" / "task design" in the prose → "bead scope" / "bead design"
- The Beads CLI gives you the design and acceptance criteria for source-of-truth lookups:

```bash
bd show <id>          # show the bead's full design + acceptance criteria
bd context "<task>"   # surface curated procedural rules from CASS, if installed
```

Other trackers work the same way, substitute the issue ID format and adjust the "Process Context" label per your team's vocabulary:

- **GitHub Issues:** `Review Scope: Issue #123` (or `Review Scope: PR #456` for self-referential reviews)
- **Linear:** `Review Scope: ENG-123`
- **Jira:** `Review Scope: PROJ-1234`
- **Shortcut:** `Review Scope: sc-12345`

## Invocation examples

- "Review this PR using structured-code-review's format."
- "Audit this implementation against the design at `docs/specs/auth-flow.md`. Tag findings with severity."
- "Code review the changes on this branch, what doesn't match the PRD?"
- "Is this PR ready to merge? Apply structured-code-review."
- "Use rest-api-design + structured-code-review to review the new endpoint."

## See also

- [`rest-api-design`](../../../rest-api-design/skills/rest-api-design/SKILL.md), domain review opinions for HTTP REST APIs. Pair with this skill: rest-api-design identifies the REST violations; structured-code-review structures the output.
