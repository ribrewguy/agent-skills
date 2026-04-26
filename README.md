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
index.md, install/, concepts/, skills/   # GitHub Pages docs site
LICENSE                              # MIT
README.md                            # this file
```

## Contributing

See **[Skills → Contributing a new skill](https://ribrewguy.github.io/agent-skills/skills/#contributing-a-new-skill)**.

## License

[MIT](LICENSE).
