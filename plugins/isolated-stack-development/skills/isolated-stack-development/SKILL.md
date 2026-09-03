---
name: isolated-stack-development
description: "Use when starting a dev server, booting or resetting a local Supabase stack (supabase start, supabase db reset), running migrations, seeding or provisioning a database, or wiring env files in a repo that has multiple git worktrees or a .isolated-stack.json — even when the request is just 'run the app' or 'start it so I can test my change'. One isolated stack per worktree: derived project_id, ports discovered at allocation time, copied-env audit for shared-system pointers, order-critical teardown. Symptoms: a dev server from a worktree pointed at the shared stack, supabase stop killing the shared stack for everyone, a seed step landing in the shared database, login 401s from a Secure cookie on http, a stack boot that rolls all the way back after applying every migration."
---

# Isolated Stack Development

## Overview

Parallel worktrees collide on one thing: the local backend stack. Two checkouts
of a Supabase-backed repo that share one database, one auth server, and one set
of ports cannot be developed or tested independently — a migration applied for
one branch corrupts the other's assumptions silently.

The mechanism: **every worktree that needs backend work gets its own stack** —
its own `project_id`, its own ports, its own volumes — stood up at kickoff and
torn down at closeout. The long-lived **shared stack** (the one the main
checkout runs, at the stack's default ports) stays at trunk parity always.

A repo opts in with a tracked `.isolated-stack.json` (see below). No file means
this skill's tooling is out of scope for that repo — say so rather than
improvising isolation.

**Prefer the shipped tool** over hand-rolling the steps:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/stack" up        # allocate + start an isolated stack for this worktree
"${CLAUDE_PLUGIN_ROOT}/scripts/stack" status    # what is running, who owns it
"${CLAUDE_PLUGIN_ROOT}/scripts/stack" down      # order-critical teardown (supports --dry-run)
"${CLAUDE_PLUGIN_ROOT}/scripts/stack" doctor    # orphaned stacks, leaked volumes, dirty config
```

The manual mechanism below is what the tool automates; read it so you can
verify what the tool did and recover when it can't run.

## Hard rules

1. **Never touch the shared stack.** A long-lived shared stack exists; never
   stop it, never point an isolated run at its ports, never reuse its
   `project_id`. Its lifecycle belongs to the human, not to any task.
2. **Never commit the isolation config.** The stack config file is tracked;
   isolation edits it. Set `git update-index --skip-worktree` on it before
   starting the stack, and revert the file at teardown. The edit must never
   reach a commit.
3. **One stack per worktree; ports chosen at allocation time.** This document
   names no port numbers, on purpose — any example here would be a second
   source of truth that drifts. Discover what is free when you allocate.
4. **Name the stack after its owner.** Derive `project_id` from
   `<stackPrefix>-<owner>` (branch, task id, or worktree name) so `docker ps`
   is self-documenting. Read `docker ps` before allocating: a stack named for
   another owner — or another application — is NOT yours.
5. **Identify dev processes by argv, never by port or broad pkill.** A
   port-based sweep kills unrelated repos' processes.
6. **Tear down on completion**, in the same close-out as the merge. Ordering
   and worktree cleanup: `multi-agent-git-workflow`.
7. **Run every command from the worktree that owns the work**, with the `cd`
   in the same shell invocation. Owned by `multi-agent-git-workflow`; it is
   repeated here only because `supabase stop` makes violating it destructive
   (see Teardown).

## The repo declaration

Tracked at the repo root as `.isolated-stack.json` — data, not logic, so it
cannot go stale-but-plausible:

```json
{
  "stackPrefix": "myapp",
  "supabase": { "config": "supabase/config.toml" },
  "apps": [
    { "name": "api", "adapter": "node", "env": "apps/api/.env", "portVar": "API_PORT" },
    { "name": "web", "adapter": "nuxt", "env": "apps/web/.env", "https": true }
  ]
}
```

- `stackPrefix` — names the shared stack (`<stackPrefix>` alone) and prefixes
  every isolated `project_id`.
- `supabase.config` — the tracked config the tool edits under skip-worktree.
- `apps[]` — each app the stack serves: which env file points it at the stack,
  which adapter knows how to start and health-check it. Adapter details:
  `references/adapters/<adapter>.md`.

## Ports

- **May not use:** the shared stack's ports, any app's default dev port, and
  any port another live workstream holds.
- **Verify the whole set is free before starting:** `docker ps` for
  container-published ports plus `lsof -nP -iTCP:<port> -sTCP:LISTEN` per
  candidate.
- **Enumerate the config's port keys; never recall them:**

  ```bash
  grep -nE '^ *[a-z0-9_]*port *=' supabase/config.toml
  ```

  Remap every key the grep finds. The key list belongs to the stack's config
  format, not to your memory of it — a missed key means one service still
  binds a shared port, and a port collision makes the boot **roll all the way
  back after applying every migration**, which is why enumeration is
  non-negotiable.

## Standing the stack up

1. From the worktree, set a distinct `project_id`
   (`<stackPrefix>-<owner>`) and remap **every** port key the grep found — in
   the config file, taken from the file, not from memory.
2. `git update-index --skip-worktree <config>` — before the stack starts.
3. `supabase start`, then `supabase status -o env` for the values the apps
   need. The `project_id` keys the underlying Docker Compose project; that is
   the entire reason two stacks can coexist.

## Pointing the apps at the stack

A fresh worktree lacks every gitignored local file the app needs to boot. Copy
them from the main checkout — **then audit every copied value for anything
that points at a shared port or a shared system.** Copied env files start out
aimed at the shared stack, and the dangerous values are the ones that do
not fail when stale: requests land on the shared system and succeed there.
This audit is the highest-value step in the whole mechanism.

While auditing, apply these portable rules — each learned from an incident:

- **A readiness gate must resolve its target the same way the app it gates
  does.** A wait-for-healthy probe that reads a different variable than the
  app connects with can go green against the wrong system.
- **A connection config should refuse a partial variable set by name**, not
  silently fall back — because the fallback is the shared stack.
- **Never `export` stack-pointing variables into the shell environment.** An
  exported variable shadows the per-worktree env file in every worktree.
- **Prefer `127.0.0.1` over `localhost`** — IPv6-first resolution makes
  `localhost` bind/connect mismatches intermittent.
- **Code running inside a stack container reaches the host as
  `host.docker.internal`, never `localhost`.**
- **All local stacks typically share a demo JWT secret**, so tokens are
  cross-valid: a frontend on stack A with a backend on stack B "works" until
  the other stack dies. Verify both ends point at the same stack, not that
  login succeeds.
- **If the app's session cookie is `Secure`, an `http://` origin silently
  drops it** and login 401s with no visible error. Serve HTTPS locally or
  relax the flag per the adapter; a production-build server that speaks plain
  HTTP needs a TLS terminator in front for UAT.
- **Mail/webhook containment comes from the transport** (a local catcher
  delivers nowhere real), not from an application-level guard. Derive catcher
  ports from the config block like every other port.

## Migrations and seeds

`supabase db reset` applies migrations to whatever stack the current config
resolves — from an isolated worktree, that is correctly the isolated stack.

**Seed and provisioning steps default to the shared database unless given an
explicit target.** That shape — a write step whose unstated destination is the
shared system — is the single most common way isolation silently fails. Pass
the isolated stack's connection explicitly, every time, and treat "it worked
with no target" as a red flag, not a convenience. A reset database is empty of
seeded content; reset ≠ seeded, and a platform-only database makes the app
look broken when it is merely unseeded.

## Teardown

Order-critical; the tool does this, in this order, and so must you:

1. `supabase stop` — **run from the worktree that owns the stack.**
   `supabase stop` resolves its config by walking up from the current
   directory: run from the wrong place — or from a worktree still pointed at
   the shared config — **it stops the shared stack for everyone**. Assert the
   config's `project_id` matches the stack you intend to stop, in the same
   invocation.
2. Remove the stack's volumes — `supabase stop` leaves them:

   ```bash
   docker volume ls -q --filter label=com.supabase.cli.project=<project_id> | xargs -r docker volume rm
   ```

   Assert the filter output is non-empty AND that `<project_id>` is not the
   shared stack's before deleting anything.
3. `git update-index --no-skip-worktree <config>` — **before** the checkout.
   With the bit still set, the next step silently no-ops and the isolation
   config survives into a merge.
4. `git checkout -- <config>` — the tracked file is clean again.
5. Worktree removal and branch deletion: `multi-agent-git-workflow` owns the
   ordering and the traps.
6. `stack doctor` (or `docker ps` + `docker volume ls`) — confirm the shared
   stack is untouched and nothing leaked.

## Footguns

- **Analytics/telemetry containers may never report healthy under
  concurrent-stack load**, and one unhealthy service rolls back the entire
  boot. Disable optional service blocks (e.g. `[analytics]`) in the isolated
  config.
- **A wrapper's `--` can swallow the flag you meant for the inner tool**, and
  the failure is silent (the flag is simply ignored). Framework specifics:
  the adapter files.
- **A committed stack config** is Hard rule 2 violated; `stack doctor` flags a
  config still carrying isolation edits.

## Red flags — STOP

| Thought | Reality |
|---|---|
| "The request is just to run the app" | Running the app is the trigger. Check for worktrees and `.isolated-stack.json` first. |
| "I'll reuse the ports from last time" | Discover at allocation time. Recorded ports are the drift this skill refuses. |
| "The env file copied over fine" | Copied means pointed at the shared stack. Audit every value. |
| "Login works, the wiring must be right" | Cross-valid demo tokens make split-brain look healthy. Verify both ends' targets. |
| "supabase stop, then I'll sort the config" | Stop resolves config from cwd. Wrong directory stops the shared stack for everyone. |
| "The seed ran without a target and succeeded" | It succeeded against the shared database. That is the failure. |
| "I'll checkout the config, then clear skip-worktree" | Wrong order. The checkout silently no-ops with the bit set. |
| "It's additive, the shared stack is fine" | The named rationalization. Use the isolated stack. |

## The guard

This plugin ships a `PreToolUse` hook on stack-affecting commands. It stays
silent in repos without `.isolated-stack.json`. It **blocks** only where the
damage is irreversible: a `db reset` whose resolved target is a stack the
current directory does not own, a shared-stack reset while an isolated stack
is live, and a command aimed at a worktree's stack from outside that worktree.
Everything else — `supabase start` or a dev server from the main checkout
while worktrees exist — gets injected context, because deliberate shared-stack
use is legitimate. If the guard blocks you, it prints the corrected command;
run that, don't work around the block.

## Don't cite this skill in the output

Explain the isolation steps in terms of their reasons — never "per the
isolated-stack-development skill...".

## See also

- [`multi-agent-git-workflow`](../../../multi-agent-git-workflow/skills/multi-agent-git-workflow/SKILL.md) — worktree location, run-from-the-worktree, cleanup ordering
- [`throughline`](../../../throughline/skills/throughline/SKILL.md) — when isolation is stood up (kickoff) and torn down (closeout)
- `references/adapters/` — nuxt, node, vite, spring: env wiring, start, health-check per framework
