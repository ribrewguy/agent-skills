**Review Scope:** Single new function `claimBead(beadId, workerId)` added at end of `api/services/beads.ts`, including its `ClaimResult` interface. Tests are referenced in the acceptance criteria but no test source was provided in the package; tests are reviewed only against the design's stated coverage.

**Process Used:** Cold structured code review of the diff against the stated acceptance criteria. Re-derived correctness by tracing concurrent and sequential call paths through the implementation; no automated gates (typecheck, tests, lint) were available in the package and none have been independently run. Findings are derived from manual analysis only.

**Execution Context:** Closed-context review. Only the supplied package was read. No repository, no `db` module, no `Bead` schema, no test files, and no neighboring code in `api/services/beads.ts` were available, so claims about surrounding behavior (transaction semantics of `db`, schema nullability of `assignee`, the meaning of statuses other than `ready`/`in_progress`) are based on what the diff itself asserts.

**Integration Target:** `api/services/beads.ts` in the host service. The function is consumed by whatever orchestrator hands work to workers; concurrent callers competing for the same bead are explicitly in scope per the design.

**Governing Documents:** The "Design / Acceptance criteria" block in the supplied package, specifically the bulleted acceptance criteria covering return shape, atomicity under concurrent calls, post-claim state, and 8-test coverage.

**Reviewer:** Cross-vendor second-pass reviewer (Claude).

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

**1. Claim is not atomic — classic check-then-act TOCTOU lets two workers claim the same bead**
- Citation: `api/services/beads.ts` lines 61-77 (the `findOne` at line 61, the predicate at line 65, and the unconditional `update` at lines 70-77).
- Problem: The function reads the bead, decides locally whether it is claimable, and then issues an `update` keyed only by `{ id: beadId }` with no guard on `status` or `assignee`. Between the `findOne` and the `update`, any number of other callers can perform the same read, see the same `ready`/`assignee === null` snapshot, and proceed to their own unconditional `update`. The last write wins; every concurrent caller returns `{ success: true, ... }` with their own `workerId`, but the persisted `assignee` is whichever update happened to land last. There is no row lock, no `WHERE status = 'ready' AND assignee IS NULL` predicate on the update, no `updateOne` affected-row check, no transaction, no optimistic-concurrency token, and no unique partial index being relied upon.
- Why it matters: This directly violates the design's explicit atomicity requirement ("under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`"). In production it causes silent double-assignment: two workers both believe they own the bead, both do the work, and downstream systems see conflicting `assignee` values, duplicate side effects, and corrupted progress state. This is the headline bug of the change and the entire purpose of the function is defeated.
- Source-of-truth reference: Acceptance criteria, bullet 4 ("The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`...").
- Proposed fix: Make the claim a single conditional write and decide success from the affected-row count. For a SQL-style backend: `UPDATE beads SET status='in_progress', assignee=$workerId, claimedAt=NOW() WHERE id=$beadId AND status='ready' AND assignee IS NULL` and treat `rowsAffected === 1` as success. To still distinguish `not_found` from `unavailable`, either (a) on `rowsAffected === 0` re-`findOne` and branch on whether the row exists, or (b) wrap the whole thing in a transaction with `SELECT ... FOR UPDATE` and keep the existing branching. Whichever is chosen, the success path must be derived from the conditional write, never from a stale read.

### High

**2. Idempotency of repeated calls by the same worker is not honored**
- Citation: `api/services/beads.ts` line 65 (`if (bead.status !== 'ready' || bead.assignee !== null)`).
- Problem: The acceptance criteria call out "idempotency of repeat calls" as a required test case. As written, once a worker successfully claims a bead, a second call to `claimBead(beadId, sameWorkerId)` will find `status === 'in_progress'` and `assignee === workerId`, fail the `status !== 'ready'` check, and return `{ success: false, reason: 'unavailable' }`. The same worker re-asking for a bead it already owns is told it cannot have it — the opposite of idempotent.
- Why it matters: Workers commonly retry on transient network failures, restart and re-hydrate their work queue, or re-issue claims after losing an ack. Returning `unavailable` to the rightful owner causes the orchestrator to reassign the bead to a different worker (compounding the Critical-1 race) or to mark the worker as failed. Either way the behavior contradicts the design and produces silent inconsistency.
- Source-of-truth reference: Acceptance criteria, last bullet ("8 unit tests cover ... idempotency of repeat calls ...").
- Proposed fix: Before returning `unavailable`, check `bead.status === 'in_progress' && bead.assignee === workerId` and return `{ success: true, beadId, assignee: workerId }` (without rewriting `claimedAt`, to preserve the original claim time). Implement this in conjunction with fix #1 so the conditional write and the idempotent re-read agree.

**3. `assignee !== null` assumes a nullable column the design never guarantees**
- Citation: `api/services/beads.ts` line 65 (`bead.assignee !== null`).
- Problem: The check uses strict inequality with `null`. If the underlying schema represents an unassigned bead with `undefined`, an empty string, or simply omits the field, the predicate will treat an unassigned bead as already-claimed and always return `unavailable`. Conversely, if the field is later modeled as `string | undefined`, a `null` round-tripped through JSON becomes a truthy "claimed" sentinel.
- Why it matters: This is a silent functional break that depends on a schema detail the design does not pin down. It will show up as "no bead is ever claimable" in some environments and "every bead looks unclaimed" in others, with no error surface.
- Source-of-truth reference: Acceptance criteria, bullet 3 ("if the bead exists but is not `ready` or already has an assignee").
- Proposed fix: Use a truthiness check (`bead.assignee != null` or `!bead.assignee`) and, more importantly, encode the same condition in the conditional `UPDATE` predicate from fix #1 so the database — not the in-memory snapshot — is the source of truth.

**4. No error handling around DB calls; rejection from `db.beads.update` produces an unspecified failure mode**
- Citation: `api/services/beads.ts` lines 61 and 70-77 (`await db.beads.findOne(...)` and `await db.beads.update(...)`).
- Problem: Both DB calls are awaited with no `try/catch`. If `findOne` rejects, the caller gets a raw exception instead of the specified `ClaimResult` shape. More dangerously, if `findOne` succeeds but `update` rejects after partially applying (depending on the driver, retries, or a connection drop after the write commits), the caller sees an exception while the bead may or may not be claimed — there is no compensating action and no way for the caller to know which.
- Why it matters: The design specifies the function's return type as `ClaimResult` with `success` and `reason`. Throwing breaks that contract and forces every caller to wrap calls defensively or risk crashing the worker loop. Combined with finding #1, an exception during `update` can leave the row in a half-known state and cause the orchestrator's retry logic to re-issue the claim, multiplying the race window.
- Source-of-truth reference: Acceptance criteria, return-shape bullets 1-3 (all specify a `ClaimResult` return, none mention thrown exceptions).
- Proposed fix: Either document and enforce a "throw on infrastructure failure" contract explicitly, or wrap the DB calls in `try/catch`, log, and translate to a defined failure result (e.g., a new `reason: 'error'`). At minimum, the conditional-update fix from #1 makes the success/failure determination atomic, so any thrown error means "no claim happened" with certainty.

**5. Test coverage as described cannot demonstrate atomicity**
- Citation: Acceptance criteria, last bullet ("8 unit tests cover not_found, unavailable, successful claim, idempotency of repeat calls, and 4 edge cases").
- Problem: The named tests (`not_found`, `unavailable`, `successful claim`, `idempotency`, plus 4 unspecified edges) describe sequential single-caller scenarios. None of them exercises the concurrency requirement, which is the only requirement that could have caught finding #1. No test source was provided in the package, so I cannot verify the 4 edge cases, but the enumeration in the design itself omits the concurrency test.
- Why it matters: A passing 8/8 test suite gives false assurance. The author and any reviewer trusting test counts will believe the function meets the atomicity bullet when in fact the bug in #1 is invisible to the tests as scoped.
- Source-of-truth reference: Acceptance criteria, bullet 4 (atomicity) read against the last bullet (test enumeration).
- Proposed fix: Add at least one concurrent-claim test that fires N parallel `claimBead(sameId, workerN)` calls and asserts exactly one returns `success: true` and the persisted row has that worker's id. If the test harness cannot fork true concurrency against the in-process `db`, mock `db.beads.update` to respect a conditional predicate and assert the predicate is included in the call. Independently, no claim of "tests pass" should be accepted in review without the test file being shown.

### Medium

**6. `claimedAt` is generated in application time, not database time**
- Citation: `api/services/beads.ts` line 75 (`claimedAt: new Date()`).
- Problem: The timestamp is taken from the API process's clock at the moment of the (non-atomic) `update` call. With multiple API replicas this introduces clock skew between rows, and with retries and queueing the `claimedAt` may diverge significantly from when the row actually transitioned. After fix #1 turns this into a conditional update, the gap between "decision to claim" and "row written" widens further.
- Why it matters: Any downstream lease-expiry logic ("reclaim a bead whose `claimedAt` is older than X") will be inconsistent across replicas. The design specifies "the current time" without pinning the clock source, but database-side time is the standard choice for claim-style operations.
- Source-of-truth reference: Acceptance criteria, bullet 5 ("`claimedAt` is the current time").
- Proposed fix: Use the database's `NOW()` / `CURRENT_TIMESTAMP` in the conditional `UPDATE` from fix #1, or document explicitly that application time is intentional.

**7. No input validation on `beadId` or `workerId`**
- Citation: `api/services/beads.ts` lines 57-60 (function signature) and line 61 (first use of `beadId`).
- Problem: Empty strings, whitespace, or `undefined` cast through `as string` will be passed straight to `db.beads.findOne({ id: '' })`. Depending on the driver this may throw, return the first row, or silently miss. An empty `workerId` will be written as the `assignee`, producing a "claimed by nobody" row that subsequent calls will see as already-assigned and refuse to reclaim.
- Why it matters: The design implies these IDs come from authenticated sources, but the function is now part of the service surface and should fail loudly on unusable inputs rather than corrupt rows.
- Source-of-truth reference: Acceptance criteria, bullet 5 ("`assignee` is the workerId") implies `assignee` must be a meaningful identifier.
- Proposed fix: Reject empty/whitespace `beadId` and `workerId` early with a `not_found`/`unavailable`/new-reason result, or throw a typed validation error and document it.

**8. `ClaimResult` type does not encode the success/failure discriminated-union, weakening type-checked usage**
- Citation: `api/services/beads.ts` lines 50-55.
- Problem: Every field other than `success` is declared optional, so callers cannot rely on the type system to enforce "if `success === true`, `beadId` and `assignee` are set; if `success === false`, `reason` is set." Callers have to defensively check for `undefined` on all branches, which both invites bugs and makes it easy to miss the actual failure case (a caller can read `result.beadId` on a failure result and get `undefined` without a type error).
- Why it matters: The acceptance criteria define two precise return shapes. A discriminated union would make the contract checkable at the type level and prevent the kind of "I forgot to check `success`" bug that compounds finding #1 in real call sites.
- Source-of-truth reference: Acceptance criteria, return-shape bullets 1-3.
- Proposed fix: Replace the interface with `type ClaimResult = { success: true; beadId: string; assignee: string } | { success: false; reason: 'not_found' | 'unavailable' }`.

**9. Function exists outside any transaction or retry policy**
- Citation: `api/services/beads.ts` lines 57-80 (whole function body).
- Problem: There is no transaction wrapping the read and the write, no `SELECT ... FOR UPDATE`, no advisory lock, and no documented retry policy on transient DB failures. Even after fix #1 makes the write itself atomic, callers that need to atomically pair the claim with another write (e.g., enqueue a job, increment a counter) have no hook to do so within the same transaction.
- Why it matters: For a primitive whose entire job is "atomically claim", omitting transaction support locks downstream code into the same TOCTOU pattern at a higher level.
- Source-of-truth reference: Acceptance criteria, bullet 4 (atomicity), interpreted to include composability.
- Proposed fix: Accept an optional transaction/connection parameter (`claimBead(beadId, workerId, tx?)`) and route the conditional update through it when supplied.

### Low

**10. Function has no doc comment describing the contract**
- Citation: `api/services/beads.ts` lines 57-60.
- Problem: There is no JSDoc/TSDoc explaining the return-shape contract, the atomicity guarantee, the idempotency expectation, or the failure modes. Future maintainers will re-derive the contract from the implementation, which is the bug source for finding #1.
- Why it matters: Low-impact in isolation, but the absence of a written contract is part of why the implementation drifted from the design.
- Source-of-truth reference: General code-quality practice; aligns with making the design's bullets explicit at the call site.
- Proposed fix: Add a TSDoc block above the function summarizing the four return shapes and the atomicity/idempotency guarantees.

**11. `success: false` results omit `beadId`, making logging and tracing harder**
- Citation: `api/services/beads.ts` lines 63 and 66.
- Problem: Failure results return only `{ success, reason }`. Callers logging the result lose the `beadId` context unless they re-thread it themselves. Including the `beadId` on failure results is cheap and aids observability.
- Why it matters: Cosmetic / ergonomic. Does not affect correctness.
- Source-of-truth reference: Not specified by the design; quality-of-life improvement.
- Proposed fix: Include `beadId` on failure results too. (If using the discriminated union from #8, add `beadId: string` to the failure variant.)

**12. The comment "Bead is available, claim it" actively misleads**
- Citation: `api/services/beads.ts` line 69.
- Problem: The comment asserts a property — "the bead is available" — that the surrounding code cannot guarantee, because the read at line 61 may have been stale by the time line 70 executes. The comment will reinforce the (incorrect) mental model for future readers.
- Why it matters: Documentation drift in a hot spot. Low severity but contributes to the same blind spot as finding #1.
- Source-of-truth reference: N/A (style).
- Proposed fix: Remove the comment, or rewrite it to describe the conditional-update contract once finding #1 is fixed (e.g., "Atomically transition ready -> in_progress; success is determined by rowsAffected").
