# Starting the app in `.worktrees/tf-9`

"Start the app" from a worktree is not just `pnpm dev`. This repo has multiple worktrees and a tracked `.isolated-stack.json`, which means each worktree gets its **own** Supabase stack — its own `project_id`, ports, and volumes — so nothing here can touch the shared stack the main checkout runs on its default ports (54321–54326). Booting the app from this worktree against the shared stack would mean my search-branch migrations and seeds land in the database every other workstream depends on.

So before starting anything I stood up the isolation wiring. Here is exactly what I did and what runs next.

## What I already did (file/git changes, done)

### 1. Surveyed before allocating

- `docker ps` — no containers running; no stack (shared or otherwise) currently up, and no container-published ports to avoid beyond the shared defaults.
- Enumerated every port key from the actual config (not from memory):

  ```
  grep -nE '^ *[a-z0-9_]*port *=' supabase/config.toml
  ```

  Seven keys: `[api] port`, `[db] port`, `[db] shadow_port`, `[studio] port`, `[inbucket] port`, `smtp_port`, `pop3_port`. Every one must be remapped — a single missed key leaves one service on a shared port, and a port collision makes `supabase start` apply every migration and then roll the whole boot back.
- Verified each candidate port free with `lsof -nP -iTCP:<port> -sTCP:LISTEN` (all free): 55420–55426 for Supabase, 3181 for the API, 3182 for the web dev server. The shared stack's ports (54320–54326), the apps' default dev ports (3100, 3000), and Nuxt's default were treated as off-limits even though nothing is listening right now.

### 2. Edited `supabase/config.toml` in the worktree

- `project_id = "myapp-tf-9"` — derived from the stack prefix + this worktree's task id, so `docker ps` will be self-documenting and this stack can coexist with the shared one (the project id keys the Docker Compose project).
- Remapped all seven port keys: api 55421, db 55422, shadow 55420, studio 55423, inbucket 55424, smtp 55425, pop3 55426.
- Set `[analytics] enabled = false` — the analytics container often never reports healthy under concurrent-stack load, and one unhealthy service rolls back the entire boot.

### 3. Protected the tracked config from being committed

```
git update-index --skip-worktree supabase/config.toml
```

Done **before** the stack starts. The config file is tracked; these isolation edits must never reach a commit. `git status` in the worktree is clean and `git ls-files -v` shows the `S` bit set. At teardown the bit is cleared first, then the file restored (that order matters — with the bit still set, a checkout silently no-ops).

### 4. Wrote the worktree's env files, audited for shared-stack pointers

The fresh worktree had no gitignored env files. I copied the API one from the main checkout and audited every value — copied env files start out aimed at the shared stack, and stale values there don't fail, they *succeed against the shared system*, which is the worst failure mode.

`apps/api/.env` (was 54321/54322/3100/54325 — all shared; now fully isolated):

```
SUPABASE_URL=http://127.0.0.1:55421
DB_PORT=54322 → 55422
API_PORT=3100 → 3181
SMTP_PORT=54325 → 55425
```

`apps/web/.env` (the main checkout has **no** web env file, so I created one from the stack declaration):

```
NUXT_PORT=3182
SUPABASE_URL=http://127.0.0.1:55421
API_BASE_URL=http://127.0.0.1:3181
```

Notes on the audit:
- `127.0.0.1` rather than `localhost` throughout — IPv6-first resolution makes `localhost` bind/connect mismatches intermittent.
- Nothing is `export`ed into the shell; an exported stack-pointing variable would shadow the per-worktree env file in every worktree.
- The web port goes through `NUXT_PORT` rather than a `--port` flag, because a package-manager wrapper's `--` can silently swallow the flag and the server would come up on the default (shared app) port with no error.
- Both files are gitignored (verified with `git check-ignore`), so nothing env-related can leak into a commit either.

## Commands to run, in order (each `cd` in the same invocation — Supabase resolves its config by walking up from the current directory)

Let `WT=/private/tmp/claude-501/-Users-torr-Projects-agent-skills/62a0d71b-499c-4c5e-a24e-30162c5845d6/scratchpad/eval-fixtures/eval-0-start-the-app-unprompted/with_skill/myapp/.worktrees/tf-9`

1. **Start the isolated stack** (boots as Compose project `myapp-tf-9`, on the 554xx ports only):

   ```bash
   cd "$WT" && supabase start
   ```

2. **Read the stack's actual values** and reconcile the env files against them (anon/service keys, DB URL). If the web or API app needs the anon key, append it to the worktree env files from this output — never from another stack's output, and never exported:

   ```bash
   cd "$WT" && supabase status -o env
   ```

3. **Install dependencies** (fresh worktree, no `node_modules`):

   ```bash
   cd "$WT" && pnpm install
   ```

4. **Migrate the isolated database.** Run from this worktree the config resolves to `myapp-tf-9`, so this resets only our stack:

   ```bash
   cd "$WT" && supabase db reset
   ```

   Reset ≠ seeded: the database is now empty of content. If any seed/provisioning step exists, it must be given the isolated target **explicitly** — e.g.

   ```bash
   psql "postgresql://postgres:postgres@127.0.0.1:55422/postgres" -f supabase/seed.sql
   ```

   A seed that "just works" with no target given has almost certainly written to the shared database — that's a red flag, not a convenience.

5. **Start both apps from the worktree:**

   ```bash
   cd "$WT" && pnpm dev
   ```

   (`pnpm dev` starts `apps/api` on `API_PORT=3181` and the Nuxt app on `NUXT_PORT=3182`, both reading the worktree env files written above.)

6. **Health-check on the allocated ports, resolving the target from the same env files the apps read** (a probe that reads a different variable can go green against the wrong system):

   ```bash
   cd "$WT" && . apps/api/.env && curl -fsS "http://127.0.0.1:${API_PORT}/" >/dev/null && echo api up
   cd "$WT" && . apps/web/.env && curl -fsS "http://127.0.0.1:${NUXT_PORT}/" >/dev/null && echo web up
   ```

   If you later need to find or stop a dev process, identify it by argv (`ps -o pid,args= | grep 'nuxt dev\|node server.js'`), never by port and never with a broad `pkill`.

Then test your change at **http://127.0.0.1:3182** (search feature UI) with the API on **http://127.0.0.1:3181**.

## Two things I need from you

1. **HTTPS for the web app.** The stack declaration marks the web app `https: true`. If its session cookie is `Secure`, a plain `http://` origin silently drops it and login 401s with no visible error. How does this repo do local TLS — is there a dev cert/key pair for `devServer.https`, or a local TLS terminator you normally use? Until that's answered, expect authenticated flows on `http://127.0.0.1:3182` to fail at login even though everything else is healthy.
2. **Web runtime config names.** The main checkout has no `apps/web/.env` to copy, so I wrote one from the stack declaration (`NUXT_PORT`, `SUPABASE_URL`, `API_BASE_URL`). If the Nuxt `runtimeConfig` expects different variable names (or needs the anon key), tell me and I'll align the file with the `supabase status -o env` output after step 2.

One more caution while testing: don't treat a successful login as proof the wiring is right — local stacks share a demo JWT secret, so a frontend on one stack with a backend on another "works" until the other stack dies. The env audit above is what guarantees both ends point at `myapp-tf-9`.

## Teardown (later, when the branch is done — do not run now)

Order-critical, from this worktree only:

```bash
cd "$WT" && grep -q '^project_id = "myapp-tf-9"' supabase/config.toml && supabase stop
docker volume ls -q --filter label=com.supabase.cli.project=myapp-tf-9 | xargs -r docker volume rm   # only after confirming the filter output is non-empty and is NOT the shared stack's project
cd "$WT" && git update-index --no-skip-worktree supabase/config.toml
cd "$WT" && git checkout -- supabase/config.toml
docker ps && docker volume ls   # confirm the shared stack untouched, nothing leaked
```

`supabase stop` from the wrong directory stops whatever stack that directory's config resolves to — which is how a worktree cleanup takes down the shared stack for everyone; hence the project-id assertion in the same invocation.
