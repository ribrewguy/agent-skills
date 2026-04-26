---
title: Skills
nav_order: 3
has_children: true
permalink: /skills/
---

# Skills

The catalog. Each skill has its own page with a summary, its key opinions, install snippets, and a link to the canonical SKILL.md.

## Currently shipping

- **[rest-api-design](rest-api-design)**: design and review HTTP REST APIs. Resource-oriented URLs, PATCH for state transitions, domain-expressive error codes, flat error envelopes, idempotency, content-type negotiation, typed contracts across TS/Python/Go/Rust.
- **[structured-code-review](structured-code-review)**: a review-only output format for code reviews. Source-of-truth-aware preamble, severity-tagged findings, file:line citations, no-findings-still-formal. Composes with domain-review skills.
- **[task-handoff-summaries](task-handoff-summaries)**: three structured report formats. Implementation summary (before commit), worker handoff summary (multi-agent to orchestrator), closeout summary (after completion). Hard rules against using the summary to mask incomplete work.
- **[cross-agent-review](cross-agent-review)**: workflow for routine cross-vendor agent peer review (Claude reviews Codex's work; Codex reviews Claude's). The handoff package with self-assessment redacted, the cold-review discipline, the disagreement protocol, the bounded iteration loop.
- **[multi-agent-git-workflow](multi-agent-git-workflow)**: git discipline for multi-agent work. Branch hierarchy, worktree-per-agent topology, orchestrator/worker roles, merge authority, acceptance/rejection rules, plus universal commit discipline (Conventional Commits, mandatory task ID, co-author line, UAT gate, no silent amends).
- **[branch-promotion-discipline](branch-promotion-discipline)**: the layer above multi-agent-git-workflow. 3-tier `develop` to `uat` to `main` promotion, UAT branch as a long-lived environment, per-tier CI gate matrix, source-ref enforcement, hotfix flow with forward-merge, branch protection ruleset, pre-commit hook setup.

## How skills are evaluated

Every skill in this collection passes through an evaluation loop before it ships:

1. Draft the SKILL.md based on real policies or design intent
2. Write 4 test prompts in `evals/evals.json` that probe the skill's distinct opinions
3. Spawn parallel runs, one with the skill loaded, one baseline without
4. Grade outputs against per-case assertions; aggregate into a benchmark
5. Iterate until the with-skill output is materially better than the baseline on the assertions that matter

The eval set ships in the repo at `plugins/<plugin-name>/skills/<skill-name>/evals/evals.json` so anyone can re-run it.

## Contributing a new skill

To add a new skill to the collection:

1. **Plugin manifest**: `plugins/<plugin-name>/.claude-plugin/plugin.json` with `name`, `description`, `version`.
2. **Skill file**: `plugins/<plugin-name>/skills/<skill-name>/SKILL.md` in the standard SKILL format (YAML frontmatter with `name`, `description`; markdown body).
3. **Marketplace entry**: add to `.claude-plugin/marketplace.json` under `plugins` with `source: ./plugins/<plugin-name>`.
4. **Evals** (optional but the whole point): `plugins/<plugin-name>/skills/<skill-name>/evals/evals.json` with test cases and per-assertion pass/fail criteria.
5. **Docs page**: `skills/<skill-name>.md` (this directory) with the human-facing summary, key opinions, install snippets, and a link to the SKILL.md.

Open a PR. If you ran evals, drop the iteration-1 benchmark in the PR description.

See the existing [rest-api-design](rest-api-design) and [structured-code-review](structured-code-review) pages for the format.
