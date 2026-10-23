# Tools the kickoff runs

Back to [SKILL.md](../SKILL.md#fresh-kickoff). Exact commands, why each flag, what each writes, and the failures seen. Versions these notes were checked against: bd 1.3.1, cass-memory (`cm`) 0.2.5, skills CLI 1.7.4.

## git

`git init -q` then `git symbolic-ref HEAD refs/heads/main`. The second command sets the initial branch on every git version, where `git init -b main` does not. The tool treats a directory as a repository only when `git rev-parse --show-toplevel` resolves to that directory itself; a project folder nested inside a parent repository still gets its own `git init`, which keeps the kickoff commit out of the parent.

Identity comes from `git config --get user.name` and `user.email`, never from `git var`, because an auto-generated `user@hostname` identity is a machine-local leak. Owners who set `user.useConfigOnly` and supply the email through `includeIf` rules per client directory will see `FAIL git user.email is not set` outside those directories; that is correct, and the fix is to set the email or move the project under the matching path.

## bd (Beads)

```
bd init --skip-agents --prefix <name> --non-interactive
```

- `--skip-agents` keeps `bd init` from writing `AGENTS.md`, `CLAUDE.md`, `.agents/skills/beads/`, `.claude/settings.json`, `.codex/` and `.cursor/`. The owner's installed Beads skill owns that guidance; a managed block in the instruction files would duplicate it and then drift from it.
- `--prefix` names issues `<name>-<hash>`.
- `--non-interactive` takes the maintainer defaults and never prompts.

What remains: `.beads/` with `config.yaml`, `metadata.json`, `README.md`, `.gitignore` and five hooks; `core.hooksPath` pointing at `.beads/hooks`; the Beads lines appended to `.gitignore`; and bd's own commit, `bd init: initialize beads issue tracking`. That commit sometimes fails (exit 128) when the repository has no commits and no identity yet; the kickoff commit covers whatever is still staged.

`seed` uses `bd list --type epic --json`, `bd list --parent <id> --json` and `bd create --title ... --type epic|task --priority 2 [--parent <id>] --description ... --json`. The JSON from `bd list` has `id`, `title`, `issue_type` and `status`; children are found by listing with `--parent`, not by a parent field.

Do not run `bd setup codex --global` to supply the Beads skill. It writes bd's bundled skill over `~/.agents/skills/beads`, which the owner installs from `steveyegge/beads` with the skills CLI, and `bd setup codex --check` will report that copy as stale. Leave it.

The per-project `bd prime` SessionStart hook in `.claude/settings.json` is deliberately not written. The owner's global Claude Code settings carry it. A collaborator without the global hook runs `bd setup claude` in the project for the hook only.

## Existing hooks

`init` stops with `ASK` when the project already has `.git/hooks/pre-commit` or a `core.hooksPath` that is not `.beads/hooks` (husky, the pre-commit framework, a hand-written hook), because `bd init` would set `core.hooksPath` and the existing hooks would stop running. The usual resolution, after the owner agrees: let `bd init` run, then make the existing tool's hook chain the Beads hook, or append to `.beads/hooks/pre-commit`, outside the beads-managed markers, a line that runs the previous hook:

```sh
# --- previous pre-commit hook, chained ---
sh "$(git rev-parse --show-toplevel)/.husky/pre-commit" "$@" || exit 1
```

## cm (cass-memory)

```
cm init --repo --no-interactive
```

Creates `.cass/playbook.yaml` (project rules, merged over the global `~/.cass-memory/playbook.yaml`) and `.cass/blocked.log`. Both are committed. `cm` reads its global configuration from the home directory; on a machine where `cm init` has never run globally, run it once first.

## npx skills (the Beads skill)

```
npx skills add steveyegge/beads --skill beads --global -y
```

Installs the Beads skill to `~/.agents/skills/beads` and links it for every agent the skills CLI knows about, including Claude Code via `~/.claude/skills/beads`. `preflight` runs this only when `~/.agents/skills/beads/SKILL.md` is absent and `npx` is on PATH; on a dry run it prints the command and does nothing. Without `npx` it reports `SKIP` with the command for the owner.

## The documentation gate

`gate` appends `assets/pre-commit-gate.sh` to `.beads/hooks/pre-commit` after the `END BEADS INTEGRATION` marker. bd rewrites only the text between its markers on `bd hooks install`, so the gate survives upgrades. The block runs `python3 scripts/check_docs.py --staged`, which checks exactly the index snapshot being committed, and fails the commit on findings. `gate` refuses to install while the checker fails, so an adopted project is never left unable to commit over a rule the owner has not acted on.
