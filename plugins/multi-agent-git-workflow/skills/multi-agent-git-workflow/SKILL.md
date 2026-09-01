---
name: multi-agent-git-workflow
description: "Use when coordinating git across multiple AI agents (orchestrator + N workers), or authoring commits in any context. Covers branch hierarchy (main/develop/integration/feature), worktree-per-agent topology (multi-agent MUST use worktrees), orchestrator-vs-worker roles, merge authority (workers MUST NOT merge their own branches), acceptance/rejection rules, plus commit discipline (Conventional Commits, mandatory task ID, co-author line, UAT gate, no silent amends). Symptoms, multiple agents in same worktree, workers self-merging, orchestrator silently fixing worker defects, commits without task IDs, silent amends, integration branches drifting from epic design."

---
# Multi-Agent Git Workflow

## Overview

Discipline for the git/branch/worktree layer when work is split across multiple AI agents (one orchestrator + N workers), and the universal commit-format rules that apply whether the work is single-agent or multi-agent.

Two distinct concerns covered together because they're the same git-author moment:

1. **Multi-agent topology**, how branches, worktrees, and roles are arranged so multiple agents don't trip over each other and so integration is auditable.
2. **Commit discipline**, Conventional Commits, mandatory task ID, co-author line, UAT gate ceremony, no silent amends.

The 3-tier promotion (`develop` → `uat` → `main`), UAT branch as a long-lived environment, CI gate matrix, source-ref enforcement, and pre-commit hook setup are in the **branch-promotion-discipline** skill, this skill stays in the multi-agent + commit-format lane.

## Tooling and dependencies

### Required

- **Git** with **Git worktrees** support. The whole multi-agent topology is built on worktrees; you can't run two agents in the same checkout safely.
- **A task tracker** that issues task IDs the branch names and commits reference. Examples: [Beads](https://github.com/gastownhall/beads), GitHub Issues, Linear, Jira, Shortcut. Single-agent work can run with no tracker if commits reference the change's intent some other way, but multi-agent topology depends on stable task IDs to anchor `feature/<id>_<short_name>` branches.

### Strongly recommended

- **A code-hosting platform with PR review** (GitHub, GitLab, Bitbucket). Acceptance into integration / develop normally happens via a published branch + PR, not just a local merge.
- **A way to invoke other agents from within an agent's session** if the multi-agent topology is implemented with N independent AI agents (e.g., `claude --print` for sub-claudes, `codex exec`, etc.). The skill is also valid for human-orchestrator + AI-worker topologies; the role definitions don't change.

### Optional

- [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) tooling (`commitlint`, `cz-cli`, etc.), the format is required either way, the tooling just helps enforce it.

### Composes with

- [`task-handoff-summaries`](../../../task-handoff-summaries/skills/task-handoff-summaries/SKILL.md), the worker handoff and orchestrator close-out summaries reference this skill's role and branch vocabulary directly. The two skills are designed to be used together.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md), when an orchestrator reviews a worker's branch (or a PR is reviewed before a develop merge), the review uses that format.
- [`cross-agent-review`](../../../cross-agent-review/skills/cross-agent-review/SKILL.md), high-stakes branches benefit from cross-vendor review before integration.
- `branch-promotion-discipline`, the layer above this one: 3-tier promotion (`develop` → `uat` → `main`), UAT branch as a long-lived environment, CI gate matrix, source-ref enforcement.

## When to use

- Any time more than one AI agent is contributing code to the same deliverable. Multi-agent topology is mandatory in that case.
- Any commit, single-agent or multi-agent. The commit-format rules apply universally.
- When a coordinated epic is being split into parallel workstreams across worker agents.
- When you're handing a worker branch to an orchestrator for integration review (the handoff format is in `task-handoff-summaries`; the *what happens at acceptance* is in this skill).

## Branch hierarchy

Long-lived branches relevant to this skill:

- **`main`**, production branch.
- **`develop`**, long-lived integration branch. Internal review surface; the place implementation work lands before any further promotion.

The 3-tier extension (`main` ← `uat` ← `develop`) is in `branch-promotion-discipline`. Skills that need the 3-tier vocabulary should compose with that skill rather than re-derive it here.

Implementation branches:

- **`feature/<task_id>_<short_name>`**, implementation branch for a single task. One task = one feature branch. Always mapped 1:1, never reuse a feature branch for multiple unrelated tasks.
- **`integration/<parent_task_id>_<short_name>`**, intermediate integration branch for a coordinated multi-agent parent task. Used only when work is split across multiple worker agents under a shared epic.

`<short_name>` is a few-word slug describing the change. `<task_id>` is whatever the task tracker emits (`proj-42`, `ENG-123`, `#456`, etc.).

## Worktree discipline

**Multi-agent workloads MUST use Git worktrees.** Each implementation agent gets:

- An assigned task (one-per-agent, never assign the same worker task to two agents)
- A dedicated `feature/*` branch for that task
- A dedicated Git worktree checked out to that branch

Do not run multiple implementation agents in the same worktree. Do not assign multiple worker tasks to the same `feature/*` branch.

Single-agent work *may* use a standard checkout or a dedicated worktree, the choice is operational. Multi-agent work *must* use dedicated worktrees per agent.

### Where worktrees go

**`.worktrees/<short_name>/` at the repo root.** Resolve the location with this
order and nothing else:

1. An existing `.worktrees/` (or `worktrees/`) directory at the repo root — use it.
2. A repo policy naming a **specific path** — use that path.
3. Otherwise — **create `.worktrees/` and use it.** Then add it to `.gitignore`.

**There is no fourth branch. Never invent a location.** If you are about to
choose a path that came from your own judgement rather than one of the three
rules above, you have left the procedure.

**A repo that declines to mandate a location is NOT an override.** "This policy
does not mandate a filesystem location", "choose any location that keeps
worktrees outside each other and outside generated output", or any similar
permissive phrasing is the repo *delegating* the choice — and rule 3 is the
answer it delegates to. Only a repo naming a **specific** path overrides the
default. Read "absent a specific path" as covering both a silent policy and a
deliberately permissive one.

**The reason is discoverability, not tidiness.** Anyone — a person, a later
session, a cleanup script — must be able to find every in-flight worktree at one
predictable path relative to the repo, without running `git worktree list` and
without knowing what the last agent decided. A sibling directory
(`../<repo>-wt/`, `../worktrees/<name>/`) keeps worktrees out of each other and
out of generated output just as well, and is still **wrong**: it is not
discoverable from the repo, so it fails the only requirement that matters. Do
not evaluate a candidate location against the tidiness benefits — evaluate it
against "would someone find this without being told".

**Verify after creating**, in the same step: the path is under the repo root,
and `git check-ignore .worktrees` reports it ignored. A worktree in the right
place but tracked will be committed by the next `git add -A`.

### Run commands from the worktree that owns the work

Most dev and stack tooling resolves its config by walking up from the **current
directory**, so the identical command means different things depending on where
you run it — and its output usually doesn't say which one it picked. Two
consequences:

- **Two shell invocations is the bug.** `cd .worktrees/<short>` in one tool call
  and `<command>` in the next runs in the main checkout: an agent's working
  directory does not survive between tool calls. Write it as ONE command:
  `cd /abs/path/to/repo/.worktrees/<short> && <command>`. This is the actual
  failure mode; it is not forgetfulness, and re-reading the rule does not
  prevent it.
- **The main checkout is not a launch surface** while worktree work is in
  flight. A dev server started there will also drag every sibling worktree under
  `.worktrees/` into its file scans, which is its own resource problem.

## Multi-agent roles

A multi-agent workload exists when more than one implementation agent contributes code or policy changes to the same deliverable.

Every multi-agent workload has **exactly one orchestrator**.

- **Default:** the top-level agent that starts the workload is the orchestrator unless the user explicitly assigns a different owner. The bead's DESIGN section, the kickoff declaration, or user instructions can reassign.
- **Workers** must assume they are not the orchestrator unless the governing task or kickoff explicitly says so.

### Orchestrator's job

- Owns the parent task / epic.
- Owns the `integration/*` branch (if one exists for the workload).
- Resolves merge conflicts and makes integration-only changes on the integration branch.
- Does **NOT** implement worker-scoped functionality on the integration branch unless ownership is explicitly reassigned or a new task is created for that work.
- Reviews worker handoffs, accepts or rejects with explicit notes.

### Worker's job

- Implements exactly one task slice on a dedicated `feature/*` branch in a dedicated worktree.
- Hands off the branch to the orchestrator with a worker handoff summary (see `task-handoff-summaries`).
- Does **NOT** merge their own branch into integration, develop, or main.
- Stays in their lane, doesn't fix things outside their assigned slice unless the orchestrator explicitly delegates.

## Merge authority

The merge-authority rules are the load-bearing discipline of multi-agent topology:

- **Workers MUST NOT merge their own `feature/*` branches** into:
  - another worker branch
  - an epic `integration/*` branch
  - `develop`
  - `main`
- **Only the orchestrator** merges accepted worker branches into the coordinated integration branch.
- **For single-agent work**, the implementing agent is also the integrator for that single branch and may merge `feature/*` → `develop` once governance requirements pass **and the user has accepted the work** (see below).

The reason workers can't merge themselves is the same reason any code-review system has authors-not-merging-their-own-PRs: integration topology is a coordinated decision, not a per-worker one. Workers integrating themselves leads to silent re-orderings, conflict-mediation drift, and lost orchestrator visibility into what landed when.

### The user's acceptance is a separate gate

**Nothing merges into the integration trunk (`develop`, or `main` in a
single-trunk repo) without the user's explicit acceptance.** Unconditional, every
time, whether or not the change is externally visible.

None of the following is acceptance:

- Passing quality gates, CI, or a review
- The user approving the task at kickoff
- The user acknowledging your summary, or asking a follow-up question about it
- A closed task in the tracker
- Being the person authorized to perform the merge

Having merge *authority* is the ABILITY to merge; it is never the AUTHORITY to
decide it is time. Deliver the implementation summary, state that the branch is
ready to merge, and **stop until the user says to merge it**.

**Orchestrator acceptance is not the user's acceptance.** When an orchestrator
accepts a worker branch, that authorizes exactly one thing: integrating that
branch into the epic `integration/*` branch and cleaning up that worker's branch
and worktree. Merging the epic into the trunk still requires the user's explicit
acceptance.

When a merge is gated on UAT, UAT runs on an isolated environment or a preview
deploy **before** the merge — never by merging first and verifying on the trunk
afterwards.

## Acceptance and rejection

When a worker's branch is ready, the worker hands it to the orchestrator for integration review.

The worker branch **stays local by default** when the orchestrator can access it through the same repository and worktree set. The branch **MUST be published** when:

- The orchestrator needs remote access to the branch
- CI or branch-level review is required on that branch
- The user explicitly requires remote branch visibility or auditability
- The team needs a remote recovery point before integration

### Orchestrator's responsibilities at acceptance

- Attempt the merge into the integration branch
- Resolve integration order if multiple worker branches are pending
- Run required integrated quality gates
- Verify alignment with task design, architecture, and PRD scope
- Either **accept** the branch (merge it into integration) or **reject** it back to the responsible worker

### Mandatory rejection conditions

The orchestrator MUST reject a worker branch when integration fails because of:

- Merge conflicts
- Failing tests or other failing required gates
- Syntax, typecheck, build, or lint errors that violate required gates
- Divergence from the task design
- Divergence from architecture or PRD constraints

### Rejection discipline

Return rejection feedback as **explicit notes to the worker**, in the same format as `structured-code-review` if applicable.

**Don't silently fix worker-owned defects.** The temptation when an orchestrator can clearly see "the worker made a small mistake; I could just fix it on the integration branch" is exactly when the orchestrator/worker boundary breaks down. Either reassign ownership explicitly (the orchestrator takes the task), create a new task that the orchestrator owns, or return the branch to the worker with rejection notes. Silent fixes destroy the audit trail and erode the worker's ability to learn from feedback.

## Branch publication policy

Local-by-default protects two things: a clean remote branch list (no stale half-done work) and a clear "ready for review" signal (publishing means something).

Worker `feature/*` branches stay local by default. Publish only when one of the conditions in the acceptance section above applies.

Branches that *must* be published:

- The orchestrator's coordinated `integration/*` branch when it's the shared integration target across workers
- Any branch proposed for a PR review

Branches that *must* be cleaned up:

- Accepted worker `feature/*` branches after they're merged into integration (orchestrator deletes locally and on remote if published)
- Stale multi-agent worktrees no longer needed

## Conventional Commits + Task ID + Co-Author

Every commit follows this discipline, regardless of single-agent or multi-agent context.

### Format

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), `<type>[optional scope]: <description>` on the subject line, blank line, multi-paragraph body explaining what changed and why.

```
feat(payments): add idempotent retry on transient processor failures

Adds retryWithBackoff helper that retries up to 3 times with the
schedule from the task design (250 / 500 / 1000 ms). Persists the
Idempotency-Key in the new idempotency_keys module before the first
attempt so retries survive in-process state loss.

Returns the original 5xx if all retries exhaust. 4xx responses
are surfaced immediately and not retried.

Refs: task-100

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Body requirements

- **Multi-paragraph body that explains what changed AND why.** A short summary alone is insufficient. Future readers (including future-you) need the *why* to evaluate whether the change is still appropriate.
- The *why* layer matters more than the *what*, `git diff` shows the *what* better than any prose can.

### Task ID required

Every commit MUST reference the task tracker ID it relates to.

- The ID SHOULD appear in the commit subject (preferred) or body (`Refs: <id>`).
- Commits without a task reference are invalid and must be corrected before pushing.
- If no applicable task exists, **don't commit**, inform the user and ask how to proceed. Default: create a miscellaneous task describing the change and associate the commit with it.

### Co-author line

Every commit produced with AI assistance includes a co-author line for the implementing model:

```
Co-authored-by: <Model name and version> <model-vendor-email>
```

Examples:

- `Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- `Co-authored-by: gpt-5.2-codex-max <codex@openai.com>`

Substitute the actual model name/version in use. The vendor email is the canonical contact for the model, not a personal email.

### Merge commits along the integration path

A merge into the integration trunk is the **tip commit of a deployment**. Most
hosting platforms show that subject line as the deployment's name, and it is the
raw material release notes are assembled from. Write it for someone scanning a
list of deployments, not for someone reading `git log` with the branch graph in
front of them.

**Subject line:**

```
<concise noun phrase naming the primary work> (<primary task id>)
```

- **Noun phrase, not a sentence.** Name the thing that shipped.
- **Capitalize the first word; no trailing period.** Proper nouns and acronyms
  keep their own case.
- **Target 50 characters, hard cap 72** — including the trailing task id. Past
  that the deployment list truncates, and the task id is what disappears.
- **Never prefix with `merge`, and never name the branch.** Git already records
  both parents; the branch name belongs in the body.
- **No Conventional Commits type prefix** (`feat:`, `fix:`, …). Types stay on the
  feature commits being merged. This is the sole exemption from the Conventional
  Commits rule above — it is *not* an exemption from task-id traceability.
- **Exactly ONE task id in the subject**: the primary one, in parentheses at the
  end. Every other id in the merge goes in the body.
- **Name the merge's primary work, not the branch's last commit.** A branch that
  fixed three things gets a subject naming the one that matters, never a
  concatenation of all three.

| Instead of | Write |
|---|---|
| `merge feature/t-4821_save-commit-ux — a committed change hides at once, the list refreshes once, and a clean save closes the form (t-4821)` | `Inline row detachment handling (t-4821)` |
| `merge feature/t-5107_assoc-row-shape — association rows display like every other row (t-5107)` | `Association row shape alignment (t-5107)` |
| `merge fix/t-6620_admin-reset-send — the admin-triggered password reset actually sends the email (t-6620)` | `Admin-triggered password reset delivery (t-6620)` |

**Body (required).** The detail the subject dropped moves to the body:

```
Inline row detachment handling (t-4821)

Branch: feature/t-4821_save-commit-ux
Tasks: t-4821, t-4822

- A committed change hides at once (t-4821)
- The list refreshes once, not per row (t-4821)
- A clean save closes the form (t-4822)
```

- The body MUST list **every** task id carried by the merge. An id reachable in
  neither subject nor body is a traceability violation, not a shortened message.
- One bullet per distinct outcome, phrased as the result.

**Scope.** This format applies to merges you author along the integration path
(`feature/*` → `integration/*`, `feature/*` → trunk, `integration/*` → trunk).

It does **not** apply to:

- **Bookkeeping merges** — pulling the trunk down into a working branch, or any
  fast-forward. Leave Git's generated message exactly as-is: those commits are
  never a deployment tip, and rewriting them adds noise without traceability.
- **Promotion merges** between long-lived tiers, which are PR-gated and carry a
  release subject instead (see `branch-promotion-discipline`).

### No silent amends

**Never amend a commit unless explicitly requested by the user.** Amending a published commit changes its hash and breaks anyone who has fetched it; amending an unpublished commit can lose work if a hook or pre-commit step partially completed.

If a pre-commit hook fails:

- The commit did NOT happen, the working tree is unchanged.
- `--amend` would modify the *previous* commit, not the failed one.
- Fix the issue, re-stage, and create a NEW commit.

## UAT gate (per-commit human approval ceremony)

The "UAT gate" is a per-change ceremony performed before commit when the change affects externally visible behavior. It is **distinct** from the long-lived `uat` branch in the `branch-promotion-discipline` skill.

- If changes affect externally visible behavior, **ask the user whether they want UAT before any commit**.
- If UAT is requested, **don't commit or push until UAT approval**.
- A passing UAT gate on a feature/integration branch is **not** equivalent to client acceptance on a UAT branch, those are two separate things even though both are sometimes called "UAT".

If your project doesn't have a long-lived UAT environment, the UAT gate ceremony still applies for any externally-visible-behavior change, it just gates the commit, not a downstream branch promotion.

## Push/merge discipline

- **Work is not complete until required pushes succeed.** Don't say "ready to push when you are", if policy and approval allow a push, perform it.
- If push fails, resolve the issue and retry until it succeeds.
- After UAT approval, publish the working branch when remote visibility is required and verify parity for any published branch.
- In multi-agent workloads, workers commit on their local `feature/*` branches for orchestrator review; they don't merge those branches forward themselves.
- The orchestrator MUST publish the coordinated `integration/*` branch when it's the shared integration target.
- For single-agent work, merge the `feature/*` branch into `develop` after all governance requirements pass **and the user accepts the work**.
- For epic work, merge accepted worker branches into the epic `integration/*` branch, then — **once the user accepts the epic** — merge the integration branch into `develop`.
- Never merge a `feature/*` directly to `main`. Never merge an epic `integration/*` directly to `main`. The 3-tier promotion that prevents this is in `branch-promotion-discipline`; the rule applies regardless.

## Close-out rules

Worker close-out **ends at orchestrator acceptance** into the correct integration branch. It does **not** include merging to `develop` or `main`. The worker's required artifact is the orchestrator-facing handoff summary (see `task-handoff-summaries`).

Orchestrator close-out for epic work ends after:

- All accepted worker branches are merged into the epic `integration/*` branch
- Integrated gates pass on the epic integration branch
- The user has accepted the epic
- The epic integration branch is merged into `develop`
- Branch cleanup is complete

Single-agent close-out ends after:

- The user has accepted the work
- The `feature/*` branch is merged into `develop`
- Branch cleanup is complete

### Branch cleanup

Clean up in the **same** close-out as the merge — the merge already carried the
user's acceptance, so nothing is left to hold the environment for. Deferred
cleanup is what leaves worktrees, branches, and disposable stacks strewn across
sessions.

Tear down in this order:

1. Any disposable environment the branch owned (database stack, preview deploy)
2. Verify the branch has been fully merged into its integration target
3. **Remove the dedicated worktree**
4. Delete the local branch
5. Delete the remote branch if it was published

**Worktree removal MUST come before branch deletion.** Git refuses to delete a
branch a worktree still has checked out (`error: cannot delete branch '<x>' used
by worktree at '<path>'`), so the reverse order fails every time.

**Never use a bare `git worktree remove` when the worktree ran long-lived
processes.** It deletes the directory and leaves that worktree's dev servers
running, holding recursive filesystem watchers on paths that no longer exist.
The bill is paid later, machine-wide, by an unrelated command dying with
`EMFILE: too many open files, watch`. Use the project's wrapper if it has one
(it should stop the processes first and refuse a dirty worktree); otherwise stop
the processes yourself, then remove.

Retaining an environment past close-out is the **exception** and requires an
explicit request from the user. You may propose it with a concrete reason; you
may not take it unilaterally. When retained, report it — path, branch, what is
running — so it stays visible instead of becoming cruft.

The orchestrator is responsible for deleting accepted worker `feature/*` branches during cleanup, both locally and on remote when those branches were published.

## Hard rules

- **Worktrees mandatory for multi-agent work.** One worktree per agent, no exceptions.
- **One implementation task → one feature branch.** Never reuse a worker `feature/*` for multiple unrelated tasks.
- **Workers don't merge their own branches** into anything other than (in single-agent contexts) `develop`.
- **Orchestrator doesn't implement on integration branches.** Reassign the task, create a new task, or return the branch to the worker.
- **Conventional Commits, task ID reference, and co-author line on every commit.** No exceptions besides merge commits.
- **No silent amends.** Hook failures mean the commit didn't happen, make a new commit, don't amend.
- **No "ready to push when you are."** If push is policy-allowed and approved, perform it.
- **No bypassing quality gates** on the integration target.
- **Nothing merges to the trunk without the user's explicit acceptance.** Passing gates are not acceptance.
- **Worktree removal precedes branch deletion.** The reverse order is refused by git.
- **Worktrees go in `.worktrees/`.** A repo declining to mandate a location is not an override; never invent a path.

## Don't cite this skill in the output

The skill is a reference for *you* (the agent or human running the workflow). The audience for branch names, commit messages, rejection notes, and close-out reports is the rest of the team, humans, future-you, and other agents reading the audit trail. Don't write "Per multi-agent-git-workflow's policy..." in a commit message or rejection note, write the reasoning directly.

## Adapter: Beads

If the project uses [Beads](https://github.com/gastownhall/beads) as its task tracker:

### Branch and task ID format

- Feature branches: `feature/<bead_id>_<short_name>`, e.g., `feature/proj-42_staging-branch`
- Integration branches: `integration/<parent_bead_id>_<short_name>`, e.g., `integration/proj-42_staging-bringup`
- Commit subjects: `<type>(<scope>): <description>` with `Refs: <bead_id>` in the body, or the bead ID inline in the subject (`feat(auth): proj-42 add session expiry check`)

### Atomic claim flow

```bash
bd ready                       # see ready beads
bd show <id>                   # read the bead's design
bd update <id> --claim         # claim the bead atomically
# ... implement on feature/<id>_<short_name> ...
bd update <id> --notes "..."   # progress notes
bd close <id>                  # close after orchestrator acceptance (NOT before)
```

Use `bd update <id> --status in_progress` (instead of `--claim`) only when you explicitly do not want Beads to change the assignee.

### Multi-agent bead topology

- Create a parent bead for the coordinated workload; assign the orchestrator to it.
- Create one child bead per worker-owned implementation slice; assign each to its worker.
- Don't reuse the same worker bead for multiple independent slices.
- Worker child beads remain `in_progress` until the orchestrator accepts the worker's branch into the required integration target. The worker doesn't close their own bead.
- The orchestrator closes accepted child beads after merging them into the integration target.
- The parent bead remains `in_progress` until all required child beads are accepted, the integration branch reaches its target (typically `develop`), and the integration workflow is complete.

Other trackers work the same way, substitute their issue ID format and adjust the lifecycle commands. The topology (parent task with N child tasks, one per worker) is the same shape regardless of tracker.

## Invocation examples

- "Set up the multi-agent topology for this epic, 3 workers."
- "I'm a worker, I just finished. What's the close-out flow?"
- "The orchestrator should review my branch, what's the handoff?"
- "Write the commit message for this change."
- "Reject this worker branch, the gates are failing." (uses this skill's rejection discipline + structured-code-review for the format)
- "Should this commit need a UAT gate before I push?"
- "How do I clean up after merge?"

## See also

- [`task-handoff-summaries`](../../../task-handoff-summaries/skills/task-handoff-summaries/SKILL.md), the worker handoff format and orchestrator close-out summary reference this skill's role and branch vocabulary.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md), the format for orchestrator rejection notes and PR reviews.
- [`cross-agent-review`](../../../cross-agent-review/skills/cross-agent-review/SKILL.md), when a worker branch goes through cross-vendor review before orchestrator acceptance, this is the workflow.
- `branch-promotion-discipline`, the next layer up: 3-tier `develop` → `uat` → `main` promotion, UAT branch as a long-lived environment, CI gate matrix, source-ref enforcement, pre-commit hook setup.
