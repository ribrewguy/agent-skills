**Review Scope:** `claimBead(beadId, workerId)` implementation in `api/services/beads.ts`  
**Process Used:** Closed-context structured code review; no tools or filesystem access used.  
**Execution Context:** Implementer reports tests pass.  
**Integration Target:** Bead claim API service.  
**Governing Documents:** Provided design and acceptance criteria.  
**Reviewer:** Codex  
**Severity Scale:** Critical / High / Medium / Low as provided.  
**Date:** 2026-04-27

**Critical Findings**

None.

**High Findings**

**H1: Claim operation is not atomic**  
Citation: `api/services/beads.ts:12`, `api/services/beads.ts:21`

Problem statement: The implementation first reads the bead with `findOne`, checks availability in application code, then performs an unconditional `update` by `id`. Two concurrent callers can both observe `status === 'ready'` and `assignee === null`, then both update the same bead and both return `success: true`.

Why it matters: This directly violates the core acceptance criterion: “under concurrent calls for the same beadId, exactly one caller gets `success: true`; others get `unavailable`.” It can silently assign the same bead to multiple workers at the API level.

Source-of-truth reference: Acceptance criteria: atomic claim behavior under concurrent calls.

Proposed fix: Use a conditional atomic update whose filter includes claimability, then inspect affected row/document count:

```ts
const result = await db.beads.update(
  { id: beadId, status: 'ready', assignee: null },
  {
    status: 'in_progress',
    assignee: workerId,
    claimedAt: new Date(),
  },
)

if (result.modifiedCount === 1 || result.affectedRows === 1) {
  return { success: true, beadId, assignee: workerId }
}

const bead = await db.beads.findOne({ id: beadId })
return bead
  ? { success: false, reason: 'unavailable' }
  : { success: false, reason: 'not_found' }
```

Adapt the affected-count property to the project’s DB API.

**Medium Findings**

None.

**Low Findings**

None.
