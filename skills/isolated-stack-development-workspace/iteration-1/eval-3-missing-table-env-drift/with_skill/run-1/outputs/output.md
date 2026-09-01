# Why `search_index` is missing, and the fix

## Root cause: the API is querying the wrong database

The worktree's `apps/api/.env` was a verbatim copy of the main checkout's env file, so every stack-pointing value in it still aimed at the **shared** stack (the one the main checkout runs at Supabase's default ports):

```
SUPABASE_URL=http://127.0.0.1:54321   <- shared stack's API port
DB_PORT=54322                          <- shared stack's DB port
SMTP_PORT=54325                        <- shared stack's mail catcher
```

Meanwhile this worktree's own isolated stack (`project_id = myapp-feature-tf-9-search`, per `supabase/config.toml` in the worktree) is bound to a completely different port block: api **23110**, db **23111**, smtp **23115**.

So the API booted "fine" and queried "without errors" because its requests were landing on the shared database and succeeding there — the most dangerous kind of stale config, because nothing fails visibly. The shared database sits at trunk (`develop`) and has never had this branch's `supabase/migrations/20260901000000_search_index.sql` applied, hence no `search_index` table. The migration itself is fine; the app was simply looking at a database that will never contain it. (Applying the branch migration to the shared DB would have been the wrong fix — it would contaminate trunk state for everyone.)

Confirmed before changing anything:

- Worktree `supabase/config.toml` carries the isolation edits (project_id `myapp-feature-tf-9-search`, ports 23110–23116) and is under `skip-worktree` (`git ls-files -v` shows `S`), so those edits can't reach a commit.
- Main checkout `supabase/config.toml` is the shared stack at 54321/54322/etc. — the exact ports the worktree's `.env` was pointing at.
- `apps/api/.env` is gitignored, so editing it is purely local.

## What I changed

Rewrote `.worktrees/tf-9/apps/api/.env` to point at this worktree's isolated stack:

```
SUPABASE_URL=http://127.0.0.1:23110
DB_PORT=23111
API_PORT=23117
SMTP_PORT=23115
```

Notes on each value:

- `SUPABASE_URL` / `DB_PORT` / `SMTP_PORT` now match the port keys in the worktree's `supabase/config.toml` (`[api] port`, `[db] port`, `[inbucket] smtp_port`) — taken from the file, not from memory.
- `API_PORT` moved from **3100 → 23117**. 3100 is the app's default dev port, i.e. the port the main checkout's API server uses; a worktree dev server must not squat on it, or the two checkouts collide. I verified 23117 is free (`lsof -nP -iTCP:23117 -sTCP:LISTEN` shows no listener) and it sits in the same block as the rest of this stack's ports. **This means the worktree's API will now answer on `http://127.0.0.1:23117`, not 3100.**
- Kept `127.0.0.1` rather than `localhost` to avoid intermittent IPv6-first resolution mismatches.

`git status` in the worktree is clean — no tracked file changed, and no commit is needed for this fix.

## Commands to run, in order

I don't run stack/daemon commands from here; run these exactly as written. Every one starts with a `cd` into the worktree in the same invocation — Supabase resolves its config by walking up from the current directory, so running from the wrong place would target the shared stack.

1. **Confirm the isolated stack has the branch migration applied** (the stack is up, but "up" is not "migrated"):

   ```bash
   cd /private/tmp/claude-501/-Users-torr-Projects-agent-skills/62a0d71b-499c-4c5e-a24e-30162c5845d6/scratchpad/eval-fixtures/eval-3-missing-table-env-drift/with_skill/myapp/.worktrees/tf-9 \
     && supabase migration list
   ```

2. **Only if `20260901000000` is not applied**, reset the isolated database from the worktree (this applies all migrations to `myapp-feature-tf-9-search` and only that stack):

   ```bash
   cd /private/tmp/claude-501/-Users-torr-Projects-agent-skills/62a0d71b-499c-4c5e-a24e-30162c5845d6/scratchpad/eval-fixtures/eval-3-missing-table-env-drift/with_skill/myapp/.worktrees/tf-9 \
     && grep '^project_id' supabase/config.toml \
     && supabase db reset
   ```

   The `grep` is the assertion that the config resolving here is the isolated stack, in the same invocation as the reset. Note a reset database is empty of seeded content — if the API needs seed data, run the seed step with the isolated DB connection passed **explicitly** (e.g. `--db-url postgresql://postgres:postgres@127.0.0.1:23111/postgres`); a seed step run with no target defaults to the shared database, which is exactly the class of drift that caused this bug.

3. **Restart the API server so it re-reads the env file.** Find the stale process by its argv and path — never by port, and never with a broad pkill (a port sweep can kill the main checkout's server or an unrelated repo's process):

   ```bash
   pgrep -fl "node server.js"
   # kill ONLY the PID whose cwd/argv is under .worktrees/tf-9 (check with: lsof -p <PID> | grep cwd)
   kill <PID-of-the-tf-9-instance>
   cd /private/tmp/claude-501/-Users-torr-Projects-agent-skills/62a0d71b-499c-4c5e-a24e-30162c5845d6/scratchpad/eval-fixtures/eval-3-missing-table-env-drift/with_skill/myapp/.worktrees/tf-9/apps/api \
     && pnpm dev
   ```

   If the only `node server.js` running belongs to the main checkout, leave it alone and just start the worktree's instance.

4. **Verify against the right database** — check the table exists on the isolated stack and the API sees it:

   ```bash
   psql "postgresql://postgres:postgres@127.0.0.1:23111/postgres" -c '\d search_index'
   curl http://127.0.0.1:23117/<your-search-endpoint>
   ```

   The point of verifying by port is that "the query succeeds" was the misleading signal in the first place; success only counts against 23111/23117.

## Things to be aware of

- **The API's address changed:** anything that calls this worktree's API (the web app, your curl/tests) must use `http://127.0.0.1:23117` now. If the web app is run from this worktree, its `apps/web/.env` does not exist yet — when you create it (typically by copying from the main checkout), audit it the same way: every URL/port in a copied env file starts out pointed at the shared stack, and the API base URL must be updated to 23117. Say the word and I'll wire that file too.
- **Nothing was done to the shared stack** — it stays at trunk parity; this branch's migration lives only on the isolated stack, and no state-changing command in this session touched anything.
- All local stacks share the demo JWT secret, so a token minted by one stack validates on another — "auth works" is not evidence the wiring is right. The port check in step 4 is the real verification.
