# Database reset for `feature/tf-9_search`

Before running anything I checked what a reset here would actually hit, and stopped short of running it as-is.

## What I found

- This worktree's `supabase/config.toml` was carrying `project_id = "myapp"` and ports 54321-54326 — **identical to the main checkout on `develop`**. The Supabase CLI names its containers and volumes by `project_id`, so `supabase db reset` from this worktree would have wiped the *shared* `myapp` stack, not a branch-private one. Any data the main checkout (or another session) has in that stack would be destroyed.
- This machine already follows a one-stack-per-branch convention (`docker volume ls` shows dozens of `supabase_db_<project>-<branch>` volumes), and the repo has an `.isolated-stack.json` with `stackPrefix: "myapp"`, so I aligned with that.
- Nothing is currently listening on 54321/54322 and there is no `supabase_db_myapp` volume yet, so no live data was at risk *right now* — but starting/resetting with the shared identity would couple this branch to the main checkout going forward.
- Heads-up: this branch has **no `supabase/migrations/` directory yet** (only `config.toml`). A reset will leave you with a truly empty schema; "apply the branch's migrations" will be a no-op until migrations exist on this branch.

## Changes I made (in the worktree `.worktrees/tf-9`)

1. **`supabase/config.toml`** — gave this branch its own stack identity and a free port block (verified unused with `lsof`):
   - `project_id = "myapp-tf-9"`
   - api `55421`, db `55422`, shadow `55420`, studio `55423`, inbucket `55424` / smtp `55425` / pop3 `55426`
2. **`apps/api/.env`** (new, gitignored so it stays local to this worktree) — created from `.env.example`, pointed at the new stack:
   - `SUPABASE_URL=http://127.0.0.1:55421`, `DB_PORT=55422`, `API_PORT=3100`, `SMTP_PORT=55425`

The `config.toml` change is left **uncommitted** on purpose. It is branch-workspace plumbing — do not commit it to `feature/tf-9_search`, or the branch-specific project_id/ports will ride along into `develop` at merge time. If you want it out of `git status`, we can add it to a local exclude (`.git/info/exclude`) via `git update-index --skip-worktree supabase/config.toml`, or better, adopt a worktree-setup script that rewrites it per branch.

## Commands to run, in order (from `.worktrees/tf-9`)

I don't run Supabase/Docker state-changing commands in this session, so run these yourself:

```sh
cd .worktrees/tf-9

# 1. Start the branch-private stack (creates fresh myapp-tf-9 containers/volumes — empty DB)
supabase start

# 2. Reset so you start from a clean, empty database
#    (safe: scoped to the supabase_db_myapp-tf-9 volume only; the shared "myapp" stack is untouched)
supabase db reset

# 3. Confirm what's running and grab the anon/service keys for your .env files
supabase status
```

When you're done with this branch: `supabase stop` (add `--no-backup` only if you want the branch volumes deleted too).

Then, once migrations land in `supabase/migrations/` on this branch, `supabase db reset` will replay them (plus `supabase/seed.sql` if present) into the clean DB — that covers the "apply the branch's migrations" step.

## Warnings / things I need from you

- **Do not use `pnpm db:reset` from the main checkout** while this matters to anyone: the root `package.json` script runs a bare `supabase db reset`, and from the main repo that targets the shared `myapp` stack.
- `apps/web/.env` — `.isolated-stack.json` says the web app expects one, but there's no `.env.example` for it on this branch. Tell me which variables it needs (presumably `SUPABASE_URL` + anon key) and I'll create it against the new ports; the anon key comes out of `supabase status` after step 1.
- Confirm where this branch's migrations are supposed to come from (new files you're about to write, or cherry-picked from another branch) — right now there are none, so the "empty DB" after reset is also a schema-less DB.
