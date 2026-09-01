# Clean database for `feature/tf-9_search`

One important adjustment before any reset: I did **not** aim the reset at the stack the repo's config pointed to. This worktree's `supabase/config.toml` came in with `project_id = "myapp"` and the default ports — that is the long-lived shared stack the main checkout owns. `supabase db reset` resolves its target from the config it finds by walking up from the current directory, so running it as-is from this worktree would have wiped the **shared** database for everyone, not given you a private empty one.

Instead, this worktree now gets its own isolated stack, and the reset runs against that. The repo opts into exactly this workflow via its tracked `.isolated-stack.json`.

## What I changed (already done)

All changes are inside the worktree `.worktrees/tf-9`:

1. **`supabase/config.toml` rewritten for an isolated stack.**
   - `project_id = "myapp-tf-9"` (stack prefix + branch owner) — this keys the underlying Docker Compose project, which is what lets this stack coexist with the shared one, and makes `docker ps` self-documenting.
   - Every port key in the file remapped (I enumerated them with `grep -nE '^ *[a-z0-9_]*port *=' supabase/config.toml` rather than from memory — a single missed key would leave one service bound to a shared port, and a port collision makes the boot roll back after applying every migration):

     | key | shared | isolated |
     |---|---|---|
     | `[api] port` | 54321 | 55421 |
     | `[db] port` | 54322 | 55422 |
     | `[db] shadow_port` | 54320 | 55420 |
     | `[studio] port` | 54323 | 55423 |
     | `[inbucket] port` | 54324 | 55424 |
     | `[inbucket] smtp_port` | 54325 | 55425 |
     | `[inbucket] pop3_port` | 54326 | 55426 |

     I verified each 554xx port is free right now (`lsof -nP -iTCP:<port> -sTCP:LISTEN` per port, plus `docker ps` for container-published ports) before choosing it.
   - `[analytics] enabled = false` — the analytics container often never reports healthy when a second stack is running, and one unhealthy service rolls back the entire boot.

2. **`git update-index --skip-worktree supabase/config.toml`** — the config is a tracked file and the isolation edit must never reach a commit. With the bit set, `git status` is clean and the edit can't be staged by accident. It gets reverted at teardown (order matters there — see below).

3. **`apps/api/.env` created in the worktree** (gitignored). A fresh worktree has none, and a straight copy from the main checkout would still point at the shared stack — copied env values are dangerous precisely because they don't fail: requests just land on the shared system and succeed. I copied the shape and audited every value:

   ```
   SUPABASE_URL=http://127.0.0.1:55421   # was 54321 → shared API
   DB_PORT=55422                          # was 54322 → shared DB
   API_PORT=3190                          # 3100 is the default dev port; left free for the main checkout
   SMTP_PORT=55425                        # mail stays contained in this stack's local catcher
   ```

   (`127.0.0.1` rather than `localhost` on purpose — IPv6-first resolution makes `localhost` mismatches intermittent. `apps/web` has no env file in the main checkout, so nothing to wire there yet.)

## Commands to run, in this order

I can't start daemons from here, so run these yourself (or say the word and I'll hand them off). Each one runs **from the worktree** — the `cd` is part of the command on purpose, because the Supabase CLI resolves which stack it targets from the current directory:

```bash
# 1. Boot the isolated stack (fresh volumes = already-empty database)
cd .worktrees/tf-9 && supabase start

# 2. Capture the stack's connection values (API URL, anon/service keys, DB URL)
cd .worktrees/tf-9 && supabase status -o env

# 3. The reset you asked for — applies this branch's migrations to the empty DB.
#    Safe now: the config here resolves to myapp-tf-9, not the shared stack.
cd .worktrees/tf-9 && supabase db reset

# 4. Verify isolation held: expect only myapp-tf-9-named containers on 554xx
#    ports, and the shared stack's containers/ports untouched.
docker ps
```

Two notes on step 3:

- **This branch currently has no `supabase/migrations/` directory**, so the reset will produce a platform-schema-only database. If the branch's migrations are about to be written as part of this task, run `supabase db reset` again after adding them (or `supabase migration up` incrementally).
- **Reset ≠ seeded.** If you later want seed data, the seed/provision step must be given the isolated DB target explicitly, e.g. `psql "postgresql://postgres:postgres@127.0.0.1:55422/postgres" -f seed.sql`. A seed command that "works" with no explicit target has defaulted to the shared database — treat that as a failure, not a convenience.

Also worth knowing while you test: all local stacks share a demo JWT secret, so a login succeeding proves nothing about which stack you're on — check both ends' URLs, not the login.

## Teardown (when this branch is done — don't run now)

Order-critical, from the worktree:

```bash
# 1. Stop THIS stack — from the worktree, asserting the target first
cd .worktrees/tf-9 && grep 'project_id' supabase/config.toml && supabase stop

# 2. Remove its volumes (stop leaves them); filter must be non-empty and must
#    name myapp-tf-9, never bare "myapp"
docker volume ls -q --filter label=com.supabase.cli.project=myapp-tf-9 | xargs -r docker volume rm

# 3. Clear the skip-worktree bit BEFORE the checkout — otherwise the checkout
#    silently no-ops and the isolation edit survives into a merge
cd .worktrees/tf-9 && git update-index --no-skip-worktree supabase/config.toml
cd .worktrees/tf-9 && git checkout -- supabase/config.toml

# 4. Confirm nothing leaked and the shared stack is untouched
docker ps && docker volume ls
```

## What I need from you

Nothing blocking — run steps 1–4 above and you'll have your empty database on this branch. Just confirm whether the branch's migrations exist somewhere I haven't seen or are still to be written, so we know whether step 3 needs a second pass.
