# Adapter: vite

How a Vite-served frontend (React, Vue, Svelte, vanilla) in `apps[]` binds to
an isolated stack.

## Env wiring

Vite only exposes env vars with the configured prefix (`VITE_` by default) to
client code, and it snapshots them **at dev-server start** — changing the env
file requires a restart, not a reload. Point `VITE_`-prefixed stack values
(Supabase URL, anon key, API base) at the isolated stack in the worktree's env
file. Values without the prefix silently come through as `undefined` in client
code, and many Supabase client wrappers then fall back to a default or throw
only at first query — audit for the prefix, not just the value.

## Port

`server.port` in `vite.config` is a *preference*: if the port is taken, Vite
**increments to the next free port and keeps going** (unless `strictPort` is
set). That auto-bump hides a collision with the shared app's port instead of
failing — set `strictPort: true` (or pass `--strictPort`) for isolated runs so
a collision is an error, and drive the port from the allocation via env.

## Proxy targets

A `server.proxy` block that hardcodes a backend origin is a shared-system
pointer the env audit must catch: the frontend will "work" while every API
call lands on the shared backend. Drive proxy targets from the same env values
as everything else.

## Start and health-check

- Start: the repo's dev script, from the worktree, same invocation as the
  `cd`.
- Health: the dev server prints its actual listen URL on boot; verify it is
  the **allocated** port (with `strictPort`, a mismatch fails instead of
  lying). Probe using the env file's values, not a remembered URL.
