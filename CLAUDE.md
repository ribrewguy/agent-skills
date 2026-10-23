# agent-skills agent instructions

This repository is the public source of the skills and plugins in the ribrewguy marketplace. These rules are specific to it; shared workflow guidance comes from the installed skills (throughline, beads, and the rest).

## Hard rules

1. Keep this file and `AGENTS.md` identical. Mirror every edit in the same change. The pre-commit gate refuses a commit where the staged pair differs.
2. **Nothing machine-local enters a commit.** No absolute home paths (`/Users/<name>`, `/home/<name>`, `C:\Users\<name>`), no per-machine temp or scratchpad paths (the macOS `var/folders` tree, the Claude Code scratchpad under `tmp/claude-<uid>`), no hostnames, no local settings (`.claude/settings.local.json`, `.env` and variants, editor state, `.DS_Store`), no per-machine tracker state. Scripts derive paths from their own location. When a published transcript must show a path, it uses the placeholders `/Users/user` or `/tmp/...`. `python3 tools/check_local_refs.py --staged` enforces this from the Beads pre-commit hook; fix the content rather than bypassing the hook. History was rewritten once, on 2026-10-23, to remove such paths and must not need it again.
3. Plans, designs and task status live in Beads (prefix `agent-skills`), never in markdown files in this repository. `tasks/` is gitignored scratch space, not a document store.
4. No project file has a date in its filename. Dates belong in content.
5. Every concrete example in a skill, reference, template, eval or docs page uses fictional names and placeholder ids. Nothing from a private project, client or tracker.
6. Every `SKILL.md` passes `python3 tools/check_skill_spec.py plugins/<plugin>` before it is committed: description 600 to 950 characters in double quotes with none inside, body at most 500 lines, no bare URLs, references never link to sibling references.
7. Evals are run only when the owner asks; they are expensive. Authoring eval cases is always fine.

## Repository layout

`plugins/<plugin>/` is the canonical source each AI tool loads. `skills/`, `evals/`, `concepts/`, `install/` and `index.md` are the GitHub Pages site. `tools/` holds repository checks and eval harnesses. See `README.md` for the per-plugin layout.

## Local tooling

Beads is initialised with prefix `agent-skills`; run `bd prime` for tracker context and `bd ready` for available work. Git hooks live in `.beads/hooks` through `core.hooksPath`; the local-content gate sits after the beads-managed markers in `pre-commit`, so `bd hooks install` preserves it.

Checks: `python3 tools/check_local_refs.py` (whole tree) or `--staged`; `python3 tools/check_skill_spec.py plugins/<plugin>`; `cd tools && python3 -m unittest -q test_check_local_refs test_check_skill_spec`. Plugin-specific tests live under `tools/<plugin>/`.
