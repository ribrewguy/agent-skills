---
title: throughline
parent: Skills
nav_order: 7
---

# throughline

The lifecycle spine for tracked engineering work: **requirements → architecture → task → implementation → commit → merge → closeout**, with an auditable artifact at every hand-off.

Throughline is a *dispatcher*. It owns the ceremony that has no other home — the Kickoff Declaration, the three completion phases, the source-of-truth ladder — and hands every other concern to the skill that owns it. It deliberately does not restate those skills' contents, because a second copy is a second thing to drift.

## What makes this skill distinct

- **A design doc is work.** The kickoff trigger fires before the first *authored file*, not the first code edit. Brainstorming output counts. This clause exists because spec files kept being born in the main checkout while the trigger read as code-only.
- **Scaffold centrally, then move.** For epic work, the task scaffolding is committed to the trunk from the main checkout *first*; everything after that — including the design docs themselves — is committed on the worktree branch. The main checkout is for tracker commands and `git worktree add`, never an authoring surface.
- **Gates are not acceptance.** Nothing merges to the trunk without the user's explicit yes. Passing CI, approving the task at kickoff, and acknowledging a summary are each explicitly not acceptance. The implementation summary ends at "ready to merge, awaiting your acceptance" and stops there.
- **Cleanup belongs to the same close-out as the merge.** The merge already carried the user's acceptance, so nothing is left to hold the environment for. Worktree removal precedes branch deletion, because git refuses to delete a branch a worktree has checked out.
- **Lightweight is the user's call.** If a task looks trivial, flag it and ask. The agent never downgrades the process unilaterally.
- **Escalate, never resolve.** A conflict between ladder layers stops the work. Requirements, architecture and feature specs are read-only without explicit permission.

## What it delegates

| Concern | Owner |
|---|---|
| Branches, worktrees, commits, merge authority, user acceptance | [multi-agent-git-workflow](multi-agent-git-workflow) |
| Tier promotion (`develop`/`uat`/`main`), hotfixes | [branch-promotion-discipline](branch-promotion-discipline) |
| Implementation / worker-handoff / closeout summary shapes | [task-handoff-summaries](task-handoff-summaries) |
| Code review scope and response format | [structured-code-review](structured-code-review) |
| Cross-vendor agent peer review | [cross-agent-review](cross-agent-review) |
| Isolated local stack mechanics (ports, config, env audit, teardown) | [isolated-stack-development](isolated-stack-development) |

## What it bundles

Policies with no other home, as `references/`: feature governance (discovery and PRD alignment), procedural memory, MCP↔UI parity, and Beads protected-branch mechanics.

## Adapters

Tracker-agnostic by default, with adapters for [Beads](https://github.com/gastownhall/beads) (claim flow, branch/commit id format, parent-child state) and [BeadRoad](https://github.com/ribrewguy/beadroad) token accounting. The Kickoff Declaration *begins* with the token estimate, the Phase A evidence block carries the recorded segment(s), and the closeout summary reports initial estimate vs actual — a backfill after a failed recording is an *estimated actual*, labeled as an estimate, never promoted to measured. Estimate drift is a reported metric, not a mistake to hide.
