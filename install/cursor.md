---
title: Cursor
parent: Install
nav_order: 6
---

# Cursor

Cursor doesn't have a native skills system as of April 2026. It uses `.cursor/rules/` with `.mdc` files for project-level rules. To use these skills in Cursor, reference the SKILL.md from a Cursor rule file or paste the relevant sections directly.

## Reference from a Cursor rule file

Replace `<path-to-cloned-repo>` with your actual clone path — Cursor rule files don't get shell variable expansion.

```markdown
<!-- .cursor/rules/rest-api.mdc -->
# REST API conventions

When designing or reviewing HTTP REST APIs, apply the guidance in
<path-to-cloned-repo>/plugins/rest-api-design/skills/rest-api-design/SKILL.md.

Key rules: state transitions use PATCH, error codes name the domain
reason (not HTTP status), flat error envelopes, pagination uses
cursor with default limit 20 and max 100. Full details in the file
above.
```

```markdown
<!-- .cursor/rules/code-review.mdc -->
# Code review format

When reviewing PRs, apply the format in
<path-to-cloned-repo>/plugins/structured-code-review/skills/structured-code-review/SKILL.md.

Output starts with `Findings:`, includes an eight-field preamble
(Review Scope / Process Context / Execution Context / Integration
Target / Design / Architecture / Feature Spec / PRD references),
and tags every finding with severity (High / Medium / Low).
```

## Or inline the skill content

Cursor's `.mdc` files are markdown — you can paste the relevant sections of the SKILL.md directly into a rule file. Trade-off: easier to use, but updates won't flow from `git pull`.

## Notes

Cursor's rule system was overhauled in 2025 — the legacy `.cursorrules` single-file format is being phased out in favor of `.cursor/rules/*.mdc`. Use the new format for any new project.

## Docs

- [Cursor Rules for AI](https://docs.cursor.com/context/rules-for-ai)
