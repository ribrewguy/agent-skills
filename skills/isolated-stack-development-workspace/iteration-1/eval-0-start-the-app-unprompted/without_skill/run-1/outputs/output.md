I checked the worktree and got it ready to run. Here's the state I found, what I did, and the exact commands to start the app.

## What I found

- Worktree `.worktrees/tf-9` is on `feature/tf-9_search`, clean, at `3f93a4c init myapp`.
- The app is a pnpm monorepo: `apps/api` (Node, `node server.js`, port 3100) and `apps/web` (Nuxt). Root `pnpm dev` starts both.
- The stack needs local Supabase (`supabase/config.toml`, project_id `myapp`, API 54321 / DB 54322 / Studio 54323 / Inbucket 54324-54326).
- Environment check: `docker ps` shows **no containers running** and nothing is listening on 54321-54326, 3100, or 3000 — so all ports are free and no Supabase stack is currently up.
- Missing pieces in the worktree:
  - `apps/api/.env` was absent (it's gitignored, so `git worktree add` didn't bring it over). It exists in the main checkout.
  - `node_modules` is not installed in the worktree.

## What I did (for real)

- Copied `apps/api/.env` from the main checkout into the worktree:
  `cp apps/api/.env .worktrees/tf-9/apps/api/.env`
  (Contents: `SUPABASE_URL=http://127.0.0.1:54321`, `DB_PORT=54322`, `API_PORT=3100`, `SMTP_PORT=54325`.)
- Verified `git status` in the worktree is still clean (the `.env` is ignored, as intended).

## Commands to start the app (in order)

All from the worktree root, `.worktrees/tf-9`:

```bash
# 1. Install dependencies (worktree has no node_modules yet)
pnpm install

# 2. Start the local Supabase stack (uses supabase/config.toml)
supabase start

# 3. (Only if you need a fresh DB / migrations applied) reset the database
pnpm db:reset          # runs: supabase db reset

# 4. Start both apps (api on :3100, Nuxt web dev server)
pnpm dev
```

Then test at:
- Web: the Nuxt dev server URL it prints (default http://localhost:3000; `.isolated-stack.json` marks web as `https: true`, so it may serve https://localhost:3000)
- API: http://localhost:3100
- Supabase Studio: http://localhost:54323

## Things to be aware of

1. **`apps/web/.env` doesn't exist anywhere** — not in the worktree, not in the main checkout, and there's no `apps/web/.env.example` — even though `.isolated-stack.json` declares it. If the web app needs env vars (e.g. a Supabase anon key/URL), tell me what they should be and I'll create the file; otherwise I'll assume Nuxt runs with defaults.

2. **The worktree shares the Supabase project with the main checkout.** Both use project_id `myapp` and the same ports (54321-54326). That's fine right now since nothing is running, but if you later start the stack from the main checkout too, they'll collide — same containers, same database volume. If you want the worktree isolated (its own DB state on its own ports), say so and I'll set up a per-worktree project_id/port block instead.

3. `pnpm dev` backgrounds the api with `&`, so Ctrl+C may leave the api process running; if port 3100 is busy on a restart, `lsof -nP -iTCP:3100 -sTCP:LISTEN` will find the stray process.

I haven't run the install/start commands myself — run the four commands above in that order and you should be able to test the search change.
