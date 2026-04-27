**Review Scope:** `api/services/beads.ts`, new `claimBead(beadId, workerId)` implementation  
**Process Used:** Closed-context second-pass review against supplied acceptance criteria only  
**Execution Context:** No commands run, no files read, no external context used  
**Integration Target:** Bead claim API service behavior  
**Governing Documents:** Supplied “Design / Acceptance criteria” package  
**Reviewer:** Codex cross-vendor reviewer  
**Severity Scale:** Critical = data corruption/RCE/privilege escalation; High = significant security/resource/data/design violation; Medium = incorrect edge behavior or missing implied validation; Low = style/nits  
**Date:** 2026-04-27

## Findings

### Critical

No Critical findings.

### High

**H1: Claim is not atomic and allows multiple concurrent successful claims**  
**Citation:** `api/services/beads.ts:13`, `api/services/beads.ts:17`, `api/services/beads.ts:22`

**Problem:** The implementation performs a separate `findOne`, checks availability in memory, then performs an unconditional update by `id` only. Two or more concurrent callers can all read the bead while it is still `ready` and unassigned, all pass the availability check, all execute the update, and all return `{ success: true }`.

**Why it matters:** This directly violates the core API contract. Under concurrent calls for the same `beadId`, the design requires exactly one successful claim and all other callers to receive `{ success: false, reason: 'unavailable' }`. This implementation can report multiple successful claims while the final stored assignee is whichever update writes last, creating silent inconsistency between API responses and persisted state.

**Source of truth:** Acceptance criteria: “The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`.”

**Proposed fix:** Replace the read-then-write sequence with a single conditional atomic update, for example an update whose predicate includes `id`, `status: 'ready'`, and `assignee: null`, and inspect the affected row/document count. If affected count is `1`, return success. If affected count is `0`, perform a follow-up existence check to distinguish `not_found` from `unavailable`.

### Medium

**M1: Update result is ignored, so failed or stale writes can still return success**  
**Citation:** `api/services/beads.ts:22`, `api/services/beads.ts:31`

**Problem:** The function does not check whether `db.beads.update(...)` actually modified a bead. If the bead is deleted, changed by another process, or the update affects zero rows/documents after the initial `findOne`, the function still returns success.

**Why it matters:** The API can claim success without the postcondition being true. The design requires that after a successful claim, the bead’s `status` is `in_progress`, `assignee` is the worker ID, and `claimedAt` is current time.

**Source of truth:** Acceptance criteria: “After a successful claim, the bead's `status` is `in_progress`, `assignee` is the workerId, and `claimedAt` is the current time.”

**Proposed fix:** Use the atomic conditional update result as the source of truth. Return success only when the database confirms exactly one record was updated. Otherwise classify the result as `not_found` or `unavailable`.

### Low

No Low findings.
