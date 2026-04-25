---
title: Claude Code
parent: Install
nav_order: 1
---

# Claude Code

Two ways to install: the plugin marketplace (recommended), or a manual symlink to the repo (if you prefer `git pull`-driven updates).

## Plugin marketplace (recommended)

Inside a Claude Code session:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
/plugin install structured-code-review@ribrewguy-skills
```

To pull updates later:

```
/plugin marketplace update ribrewguy-skills
```

Auto-update on session start is off by default for third-party marketplaces; flip it on in the `/plugin` UI if you want it.

## Manual symlink (alternative)

Skip the plugin layer and point Claude Code at the cloned repo directly. Updates come via `git pull` — no `/plugin update` dance.

Make sure you've done the [one-time setup](./#symlink-based-install-everything-else) first (clone the repo, export `REPO`).

```bash
mkdir -p ~/.claude/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.claude/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" \
      ~/.claude/skills/structured-code-review
```

Or, with the [canonical-home pattern](../concepts/canonical-home):

```bash
mkdir -p ~/.agents/skills ~/.claude/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" ~/.agents/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" ~/.agents/skills/structured-code-review
ln -s ../../.agents/skills/rest-api-design ~/.claude/skills/rest-api-design
ln -s ../../.agents/skills/structured-code-review ~/.claude/skills/structured-code-review
```

## Verifying

Run `/help` in Claude Code — installed skills appear under Skills. Or just drop a prompt that should trigger one of the skills (see [Install → Verifying it works](./#verifying-it-works)).

## Updating

- **Plugin marketplace install:** `/plugin marketplace update ribrewguy-skills`
- **Manual symlink install:** `git pull` in the cloned repo. Claude Code's filesystem watcher picks up the changes mid-session.

## Uninstalling

- **Plugin install:** `/plugin uninstall <skill-name>` then optionally `/plugin marketplace remove ribrewguy-skills`
- **Symlink install:** `rm ~/.claude/skills/<skill-name>` (and the canonical-home link if used)

## Docs

- [Claude Code skills documentation](https://code.claude.com/docs/en/skills)
- [Claude Code plugins documentation](https://code.claude.com/docs/en/plugins)
