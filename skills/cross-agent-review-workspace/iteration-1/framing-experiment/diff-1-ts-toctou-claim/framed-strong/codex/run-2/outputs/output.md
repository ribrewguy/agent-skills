Review Scope: `claimBead(beadId, workerId)` implementation in `api/services/beads.ts`  
Process Used: Static review of provided implementation against acceptance criteria  
Execution Context: Closed-context review; no filesystem or command execution  
Integration Target: Bead claim API  
Governing Documents: “Bead claim API” design / acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as provided  
Date: 2026-04-27

## Critical Findings

No Critical findings.

## High Findings

### H1: Claim is not atomic under concurrent callers

Citation: `api/services/beads.ts:13`, `api/services/beads.ts:22`

Problem statement: The implementation checks availability with `findOne`, then performs an unconditional `update` by `{ id: beadId }`. Two concurrent callers can both read the bead while it is `ready` and unassigned, then both update it and both return `success: true`.

Why it matters: This directly violates the acceptance criterion: “under concurrent calls for the same beadId, exactly one caller gets `success: true`; the others get `success: false` with reason `unavailable`.” It can also silently overwrite the first worker’s claim with the second worker’s `assignee`.

Source-of-truth reference: Acceptance criteria, atomic claim requirement.

Proposed fix: Make the write conditional on claimability and check the affected row count/result:

```ts
const result = await db.beads.update(
  { id: beadId, status: 'ready', assignee: null },
  {
    status: 'in_progress',
    assignee: workerId,
    claimedAt: new Date(),
  },
)

if (result.affectedRows === 1) {
  return { success: true, beadId, assignee: workerId }
}
```

Then distinguish `not_found` from `unavailable` with a follow-up existence check only after the conditional update fails.

## Medium Findings

No Medium findings.

## Low Findings

No Low findings.
