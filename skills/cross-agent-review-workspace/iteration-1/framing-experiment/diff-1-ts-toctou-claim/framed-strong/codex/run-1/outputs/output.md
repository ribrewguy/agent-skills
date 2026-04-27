**Review Scope:** `claimBead(beadId, workerId)` implementation in `api/services/beads.ts`  
**Process Used:** Structured code review against provided design and acceptance criteria only  
**Execution Context:** Closed-context review; no tools, filesystem, or tests run  
**Integration Target:** Bead claim API  
**Governing Documents:** Provided “Bead claim API” design / acceptance criteria  
**Reviewer:** Codex  
**Severity Scale:** Critical / High / Medium / Low as defined in request  
**Date:** 2026-04-27

**Critical Findings**

None.

**High Findings**

**api/services/beads.ts:12**

Problem statement: The claim operation is not atomic. The implementation first reads the bead with `findOne`, checks availability in application code, then updates by `id` only at line 22.

Why it matters: Under concurrent calls, two workers can both read the same bead while it is still `ready` and unassigned. Both will pass the check, both will execute the update, and both will return `{ success: true }`. The later update may overwrite the earlier assignee. This violates the explicit requirement that exactly one caller succeeds and all others return `unavailable`.

Source-of-truth reference: Acceptance criterion: “The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`.”

Proposed fix: Use a conditional atomic update that includes the claimability predicate:

```ts
const result = await db.beads.update(
  { id: beadId, status: 'ready', assignee: null },
  {
    status: 'in_progress',
    assignee: workerId,
    claimedAt: new Date(),
  },
)

if (result.modifiedCount === 1) {
  return { success: true, beadId, assignee: workerId }
}

const bead = await db.beads.findOne({ id: beadId })
return bead
  ? { success: false, reason: 'unavailable' }
  : { success: false, reason: 'not_found' }
```

Adjust the exact result field names to match the project’s DB adapter.

**Medium Findings**

None.

**Low Findings**

None.

Summary: The implementation matches the basic success, not-found, and unavailable branches in single-threaded execution, but it misses the core atomicity requirement. Passing unit tests likely means the concurrency case is not actually exercising simultaneous interleavings against the update predicate.
