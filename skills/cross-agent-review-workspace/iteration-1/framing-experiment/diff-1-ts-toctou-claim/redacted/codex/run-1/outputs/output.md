**Review Scope:** `api/services/beads.ts`, new `claimBead(beadId, workerId)` implementation  
**Process Used:** Closed-context static review against supplied design and acceptance criteria only  
**Execution Context:** No commands run, no filesystem reads, no external context used  
**Integration Target:** Bead claim API service function  
**Governing Documents:** Package “Design / Acceptance criteria” for Bead claim API  
**Reviewer:** Codex second-pass reviewer  
**Severity Scale:** Critical / High / Medium / Low as defined in request  
**Date:** 2026-04-26

## Critical Findings

None.

## High Findings

### High: Claim is not atomic under concurrent callers

**Citation:** `api/services/beads.ts:12`, `api/services/beads.ts:21`

**Problem:** The function performs a separate `findOne` availability check before calling `update` by `id` only. Two concurrent callers can both read the bead as `ready` with no assignee, both update it, and both return `{ success: true }`.

**Why it matters:** This directly violates the core acceptance criterion: “under concurrent calls for the same beadId, exactly one caller gets `success: true`; the others get `success: false` with reason `unavailable`.” The current implementation can silently double-claim work.

**Source-of-truth reference:** Design / Acceptance criteria: “The claim must be atomic…”

**Proposed fix:** Use a single conditional atomic update, e.g. update where `{ id: beadId, status: 'ready', assignee: null }`, then inspect affected row count. If affected count is `1`, return success. If `0`, do a follow-up existence check to distinguish `not_found` from `unavailable`.

### High: Update result is ignored, so failed claims can still return success

**Citation:** `api/services/beads.ts:21`, `api/services/beads.ts:30`

**Problem:** The function does not verify whether `db.beads.update(...)` actually modified a row. If the row is changed, deleted, or otherwise not updated between the read and update, the function still returns success.

**Why it matters:** This can produce false-success responses where the bead was not actually claimed. That violates the requirement that success is returned only “if the bead was claimable AND the claim succeeded.”

**Source-of-truth reference:** Acceptance criteria: “Returns `{ success: true, beadId, assignee: workerId }` if the bead was claimable AND the claim succeeded.”

**Proposed fix:** Require the update call to return affected/matched row count, and only return success when exactly one row was updated. Otherwise classify the result as `not_found` or `unavailable`.

## Medium Findings

### Medium: Availability check treats only `null` as unassigned

**Citation:** `api/services/beads.ts:16`

**Problem:** The implementation checks `bead.assignee !== null`. If existing data represents an unassigned bead as `undefined`, missing, or another falsy empty value, this function will treat it as unavailable.

**Why it matters:** The design says unavailable applies when the bead “already has an assignee.” It does not specify that unassigned must be encoded strictly as `null`. This can reject otherwise claimable ready beads depending on storage shape.

**Source-of-truth reference:** Acceptance criteria: “Returns `{ success: false, reason: 'unavailable' }` if the bead exists but is not `ready` or already has an assignee.”

**Proposed fix:** Align with the persisted schema. If unassigned is guaranteed `null`, enforce that invariant elsewhere and in tests. If not, use the repository’s canonical unassigned predicate in both the conditional update and any fallback checks.

## Low Findings

None.
