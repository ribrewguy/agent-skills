# Adapter: node

How a Node service (API server, worker, monorepo package) in `apps[]` binds to
an isolated stack.

## Per-worktree install

A fresh worktree has no `node_modules`. Run the repo's install
(`pnpm install` / `npm ci` / `yarn`) in the worktree before anything boots.
Lockfile-driven installs are deterministic; skipping the install and relying
on the main checkout's modules via path tricks is not.

## Env wiring

Point the service's env file at the isolated stack: database URL or
host/port/credential components, Supabase URL and keys, and the service's own
listen port — all from the allocation and `supabase status -o env`, all in the
worktree's env file, none exported.

If the service builds its connection from component variables, it should
**refuse a partial set by name** rather than fall back to a default — the
default is the shared stack. If the repo's config loader doesn't enforce
that, the audit step must: verify every component is present and isolated.

## Stale dist (this adapter's incident)

In a monorepo where the service consumes compiled workspace packages, the dev
runner typically does **not** rebuild dependencies. After changing a workspace
dependency, rebuild it before testing the consumer, or the service runs
yesterday's code with today's env — a failure that looks like the stack's
fault and isn't.

## Start and health-check

- Start: the repo's dev script for this service, from the worktree, same
  invocation as the `cd`.
- Health: probe the service's allocated port; resolve the probe target from
  the same variables the service boots with (see the readiness-gate rule in
  the core skill).
- Identify the process by argv (`ps -o pid,args= | grep <service entry>`),
  never by port, when checking or stopping it.
