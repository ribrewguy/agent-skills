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
- **[throughline](throughline)**: the lifecycle spine — requirements to architecture to task to implementation to commit to merge to closeout. Owns the Kickoff Declaration, the three completion phases and the source-of-truth ladder; dispatches everything else to the skill that owns it.
- **[isolated-stack-development](isolated-stack-development)**: one isolated local Supabase stack per worktree. Derived project_id, ports discovered at allocation time, copied-env audit, order-critical teardown — plus a `stack` tool and a PreToolUse guard that blocks resets aimed at a stack the current directory doesn't own. Repos opt in with `.isolated-stack.json`.

- **[jvm-quality](jvm-quality)**: Shared JVM quality policy for tests, module coverage, runtime compatibility, exceptions and dependency vulnerability scanning.
- **[maven-practices](maven-practices)**: Reproducible Maven builds and effective lifecycle enforcement across modules, profiles and test JVMs.
- **[java-practices](java-practices)**: Bloch-inspired Java design: immutability, defensive boundaries, small APIs, value contracts and composition, alongside compiler, formatter and analyzer practices.
- **[kotlin-practices](kotlin-practices)**: Kotlin JVM targets, ktlint, detekt, coverage and reliable Java interoperability.
- **[application-logging](application-logging)**: what a server logs, at which level, in which shape. Two appenders (console for humans, OpenTelemetry for the pipeline), fields as arguments, a never-log denylist, exceptions logged once.
- **[opentelemetry](opentelemetry)**: make a server application support OpenTelemetry and prove it. OTLP via `OTEL_*` variables, three span tiers, context propagation, default service metrics, log correlation, serverless flush, verification against a real collector.
- **[local-https](local-https)**: TLS for every locally run server. mkcert certs at `<project>-local`, a `local-https` tool, a PreToolUse guard that blocks a declared server launching without its cert, a TLS proxy for plain-HTTP builds, per-stack recipes and per-runtime client trust. Repos opt in with `.local-https.json`.
- **[project-kickoff](project-kickoff)**: the first hour of a project, every time. git on `main`, Beads with `bd init --skip-agents`, cass-memory, byte-identical `CLAUDE.md` and `AGENTS.md`, a documentation tree with a business-only PRD and a decision register, a documentation checker and its pre-commit gate. A `project-kickoff` tool with `--dry-run` does the mechanical steps; reruns and existing projects get a gap report, never an overwrite.

## How skills are evaluated

Every skill in this collection passes through an evaluation loop before it ships:

1. Draft the SKILL.md based on real policies or design intent
2. Write focused test prompts in `evals/evals.json` that probe the skill's distinct opinions
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
