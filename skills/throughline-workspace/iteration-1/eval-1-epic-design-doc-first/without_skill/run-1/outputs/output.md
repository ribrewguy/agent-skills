Here's the exact sequence I'd follow, from a clean checkout of `develop` to a committed design document. Each step names the operation and where it happens.

## Phase 1: Set up the work structure (tracker)

**1. Create the parent (epic) task — in the tracker.**
Create a task like "Migrate session handling from server-side sessions to JWTs" with the overall goal, motivation, and rough success criteria (e.g. "all session state carried in signed JWTs; server-side session store decommissioned"). This is the umbrella every child task will hang off.

**2. Create the first child task — in the tracker.**
Create "Write JWT migration design document" as a child of the epic. Set it in-progress and assign it to me/us. I record its ID (say `PROJ-124`) because I'll reference it in the branch name and commit message.

**3. Deliberately do *not* create the other child tasks yet.**
The design document is what will define the migration phases; creating implementation child tasks now would be guessing. I'd note in the epic description that further children will be broken out from the approved design doc. (If the team wants visible placeholders, I'd add coarse ones — "Phase 1: dual-issue tokens", "Phase 2: cut over reads", "Phase 3: decommission session store" — marked blocked-by the design task.)

## Phase 2: Prepare the workspace (git, in the repo terminal)

**4. Verify the checkout is truly clean and current.**
```bash
git status                 # confirm no stray changes
git fetch origin
git pull --ff-only origin develop
```

**5. Create a feature branch off `develop`.**
Even though this is "just a doc," it goes through the same review flow as code — I never commit directly to the trunk branch.
```bash
git checkout -b torr/PROJ-124-jwt-migration-design
```
The branch name carries the tracker ID so the tracker/git linkage is automatic if the tracker integrates with the forge.

## Phase 3: Research (read-only, in the working tree)

**6. Survey the current session implementation.**
Before writing a migration plan I read what exists: session middleware, cookie configuration, the session store (Redis/DB), logout/revocation paths, and anything that reads session state server-side (rate limiting, CSRF, admin impersonation, WebSocket auth). I also check where design docs conventionally live in this repo (`docs/`, `docs/adr/`, `docs/design/`, or an RFC template) and follow the existing convention rather than inventing one.

## Phase 4: Write the document (file write, in the working tree)

**7. Create the design doc file.**
For example `docs/design/jwt-session-migration.md` (or the repo's ADR/RFC format). Contents I'd make sure it covers:

- **Context & goals / non-goals** — why we're moving off server-side sessions; what's explicitly out of scope.
- **Current state** — how sessions work today, with pointers to the code found in step 6.
- **Proposed design** — token format and claims, signing algorithm and key management/rotation, access vs. refresh token strategy, storage on the client (cookie flags vs. headers), expiry choices.
- **The hard problems** — revocation/logout (the classic JWT weakness), token invalidation on password change, session data that doesn't fit in a token, CSRF posture changes.
- **Migration plan in phases** — each phase small, independently shippable, and reversible: e.g. (1) issue JWTs alongside sessions, (2) verify JWTs but still fall back to sessions, (3) switch reads to JWT-first, (4) stop creating sessions, (5) decommission the store. Each phase here becomes a child task later.
- **Rollback plan** per phase, **security considerations**, **observability** (metrics to watch during cutover), and **open questions** for reviewers.

**8. Checkpoint with the team/user before committing.**
Share the draft (or at least the outline and the open-questions list) and incorporate feedback. A design doc's value is agreement, not the file.

## Phase 5: Commit (git, in the repo terminal)

**9. Stage and commit exactly the doc.**
```bash
git add docs/design/jwt-session-migration.md
git commit -m "PROJ-124: Add JWT session migration design doc"
```
Commit message leads with the tracker ID so the child task links to the commit.

**10. Push and open a PR against `develop`.**
```bash
git push -u origin torr/PROJ-124-jwt-migration-design
gh pr create --base develop --title "PROJ-124: JWT session migration design doc" \
  --body "Design doc for the sessions→JWT migration epic. Closes nothing yet; child tasks will be created from the approved plan."
```

## Phase 6: Close the loop (tracker)

**11. Update the tracker.**
Paste the PR link into the design-doc child task and move it to in-review. Once the PR merges: mark the task done, then — and only then — break the approved migration phases out as the remaining child tasks of the epic, with blocking relationships matching the phase order.

### Summary of where things happen
| Step | Operation | Where |
|---|---|---|
| 1–3 | Create epic + design-doc child task | Tracker |
| 4–5 | Sync + feature branch off `develop` | Git (terminal) |
| 6 | Read existing session code & doc conventions | Working tree (read-only) |
| 7 | Write `docs/design/jwt-session-migration.md` | Working tree (file write) |
| 8 | Review checkpoint | With you/team |
| 9–10 | Commit, push, open PR to `develop` | Git (terminal) + forge |
| 11 | Link PR, move to in-review; spawn phase tasks after merge | Tracker |

The two ordering rules doing the real work: tracker structure exists *before* any git work (so every commit traces to a task), and implementation child tasks are created *after* the design doc is approved (so the plan drives the tasks, not the reverse).
