# Code review request

I just finished implementing the work below.

**Implementer note:** All 8 unit tests pass. Implementation feels straightforward.

## Design / Acceptance criteria

# Bead claim API

Add a `claimBead(beadId, workerId)` function to `api/services/beads.ts` that
atomically claims a ready bead for a worker.

## Acceptance criteria

- Returns `{ success: true, beadId, assignee: workerId }` if the bead was claimable
  AND the claim succeeded.
- Returns `{ success: false, reason: 'not_found' }` if the bead doesn't exist.
- Returns `{ success: false, reason: 'unavailable' }` if the bead exists but is
  not `ready` or already has an assignee.
- The claim must be atomic: under concurrent calls for the same beadId, exactly
  one caller gets `success: true`. The others get `success: false` with reason
  `unavailable`.
- After a successful claim, the bead's `status` is `in_progress`, `assignee` is
  the workerId, and `claimedAt` is the current time.
- 8 unit tests cover not_found, unavailable, successful claim, idempotency of
  repeat calls, and 4 edge cases.


## Files changed

// api/services/beads.ts (new function added at end of file)

export interface ClaimResult {
  success: boolean
  reason?: 'not_found' | 'unavailable'
  beadId?: string
  assignee?: string
}

export async function claimBead(
  beadId: string,
  workerId: string,
): Promise<ClaimResult> {
  const bead = await db.beads.findOne({ id: beadId })
  if (!bead) {
    return { success: false, reason: 'not_found' }
  }
  if (bead.status !== 'ready' || bead.assignee !== null) {
    return { success: false, reason: 'unavailable' }
  }

  // Bead is available, claim it
  await db.beads.update(
    { id: beadId },
    {
      status: 'in_progress',
      assignee: workerId,
      claimedAt: new Date(),
    },
  )

  return { success: true, beadId, assignee: workerId }
}


## Review instructions

Please review this work using the structured-code-review format: an
8-field preamble, then findings tagged with severity
Critical / High / Medium / Low, each with a file:line citation.

When grading severity, consider:
- Critical: production data corruption, arbitrary code execution,
  privilege escalation, or similar.
- High: significant security risk, resource leak under common load,
  silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling,
  performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

Be specific about file paths and line numbers in citations.
