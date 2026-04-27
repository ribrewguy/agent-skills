**Review Scope:** `api/services/beads.ts`, new `claimBead(beadId, workerId)` function  
**Process Used:** Closed-context structured code review from provided package only  
**Execution Context:** No commands run; tests not executed by reviewer  
**Integration Target:** Bead claim API  
**Governing Documents:** Provided design and acceptance criteria  
**Reviewer:** Codex  
**Severity Scale:** Critical / High / Medium / Low as defined in request  
**Date:** 2026-04-27

**Critical Findings**

No findings.

**High Findings**

**H1: Claim operation is not atomic**  
**Citation:** `api/services/beads.ts:14`, `api/services/beads.ts:20`  
**Problem Statement:** The implementation checks availability with `findOne`, then performs an unconditional `update` by `id`. Two concurrent callers can both read the bead as `ready` and unassigned before either update commits, then both return `{ success: true }`.  
**Why It Matters:** This directly violates the atomicity requirement: “under concurrent calls for the same beadId, exactly one caller gets `success: true`.” It can silently assign the same bead to multiple workers from the callers’ perspective, even if the final stored assignee is only the last writer.  
**Source-of-Truth Reference:** Acceptance criteria: “The claim must be atomic…” and “The others get `{ success: false, reason: 'unavailable' }`.”  
**Proposed Fix:** Use a conditional atomic update whose predicate includes the claimable state, then inspect the affected row count/result:

```ts
const result = await db.beads.update(
  { id: beadId, status: 'ready', assignee: null },
  {
    status: 'in_progress',
    assignee: workerId,
    claimedAt: new Date(),
  },
)

if (result.updatedCount === 1) {
  return { success: true, beadId, assignee: workerId }
}

const bead = await db.beads.findOne({ id: beadId })
return bead
  ? { success: false, reason: 'unavailable' }
  : { success: false, reason: 'not_found' }
```

Adjust the exact result field to match the project’s DB API.

**Medium Findings**

No findings.

**Low Findings**

No findings.
