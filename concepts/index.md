---
title: Concepts
nav_order: 4
has_children: true
permalink: /concepts/
---

# Concepts

A handful of cross-cutting ideas show up across every skill in this collection. They aren't part of any single skill's body, but understanding them makes the skills compose cleanly.

- **[Canonical-home pattern](canonical-home)**: keep one `~/.agents/skills/` directory and let every AI tool symlink into it. One `git pull` updates every tool from a single source.
- **[Dependency tiers](dependency-tiers)**: every skill declares its dependencies in three tiers (required, strongly recommended, optional adapter). Don't conflate them.
- **[Severity ladder](severity-ladder)**: `High` / `Medium` / `Low` (with optional `Critical` for production-blockers) is the shared vocabulary across review and audit outputs in this collection. Tagging is what makes triage possible.
- **[Composition over absorption](composition)**: skills stay strictly in their lane and name neighbor skills for adjacent concerns. You get a small, sharp library where each skill does one thing well.

These are the principles behind why the skills look the way they do. If you're authoring a new skill for the collection, this is the design lens.
