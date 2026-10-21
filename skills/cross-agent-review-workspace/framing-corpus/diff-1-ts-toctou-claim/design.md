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
