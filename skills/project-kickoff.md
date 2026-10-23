---
title: project-kickoff
parent: Skills
nav_order: 15
---

# project-kickoff

The first hour of a project, done the same way every time. One command stands up git on `main`, Beads, cass-memory, a byte-identical `CLAUDE.md` and `AGENTS.md`, a documentation tree with a business-only PRD and a technical decision register, a portable documentation checker and the pre-commit gate that runs it. The failure it targets is the project kicked off by hand in the morning that by the afternoon has a spec at `docs/specs/2026-03-14-...-design.md` and two instruction files that disagree, because `bd init` wrote one and a person wrote the other.

Like [local-https](local-https) and [isolated-stack-development](isolated-stack-development), it ships a skill and a tool together. The tool does the mechanical steps identically every run; the skill owns the inputs, the merge proposals and every decision the tool hands back as `ASK`.

## What makes this skill distinct

- **`bd init --skip-agents`, always.** The installed Beads skill owns the tracker guidance. A managed block inside `CLAUDE.md` duplicates it and then drifts from it, so the tool never lets `bd init` write instruction files.
- **One rendering, two files.** `CLAUDE.md` is rendered from a template and copied byte for byte to `AGENTS.md`. The checker fails any commit where the staged pair differs.
- **No date in any filename.** The checker recognises numeric, named-month and quarter forms (`2026-03-14`, `20260314`, `mar-2026`, `2026q1`) and refuses them from the pre-commit hook, in generated files too.
- **Decisions have a status.** The register uses exactly `required`, `selected`, `proposed` or `unresolved`; stack rows start `unresolved`, and `seed` turns each one into a `Decide:` task under an `Open decisions` epic in Beads. A recommendation never silently becomes a decision.
- **Idempotent, and honest about what it finds.** Every step checks before it writes and reports `OK`, `KEEP`, `WRITE`, `RUN`, `SKIP`, `ASK` or `FAIL`. A rerun is all `KEEP`. In an existing project the dry run is the gap report; differing instruction files and foreign hook setups come back as `ASK`, never as an overwrite.
- **The gate goes in last.** In an adopted project the pre-commit gate is installed only once the checker passes, so a rule the owner has not acted on cannot block their commits. There is no exemption list.

## What ships in the plugin

| Piece | What it does |
|---|---|
| `SKILL.md` | The rule, the inputs, the ordered steps, how to read the output, adopt mode, the eight universal hard rules, what the skill never does, red flags, verification. |
| `scripts/project-kickoff` | `preflight`, `init`, `write`, `gate`, `seed`, `commit`, `all`; every writing step takes `--dry-run`. Python 3.9 stdlib. |
| `assets/check_docs.py` and its tests | Instruction parity, portable local links and anchors, date-bearing filenames, index coverage, feature-design structure; `--staged` checks exactly the index snapshot being committed. |
| `assets/pre-commit-gate.sh` | The block appended to the Beads pre-commit hook, outside the managed markers so `bd hooks install` keeps it. |
| `assets/templates/` | The instruction file, the parent-prerequisite section, the README and the six seed documents. |
| `references/` | Both rendered instruction-file variants and the merge procedure; the documentation tree and register vocabulary; the exact `git`, `bd`, `cm` and `npx skills` commands with their failure cases. |

## Coverage limits

macOS with the system `python3` (3.9) is the target. `bd` and `cm` must be installed for the tracker and memory steps; without them those steps report `SKIP` and the rest proceeds. The tool's behaviour is covered by stub-based tests under `tools/project-kickoff/` plus one real-tool smoke run; the eval cases in `evals/evals.json` are written but have not been run, so no evaluation receipts are recorded.
