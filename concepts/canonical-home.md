---
title: Canonical-home pattern
parent: Concepts
nav_order: 1
---

# Canonical-home pattern

If you use more than one AI coding tool, the canonical-home pattern lets all of them share the same skill files via symlinks. One `git pull` propagates updates to every tool, and adding a new tool is a one-line symlink — no re-cloning, no copying, no version drift.

## The pattern

Two-hop symlink:

1. **Canonical home** at `~/.agents/skills/<skill-name>` → the cloned repo's plugin directory
2. **Tool-specific link** at `~/.<tool>/skills/<skill-name>` → `../../.agents/skills/<skill-name>` (relative)

GitHub Copilot CLI already reads `~/.agents/skills/` natively, so for Copilot the canonical home *is* the install — no second symlink needed.

## Setup

```bash
# After cloning the repo and exporting REPO (see Install):
mkdir -p ~/.agents/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" ~/.agents/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" ~/.agents/skills/structured-code-review
```

Then for each tool you use:

```bash
mkdir -p ~/.claude/skills ~/.gemini/skills ~/.codex/skills ~/.cline/skills

ln -s ../../.agents/skills/rest-api-design ~/.claude/skills/rest-api-design
ln -s ../../.agents/skills/rest-api-design ~/.gemini/skills/rest-api-design
ln -s ../../.agents/skills/rest-api-design ~/.codex/skills/rest-api-design
ln -s ../../.agents/skills/rest-api-design ~/.cline/skills/rest-api-design

# Repeat for structured-code-review
ln -s ../../.agents/skills/structured-code-review ~/.claude/skills/structured-code-review
# ...
```

## Why relative symlinks

The tool-specific links use `../../.agents/skills/<name>` rather than absolute paths. That means the whole `~/` tree can move (new user, machine migration, dotfile sync) without breaking the symlink chain. Only the canonical home at `~/.agents/skills/<name>` is an absolute symlink to the repo, and it's the only one you'd update if you cloned the repo elsewhere.

## Why this scales

When you author or install a new skill (in this repo or another):

1. Add one symlink under `~/.agents/skills/`
2. Add one tool-specific link per AI tool you use
3. Done — every tool sees it on next session

When you want to remove a skill from circulation:

1. Delete the symlink under `~/.agents/skills/<name>` (orphans the per-tool links — they harmlessly point at nothing)
2. Optionally clean up the per-tool links

When you `git pull` and the skill's content changed:

- Every tool sees the updated content the next time it loads the skill. No reinstall, no `update` command, no version drift across tools.

## Limitations

- This pattern works with tools that read local skill files (Claude Code, Gemini CLI, Codex CLI, Copilot CLI, Cline). It doesn't apply to tools that use a registry-based install (none of the major tools as of April 2026, but Copilot CLI's `gh skill` registry is coming).
- It doesn't apply to tools without a native skills system — Cursor and Aider, for instance, embed the skill content via rule-file references rather than symlinks.

## See also

- [Install](../install) — per-tool install instructions, all of which optionally use this pattern.
