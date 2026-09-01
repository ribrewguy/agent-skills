# tf-9 closeout: worktree + isolated stack teardown

tf-9 is merged, so I closed out the whole workstream: the isolated Supabase stack
(`myapp-feature-tf-9-search`), its volumes, the isolation edits to
`supabase/config.toml`, the worktree, and the branch.

Teardown here is order-critical, so I'll list the full sequence first, then what
I actually did at each step.

## The order, and why it matters

1. **Stop dev processes owned by the worktree** — identified by argv (their
   command line contains the tf-9 worktree path), never by port or a broad
   pkill, which would kill unrelated repos' processes.
2. **`supabase stop` — from inside the tf-9 worktree, while the isolation
   config is still in place.** `supabase stop` resolves its config by walking
   up from the current directory. Run from the wrong directory — or after the
   config has been reverted to the tracked `project_id = "myapp"` — it stops
   the *shared* stack for everyone. That's why the stop must come before any
   git cleanup of the config, and why I assert the config's `project_id` in
   the same invocation.
3. **Remove the stack's volumes** — `supabase stop` leaves them behind. Delete
   only volumes labeled with the isolated project id, and only after asserting
   the filter output is non-empty and the id is not the shared stack's.
4. **`git update-index --no-skip-worktree supabase/config.toml`** — the
   isolation edits were held under skip-worktree so they could never reach a
   commit. This bit must be cleared *before* the checkout: with it still set,
   the checkout silently no-ops and the isolation config survives.
5. **`git checkout -- supabase/config.toml`** — the tracked file is clean
   again.
6. **Worktree removal, branch deletion, prune** — from the main checkout.
7. **Verify** — worktree list, branches, `docker ps` / `docker volume ls` to
   confirm the shared stack is untouched and nothing leaked.

## What I found on inspection (steps 1–3)

Before touching anything, I verified the live state with read-only commands:

- `ps aux` filtered for node/nuxt/vite processes whose argv references the
  tf-9 worktree path: **none running**.
- `docker ps`: **no containers running at all** — the `myapp-feature-tf-9-search`
  stack is already down (and the shared `myapp` stack is not up either, so
  there was nothing shared at risk).
- `docker volume ls -q --filter label=com.supabase.cli.project=myapp-feature-tf-9-search`:
  **empty** — no volumes left behind.

So steps 1–3 turned out to be no-ops on this machine. Because container- and
daemon-touching commands are reserved in this session, here is exactly what I
would have run — in this order — had the stack still been up:

```bash
# 1. Stop dev processes owned by this worktree (argv-identified, per PID):
ps aux | grep -E 'node|nuxt' | grep '\.worktrees/tf-9'   # then kill <pid> for each

# 2. Stop the isolated stack — FROM the worktree, asserting ownership first:
cd .worktrees/tf-9 \
  && grep -q '^project_id = "myapp-feature-tf-9-search"' supabase/config.toml \
  && supabase stop

# 3. Remove its volumes — assert the filter hits are non-empty and not the shared stack's:
docker volume ls -q --filter label=com.supabase.cli.project=myapp-feature-tf-9-search
docker volume ls -q --filter label=com.supabase.cli.project=myapp-feature-tf-9-search \
  | xargs -r docker volume rm
```

With the inspection confirming the stack was already stopped and volume-free,
it was safe to proceed to the git-side teardown for real.

## What I did for real (steps 4–7)

From inside `.worktrees/tf-9`:

```bash
git update-index --no-skip-worktree supabase/config.toml   # clear the bit FIRST
git checkout -- supabase/config.toml                        # then restore the tracked file
```

Confirmed: `supabase/config.toml` is back to the tracked content
(`project_id = "myapp"`, default ports, `[analytics]` block restored), the
skip-worktree flag reads `H` (normal), and `git status` in the worktree was
clean — the isolation edits (project id `myapp-feature-tf-9-search`, ports
23110–23116, analytics disabled) never touched a commit.

From the main checkout:

```bash
git worktree remove .worktrees/tf-9
git branch -d feature/tf-9_search    # -d, not -D: verifies the branch is merged
git worktree prune
rmdir .worktrees                     # directory was empty afterward
```

`git branch -d` succeeded ("Deleted branch feature/tf-9_search (was 3f93a4c)"),
which independently confirms the branch was fully merged.

## Final state (verified)

- `git worktree list`: only the main checkout on `develop` remains.
- `git branch -a`: only `develop`; `feature/tf-9_search` is gone.
- `git status`: clean — no stray `.worktrees/` entry, no config drift.
- `docker ps` / labeled volume filter: no `myapp-feature-tf-9-search`
  containers or volumes; the shared stack was never touched.

## Anything I need from you

Nothing, unless your Docker context differs from what I could see here. If you
believe the tf-9 stack is still up somewhere (e.g. a different Docker context),
run the three reserved-command steps above **in that order** — the stop must
happen from a directory whose `supabase/config.toml` still says
`project_id = "myapp-feature-tf-9-search"`. Since that worktree and its config
edits are now gone, the safe way to stop a straggler at this point is by
project name rather than config resolution:

```bash
docker ps --filter name=myapp-feature-tf-9-search            # confirm ownership first
docker ps -q --filter name=supabase --filter name=myapp-feature-tf-9-search | xargs -r docker stop
docker volume ls -q --filter label=com.supabase.cli.project=myapp-feature-tf-9-search | xargs -r docker volume rm
```

Never run a bare `supabase stop` from the main checkout for this — its config
resolves to the shared `myapp` stack and would take it down for everyone.
