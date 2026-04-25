---
title: Dependency tiers
parent: Concepts
nav_order: 2
---

# Dependency tiers

Every skill in this collection declares its dependencies in three tiers. Conflating them — calling everything "uses Beads" — would scare off readers without Beads or hide where Beads is actually load-bearing. Each skill's body has a "Tooling and dependencies" section that maps explicitly to these tiers.

## Required

The skill is meaningless without these. If you don't have them, don't use the skill.

Examples:
- `multi-agent-git-workflow` requires Git and Git worktrees — the entire skill is built on worktree topology.
- A future testing skill might require a test runner of some kind.

The bar for "Required" is high — most skills should have an empty Required tier.

## Strongly recommended

The skill works without these but loses 70% of its value, or several sections are inert. The skill names a fallback for the missing-this-tool case.

Examples:
- `structured-code-review` strongly recommends a task tracker — without one, the `Review Scope:` field is `No task identified` for every review.
- `multi-agent-git-workflow` strongly recommends a code-hosting platform with branch protection — without it, the 3-tier promotion gates are advisory rather than enforced.

If the strongly-recommended dependency is generic (any task tracker, any CI system), the skill body lists examples to make the abstraction concrete.

## Optional adapters

These are *one* concrete example of how to satisfy the strongly-recommended tier. The skill body has a dedicated "Adapter: <tool>" section showing the literal commands and paths.

Examples:
- `structured-code-review` has a Beads adapter section that maps `Review Scope: Task <id>` → `Review Scope: Bead rp-c74` and shows `bd show <id>` for source-of-truth lookups.
- A future skill might have GitHub Issues, Linear, Jira adapters all under the same "task tracker" abstraction.

Readers using a different tool than the adapter substitute their tool's vocabulary; the rest of the skill stays the same.

## Composes-with

A separate axis from the dependency tiers: **composes-with** declares which other skills in this collection naturally pair with this one. Listed at the bottom of every skill's "Tooling and dependencies" section as cross-references with concrete URLs.

Example: `structured-code-review` composes with `rest-api-design` (the format skill structures the output; the domain skill identifies the violations).

These cross-references are themselves a dependency story — they say "this skill expects to be used alongside that skill, and assumes its vocabulary."

## Why three tiers and not two

The temptation is to collapse "strongly recommended" and "optional adapter" into one — they're both not-required. But they're answering different questions:

- *Strongly recommended* answers: "What kind of tool do I need at this slot?" (a task tracker, a code-hosting platform with branch protection, etc.)
- *Optional adapter* answers: "Here's how the skill speaks to one specific concrete instance of that tool." (Beads' CLI looks like this; GitHub Issues' looks like that; Linear looks like the other thing.)

Keeping them separate lets the skill be portable (the abstraction stays in the body) while still being concrete (an adapter shows the actual commands).

## Reading order in a skill body

Every skill follows this order in its "Tooling and dependencies" section:

1. **Required** — non-negotiable, named first because its presence/absence is a deal-breaker
2. **Strongly recommended** — what kind of tool fits this slot, with examples
3. **Optional** — minor convenience tools (linters, code formatters, etc.)
4. **Composes with** — cross-references to neighbor skills

Then in the skill body proper, an **Adapter** section appears for each concrete tool worth illustrating with literal commands.

## See also

- [Composition over absorption](composition) — the principle behind why skills stay narrow and rely on neighbors.
