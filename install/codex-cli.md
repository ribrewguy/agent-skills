---
title: OpenAI Codex CLI
parent: Install
nav_order: 3
---

# OpenAI Codex CLI

Codex CLI looks for `SKILL.md` files under `~/.codex/skills/`. The path is configurable in `~/.codex/config.toml` if you want it elsewhere.

Make sure you've done the [one-time setup](./#symlink-based-install-everything-else) first (clone the repo, export `REPO`).

## Install

```bash
mkdir -p ~/.codex/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.codex/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" \
      ~/.codex/skills/structured-code-review
```

Or, via the [canonical-home pattern](../concepts/canonical-home):

```bash
mkdir -p ~/.agents/skills ~/.codex/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" ~/.agents/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" ~/.agents/skills/structured-code-review
ln -s ../../.agents/skills/rest-api-design ~/.codex/skills/rest-api-design
ln -s ../../.agents/skills/structured-code-review ~/.codex/skills/structured-code-review
```

## Verifying

In a fresh Codex session (`codex` or `codex exec`), drop a prompt that should trigger one of the skills (see [Install Verifying it works](./#verifying-it-works)).

## Docs

- [OpenAI Codex Agent Skills](https://developers.openai.com/codex/skills)
