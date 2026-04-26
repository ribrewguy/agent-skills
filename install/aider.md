---
title: Aider
parent: Install
nav_order: 7
---

# Aider

Aider doesn't have a native skills system. It uses `CONVENTIONS.md` files loaded via the `--read` flag, or via a project-level `.aider.conf.yml`. The SKILL.md files in this collection work as Aider read-only context. They're plain markdown.

Make sure you've done the [one-time setup](./#symlink-based-install-everything-else) first (clone the repo, export `REPO`).

## Install via `.aider.conf.yml`

In any project where you want a skill active:

```bash
echo "read: $REPO/plugins/rest-api-design/skills/rest-api-design/SKILL.md" >> .aider.conf.yml
echo "read: $REPO/plugins/structured-code-review/skills/structured-code-review/SKILL.md" >> .aider.conf.yml
```

`$REPO` gets expanded by the shell here, so the value baked into `.aider.conf.yml` will be the absolute path to each SKILL.md. No further substitution needed when Aider reads the config.

Aider then includes the skill content as read-only context on every prompt in that project.

## Install via CLI flag (one-off)

```bash
aider --read "$REPO/plugins/rest-api-design/skills/rest-api-design/SKILL.md" \
      --read "$REPO/plugins/structured-code-review/skills/structured-code-review/SKILL.md"
```

## Install at user level

`.aider.conf.yml` is read from git root, current working directory, and home directory. To make a skill globally available across all your Aider sessions:

```bash
echo "read: $REPO/plugins/rest-api-design/skills/rest-api-design/SKILL.md" >> ~/.aider.conf.yml
```

## Notes

The skills include sections that target AI tools generally (e.g., the "Don't cite this skill in the output" section in `structured-code-review`). Aider treats the entire SKILL.md as read-only context, so it sees these instructions and follows them.

## Docs

- [Aider Configuration](https://aider.chat/docs/config.html)
