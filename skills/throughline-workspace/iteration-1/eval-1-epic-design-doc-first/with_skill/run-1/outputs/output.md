Here is the exact sequence I'd follow, in order, with where each step happens. The shape of the whole thing is driven by two rules: this is an epic (multi-task effort), so the epic scaffolding is created centrally on the trunk *before* any work begins; and a design document **is** work, so the worktree is created before the first authored file — the main checkout is only a surface for tracker commands and `git worktree add`, never for authoring.

One caveat up front: a design doc sits *below* requirements and architecture in the source-of-truth ladder. If the repo has no PRD or architecture guardrails covering session handling, I stop at step 2 and ask you where intent lives (or whether capturing requirements is itself the first child task) rather than inventing them inside the design doc.

---

## Phase 0 — Orientation (read-only, main checkout)

**Step 1 — Load context.** In the main checkout on `develop`: load any recorded procedural memory for this repo, and locate the governing documents — the requirements/PRD covering authentication or session handling, and the architecture spec (commonly under `docs/prds/` and `docs/architecture/`, but I adopt whatever layout the repo uses). I read both and will cite file + section in the kickoff. No files are written or edited in this phase.

**Step 2 — Escalate any gap or conflict.** If requirements or architecture are missing or contradict the migration's premise (e.g., an architecture doc that mandates server-side sessions), I quote the conflict and stop for your decision. I never silently resolve it and never modify those documents without your explicit permission.

## Phase 1 — Epic scaffolding (tracker + main checkout, on the trunk)

**Step 3 — Create the epic (tracker).** Create the parent task: *"Migrate session handling from server-side sessions to JWTs"*, with the scope and acceptance criteria we know today. Call its id `proj-100`.

**Step 4 — Create the design task as its first child (tracker).** One child task: *"Design document: JWT migration plan"* → `proj-101`, parented to `proj-100`. No other children yet — the implementation breakdown is an *output* of the design doc, so those child tasks get created after the design is accepted, not now.

**Step 5 — Claim the design task atomically (tracker).** Claim `proj-101` so no other agent picks it up. (With a Beads-style tracker: `bd show proj-101` then `bd update proj-101 --claim`; with Jira/Linear/GitHub Issues, the equivalent assign + move to in-progress.)

**Step 6 — Commit only the scaffolding to `develop` (main checkout).** If the tracker persists state in the repo (e.g., a Beads database), commit exactly that scaffolding — the epic and design task records — directly on `develop` in the main checkout, so both tasks exist centrally before any worktree work begins. If the tracker is external (Jira, Linear), there is nothing to commit and this step is a no-op. Either way, **nothing else** lands on the trunk: no docs, no stubs, no placeholder directories.

## Phase 2 — Kickoff (conversation + main checkout)

**Step 7 — Emit the kickoff declaration (conversation).** Before any authored file exists:

```
### Kickoff Declaration
- Process: single-agent
- Requirements: docs/prds/auth-session-management.md §<section>   (as found in step 1)
- Architecture: docs/architecture/authentication.md §<section>   (as found in step 1)
- Parent task: proj-100
- Task: proj-101
- Worktree: .worktrees/jwt-migration-design/
- Branch: feature/proj-101_jwt-migration-design
- Integration target: develop
```

The design task itself is single-agent work; the multi-agent question (orchestrator + workers, an `integration/proj-100_*` branch) is deferred until the design doc defines the implementation slices.

**Step 8 — Create the branch and worktree (main checkout).**

```bash
git worktree add .worktrees/jwt-migration-design -b feature/proj-101_jwt-migration-design develop
```

(`.worktrees/` is the default location at the project root and belongs in `.gitignore`; a repo-specific convention wins if one exists.) This is the last thing the main checkout does. From here on, every file write and every command runs inside the worktree — as a single `cd /abs/path/.worktrees/jwt-migration-design && <command>` invocation each time, since working directory doesn't persist between tool calls.

## Phase 3 — Author the design document (worktree only)

**Step 9 — Write the doc (worktree file writes).** Author the design document inside the worktree, in the repo's established location for feature/design specs (e.g., `docs/features/jwt-session-migration.md`). Content: current-state analysis of the session code (read from the worktree's checkout), target JWT architecture, migration phases with rollback points, token/refresh/revocation strategy, security considerations, and — critically for the epic — the proposed breakdown into implementation child tasks. Anything already written accidentally in the main tree beforehand would be moved in via patch/stash, never branch-and-committed from the main checkout. No disposable environment is needed for a doc-only deliverable; if the design work turns out to need one (e.g., prototyping against a schema change), it gets stood up fresh and torn down at closeout — the shared local environment stays trunk-parity, always.

**Step 10 — Run quality gates (worktree).** Whatever the project's stack policy defines for docs — markdown lint, link check, spell check, or the standard gate suite if it runs repo-wide. I report concrete pass/fail results, not "looks fine."

**Step 11 — UAT check (conversation).** A design doc has no externally visible runtime behavior, so no UAT environment gate applies — but the review-before-commit question is still yours: if you want to read the draft before it's committed, say so now and I hold the commit.

## Phase 4 — Commit (worktree)

**Step 12 — Commit on the feature branch (worktree).** Conventional Commit, multi-paragraph body explaining what and why, task id, co-author line:

```
docs(auth): add JWT session migration design document (proj-101)

Lays out the migration plan from server-side sessions to JWTs:
current-state analysis, target token architecture, phased rollout
with rollback points, and revocation/refresh strategy.

Defines the proposed implementation task breakdown for epic
proj-100 so child tasks can be scaffolded once the design is
accepted.

Refs: proj-101

Co-authored-by: <model name and version> <noreply@anthropic.com>
```

**Step 13 — Publication decision + evidence block (worktree/conversation).** A single-agent `feature/*` branch stays local by default; I publish only if you want remote visibility or PR review. Then I emit the pre-integration evidence block:

```
Branch: feature/proj-101_jwt-migration-design
Local SHA:  <hash>
Remote SHA: not published
Gates:      markdown-lint=PASS link-check=PASS
git status: clean
```

**Step 14 — Implementation summary (conversation).** The structured summary — process used, task scope (`proj-101`), implementation outcome, behavioral impact, risks/gaps, file references, governance status — ending at exactly: **"ready to merge into `develop`, awaiting your acceptance."** And it stops there.

---

## What deliberately has *not* happened at this point

- **No merge to `develop`.** Passing gates aren't acceptance; you acknowledging the summary isn't acceptance. The merge happens only when you explicitly say to merge.
- **`proj-101` is not closed.** It closes only after its branch actually lands on `develop` — never before.
- **`proj-100` stays open** for the life of the epic.
- **The worktree stays up** until the same closeout as the merge, at which point cleanup runs in order: worktree removal first, then local branch deletion (git refuses the reverse order), then remote branch if published.

Once you accept and the design lands, the accepted doc drives the next tracker step: scaffolding the implementation child tasks under `proj-100`, and deciding single-agent vs. multi-agent topology (with an `integration/proj-100_*` branch if we go multi-worker) per the breakdown the design defines.
