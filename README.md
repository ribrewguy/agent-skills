# RI Brew Guy's AI Agent Skills

Skills for AI coding tools: Claude Code, Gemini CLI, OpenAI Codex, GitHub Copilot CLI, Cline, and others. They're plain markdown with YAML frontmatter (the standard `SKILL.md` format), so they work in every tool that reads it.

📖 **Full docs:** **<https://ribrewguy.github.io/agent-skills/>**

## Quick install (Claude Code)

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
/plugin install structured-code-review@ribrewguy-skills
```

Other tools (Gemini CLI, Codex CLI, Copilot CLI, Cline, Cursor, Aider) plus the canonical-home symlink pattern: see **[Install](https://ribrewguy.github.io/agent-skills/install/)**.

## Skills

- **[rest-api-design](https://ribrewguy.github.io/agent-skills/skills/rest-api-design/)**: design and review HTTP REST APIs. State transitions via PATCH (not sub-resource verbs), domain-expressive error codes, flat error envelopes, idempotency, content-type negotiation, typed contracts across TS/Python/Go/Rust.
- **[structured-code-review](https://ribrewguy.github.io/agent-skills/skills/structured-code-review/)**: review-only output with a source-of-truth-aware preamble, severity-tagged findings, file:line citations, and a "no findings, still formal" rule. Composes with domain-review skills.
- **[task-handoff-summaries](https://ribrewguy.github.io/agent-skills/skills/task-handoff-summaries/)**: three structured report formats (implementation summary before commit, worker handoff to orchestrator, closeout after completion). Hard rules against using the summary to mask incomplete work.
- **[cross-agent-review](https://ribrewguy.github.io/agent-skills/skills/cross-agent-review/)**: workflow for routine cross-vendor agent peer review (Claude reviews Codex's work; Codex reviews Claude's). The handoff package with self-assessment redacted, the cold-review discipline, the disagreement protocol.
- **[multi-agent-git-workflow](https://ribrewguy.github.io/agent-skills/skills/multi-agent-git-workflow/)**: git discipline for multi-agent work. Worktree-per-agent topology, orchestrator/worker roles, merge authority, acceptance/rejection rules, plus universal commit discipline (Conventional Commits, mandatory task ID, co-author line, UAT gate, no silent amends).
- **[branch-promotion-discipline](https://ribrewguy.github.io/agent-skills/skills/branch-promotion-discipline/)**: the layer above multi-agent-git-workflow. 3-tier `develop` to `uat` to `main` promotion, per-tier CI gate matrix, source-ref enforcement, hotfix flow with forward-merge, branch protection ruleset, pre-commit hook setup.
- **[throughline](https://ribrewguy.github.io/agent-skills/skills/throughline/)**: the lifecycle spine — requirements to architecture to task to implementation to commit to merge to closeout. Owns the Kickoff Declaration, the three completion phases and the source-of-truth ladder; dispatches everything else to the skill that owns it.
- **[isolated-stack-development](https://ribrewguy.github.io/agent-skills/skills/isolated-stack-development/)**: one isolated local Supabase stack per worktree, so parallel worktrees don't collide. Ships a `stack` tool and a PreToolUse guard alongside the skill; repos opt in with `.isolated-stack.json`.
- **[local-https](https://ribrewguy.github.io/agent-skills/skills/local-https/)**: TLS for every locally run server, with mkcert certs at `<project>-local`. Ships a `local-https` tool, a PreToolUse guard and a TLS proxy alongside the skill; repos opt in with `.local-https.json`.
- **[project-kickoff](https://ribrewguy.github.io/agent-skills/skills/project-kickoff/)**: the first hour of a project, every time: git, Beads with `bd init --skip-agents`, cass-memory, byte-identical `CLAUDE.md` and `AGENTS.md`, the documentation tree, a documentation checker and its pre-commit gate. Ships a `project-kickoff` tool with `--dry-run`; reruns and existing projects get a gap report, never an overwrite.

- **[jvm-quality](https://ribrewguy.github.io/agent-skills/skills/jvm-quality/)**: Shared JVM quality policy for tests, module coverage, runtime compatibility, exceptions and dependency vulnerability scanning.
- **[maven-practices](https://ribrewguy.github.io/agent-skills/skills/maven-practices/)**: Reproducible Maven builds and effective lifecycle enforcement across modules, profiles and test JVMs.
- **[java-practices](https://ribrewguy.github.io/agent-skills/skills/java-practices/)**: Bloch-inspired Java design: immutability, defensive boundaries, small APIs, value contracts and composition, alongside compiler, formatter and analyzer practices.
- **[kotlin-practices](https://ribrewguy.github.io/agent-skills/skills/kotlin-practices/)**: Kotlin JVM targets, ktlint, detekt, coverage and reliable Java interoperability.
- **[application-logging](https://ribrewguy.github.io/agent-skills/skills/application-logging/)**: what a server logs, at which level, in which shape. Two appenders (console for humans, OpenTelemetry for the pipeline), fields as arguments, a never-log denylist, exceptions logged once.
- **[opentelemetry](https://ribrewguy.github.io/agent-skills/skills/opentelemetry/)**: make a server application support OpenTelemetry and prove it. OTLP via `OTEL_*` variables, three span tiers, context propagation, default service metrics, log correlation, serverless flush, verification against a real collector.

Full catalog: **[Skills](https://ribrewguy.github.io/agent-skills/skills/)**.

## Repo layout

```
.claude-plugin/marketplace.json      # marketplace manifest
plugins/                             # canonical skill source (what AI tools load)
  rest-api-design/
    .claude-plugin/plugin.json
    skills/rest-api-design/
      SKILL.md                       # the skill itself
      evals/evals.json               # test cases + assertions
  structured-code-review/
    .claude-plugin/plugin.json
    skills/structured-code-review/
      SKILL.md
      evals/evals.json
  application-logging/
    .claude-plugin/plugin.json
    skills/application-logging/
      SKILL.md
      references/
      evals/evals.json
  opentelemetry/
    .claude-plugin/plugin.json
    skills/opentelemetry/
      SKILL.md
      references/
      assets/
      evals/evals.json
  project-kickoff/
    .claude-plugin/plugin.json
    scripts/project-kickoff           # the tool; lib/kickoff.py holds the logic
    skills/project-kickoff/
      SKILL.md
      references/
      assets/                         # check_docs.py, gate block, templates
      evals/evals.json
index.md, install/, concepts/, skills/   # GitHub Pages docs site
LICENSE                              # MIT
README.md                            # this file
```

## Contributing

See **[Skills → Contributing a new skill](https://ribrewguy.github.io/agent-skills/skills/#contributing-a-new-skill)**.

## License

[MIT](LICENSE).
