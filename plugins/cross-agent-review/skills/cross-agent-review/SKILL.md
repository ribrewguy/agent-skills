---
name: cross-agent-review
description: Use when high-stakes work needs a second-agent review pass — when Claude's work should be reviewed by Codex (or vice versa), when a security-sensitive change wants two model families' blind spots covered, when a complex refactor's one-agent review feels like rubber-stamping. Defines the handoff package (what context the second agent gets, with the implementer's self-assessment REDACTED so the reviewer doesn't anchor on confidence claims), the cold-review discipline, the disagreement protocol when agents conflict, the bounded iteration loop. The reviewing agent's job is to find what the first agent missed, not to validate that the first agent did good work. Symptoms — single-agent code reviews that consistently approve the agent's own work; "AI reviewed it" used as authority without naming WHICH AI or what they actually checked; cross-agent reviews that are 90% agreement with the implementing agent (a sign the reviewer was anchored, not actually checking); high-stakes deploys that went out with one model's blind spot intact because no second model class touched them.
---

# Cross-Agent Review

## Overview

A workflow for routine cross-vendor AI peer review. Claude writes; Codex reviews. Or Gemini writes; Claude reviews. The goal is *blind-spot coverage* — different model families have different training distributions, different patterns they over-trust, different things they miss. Putting the same work through two model families catches what any single one would have shipped.

Three things make this not just "ask another model the same question":

1. **The handoff package excludes the implementer's self-assessment.** No "LGTM," no "all tests pass," no confidence claims. The reviewer gets the work + the design + the acceptance criteria, *cold*. Otherwise the reviewer anchors on the implementer's framing and produces a rubber-stamp.
2. **The reviewing agent's job is finding what was missed.** Not validating that the implementing agent did good work. The framing is adversarial in the same way a security audit is adversarial — assume the implementer was careful but missed something a different vendor's training would catch.
3. **Disagreements escalate to a human, with the conflict summarized.** Not to a third agent (infinite ping-pong), not to the implementer's preference (the whole point is to surface disagreement). The skill defines what a disagreement summary looks like.

## Tooling and dependencies

### Required

- **Two AI agents from different model families.** This is the only hard requirement. Same-vendor "second pass" (Claude reviews Claude) doesn't deliver blind-spot coverage — same training distribution, same patterns over-trusted. Examples of viable pairings:
  - Claude Code as primary; OpenAI Codex CLI as reviewer
  - Codex as primary; Claude Code as reviewer
  - Either of the above with Gemini CLI as the third pair element
  - Any cross-vendor combination that satisfies "different model family"

### Strongly recommended

- **A way to invoke the second agent from within the first agent's session.** The user's typical pattern: from a Claude Code session, dispatch a Codex review via the `codex exec` CLI, capture the output, return to Claude. The skill assumes this pattern but works with manual hand-offs (copy work into a Codex session, run the review, paste output back) too.
- **`task-handoff-summaries`** — the handoff package is *almost* the implementation summary, with a critical exception (see §"The handoff package" below). Format consistency makes the package legible to the second agent.
- **`structured-code-review`** — the reviewer's output uses that format. Format consistency makes the cross-agent flow legible: implementer hands off → reviewer's findings come back severity-tagged with source-of-truth.

### Optional

- A domain skill (`rest-api-design`, etc.) for both agents to load. The cross-agent value is highest when both agents apply the same domain rules but bring different blind spots to them.

### Composes with

- [`task-handoff-summaries`](../../../task-handoff-summaries/skills/task-handoff-summaries/SKILL.md) — provides the implementation-summary format. Cross-agent adapts it by **redacting the self-assessment fields** before handoff.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md) — the reviewing agent's output format. Severity tags, source-of-truth, file:line citations.
- *(planned)* `multi-agent-git-workflow` — branch and integration-target vocabulary that may appear in handoff packages.

## When to use

**High-value triggers:**

- **Security-sensitive code** — auth flows, crypto handling, permission checks, anywhere a single agent's blind spot is a vulnerability.
- **Money-touching paths** — payments, transfers, billing logic, anything where a missed bug has direct dollar cost.
- **Concurrency / state machines** — race conditions and ordering bugs are notoriously training-distribution-dependent; different models miss different ones.
- **Complex refactors of load-bearing code** — large-scale changes where the implementing agent's framing of "what's correct" might be too narrow.
- **Anywhere the implementing agent expressed unusual confidence or unusual uncertainty** — both signals that a different model class might see the work differently.

**Skip for:**

- Trivial changes (typos, dependency bumps, formatting).
- Work covered comprehensively by tests + types — the cross-agent overhead doesn't pay back when the deterministic gates already caught the bug class.
- Time-pressed changes where the cost of waiting for a second review exceeds the value of catching what it might find. (Be honest about this calculation; "it's urgent" is the most-misused excuse for skipping review.)

## The handoff package

What you bundle for the reviewing agent. **The implementer's self-assessment is redacted.** That's the load-bearing rule.

### Include

- **The diff or the changed files in their final state.** What the reviewer is reviewing.
- **The design or specification the work claimed to implement.** Task description, design doc, acceptance criteria, PRD section — whatever the source of truth is. The reviewer needs to be able to check the work *against something*, not just judge it on aesthetics.
- **The architectural context** the change touches. Files, modules, integration points the reviewer needs to know about to evaluate the change's fit. Keep this minimal — too much context is also anchoring.
- **The skills the implementing agent loaded.** If the implementer used `rest-api-design` while writing the code, the reviewer should also load `rest-api-design` so both agents are evaluating against the same domain rules.

### Redact (this is the key step)

- **Self-assessment / completion claims** — "LGTM", "all tests pass", "implementation complete", confidence ratings. Anything that signals the implementer's confidence in the result.
- **Quality-gate results** that the reviewer should re-run themselves. If you tell the reviewer "lint passed, typecheck passed, 142/142 unit tests" before they look, they will anchor; if they re-run those gates as part of the review, the result is independent.
- **Framing language** that pre-shapes the answer — "the only tricky part is X", "the obvious approach didn't work", "I considered Y but rejected it." The reviewer should derive their own model of what's tricky.
- **The implementing agent's reasoning trace** when one is available. Especially anchor-prone: a reviewer shown "I considered approach A but went with B because…" almost always validates B.

### Frame the request

The instruction to the reviewing agent should be adversarial:

> "This work is purported to implement [design]. Find what's wrong. Things to look for specifically: [domain anti-patterns the implementer's model class is statistically prone to missing]. Don't validate that the work is good — assume something was missed."

Not:

> "Please review this code."

The framing matters as much as the redaction. A reviewer asked to "review" produces a balanced "here's what's good, here's what could be better" answer; a reviewer asked to "find what was missed" produces a list of concerns.

## Cold-review discipline

The reviewing agent reads the handoff package and produces a review. Three rules that make the review actually independent:

1. **Re-run the gates yourself, don't trust the report.** If types and tests are part of the contract, type-check and test in the review session — don't assume the implementer's claim "all green" was accurate. Most regressions slipped through "all green" claims because the gate didn't cover the regression.
2. **Don't read the implementer's reasoning, even if you have access to it.** The point is to derive your own model. Read the design and the diff; ignore the commit messages and PR description if they reveal the implementer's thought process.
3. **Argue from first principles, not from "the implementing agent's pattern."** A reviewer who writes "the implementing agent uses pattern X here, which is fine" has just rubber-stamped. A reviewer who writes "this code uses pattern X for Y reason; the reason is unsound because Z" has actually reviewed.

The reviewer's output uses `structured-code-review`'s format (severity tags, source-of-truth, file:line citations). The format consistency lets the implementer (or human triaging the review) absorb findings quickly.

## The disagreement protocol

When the reviewing agent disagrees with the implementing agent's choices, three outcomes:

### Outcome 1 — Reviewer's finding is correct; implementer adopts it

The implementer revises and re-submits. The cycle is: handoff → review → adopt → re-handoff (with the revised work and the reviewer's accepted findings) → re-review. Stop when the reviewer's next round produces no new findings.

### Outcome 2 — Implementer's choice is correct; reviewer's finding is wrong

The implementer documents *why* the reviewer's finding doesn't apply, in language the reviewer can verify on a re-pass. Not "I disagree" — "the reviewer assumed X, but actually the constraint is Y, so the alternative they proposed wouldn't work." Re-handoff with this rebuttal added; the reviewer either accepts the rebuttal or escalates.

### Outcome 3 — Both have a defensible position; this is a real design choice

Escalate to a human with a **disagreement summary**:

```
## Cross-Agent Review Disagreement

Topic: <one-sentence description of the contested decision>

Implementing agent's position:
  <what they did and why, in 2-4 sentences>
  Tradeoff they accepted: <what cost was incurred for what benefit>

Reviewing agent's position:
  <what they recommend instead, in 2-4 sentences>
  Tradeoff they propose: <what cost would be incurred for what benefit>

What both agree on:
  <the constraints / requirements both positions satisfy>

What's at stake in the choice:
  <the consequence the disagreement is really about — performance,
   maintainability, security posture, future flexibility, etc.>

Recommended escalation:
  <which human to ask, what specific question to ask them>
```

The disagreement summary is intentionally even-handed. The skill's job is not to break the tie — it's to make the tie legible enough that a human can break it in five minutes.

**Don't escalate to a third agent.** A third agent reviewing two prior agents' positions tends to either side with the more confidently-written position (anchoring again) or hedge into a wishy-washy "both have merit" answer that doesn't help. The third pass-through is a human.

## The iteration loop

```
implementer produces work
  ↓
write handoff package (redact self-assessment per §"Include / Redact")
  ↓
reviewer produces structured-code-review-format output
  ↓
  ├─ no findings: ship.
  ├─ findings, all High/Medium accepted by implementer:
  │    revise → re-handoff → re-review → repeat
  ├─ findings, implementer disagrees:
  │    rebuttal → re-handoff → re-review
  │      ├─ reviewer accepts rebuttal: ship.
  │      └─ reviewer maintains finding: write disagreement summary,
  │         escalate to human.
  └─ findings, Critical: ship is blocked. revise → re-handoff.
```

**Bound the loop.** Cap at three review rounds without convergence. Beyond three, escalate to a human even if the disagreement is small — three rounds without convergence is itself a signal that something about the work or the review is harder to resolve than agent-only iteration can fix.

## Targeted vs. open-ended review

Two modes:

- **Open-ended** — "Review this work for anything wrong." Useful when you don't know where the risks are. Catches a wide net but can produce noisy reviews (lots of low-severity nits).
- **Targeted** — "Review this work specifically for [class of issue]." Useful when the work has a known risk vector — concurrency, security boundary, contract change. Higher-precision findings, lower coverage.

The skill recommends **targeted on the second pass** when the first pass surfaces a class of concern. "Codex flagged a potential race condition; ask Codex to look specifically for race conditions across the rest of the change too" is the canonical follow-up. This converges faster than re-running open-ended reviews.

## What this skill doesn't replace

- **Type checking, linting, unit tests, integration tests.** These are deterministic gates that catch mechanical bugs cheaply. Cross-agent review is for the bugs the deterministic gates can't catch — design errors, missed edge cases, security thinkos.
- **Human review.** A senior reviewer who knows the codebase, the business, and the team's history catches things no agent (single or paired) catches. Cross-agent review reduces the human reviewer's load on mechanical issues so they can focus on judgment calls.
- **Security audits.** A trained security reviewer evaluating against a threat model is different from a cross-agent review. The two complement; neither replaces the other.

## Don't cite this skill in the output

The implementing agent and reviewing agent both produce concrete outputs (handoff package, review, disagreement summary). Those outputs go to humans (or to each other) for action. The skill is a reference for *how to run the workflow*; the audience for any single output is the recipient, not the workflow itself.

Avoid:

- "Per cross-agent-review's protocol..."
- "This skill requires..."
- "As specified in the workflow..."

Write the package, the review, the disagreement summary directly.

## Adapter: Claude Code + Codex CLI

The user's typical pattern. From a Claude Code session, dispatch a Codex review:

```bash
codex exec "Review this work as a second-pass cross-vendor reviewer. \
This work is purported to implement [paste design]. \
Find what's wrong. Things to look for specifically: \
[domain anti-patterns this Claude session might miss]. \
Don't validate that the work is good — assume something was missed.

Files to review:
[paste relevant files in their final state, with NO commit messages]

Acceptance criteria:
[paste from the task design]

Apply structured-code-review's format and any relevant domain skills."
```

Codex returns its review. Claude (the implementing agent) reads the review and either adopts findings or writes a rebuttal per §"The disagreement protocol".

The reverse direction (Codex implementing, Claude reviewing) is symmetric — substitute `claude --print` or equivalent for `codex exec`.

For other pairings (Gemini ↔ Claude, Codex ↔ Gemini, etc.), the pattern is the same: invoke the second agent with the redacted handoff package and the adversarial framing.

## Invocation examples

- "Get a Codex review of this work."
- "I want a cross-agent review of the auth flow changes — they're security-sensitive."
- "Send this to Codex with the self-assessment redacted; come back with the review."
- "Resolve the disagreement with Codex on the cache-invalidation approach."
- "Apply cross-agent-review to this PR before I push to develop."

## See also

- [`task-handoff-summaries`](../../../task-handoff-summaries/skills/task-handoff-summaries/SKILL.md) — the handoff package adapts the implementation-summary format with self-assessment redacted.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md) — the reviewer's output format.
- [`rest-api-design`](../../../rest-api-design/skills/rest-api-design/SKILL.md) (and other domain skills) — load on both agents so both apply the same domain rules.
