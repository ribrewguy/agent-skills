Review Scope: `claimBead(beadId, workerId)` implementation in `api/services/beads.ts`  
Process Used: Closed-context structured code review of provided diff/package only  
Execution Context: Static review; no tools, filesystem reads, or tests run  
Integration Target: Bead claim service API  
Governing Documents: Bead claim API acceptance criteria in review package  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as defined in request  
Date: 2026-04-27

**High Findings**

**H1: Claim is not atomic under concurrent callers**  
Citation: `api/services/beads.ts:14`, `api/services/beads.ts:23`

Problem statement: The implementation checks availability with `findOne`, then performs an unconditional `update` by `id`. Two concurrent callers can both read the bead while it is `ready` and unassigned, then both update it and both return `{ success: true }`.

Why it matters: This directly violates the atomicity acceptance criterion: under concurrent calls for the same `beadId`, exactly one caller should succeed and all others should receive `{ success: false, reason: 'unavailable' }`.

Source-of-truth reference: Acceptance criteria: “The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`.”

Proposed fix: Make the write itself conditional and check the affected row/document count. For example, update with a predicate like `{ id: beadId, status: 'ready', assignee: null }`. If the update count is `1`, return success. If it is `0`, perform a follow-up existence check to distinguish `not_found` from `unavailable`.

**H2: Function can report success even if the update did not actually claim the bead**  
Citation: `api/services/beads.ts:23`, `api/services/beads.ts:32`

Problem statement: The result of `db.beads.update(...)` is ignored. If the update affects zero records because the bead was deleted or changed between the initial read and update, the function still returns success.

Why it matters: The success response is supposed to mean the claim succeeded and the bead is now `in_progress` with the requested assignee. Returning success without verifying the write result can create silent state inconsistency for callers.

Source-of-truth reference: Acceptance criteria: “Returns `{ success: true, beadId, assignee: workerId }` if the bead was claimable AND the claim succeeded.”

Proposed fix: Use the update result as the source of truth. Return success only when the conditional update modifies exactly one bead. Otherwise, re-read by `id` and return `not_found` or `unavailable`.

**Medium Findings**

None.

**Low Findings**

None.
