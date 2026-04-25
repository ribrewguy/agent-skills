---
title: Install
nav_order: 2
has_children: true
permalink: /install/
---

# Install

Pick the section that matches your tool. The plugin marketplace path (Claude Code only) needs no setup. The symlink-based installs share a one-time setup so they can compose cleanly across multiple AI tools.

## Plugin marketplace (Claude Code, easiest)

Inside a Claude Code session:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
/plugin install structured-code-review@ribrewguy-skills
```

Run `/plugin marketplace update ribrewguy-skills` to pull updates. Auto-update on session start is off by default for third-party marketplaces; flip it on in the `/plugin` UI if you want it.

Once installed, each skill fires automatically when a task matches its description, or you can invoke it explicitly with `/<skill-name>`.

## Symlink-based install (everything else)

The remaining tools want a directory or file to point at. Clone the repo wherever you keep dev tooling, then export `REPO` so the snippets in the per-tool pages resolve. (Add the export to your shell rc if you want it persistent.)

```bash
# wherever you keep cloned repos — adjust to taste
git clone git@github.com:ribrewguy/agent-skills.git
export REPO="$(pwd)/agent-skills"
```

After that, every `ln -s "$REPO/..."` snippet in the per-tool pages can be pasted as-is.

{: .tip }
If you use more than one AI tool, set up the [canonical-home pattern](../concepts/canonical-home) first. GitHub Copilot CLI reads `~/.agents/skills/` natively, and the others get pointed at it with one line each — `git pull` then updates every tool from a single source.

## Per-tool pages

- [Claude Code](claude-code) — plugin marketplace OR symlink
- [Gemini CLI](gemini-cli) — `~/.gemini/skills/`
- [OpenAI Codex CLI](codex-cli) — `~/.codex/skills/`
- [GitHub Copilot CLI](copilot-cli) — reads `~/.agents/skills/` natively
- [Cline](cline) — `~/.cline/skills/`
- [Cursor](cursor) — `.cursor/rules/` reference (no native skills system)
- [Aider](aider) — `CONVENTIONS.md` via `--read` or `.aider.conf.yml`

## Verifying it works

In a fresh session of whichever tool you installed it in, drop a prompt that should trigger one of the skills:

> "Review this endpoint: `POST /api/createOrder` returning `200 { order_id: '...' }`. What's wrong?"

If `rest-api-design` is loaded, the output will catch the verb in the URL, the wrong success status, the missing `Location` header, the snake_case response key. If `structured-code-review` is also loaded, those findings come back severity-tagged in a `Findings:`-prefixed preamble.

Without either skill, you'll get a looser answer that misses some of these or treats them all with equal weight.
