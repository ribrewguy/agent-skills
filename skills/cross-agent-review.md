---
title: cross-agent-review
parent: Skills
nav_order: 4
---

# cross-agent-review

A workflow for routine cross-vendor AI peer review. Claude writes; Codex reviews. Or Gemini writes; Claude reviews. What you're after is *blind-spot coverage*. Different model families have different training distributions, different patterns they over-trust, different things they miss. Putting the same work through two model families catches what either alone would have shipped.

## What makes this skill distinct

- **The handoff package excludes the implementer's self-assessment.** No "LGTM," no "all tests pass," no confidence claims. The reviewer gets the work + the design + the acceptance criteria, *cold*. Otherwise the reviewer anchors on the implementer's framing and produces a rubber-stamp. This is the skill's load-bearing rule.
- **The reviewing agent's job is finding what was missed.** Not validating that the implementing agent did good work. The framing is adversarial in the same way a security audit is. Assume the implementer was careful but missed something a different vendor's training would catch.
- **Disagreements escalate to a human, not a third agent.** Recursing to a third agent tends to produce anchoring (siding with the more confidently-written position) or wishy-washy hedging. The skill defines a disagreement summary format that makes the conflict legible enough for a human to break in five minutes.
- **Bounded iteration loop.** Cap at three review rounds without convergence. Beyond three, escalate even if the disagreement seems small. Three rounds without convergence is itself a signal that something about the work or the review needs human judgment.
- **Don't cite the skill in the output.** The handoff package, the review, and the disagreement summary all go to humans (or to each other) for action. The skill is the reference for *how to run the workflow*; the audience for any single output is the recipient, not the workflow itself.

## What it covers

- **The handoff package**: what to include (diff, design, acceptance criteria, architectural context, skills both agents should load), what to redact (self-assessment, framing language, reasoning trace, quality-gate claims), how to frame the request (adversarial, not conversational).
- **Cold-review discipline**: re-run gates yourself, don't read the implementer's reasoning even if available, argue from first principles not from "the implementing agent's pattern."
- **The disagreement protocol**: Outcome 1 (reviewer correct, implementer adopts), Outcome 2 (implementer correct, rebuts), Outcome 3 (real design choice, escalate to human with a structured disagreement summary).
- **The iteration loop**: bounded ping-pong with explicit escalation triggers.
- **Targeted vs. open-ended review**: when to ask for specific risk classes vs. cast a wide net.
- **What this skill doesn't replace**: type checking, tests, human review, security audits. Cross-agent review is one signal among many; it's not authoritative.

## Quick install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install cross-agent-review@ribrewguy-skills
```

For other tools, see [Install](../install).

## Composes with

- **[task-handoff-summaries](task-handoff-summaries)**: the handoff package adapts the implementation-summary format with self-assessment redacted. Format consistency makes the package legible to the second agent.
- **[structured-code-review](structured-code-review)**: the reviewing agent's output uses that format. Severity tags, source-of-truth, file:line citations.
- **(planned)** `multi-agent-git-workflow`: branch and integration-target vocabulary that may appear in handoff packages.

## Tooling and dependencies

- **Required:** two AI agents from different model families. Same-vendor "second pass" doesn't deliver blind-spot coverage. Same training distribution, same patterns over-trusted. Examples of viable pairings: Claude Code as primary + Codex CLI as reviewer; either with Gemini CLI as the third pair element.
- **Strongly recommended:** a way to invoke the second agent from within the first agent's session (e.g., `codex exec` from a Claude Code session). The skill assumes this pattern but works with manual hand-offs (copy work into a Codex session, run the review, paste output back) too.
- **Strongly recommended:** `task-handoff-summaries` for the package format and `structured-code-review` for the reviewer output format.

## Source of truth

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/cross-agent-review/skills/cross-agent-review/SKILL.md)**: the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/cross-agent-review/skills/cross-agent-review/evals/evals.json)**: the four test cases used to verify the skill's behavior.

## Eval results

Full per-eval breakdown, interactive review viewer, and links to raw model outputs: **[cross-agent-review evaluations](../evals/cross-agent-review)**.

Iteration-1 benchmark: **100% pass rate with-skill vs. 77% baseline** (+23pp delta) across four cases. Per-eval pattern: largest delta on the redact-self-assessment handoff (+50pp) and disagreement-summary even-handedness (+30pp); smaller delta on the cold-review (+13pp because both can review code competently); zero delta on skip-trivial-work (the prompt itself supplied the policy framing, a non-discriminating eval to revisit in iteration-2).

| Eval | What it probes |
|---|---|
| `build-handoff-package-with-redaction` | Does the skill produce a handoff package with self-assessment, framing language, and reasoning trace REDACTED? Does it include the design, the diff, and adversarial framing? |
| `perform-cold-review-no-anchoring` | Does the reviewing agent treat the work cold, catch the load-bearing issues (timing attack, fundamental misuse of signing key, missing malformed/expired handling), and produce structured-code-review-format output without anchoring? |
| `write-disagreement-summary` | Does the skill produce an even-handed disagreement summary in the prescribed 6-section format, with a named human escalation, without advocating for either side? |
| `skip-cross-agent-for-trivial-work` | Does the skill correctly recommend skipping cross-agent review for trivial mechanical changes (typos, dependency bumps) and applying it to high-value triggers (money-touching, complex refactors)? |

Eval transcripts and benchmark JSON live alongside the skill source.

## Invocation examples

- "Get a Codex review of this work."
- "I want a cross-agent review of the auth flow changes. They're security-sensitive."
- "Send this to Codex with the self-assessment redacted; come back with the review."
- "Resolve the disagreement with Codex on the cache-invalidation approach."
- "Apply cross-agent-review to this PR before I push to develop."

## Adapter: Claude Code + Codex CLI

The user's typical pattern. From a Claude Code session, dispatch a Codex review:

```bash
codex exec "You are a second-pass cross-vendor reviewer. The work below is purported to implement [paste design]. Find what's wrong. Things to look for specifically: [domain anti-patterns]. Don't validate that the work is good; assume something was missed. ..."
```

Codex returns its review. Claude (the implementing agent) reads the review and either adopts findings or writes a rebuttal per the disagreement protocol.

The reverse direction (Codex implementing, Claude reviewing) is symmetric. Substitute `claude --print` or equivalent for `codex exec`.
