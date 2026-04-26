---
title: GitHub Copilot CLI
parent: Install
nav_order: 4
---

# GitHub Copilot CLI

Copilot CLI reads `~/.agents/skills/` and `~/.claude/skills/` natively. If you've already set up either of those for another tool (especially via the [canonical-home pattern](../concepts/canonical-home)), Copilot picks up the same skills without an additional symlink.

If you want an explicit Copilot-specific home, that works too.

Make sure you've done the [one-time setup](./#symlink-based-install-everything-else) first (clone the repo, export `REPO`).

## Install (canonical-home, recommended)

If you've followed the canonical-home pattern, Copilot CLI is already covered. Verify:

```bash
ls ~/.agents/skills/   # should list the skills you've installed
```

Copilot CLI will discover them automatically.

## Install (explicit Copilot home)

```bash
mkdir -p ~/.copilot/skills
ln -s "$REPO/plugins/rest-api-design/skills/rest-api-design" \
      ~/.copilot/skills/rest-api-design
ln -s "$REPO/plugins/structured-code-review/skills/structured-code-review" \
      ~/.copilot/skills/structured-code-review
```

## `gh skill` (registry-based, April 2026+)

GitHub introduced a `gh skill` command for registry-based install/publish (analogous to `npm` or `pip`). Check the Copilot CLI docs for the latest syntax. The registry path may eventually replace symlinks for hosted distributions.

## Verifying

In a fresh `gh copilot` session, drop a prompt that should trigger one of the skills (see [Install Verifying it works](./#verifying-it-works)).

## Docs

- [Adding agent skills for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)
