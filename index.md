---
title: Home
nav_order: 1
description: "RI Brew Guy's AI Agent Skills, a curated collection for Claude Code, Gemini CLI, OpenAI Codex, GitHub Copilot CLI, Cline, and other tools that read the SKILL.md format."
permalink: /
---

# RI Brew Guy's AI Agent Skills

Skills I've built for AI coding tools. They're just markdown with a bit of YAML frontmatter, the `SKILL.md` format that [Claude Code](https://claude.com/code), [Gemini CLI](https://geminicli.com), [OpenAI Codex](https://developers.openai.com/codex), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), and [Cline](https://docs.cline.bot) all read natively. Other tools (Cursor, Aider) don't have a native skills system, but you can point their rule files at these.

Each skill is shaped the same way. Write a draft, run it against its own test prompts, read the outputs side by side with a baseline, revise. The test prompts and per-case assertions ship with the skill in `evals/evals.json`, so "the skill works" means something you can actually measure instead of vibes.

## Quick start

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
```

That's the Claude Code path. For other tools (Gemini, Codex, Copilot, Cline, Cursor, Aider), see **[Install](install)**.

## What's inside

- **[rest-api-design](skills/rest-api-design)**: design and review HTTP REST APIs. Resource-oriented URLs, PATCH for state transitions, domain-expressive error codes, flat error envelopes, idempotency, content-type negotiation, typed contracts across TS/Python/Go/Rust.
- **[structured-code-review](skills/structured-code-review)**: a review-only output format for code reviews. Source-of-truth-aware preamble, severity-tagged findings, file:line citations, no-findings-still-formal. Composes with domain-review skills.
- **[task-handoff-summaries](skills/task-handoff-summaries)**: three structured report formats (implementation summary before commit, worker handoff to orchestrator, closeout after completion). Hard rules against using the summary to mask incomplete work.
- **[cross-agent-review](skills/cross-agent-review)**: workflow for routine cross-vendor agent peer review (Claude reviews Codex's work; Codex reviews Claude's). The handoff package with self-assessment redacted, the cold-review discipline, the disagreement protocol.
- **[multi-agent-git-workflow](skills/multi-agent-git-workflow)**: git discipline for multi-agent work. Worktree-per-agent topology, orchestrator/worker roles, merge authority, acceptance/rejection rules, plus universal commit discipline (Conventional Commits, mandatory task ID, co-author line, UAT gate, no silent amends).

The full catalog lives at **[Skills](skills)**.

## Why a skill collection?

A skill captures the *opinionated* part of how I work. The conventions and rules that don't show up in any framework's defaults but that I keep re-explaining to AI assistants across projects. Distilling them into a SKILL.md once and pointing every tool at the same file means I (and my future self, and anyone else using these) don't re-litigate the same patterns every conversation.

The skills here are extracted from real `policies/development/` directories I maintain in production projects. Each one passed an evaluation pass before it shipped: a 4-case test set with per-assertion grading, comparing skill-loaded output against a baseline.

## Where to go next

- **[Install](install)**: set up the skills for your AI tool of choice.
- **[Skills](skills)**: browse the catalog, see what each one covers, link out to the canonical SKILL.md.
- **[Concepts](concepts)**: the cross-cutting ideas these skills share. The canonical-home symlink pattern, dependency tiers, severity ladders, composition over absorption.

This site is also the docs for contributors who want to add their own skills to the collection. See [Skills → Contributing a new skill](skills#contributing-a-new-skill).
