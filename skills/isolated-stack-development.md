---
title: isolated-stack-development
parent: Skills
nav_order: 8
---

# isolated-stack-development

One isolated local stack per worktree for Supabase-backed repos, so parallel worktree development doesn't collide on the shared database. The mechanism: a derived `project_id`, ports discovered free at allocation time, a copied-env audit for shared-system pointers, and an order-critical teardown.

This is the collection's first plugin that is more than prose: it ships a **tool**, a **hook**, and the skill together, because the failure it targets is a *discovery* failure — the agent that boots the shared stack from a worktree didn't decide to read a runbook about isolation; it thought the topic was "run the app". Reading is opt-in; acting is not.

## What makes this skill distinct

- **Allocation is derived, never registered.** `project_id` comes from `<stackPrefix>-<owner>`; ports come from `docker ps` + `lsof` at the moment of allocation. There is no registry file, and the skill deliberately names no port numbers — a recorded list is a second source of truth that drifts.
- **Enumerate port keys, never recall them.** The config's port keys are grepped from the file, because the one you forget (`smtp_port`, `pop3_port`) still binds a shared port — and a collision rolls the whole boot back *after applying every migration*.
- **The copied-env audit.** A fresh worktree's env files are copied from the main checkout, and every copied value starts out pointed at the shared stack. The dangerous ones don't fail — requests land on the shared system and succeed there.
- **Teardown order is load-bearing.** Clear `--skip-worktree` *before* the checkout (with the bit set, the checkout silently no-ops and the isolation config survives into a merge). `supabase stop` resolves its config from the cwd — from the wrong directory it stops the shared stack for everyone.
- **Teeth only where damage is irreversible.** The PreToolUse guard blocks a `db reset` aimed at a stack the current directory doesn't own, or at the shared stack while isolated stacks are live; everything recoverable gets injected context instead. An over-blocking hook is the kind people disable.

## What ships in the plugin

| Piece | What it does |
|---|---|
| `SKILL.md` | The portable mechanism: hard rules, ports, stand-up, env audit, migrations/seeds, teardown, footguns. |
| `scripts/stack` | `up` / `status` / `down` / `doctor`, with `--dry-run` on the destructive paths and same-invocation ownership assertions. |
| `scripts/guard.sh` + `hooks/hooks.json` | The PreToolUse guard on stack-affecting Bash commands. Silent in repos without a declaration. |
| `references/adapters/` | nuxt, node, vite, spring — how each app type wires env, starts, and health-checks against an isolated stack. |

## The repo declaration

A repo opts in with a tracked `.isolated-stack.json` (stack prefix, config path, apps with their adapters). Data, not logic — it cannot go stale-but-plausible, and a repo without one is out of scope for both the tool and the hook.

## What it delegates

| Concern | Owner |
|---|---|
| Worktree location, run-commands-from-the-worktree, cleanup ordering | [multi-agent-git-workflow](multi-agent-git-workflow) |
| When isolation is stood up (kickoff) and torn down (closeout) | [throughline](throughline) |

## Coverage limits

Claude Code gets all three layers. Other agents (Codex etc.) get the skill and the tool via symlinks but not the hook — hooks are Claude Code only. The floor rises substantially; the mistake does not become impossible.
