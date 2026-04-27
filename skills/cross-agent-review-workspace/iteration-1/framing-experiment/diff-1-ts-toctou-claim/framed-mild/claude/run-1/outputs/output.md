- **Review Scope:** New `claimBead(beadId, workerId)` function appended to `api/services/beads.ts` (lines 32-64 of the package diff), plus its public `ClaimResult` interface. Review limited to the code and acceptance criteria provided in the package; no surrounding repository context was consulted.
- **Process Used:** Manual static review of the supplied diff against the stated acceptance criteria, with focus on concurrency semantics, error handling, input validation, and API surface correctness.
- **Execution Context:** Single-pass closed-context review. No tests were executed and no other repository files were inspected. The implementer's note that "tests pass" was taken at face value but not verified.
- **Integration Target:** `api/services/beads.ts` in a TypeScript service that exposes `db.beads.findOne` / `db.beads.update` (storage backend unspecified in the package).
- **Governing Documents:** The "Design / Acceptance criteria" section of the package (lines 7-27), specifically the atomicity requirement and the success/failure response contract.
- **Reviewer:** Claude (Opus 4.7, 1M context), acting as automated code reviewer.
- **Severity Scale:** Critical (data corruption / RCE / privilege escalation), High (significant security risk, resource leak, silent inconsistency, design requirement violated), Medium (incorrect behavior on some inputs, unclear error handling, missing implied validation, perf), Low (style, naming, nits).
- **Date:** 2026-04-26.

## Findings

### Critical

#### 1. TOCTOU race violates the atomicity acceptance criterion
- **Citation:** `api/services/beads.ts` lines 45-61 (package lines 45-61).
- **Problem:** The function reads the bead with `db.beads.findOne({ id: beadId })`, checks `bead.status` and `bead.assignee` in application memory, and then issues an unconditional `db.beads.update({ id: beadId }, { status: 'in_progress', assignee: workerId, claimedAt: new Date() })`. There is no compare-and-set predicate on the update, no transaction, and no row-level lock between the read and the write. Two concurrent callers for the same `beadId` can both pass the `status === 'ready' && assignee === null` check before either has written, and both will then execute the update. The last writer wins; both callers receive `{ success: true }`, but only one workerId actually ends up as the assignee in storage.
- **Why it matters:** The acceptance criteria explicitly state: "The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`." This implementation violates that contract directly. Two workers will believe they own the same bead and will perform duplicate (or conflicting) work, double-spend side effects, or corrupt downstream state. This is the canonical TOCTOU bug for a claim/lease primitive and is the single most important property the function was asked to provide.
- **Source-of-truth reference:** Acceptance criteria bullet 4 (package lines 21-23): "The claim must be atomic ... exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`."
- **Proposed fix:** Push the precondition into the write itself so the database arbitrates the race. For example, a conditional update that filters on the prior state and inspects the affected-row count:
  ```ts
  const result = await db.beads.update(
    { id: beadId, status: 'ready', assignee: null },
    { status: 'in_progress', assignee: workerId, claimedAt: new Date() },
  )
  if (result.modifiedCount === 0) {
    // Either the bead doesn't exist or it was already claimed; disambiguate.
    const exists = await db.beads.findOne({ id: beadId })
    if (!exists) return { success: false, reason: 'not_found' }
    return { success: false, reason: 'unavailable' }
  }
  return { success: true, beadId, assignee: workerId }
  ```
  Equivalent alternatives: wrap read + check + write in a serializable transaction; use `SELECT ... FOR UPDATE` followed by the update; or use an `UPDATE ... WHERE status='ready' AND assignee IS NULL RETURNING *` in a single statement. Whichever primitive is used, the precondition must be evaluated by the storage engine, not by JS.

### High

#### 2. Idempotency of repeat calls by the same worker is not handled
- **Citation:** `api/services/beads.ts` lines 49-51 (package lines 49-51).
- **Problem:** The acceptance criteria call out "idempotency of repeat calls" as a tested behavior, but the implementation treats any bead whose `assignee !== null` as `unavailable`. If the same worker calls `claimBead(beadId, workerId)` a second time after a successful claim, the function returns `{ success: false, reason: 'unavailable' }` even though that worker already owns the bead. Most claim/lease APIs treat a re-claim by the current owner as a no-op success.
- **Why it matters:** Workers commonly retry on transient errors (network blips, timeouts after a successful write). Returning `unavailable` to the legitimate owner will cause the worker to abandon work it actually owns, leading to stuck or orphaned beads and contradicting the "idempotent" property the test list implies.
- **Source-of-truth reference:** Acceptance criteria bullet 6 (package lines 26-27): "8 unit tests cover not_found, unavailable, successful claim, idempotency of repeat calls, and 4 edge cases."
- **Proposed fix:** Before returning `unavailable`, check whether `bead.assignee === workerId && bead.status === 'in_progress'` and, if so, return `{ success: true, beadId, assignee: workerId }` without rewriting `claimedAt`. Confirm with the spec author whether `claimedAt` should be preserved (recommended) or refreshed on re-claim.

#### 3. No input validation on `beadId` or `workerId`
- **Citation:** `api/services/beads.ts` lines 41-45 (package lines 41-45).
- **Problem:** The function accepts `beadId: string` and `workerId: string` and forwards them straight to the data layer with no validation. Empty strings, whitespace-only strings, or `null`/`undefined` cast through `any` will all reach the query. An empty `workerId` will succeed and stamp the bead with an empty assignee string; an empty `beadId` will simply return `not_found` after a needless query.
- **Why it matters:** A successful claim with `workerId === ''` silently corrupts ownership state - downstream code that trusts `assignee` to identify a worker has no way to distinguish "unowned" from "owned by empty string". This is a silent data-inconsistency risk and is one of the obvious "edge cases" the acceptance criteria allude to.
- **Source-of-truth reference:** Acceptance criteria bullet 6 (package lines 26-27) calls for "4 edge cases"; the severity rubric in the package (lines 73-79) classifies "missing validation that the design implies" as Medium-to-High.
- **Proposed fix:** At the top of the function, reject empty/whitespace inputs with a thrown `Error` (or a new `reason: 'invalid_input'` if the response shape is preferred). For example: `if (!beadId?.trim() || !workerId?.trim()) throw new TypeError('beadId and workerId must be non-empty strings')`.

### Medium

#### 4. `assignee !== null` is too strict and may misclassify `undefined`
- **Citation:** `api/services/beads.ts` line 49 (package line 49).
- **Problem:** The unavailability check uses `bead.assignee !== null`. If the storage layer returns `undefined` (or omits the field) for an unassigned bead - which is common in document stores and in TS models that declare `assignee?: string` - the strict inequality against `null` will be `true`, and a genuinely unassigned `ready` bead will be reported as `unavailable`.
- **Why it matters:** Causes false negatives: claimable beads are reported as unclaimable, starving workers and creating apparent deadlocks. The bug is invisible in tests that always seed `assignee: null` explicitly but appears the moment storage normalizes missing fields to `undefined`.
- **Source-of-truth reference:** Acceptance criteria bullet 3 (package lines 19-20): a bead is unavailable only when it "is not `ready` or already has an assignee."
- **Proposed fix:** Use a nullish check: `if (bead.status !== 'ready' || bead.assignee != null)` or `if (bead.status !== 'ready' || bead.assignee)`. The conditional update suggested in finding 1 should likewise filter on `{ status: 'ready', assignee: { $in: [null, undefined] } }` (or the storage-appropriate equivalent).

#### 5. `ClaimResult` discriminated union is not enforced by the type system
- **Citation:** `api/services/beads.ts` lines 34-39 (package lines 34-39).
- **Problem:** `ClaimResult` declares `success: boolean` and makes every other field optional. Callers cannot use TypeScript's narrowing to safely access `beadId`/`assignee` after checking `success === true`, nor `reason` after checking `success === false` - the compiler still considers all fields possibly `undefined`. This pushes runtime `!`/`as` assertions onto every call site and undermines the stated contract.
- **Why it matters:** The contract advertised in the acceptance criteria is a true sum type ("returns A if X, returns B if Y, returns C if Z"). Encoding it as a flat optional bag invites callers to forget the discriminator or to read `assignee` from a failure response.
- **Source-of-truth reference:** Acceptance criteria bullets 1-3 (package lines 16-20) describe three mutually exclusive shapes.
- **Proposed fix:** Model it as a discriminated union:
  ```ts
  export type ClaimResult =
    | { success: true; beadId: string; assignee: string }
    | { success: false; reason: 'not_found' | 'unavailable' }
  ```
  Callers then get exhaustive narrowing for free.

#### 6. No error propagation contract for storage failures
- **Citation:** `api/services/beads.ts` lines 45 and 54-61 (package lines 45, 54-61).
- **Problem:** The function `await`s `db.beads.findOne` and `db.beads.update` with no try/catch and no documentation of what happens on transport failures, constraint violations, or write conflicts. A thrown error from the update after the find succeeded leaves the caller with no `ClaimResult` and no indication of what state the bead is in.
- **Why it matters:** The acceptance criteria define only three outcomes; in practice a fourth (storage error) exists. Silent reliance on exception propagation is acceptable, but it should be deliberate and documented so callers know to retry. As written, a transient write failure is indistinguishable from a permanent one to the caller.
- **Source-of-truth reference:** Severity rubric, package line 78: "unclear error handling" qualifies as Medium.
- **Proposed fix:** Either (a) wrap the storage calls and rethrow a typed `BeadStoreError`, or (b) extend `ClaimResult` with a `reason: 'storage_error'` arm. Document the chosen behavior with a JSDoc comment on `claimBead`.

### Low

#### 7. `claimedAt` uses `new Date()` instead of an injected clock
- **Citation:** `api/services/beads.ts` line 59 (package line 59).
- **Problem:** Hard-coding `new Date()` makes the function impossible to test deterministically without monkey-patching `Date`, and it pins the timestamp to the API server's wall clock rather than the database's clock.
- **Why it matters:** Minor; primarily a testability and clock-skew concern.
- **Source-of-truth reference:** Severity rubric, package line 80: testability/refactoring nits are Low.
- **Proposed fix:** Accept an optional `now: () => Date = () => new Date()` parameter, or have the database stamp the time (e.g., a `DEFAULT now()` column or `$currentDate` operator).

#### 8. Function lacks JSDoc documenting the contract
- **Citation:** `api/services/beads.ts` lines 41-44 (package lines 41-44).
- **Problem:** A primitive whose entire value is a precise concurrency contract has no docstring describing that contract, the meaning of each `reason`, or the atomicity guarantee.
- **Why it matters:** Future maintainers may "simplify" the conditional update back into a read-then-write (the very bug in finding 1) without realizing the atomicity requirement.
- **Source-of-truth reference:** Severity rubric, package line 80: documentation polish is Low.
- **Proposed fix:** Add a JSDoc block above `claimBead` summarizing the three return shapes, the atomicity guarantee, and the idempotent-re-claim behavior chosen in finding 2.

#### 9. Returned `beadId` echoes the caller's input verbatim
- **Citation:** `api/services/beads.ts` line 63 (package line 63).
- **Problem:** On success, the function returns the `beadId` parameter rather than the id read from storage. If the storage layer ever normalizes ids (case-folding, trimming), the response will not match what was actually written.
- **Why it matters:** Cosmetic in most schemas, but defensive coding favors returning the canonical id from the persisted record.
- **Source-of-truth reference:** Severity rubric, package line 80.
- **Proposed fix:** Return `bead.id` (the value re-read from the conditional update's `RETURNING` clause) instead of the input parameter.
