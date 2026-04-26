---
title: Gemini CLI
parent: Install
nav_order: 2
---

# Gemini CLI

Gemini CLI has a native skills system. User-level skills live at `~/.gemini/skills/`. Workspace-level skills live at `.gemini/skills/` or `.agents/skills/` (in the project root).

Make sure you've done the [one-time setup](./#symlink-based-install-everything-else) first (clone the repo, export `REPO`).

## Install

```bash
mkdir -p ~/.gemini/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.gemini/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" \
      ~/.gemini/skills/structured-code-review
```

Or, via the [canonical-home pattern](../concepts/canonical-home):

```bash
mkdir -p ~/.agents/skills ~/.gemini/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" ~/.agents/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" ~/.agents/skills/structured-code-review
ln -s ../../.agents/skills/rest-api-design ~/.gemini/skills/rest-api-design
ln -s ../../.agents/skills/structured-code-review ~/.gemini/skills/structured-code-review
```

## How Gemini loads skills

At session start, Gemini loads skill metadata (frontmatter only, not the full body). The full SKILL.md body is activated on demand via the `activate_skill` tool when a task matches the skill's description.

Same progressive-disclosure pattern Claude Code uses. The skill body doesn't bloat the system prompt unless it's actually relevant.

## Verifying

In a fresh Gemini CLI session, ask Gemini to list available skills, or drop a prompt that should trigger one (see [Install Verifying it works](./#verifying-it-works)).

## Docs

- [Gemini CLI Agent Skills](https://geminicli.com/docs/cli/skills/)
