Review Scope: `claimBead(beadId, workerId)` addition in `api/services/beads.ts`  
Process Used: Closed-context structured code review using only the provided package  
Execution Context: Static review; no commands, files, tests, or external tools used  
Integration Target: Bead claim API  
Governing Documents: Provided design / acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in the request  
Date: April 27, 2026

**Critical Findings**

No findings.

**High Findings**

Finding: `api/services/beads.ts:12`

Problem statement: The claim operation is not atomic. The function first reads the bead with `findOne`, checks availability in application code, then performs an unconditional update by `id`.

Why it matters: Under concurrent calls for the same ready bead, multiple callers can read the same `ready` / unassigned state before either update commits. Each caller then updates the bead and returns `{ success: true }`, violating the acceptance criterion that exactly one caller succeeds and the rest return `{ success: false, reason: 'unavailable' }`.

Source-of-truth reference: Acceptance criteria: “The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`.”

Proposed fix: Replace the read-then-update flow with a conditional atomic update, for example updating only where `id = beadId`, `status = 'ready'`, and `assignee IS NULL`, then checking the affected row count. If the conditional update succeeds, return success. If it affects zero rows, perform a follow-up existence check to distinguish `not_found` from `unavailable`.

**Medium Findings**

No findings.

**Low Findings**

No findings.
