# Adapter: nuxt

How a Nuxt app in `apps[]` binds to an isolated stack.

## Env wiring

Nuxt reads runtime config from env vars at process start. Point every
stack-facing runtime config value (Supabase URL, anon key, API base URL) at
the isolated stack via the app's env file — never by exporting into the shell
(an export shadows every worktree). `supabase status -o env` provides the
values; map them to the names the app's `runtimeConfig` declares.

The dev server port comes from the allocation, not from a default. Prefer the
env var Nuxt honors natively (`NUXT_PORT`/`PORT`) or `devServer.port` driven
by an env var, so the port lives in the worktree's env file with everything
else.

## The `--` trap (this adapter's incident)

Package-manager script wrappers pass `--` to mark end-of-flags. If the
wrapper's `--` reaches Nuxt's own argv parser, a following `--port <n>` is
treated as positional and **silently dropped** — the server starts on the
default port, which is the shared app's port, with no error. Prefer the env
var route above; if you must pass CLI flags through a script wrapper, verify
which layer consumed them (`ps -o args= -p <pid>` shows what the dev process
actually received; the listen line in the boot log shows what won).

## HTTPS

If the app sets `Secure` session cookies, plain `http://localhost` silently
drops them and login 401s. Run the dev server with local TLS (Nuxt supports
`devServer.https` with a local cert/key pair) or front a production build with
a TLS terminator. The cert tooling and hostname are the repo's business; the
rule that HTTPS is required is not optional when cookies are `Secure`.

## Start and health-check

- Start: the repo's dev script for this app, from the worktree, in the same
  invocation as the `cd`.
- Health: probe the dev server on its **allocated** port, and resolve the
  probe target from the same env file the app reads — a gate that reads a
  different variable can go green against the wrong system.
