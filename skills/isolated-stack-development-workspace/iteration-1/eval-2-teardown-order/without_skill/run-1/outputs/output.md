# tf-9 worktree teardown

tf-9 is merged (I verified `feature/tf-9_search` and `develop` both point to `4e641ed`, so nothing on the branch was unmerged). Here is the full teardown, in the order it must happen. The Supabase/docker/process steps are written out for you (or for me to run once daemon commands are unblocked); the git and file steps I performed for real.

## Order matters

The isolated Supabase stack is addressed by the `project_id = "myapp-feature-tf-9-search"` in the worktree's `supabase/config.toml`. If the worktree is removed first, that config is gone and the CLI can no longer find the stack's containers and volumes — they get orphaned. So: **stop the stack (and any dev servers) first, remove the worktree last.**

## Step 1 — stop any dev servers for this worktree (would run)

I checked `lsof` on the stack's ports (23110–23116) and found nothing listening, and no tf-9 processes were visible, so this is likely a no-op. If anything were running:

```sh
# from anywhere — kill the worktree's api/web dev servers if present
lsof -tiTCP:23110-23116 -sTCP:LISTEN | xargs kill
```

## Step 2 — stop and delete the isolated Supabase stack (would run)

Run from **inside the worktree** while its `config.toml` still carries the isolated `project_id`:

```sh
cd .worktrees/tf-9
supabase stop --no-backup
```

`--no-backup` because the branch is merged — the isolated database's data is disposable and we want the volumes deleted, not preserved.

## Step 3 — verify nothing is left over (would run)

```sh
docker ps -a --filter "name=myapp-feature-tf-9-search" --format '{{.Names}}'
docker volume ls --filter "name=myapp-feature-tf-9-search" --format '{{.Name}}'
```

Both should print nothing. If any volumes linger (e.g. the stack was killed uncleanly at some point):

```sh
docker volume rm $(docker volume ls -q --filter "name=myapp-feature-tf-9-search")
```

Note: my read-only checks (`docker ps -a`, `docker volume ls`, `lsof`) already show no `myapp-feature-tf-9-search` containers, volumes, or listeners on this machine, so steps 1–3 are confirmation more than cleanup.

## Step 4 — remove the worktree and branch (done for real)

The worktree's `supabase/config.toml` carried the isolation edits under `skip-worktree`, which would leave a hidden dirty file behind. I cleared the flag and restored the tracked version before removal, so git saw a genuinely clean tree:

```sh
git -C .worktrees/tf-9 update-index --no-skip-worktree supabase/config.toml
git -C .worktrees/tf-9 checkout -- supabase/config.toml
git worktree remove .worktrees/tf-9
git branch -d feature/tf-9_search      # -d (not -D): confirmed merged into develop
git worktree prune
rmdir .worktrees                        # was empty after removal
```

## Final state (verified)

- `git worktree list` → only the main checkout on `develop`
- `git branch -a` → only `develop`; `feature/tf-9_search` deleted (was `4e641ed`)
- `.worktrees/` directory removed; `git status` clean
- Main checkout's `supabase/config.toml` untouched (`project_id = "myapp"`, ports 543xx)
- No tf-9 containers, volumes, or port listeners found

## What I need from you

Nothing, unless you want me to hold off on `--no-backup` — if there's any chance you want the tf-9 database contents, run `supabase stop` (without the flag) in step 2 instead, which preserves the volumes; they can be deleted later with the step-3 volume command.
