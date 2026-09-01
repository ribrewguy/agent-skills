# Why `search_index` is missing, and the fix

## Root cause: environment drift — the api was querying the wrong stack

This worktree (`.worktrees/tf-9`, branch `feature/tf-9_search`) runs its own isolated Supabase stack:

- `supabase/config.toml` (held under `git update-index --skip-worktree`): `project_id = "myapp-feature-tf-9-search"`, API port **23110**, DB port **23111**, inbucket SMTP **23115**.
- The branch's migration `supabase/migrations/20260901000000_search_index.sql` (`create table search_index ...`) was applied to **that** stack.

But `apps/api/.env` in the worktree still pointed at the **default/main stack ports** (project_id `myapp` from the main checkout's config):

```
SUPABASE_URL=http://127.0.0.1:54321   # main stack API
DB_PORT=54322                          # main stack DB
SMTP_PORT=54325                        # main stack inbucket
```

So the api app booted fine and queried a perfectly healthy database — just the `develop` stack's database, which never received this branch's migration. That's exactly the symptom you saw: no connection errors, but `search_index` doesn't exist. (`.env` is gitignored, so nothing in `git status` hinted at the drift; it was copied from `.env.example`, which carries the main-stack defaults.)

## What I changed

Edited `.worktrees/tf-9/apps/api/.env` to point at this worktree's isolated stack:

```
SUPABASE_URL=http://127.0.0.1:23110
DB_PORT=23111
API_PORT=3100
SMTP_PORT=23115
```

Notes:

- `API_PORT=3100` (the api app's own listen port) is unchanged — it isn't part of the Supabase stack and nothing else is contending for it.
- `.env` is gitignored, so this local-only change can't leak into the branch. `apps/api/.env.example` is left untouched — it correctly documents the default (main-stack) ports for fresh checkouts.
- `supabase/config.toml` still shows `S` (skip-worktree) in `git ls-files -v`, so the isolation edits remain protected from accidental commits. Worktree `git status` is clean.

## Commands I would run, in order

(These are the state-changing/daemon commands reserved on this machine, so I'm listing them rather than executing.)

From the worktree root `.worktrees/tf-9/`:

1. Verify the isolated stack really has the table (sanity check that the migration was applied when the stack came up):

   ```sh
   psql "postgresql://postgres:postgres@127.0.0.1:23111/postgres" \
     -c "select to_regclass('public.search_index');"
   ```

   Expect `search_index`. If it comes back empty, apply this branch's migrations to the isolated stack:

   ```sh
   supabase db reset --workdir .
   ```

   (Run from the worktree so it uses the worktree's `config.toml` / project_id `myapp-feature-tf-9-search` — never from the main checkout, which would reset the `develop` stack.)

2. Restart the api app so it picks up the new `.env`:

   ```sh
   pnpm --filter ./apps/api dev
   ```

3. Confirm the fix end to end — hit whatever endpoint was failing, or directly:

   ```sh
   curl -s http://127.0.0.1:3100/health   # or the search endpoint that was missing the table
   psql "postgresql://postgres:postgres@127.0.0.1:23111/postgres" \
     -c "select count(*) from search_index;"
   ```

## Nothing needed from you

No decisions pending. One suggestion to prevent recurrence: whatever provisions these worktree stacks (the `.isolated-stack.json` tooling knows each app's env file — `apps/api/.env` with `portVar: API_PORT`) should rewrite the per-app `.env` port values at worktree setup time, the same way it rewrites `config.toml`. The web app's env (`apps/web/.env`) doesn't exist in this worktree yet; if you create it from an example file, use the 231xx ports too.
