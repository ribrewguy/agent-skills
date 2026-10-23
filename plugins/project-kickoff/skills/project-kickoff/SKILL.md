---
name: project-kickoff
description: "Use when kicking off, starting, scaffolding or setting up a new project or repository, or bringing a young existing project up to the owner's kickoff standard. Stands up git, Beads with bd init --skip-agents, cass-memory, byte-identical CLAUDE.md and AGENTS.md, the documentation tree (business-only PRD, decision register with statuses, vendor-neutral architecture, feature designs, research), a documentation checker and a pre-commit gate, through the project-kickoff tool with --dry-run on every writing step. Enforces no dates in filenames, decisions tracked in Beads under an open-decisions epic, and review records kept out of source control. Symptoms: a dated spec filename, instruction files that differ, a Beads managed block inside CLAUDE.md, a project with no tracker or memory. Not for choosing a stack or scaffolding application code."
---

# Project kickoff

## Overview

Every project should start with the same shape, so any agent opening it (Claude
Code, Codex, Cursor) finds the same places for business rules, technical
decisions, architecture, feature designs and research, the same tracker, and the
same two identical instruction files. The shape is cheap on day one and
expensive on day ten.

The drift happens on day one. A project kicked off by hand in the morning had,
by the afternoon, a spec at `docs/specs/2026-03-14-...-design.md` and a
`CLAUDE.md` that disagreed with its `AGENTS.md`, because `bd init` wrote one and
a person wrote the other. This skill exists so that never happens again.

The plugin has two parts. The `project-kickoff` tool does the mechanical steps
the same way every time, checking before every write. This skill owns the
judgment: the inputs, what to do with every `ASK`, and the adopt-mode decisions.

## The rule

**A project is kicked off with `project-kickoff all`, and nothing that tool
would write is written by hand first.**

## Inputs

Three things. Derive what you can, ask only for the rest.

| Input | Source |
|---|---|
| Project name | The directory name, as a slug (`demo-app`). It becomes the Beads prefix and appears in titles. Pass `--name` only when the directory name is not the project name. |
| Purpose | One sentence for `README.md` and the PRD header. Ask if the conversation has not supplied it. |
| Parent instructions | Detected: an `AGENTS.md` or `CLAUDE.md` one directory up. When present, the instruction files get a parent-prerequisite section with the worktree-aware path. `--parent no` suppresses it; `--parent yes` fails if none is found. |

## Fresh kickoff

Run from the project directory (which may be empty), with the tool from this
plugin's `scripts/` directory:

```bash
project-kickoff all --purpose "<one sentence>" --dry-run
project-kickoff all --purpose "<one sentence>" --trailer "<attribution line>"
```

Read the dry run before the real run. The steps, in order, each a subcommand you
can also run alone:

1. `preflight`: git, bd, cm, python3 on PATH; git `user.name` and `user.email`
   from config; the Beads skill at `~/.agents/skills/beads`. A missing skill is
   installed with `npx skills add steveyegge/beads --skill beads --global -y`,
   never with `bd setup`. Missing `bd` or `cm` is a `SKIP` with the dependent
   steps listed, not a stop.
2. `init`: `git init` on `main` when there is no repository here (a parent
   repository does not count); `bd init --skip-agents --prefix <name>
   --non-interactive` when there is no `.beads/`; `cm init --repo` when there is
   no `.cass/`.
3. `write`: `CLAUDE.md` rendered once and copied byte for byte to `AGENTS.md`;
   the seven seed documents; `scripts/check_docs.py` and its tests; the
   gitignore lines. Existing files are kept, never overwritten.
4. `gate`: runs the checker and, only when it passes, appends the documentation
   gate to `.beads/hooks/pre-commit` after the beads-managed markers.
5. `seed`: creates the `Open decisions` epic and one `Decide: <concern>` child
   per `unresolved` row of the technical decision register, then replaces the
   `<open-decisions-epic>` placeholder in both instruction files and the README.
6. `commit`: checker and its tests must pass; then one commit, `chore: kick off
   <name>`, with the trailer lines you passed. No push, no remote.

`bd init` makes a commit of its own first. That is expected; the kickoff commit
follows it.

## Reading the output

One line per fact or action.

| Kind | Meaning | You do |
|---|---|---|
| `OK` | A fact checked out, or an action succeeded. | Nothing. |
| `KEEP` | Something already existed and was left alone. | Nothing. |
| `WRITE`, `RUN` | A file written or a command run (on a dry run: would be). | Read them before the real run. |
| `SKIP` | A step could not run and says why. | Report it to the owner at the end. |
| `ASK` | The tool found something only the owner can decide. | Stop. Put the question to the owner. Do not work around it. |
| `FAIL` | A precondition failed or a command errored. | Fix the cause; rerun the step. |

Exit code 0 means nothing needs the owner, 2 means at least one `ASK`, 1 means
at least one `FAIL`. `all` stops at the first step that is not 0.

## Adopt mode

The same steps run in a project that already exists; the difference is what
each check finds. Order:

1. `project-kickoff all --purpose ... --dry-run` is the gap report. Read it to
   the owner: what differs, what is missing, what is dated.
2. Run the real steps. The tool adds what is missing (checker, `.cass/`,
   gitignore lines, missing seed documents and indexes) and keeps everything
   that exists. It stops with `ASK` on an instruction-file pair that differs or
   is half present, and on an existing hook setup that `bd init` would
   displace.
3. Resolve each `ASK` with the owner. For instruction files, propose a merged
   file: keep the owner's project-specific rules, replace any Beads managed
   block with the pointer in the Local tooling section, keep the universal
   hard rules. Write both copies only after the owner says yes. For a dated
   filename, propose the stable name and rename only on a yes.
4. `gate` installs the pre-commit gate only once `check_docs.py` passes, so a
   rule the owner has not acted on cannot block their commits. There is no
   exemption list: a dated file is fixed by renaming, never by excusing it.
5. `commit` when the checker is green.

When nobody can answer an `ASK`, finish every step that does not touch existing
tracked content, leave the proposals in your report as the first thing the
owner does, and do not install the gate.

## The hard rules every project gets

Written into the instruction files, enforced by `scripts/check_docs.py` where a
script can enforce them:

1. `CLAUDE.md` and `AGENTS.md` identical; project-specific rules only.
2. The PRD holds business rules only.
3. Technical choices live in the development policies with a status of exactly
   `required`, `selected`, `proposed` or `unresolved`.
4. Architecture is vendor- and library-neutral.
5. One discrete design document per feature; research is evidence, not authority.
6. No date in any filename.
7. Open decisions are children of the open-decisions epic in Beads.
8. Review records stay out of source control; outcomes go on the Beads task.

A `### Project-specific rules` subsection starts with "None yet". Architecture
style, standards hierarchies, edition boundaries and stack mandates belong
there, per project, never in this skill.

## What this skill never does

- Choose a language, framework or build tool. The register rows start
  `unresolved` and become `Decide:` tasks.
- Scaffold application code, CI, a remote, branch protection or deployment.
  Other skills own those.
- Write a Beads managed block into the instruction files, or run `bd setup
  codex --global`, which replaces the owner's installed Beads skill with the
  bd-bundled one.
- Overwrite, merge or rename an existing tracked file without the owner's yes.
- Write the per-project `bd prime` SessionStart hook. The owner's global Claude
  Code settings carry it; a collaborator without it runs `bd setup claude`.
- Put a real project, client or issue id into an example. Examples here use
  `demo-app` and `demo-abc`.

## Red flags

| Thought | Reality |
|---|---|
| "bd init already wrote AGENTS.md, I'll add to it" | It wrote the managed block. Use `--skip-agents`; the Beads skill owns that content. |
| "I'll put the design in docs/specs/2026-..." | Dated filename. The gate refuses the commit; name it for what it is. |
| "CLAUDE.md is for Claude, AGENTS.md can be shorter" | Same file, different readers. A rule missing from one is missing for one agent, silently. |
| "The stack is obvious, I'll fill in the register" | It is `unresolved` until the owner says otherwise. A guess with a status is a decision nobody made. |
| "This directory has a README already, start over" | Keep it. The tool reports what differs; propose, get a yes. |
| "The ASK is trivial, I'll decide it" | An ASK is by definition the owner's. Stop and ask. |

## Verification

| Check | Command | Passing looks like |
|---|---|---|
| Rerun is quiet | `project-kickoff all --purpose ...` a second time | No `WRITE` or `RUN` lines; exit 0 |
| Pair identical | `cmp CLAUDE.md AGENTS.md` | No output |
| Documentation rules | `python3 scripts/check_docs.py` | `PASS: instruction parity, ...` |
| Gate installed | `grep -c "PROJECT KICKOFF DOCUMENTATION GATE" .beads/hooks/pre-commit` | `2` |
| Decisions tracked | `bd list` | `Open decisions` epic with one child per unresolved row |
| Placeholder gone | `grep -r "<open-decisions-epic>" CLAUDE.md AGENTS.md README.md` | No output |

## References

- `references/instruction-files.md`: both rendered variants of the instruction
  file (with and without a parent), the worktree path rule, and how to propose
  a merge when files already exist.
- `references/doc-tree.md`: every seed document as rendered, the register
  vocabulary, and how a feature design is added.
- `references/tools.md`: the exact `git`, `bd`, `cm` and `npx skills` commands
  the tool runs, why each flag, what each writes, and the failure cases seen.
