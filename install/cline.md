---
title: Cline
parent: Install
nav_order: 5
---

# Cline

Cline (the VS Code extension) reads `~/.cline/skills/` (user-level) and `.cline/skills/` (workspace-level). Skills follow the same SKILL.md format as Claude Code and Gemini CLI.

Make sure you've done the [one-time setup](./#symlink-based-install-everything-else) first (clone the repo, export `REPO`).

## Install

```bash
mkdir -p ~/.cline/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.cline/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" \
      ~/.cline/skills/structured-code-review
```

Or, via the [canonical-home pattern](../concepts/canonical-home):

```bash
mkdir -p ~/.agents/skills ~/.cline/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" ~/.agents/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" ~/.agents/skills/structured-code-review
ln -s ../../.agents/skills/rest-api-design ~/.cline/skills/rest-api-design
ln -s ../../.agents/skills/structured-code-review ~/.cline/skills/structured-code-review
```

## Notes

Cline keeps skills under 5k tokens in the active context window and lazy-loads anything under a `docs/` subdirectory of the skill. This matches the progressive-disclosure pattern Claude Code uses — the metadata is always loaded, but the full body only activates when the skill matches the task.

## Verifying

Open Cline in VS Code and drop a prompt that should trigger one of the skills (see [Install → Verifying it works](./#verifying-it-works)).

## Docs

- [Cline Skills documentation](https://docs.cline.bot/customization/skills)
