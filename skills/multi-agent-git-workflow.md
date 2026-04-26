---
title: multi-agent-git-workflow
parent: Skills
nav_order: 5
---

# multi-agent-git-workflow

Git workflow discipline for multi-agent work. Branch hierarchy, worktree-per-agent topology, orchestrator vs. worker roles, merge authority, acceptance/rejection rules, branch publication policy, close-out. Combined with universal commit discipline (Conventional Commits, mandatory task ID, co-author line, UAT gate ceremony, no silent amends).

Two concerns covered in one skill because they're the same git-author moment: how branches and worktrees are arranged so multiple agents don't trip over each other, and how every commit (single- or multi-agent) is shaped so the audit trail is legible.

## What makes this skill distinct

- **Worktrees mandatory for multi-agent work.** One worktree per agent, never two agents in the same checkout. The whole topology is built on this, and skipping it produces silent corruption that's expensive to unwind.
- **Workers MUST NOT merge their own branches.** Only the orchestrator merges accepted worker branches into the coordinated integration target. Same reason any code-review system has authors-not-merging-their-own-PRs: integration is a coordinated decision, not a per-worker one.
- **Orchestrator MUST NOT silently fix worker-owned defects.** When the orchestrator can clearly see "the worker made a small mistake; I could just fix it on the integration branch," that's where the boundary breaks. Either reassign ownership explicitly, create a new task, or return the branch with rejection notes.
- **Mandatory rejection conditions.** Failing tests / failing required gates / merge conflicts / divergence from task design / divergence from architecture or PRD scope. Any one of these is a *required* rejection, not a judgment call.
- **Local-by-default branches.** Worker `feature/*` branches stay local unless the orchestrator needs remote access, CI is required on that branch, or the user requires remote visibility. Protects a clean remote branch list and keeps "ready for review" meaning something.
- **Conventional Commits + mandatory task ID + co-author line on every commit.** No exceptions besides merge commits. The task ID anchors the commit to the tracker; the co-author line acknowledges AI assistance.
- **No silent amends.** A failed pre-commit hook means the commit didn't happen. The working tree is unchanged. `--amend` would modify the *previous* commit, which on an unpublished commit can lose work and on a published commit breaks anyone who fetched it. Fix the issue, re-stage, create a NEW commit.
- **UAT gate is a per-commit ceremony, distinct from a UAT branch.** If a change affects externally visible behavior, ask the user about UAT before commit. This is separate from the long-lived `uat` branch (which is in the planned `branch-promotion-discipline` skill).

## What it covers

- **Branch hierarchy**: `main`, `develop`, `feature/<task_id>_<short_name>`, `integration/<parent_task_id>_<short_name>`. The 3-tier extension (`main` ← `uat` ← `develop`) is deferred to `branch-promotion-discipline` so the layers compose cleanly.
- **Worktree discipline**: one task to one feature branch to one worktree, no exceptions for multi-agent work.
- **Multi-agent roles**: exactly one orchestrator per workload; default is the top-level agent unless the user reassigns. Workers assume they are not the orchestrator unless explicitly told.
- **Merge authority**: workers don't merge into integration / develop / main; only the orchestrator does. Single-agent work is its own integrator.
- **Acceptance and rejection**: what the orchestrator does at acceptance (attempt the merge, run integrated gates, verify alignment with the design), the mandatory rejection conditions, and the rejection-notes discipline.
- **Branch publication policy**: local-by-default; published only when the orchestrator needs remote access, CI requires it, or the user requires remote visibility.
- **Conventional Commits + Task ID + Co-Author**: required on every commit; multi-paragraph body explaining what AND why.
- **UAT gate ceremony**: per-commit human approval for externally-visible behavior changes.
- **Push/merge discipline**: work isn't complete until required pushes succeed; never merge `feature/*` directly to `main`.
- **Close-out rules**: worker close-out ends at orchestrator acceptance, not at `develop` merge; orchestrator close-out for an epic ends after integration to `develop` and branch cleanup.
- **Beads adapter**: branch and bead-ID format, atomic claim flow (`bd ready` → `bd update --claim` → `bd close`), parent/child bead topology for multi-agent epics.

## Quick install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install multi-agent-git-workflow@ribrewguy-skills
```

For other tools, see [Install](../install).

## Composes with

- **[task-handoff-summaries](task-handoff-summaries)**: the worker handoff and orchestrator close-out summaries reference this skill's role and branch vocabulary directly. The two are designed to be used together.
- **[structured-code-review](structured-code-review)**: when an orchestrator reviews a worker's branch (or a PR is reviewed before a develop merge), the review uses that format. Same format for rejection notes.
- **[cross-agent-review](cross-agent-review)**: high-stakes worker branches benefit from cross-vendor review before orchestrator acceptance.
- **(planned)** `branch-promotion-discipline`: the layer above this one. 3-tier promotion (`develop` to `uat` to `main`), UAT branch as a long-lived environment, CI gate matrix, source-ref enforcement, pre-commit hook setup.

## Tooling and dependencies

- **Required:** Git with worktrees support. The whole multi-agent topology is built on worktrees; you can't safely run two agents in the same checkout.
- **Required:** A task tracker that issues task IDs the branches and commits reference. Examples: [Beads](https://github.com/gastownhall/beads), GitHub Issues, Linear, Jira, Shortcut. Single-agent work can run with no tracker if commits reference intent some other way; multi-agent topology depends on stable task IDs to anchor `feature/<id>_<short_name>` branches.
- **Strongly recommended:** A code-hosting platform with PR review (GitHub / GitLab / Bitbucket). Acceptance into integration / develop normally happens via a published branch + PR, not just a local merge.
- **Strongly recommended:** A way to invoke other agents from within an agent's session if the topology is implemented with N independent AI agents (`claude --print`, `codex exec`, etc.). The skill is also valid for human-orchestrator + AI-worker topologies; the role definitions don't change.
- **Optional:** [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) tooling (`commitlint`, `cz-cli`, etc.). The format is required either way; tooling helps enforce it.

## Source of truth

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/multi-agent-git-workflow/skills/multi-agent-git-workflow/SKILL.md)**: the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/multi-agent-git-workflow/skills/multi-agent-git-workflow/evals/evals.json)**: the four test cases used to verify the skill's behavior.

## Eval results

Iteration-1 benchmark: **100% pass rate with-skill vs. 73% baseline** (+27pp delta) across four cases. Per-eval pattern: largest delta on the orchestrator-acceptance-flow eval (+50pp) and the conventional-commits eval (+25pp); smaller delta on the rejection-with-explicit-notes eval (the prompt's own scenario was specific enough that even baseline produced a structured rejection, a non-discriminating eval to revisit in iteration-2).

| Eval | What it probes |
|---|---|
| `multi-agent-orchestrator-acceptance-flow` | Does the skill produce the right orchestrator-side flow at acceptance? Attempts merge, runs integrated gates, verifies alignment with design; does NOT silently fix worker-owned defects. |
| `write-commit-message-with-task-id-and-coauthor` | Does the commit subject use Conventional Commits format (`<type>(<scope>): <description>`), reference the task ID, and include the co-author line? Does the body explain *why* and not just *what*? |
| `orchestrator-rejection-with-explicit-notes` | When required gates fail and the design diverges, does the orchestrator produce explicit rejection notes (not silent fixes), tag failures by category, and tell the worker to fix and re-hand-off? |
| `worker-close-out-stays-in-lane` | Does the worker correctly hand off to the orchestrator (without merging into integration / develop / main themselves), keep the bead in `in_progress`, and avoid claiming work outside their assigned slice? |

Eval transcripts and benchmark JSON live alongside the skill source.

## Invocation examples

- "Set up the multi-agent topology for this epic, 3 workers."
- "I'm a worker, I just finished. What's the close-out flow?"
- "The orchestrator should review my branch. What's the handoff?"
- "Write the commit message for this change."
- "Reject this worker branch. The gates are failing."
- "Should this commit need a UAT gate before I push?"
- "How do I clean up after merge?"

## Adapter: Beads

If the project uses [Beads](https://github.com/gastownhall/beads) as its task tracker:

- **Feature branches:** `feature/<bead_id>_<short_name>`, e.g., `feature/proj-42_staging-branch`
- **Integration branches:** `integration/<parent_bead_id>_<short_name>`, e.g., `integration/proj-42_staging-bringup`
- **Commit subjects:** Conventional Commits with `Refs: <bead_id>` in the body, or the bead ID inline in the subject
- **Atomic claim flow:** `bd ready` → `bd show <id>` → `bd update <id> --claim` → implement → `bd update <id> --notes "..."` → `bd close <id>` (after orchestrator acceptance, not before)
- **Parent/child bead topology:** parent bead for the coordinated workload assigned to the orchestrator; one child bead per worker-owned implementation slice. Workers don't close their own beads. The orchestrator closes accepted child beads after merging into the integration target.

Other trackers work the same way: substitute their ID format and lifecycle commands. The topology (parent task with N child tasks, one per worker) is identical regardless of tracker.

## What this skill explicitly does NOT cover

The 3-tier promotion (`develop` to `uat` to `main`), UAT branch as a long-lived environment, CI gate matrix, source-ref enforcement, and pre-commit hook setup are deferred to the planned **branch-promotion-discipline** skill. Skills that need that vocabulary should compose with both rather than have multi-agent-git-workflow re-derive it.
