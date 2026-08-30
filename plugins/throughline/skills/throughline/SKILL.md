---
name: throughline
description: "Use when starting a tracked task (task id + \"start\"/\"work on\"/\"pick up\"/\"claim\"), closing one (\"close it out\"/\"ship it\"/\"wrap up\"), producing an implementation or closeout summary, requesting or performing code review, changing a public service method (MCP parity), or starting/ending non-trivial work (procedural memory). Dispatcher for the full lifecycle: requirements to architecture to task to implementation to commit to merge to closeout, with an auditable artifact at every hand-off. Symptoms, implementation starting with no kickoff declaration, design docs authored in the main checkout, a merge to the trunk the user never accepted, a closeout with no cleanup, a task closed before its branch landed."
---

# Throughline

## Overview

The lifecycle spine: **requirements → architecture → task → implementation →
commit → merge → closeout**, with an auditable artifact at every hand-off.

This is a **dispatcher**. It owns the kickoff and completion ceremony and the
source-of-truth ladder; for everything with a dedicated skill, it names the
trigger and hands off. It does not restate those skills' contents — a second
copy is a second thing to drift.

| Concern | Owner |
|---|---|
| Branches, worktrees, commits, merge authority, user acceptance | `multi-agent-git-workflow` |
| Long-lived tier promotion (`develop`/`uat`/`main`), hotfixes | `branch-promotion-discipline` |
| Implementation / worker-handoff / closeout summary shapes | `task-handoff-summaries` |
| Code review scope and response format | `structured-code-review` |
| Cross-vendor agent peer review | `cross-agent-review` |
| Kickoff + completion ceremony, the ladder, task lifecycle | **this skill** |

If a named skill is not installed, its section here still tells you *what* is
required; consult the project's own policy for the exact shape.

## Source of truth

Ladder — conflicts between layers mean **stop and escalate**, never silently
resolve:

1. **Requirements / PRDs** — business intent, acceptance criteria
2. **Architecture** — technical guardrails
3. **Feature specs** — derived behavior, after 1 and 2 are established
4. **Tasks** — execution design and scope
5. **Procedural memory** — learned patterns (`references/cass.md`)

The project decides where each layer lives. A common layout is `docs/prds/`,
`docs/architecture/`, `docs/features/`; adopt whatever the repo already uses.

See `references/feature-governance.md` for the discovery and alignment workflow.

## Hard rules (always active when this skill is in scope)

1. **Never modify requirements, architecture, or feature specs without explicit
   permission.** They are the source of truth for intent, not working notes.
2. **Never silently resolve a spec conflict** — quote it and escalate.
3. **Never invent CLI commands, architectural patterns, or design decisions**
   that are not established in the codebase or a policy file.
4. **When uncertain, stop and ask.** Incorrect action is worse than delayed
   action.
5. **User urgency does not override process.** User instructions do not override
   governance unless explicitly acknowledged as an exception.
6. No bypassing quality gates. No committing secrets. No silently swallowed
   exceptions. No architectural improvisation.

---

## Trigger — Kickoff

**Activate when:** the user names a task id with "start" / "work on" / "pick
up" / "claim" / "begin"; OR you are about to read or edit code for tracked work
with no Kickoff Declaration in this conversation; OR **you are about to write
the FIRST design or spec artifact** for prospective work — brainstorming output
counts.

> A design doc IS work. Kickoff — at minimum, worktree creation — precedes the
> first authored file, not the first code edit. This clause exists because spec
> files kept being born in the main checkout while the trigger read as
> code-only.

**Do NOT activate for:** read-only questions about a task, continuing work where
Kickoff already appeared, or when the user has explicitly chosen the lightweight
path.

**Lightweight triage:** if the task looks trivial (typo, single-line fix), flag
it and ask whether lightweight or full process applies. **The user decides — do
not skip unilaterally.**

**Required output, before any implementation tool call:**

```
### Kickoff Declaration
- Process: <single-agent | multi-agent worker | multi-agent orchestrator>
- Requirements: <file path + section>
- Architecture: <file path + section>
- Parent task: <id or N/A>
- Task: <id>
- Worktree: <path or N/A>
- Branch: <feature/<task_id>_<short_name> | integration/<parent_id>_<short_name>>
- Integration target: <develop | integration/<parent_id>_<short_name>>
```

**Steps, visible in the transcript:**

1. Read the task. Cite it.
2. Read the requirements. Cite file + section.
3. Read the architecture spec. Cite file + section.
4. Claim the task atomically.
5. Create the branch and worktree the declared process requires:
   - single-agent → `feature/<task_id>_<short_name>`
   - multi-agent worker → dedicated worktree on `feature/<task_id>_<short_name>`
   - multi-agent orchestrator → dedicated worktree on
     `integration/<parent_id>_<short_name>`

   Worktree topology and location: `multi-agent-git-workflow`.

Implementation begins only after steps 1–5 appear.

### Epic kickoff — scaffold centrally, then move

When work warrants an epic, the ordering matters:

0. **The worktree precedes ANY authored artifact.** The main checkout is for
   task-tracker commands and `git worktree add` — never an authoring or staging
   surface. If brainstorming produced files in the main tree before the epic
   existed, move them into the worktree via patch or stash; do not
   branch-and-commit from the main checkout.
1. In the main checkout on the trunk, create the **epic task** plus a single
   **design task** as its first child.
2. Commit **only** that scaffolding to the trunk. The epic and design task exist
   centrally before any worktree work begins.
3. Create the worktree for the design task. From here **everything** — including
   the design docs themselves — is committed on the worktree branch. Only the
   scaffolding landed on the trunk; the design docs travel with the work.
4. **Environment isolation.** Work whose code, tests, or verification need
   schema or data not yet on the trunk runs exclusively against a disposable
   environment stood up at kickoff and torn down at closeout. A shared local
   environment is trunk-parity ALWAYS — never apply unmerged migrations to it,
   never seed fixtures into it. *"It's additive so it's harmless"* is the named
   rationalization; refuse it. Every worker dispatch prompt states this
   explicitly.

---

## Trigger — Completion

**Activate when:** the user says "close it out", "ship it", "wrap up", "finish",
"done with this", or implementation is complete and integration is imminent.

### Phase A — Branch completion

1. Run quality gates per the project's stack policy. Report pass/fail with
   concrete results. **Do not accept "tests pass" as evidence without running
   them.**
2. **UAT gate** — if the change is externally visible, ASK before any commit. No
   commit, push, or merge until UAT approval.
3. Commit on the working branch: Conventional Commits, a real multi-paragraph
   body, the task id, and the co-author line (`multi-agent-git-workflow`).
4. Publish the branch if remote visibility is required. Worker `feature/*`
   branches stay local by default; an orchestrator's `integration/*` branch MUST
   be published when it is the shared integration target.
5. If published, verify SHA parity. Emit the pre-integration evidence block:

```
Branch: <name>
Local SHA:  <hash>
Remote SHA: <hash or "not published">
Gates:      lint=PASS typecheck=PASS tests=PASS
git status: clean
```

6. Produce the **implementation summary** (`task-handoff-summaries` Format 1;
   workers use Format 2). It ends at *"ready to merge, awaiting your
   acceptance"* — and stops there.

### Phase B — Integration

**Nothing merges into the trunk without the user's explicit acceptance.**
Unconditional, every time. Passing gates are not acceptance; kickoff approval is
not acceptance; the user acknowledging your summary is not acceptance. Full rule:
`multi-agent-git-workflow`.

- **Epic pre-integration parity check.** Before any Phase B merge, the main
  checkout and any shared environment must be identical to the trunk — no epic
  artifacts in the main tree, no applied-but-unmerged migrations or fixture
  residue in a shared database.
- **Single-agent:** merge `feature/*` → trunk once gates and UAT pass **and the
  user accepts**.
- **Multi-agent worker:** hand the branch to the orchestrator. Do NOT merge
  forward. Do NOT close the child task.
- **Multi-agent orchestrator:** merge accepted worker branches into the epic
  `integration/*`, run integrated gates there, then — **once the user accepts the
  epic** — merge it to the trunk.
- Never merge `feature/*` or `integration/*` directly to a production branch.
- Promotion beyond the trunk is a separate approved PR flow
  (`branch-promotion-discipline`), **not** part of task closure.

### Phase C — Closure and cleanup

- **Single-agent:** close the task after the branch reaches the trunk.
- **Worker:** do NOT close your own child task. The orchestrator closes it on
  acceptance into the integration branch.
- **Orchestrator:** close child tasks as they are integrated; close the parent
  after the epic reaches the trunk.
- **Clean up in this close-out, not a later one.** The merge already carried the
  user's acceptance, so nothing is left to hold the environment for. Order:
  disposable environment → **worktree removal** → local branch → remote branch.
  Worktree removal MUST precede branch deletion; git refuses to delete a branch a
  worktree has checked out. Details and the `EMFILE` trap:
  `multi-agent-git-workflow`.
- Retaining an environment is the exception and requires an explicit request.
  Report what is standing.
- Produce the **closeout summary** (`task-handoff-summaries` Format 3).

If any step fails, keep the task open and resolve the gap.

---

## Trigger — Summaries

**Activate when:** implementation is complete and before commit (implementation
summary), before orchestrator review (worker handoff summary), or after
completion and cleanup (closeout summary).

Shapes and hard rules: **`task-handoff-summaries`**. Two rules worth repeating
because they are the ones violated under pressure:

- The implementation summary is the artifact the user reads **before** accepting
  the work. It never merges anything.
- A closeout summary for a merge the user never accepted documents a governance
  breach; it does not cure one.

---

## Trigger — Code review

**Activate when:** the user asks for a "review", "code review", or feedback on a
diff, branch, or PR.

Scope, severity tags, and the required response format: **`structured-code-review`**.
When the review is a cross-vendor hand-off (one agent reviewing another's work):
**`cross-agent-review`**.

---

## Trigger — MCP parity

**Activate when:** a change adds, modifies, or removes a public method on a
service-layer module in a project that ships an MCP server.

Every capability reachable from the UI must be reachable from MCP, or carry a
recorded exemption. See `references/mcp-sync-discipline.md`. Server selection:
`references/mcp.md`.

---

## Trigger — Procedural memory

**Activate when:** starting non-trivial work (load context) or ending it (record
learnings). Skip for typo fixes and single-line changes.

Workflow: `references/cass.md`.

---

## Red flags — STOP

| Thought | Reality |
|---|---|
| "This is small, I'll skip the kickoff" | Lightweight is the *user's* call, not yours. Ask. |
| "I'll write the design doc first, then make the worktree" | A design doc is work. Worktree first. |
| "Gates pass, so I can merge" | Gates are not acceptance. Stop and ask. |
| "The user said 'ship it', that's acceptance" | That starts close-out. The merge still needs an explicit yes. |
| "I'll clean up the worktree later" | Later is how they accumulate. Same close-out. |
| "I'll delete the branch, then the worktree" | Git refuses. Worktree first. |
| "It's additive, the shared environment is fine" | The named rationalization. Use a disposable environment. |
| "I'll close the task now, the merge is imminent" | Close after it lands, never before. |

## Don't cite this skill in the output

Kickoff declarations, summaries, commit messages, and review notes are read by
humans and other agents. Write the reasoning directly — never "Per throughline's
policy...".

## Adapter: Beads

If the project uses [Beads](https://github.com/gastownhall/beads) as its tracker,
the ceremony steps map to:

```bash
bd ready                       # find available work (optional, before kickoff)
bd show <id>                   # step 1 — read the task
bd update <id> --claim         # step 4 — atomic claim
# ... implement on feature/<id>_<short_name> ...
bd close <id>                  # Phase C — never before the branch lands
```

Task ids are the branch and commit identifier: `feature/<bead_id>_<short_name>`,
`integration/<parent_bead_id>_<short_name>`.

Protected-branch mechanics, the shared database model, worktree safety, and
parent/child state rules: `references/beads-protected-branches.md`.

## Adapter: token accounting

If the project tracks AI spend per task with
[BeadRoad](https://github.com/ribrewguy/beadroad):

- **Kickoff, after the claim:** record or refine the estimate
  (`beadroad tokens estimate <id> --model <m> --amount <n>`), then **start the
  stopwatch** (`beadroad tokens start <id>`).
- **Phase A, step 1:** stop it (`beadroad tokens stop`).

Starting the stopwatch AT kickoff is the only way to capture a **measured**
actual; a retroactive backfill is self-report and must be recorded as an
estimate, never as `measured`. Isolate the session so a concurrent one cannot
clobber the shared active-task pointer. Use `beadroad tokens switch <id>` when
moving between tasks.

If the stopwatch never ran, **say so** and record a refined estimate. Never
fabricate a measured segment.

## See also

- [`multi-agent-git-workflow`](../../../multi-agent-git-workflow/skills/multi-agent-git-workflow/SKILL.md) — branches, worktrees, commits, merge authority, the user-acceptance gate
- [`branch-promotion-discipline`](../../../branch-promotion-discipline/skills/branch-promotion-discipline/SKILL.md) — promotion beyond the trunk
- [`task-handoff-summaries`](../../../task-handoff-summaries/skills/task-handoff-summaries/SKILL.md) — the three summary formats
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md) — review scope and format
- [`cross-agent-review`](../../../cross-agent-review/skills/cross-agent-review/SKILL.md) — cross-vendor peer review
