- **Review Scope:** New `claimBead(beadId, workerId)` function added to `api/services/beads.ts` (lines 32-64 of the package), implementing an atomic bead-claim API per the design's acceptance criteria.
- **Process Used:** Static review of the diff against the stated acceptance criteria; reasoning about concurrency, error paths, type safety, and database semantics implied by the snippet. No execution of the test suite.
- **Execution Context:** Closed-context review of a single package file (`framed-moderate.md`); no other repository files were consulted, so cross-file verifications (DB driver semantics, schema, surrounding service patterns) are inferred from the snippet alone.
- **Integration Target:** `api/services/beads.ts` in the broader bead-tracking service. The function is intended to be invoked concurrently by multiple worker processes claiming work items.
- **Governing Documents:** The "Design / Acceptance criteria" section of the package (lines 7-27), in particular the atomicity requirement on lines 21-23 ("under concurrent calls for the same beadId, exactly one caller gets `success: true`").
- **Reviewer:** Claude (Opus 4.7, 1M context), acting as automated code reviewer.
- **Severity Scale:**
  - Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
  - High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
  - Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
  - Low: style, naming, minor refactoring suggestions, nits.
- **Date:** 2026-04-26

## Findings

### Critical

#### C1. Check-then-act race condition violates the atomicity acceptance criterion
- **Citation:** `api/services/beads.ts` lines 45-61 (package `framed-moderate.md` lines 45-61).
- **Problem:** `claimBead` performs a `findOne` (line 45), inspects `status`/`assignee` in JS (line 49), and only then issues an unconditional `update` (lines 54-61). Between the read and the write, another caller can win the same check and also issue an update. Both updates succeed; both callers receive `{ success: true }`. The "last writer wins" on `assignee`, so the bead silently ends up assigned to one worker while the other believes it owns the work.
- **Why it matters:** This directly violates the explicit acceptance criterion on lines 21-23 ("exactly one caller gets `success: true`"). In production, two workers will simultaneously execute the same bead, producing duplicate side effects (double-charged jobs, duplicate emails, double-applied state changes, corrupted downstream artifacts). This is the textbook TOCTOU (time-of-check-to-time-of-use) bug and is the entire reason the design called out atomicity. The implementer's note that "all 8 unit tests pass" is not evidence of correctness here — single-threaded unit tests by construction cannot exercise the interleaving that breaks this code; a concurrency test (e.g., `Promise.all` of N parallel `claimBead` calls and asserting exactly one `success: true`) would fail.
- **Source-of-truth reference:** Design / Acceptance criteria, package lines 21-23: "The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`."
- **Proposed fix:** Push the check into the write so the database enforces uniqueness. Replace the read + conditional + unconditional update with a single conditional update whose `WHERE` clause includes the precondition, and use the affected-row count (or a `RETURNING` clause) to decide success. Sketch:
  ```ts
  const result = await db.beads.update(
    { id: beadId, status: 'ready', assignee: null },
    { status: 'in_progress', assignee: workerId, claimedAt: new Date() },
  )
  if (result.matchedCount === 1) {
    return { success: true, beadId, assignee: workerId }
  }
  // Disambiguate not_found vs unavailable with a follow-up read.
  const bead = await db.beads.findOne({ id: beadId })
  return bead
    ? { success: false, reason: 'unavailable' }
    : { success: false, reason: 'not_found' }
  ```
  Equivalent SQL: `UPDATE beads SET status='in_progress', assignee=$1, claimed_at=now() WHERE id=$2 AND status='ready' AND assignee IS NULL RETURNING id;` and treat zero rows as the unavailable/not-found path. If the underlying driver does not surface affected-row counts, wrap the read+write in a `SERIALIZABLE` transaction (and retry on serialization failure) or take an advisory/row lock (`SELECT ... FOR UPDATE`) before the update. Then add a concurrency test that fires N parallel `claimBead` calls and asserts exactly one `success: true`.

### High

#### H1. `assignee !== null` is unsafe against `undefined` and against new beads with no field set
- **Citation:** `api/services/beads.ts` line 49 (package line 49).
- **Problem:** The guard `bead.assignee !== null` only treats the literal value `null` as "unassigned." If the persistence layer returns `undefined` for an unset field (common for document stores and for ORMs that omit nullable columns), or if the column's default is `undefined`/missing, a freshly created `ready` bead will fail the guard and the function will return `unavailable` for a bead that should be claimable.
- **Why it matters:** Symmetrically, if some code paths set `assignee` to `undefined` after release (rather than `null`), the guard will accept the bead as unassigned and re-claim it, double-assigning work. Either way the boundary between "assigned" and "unassigned" is decided by JS reference equality to one specific sentinel, with no schema-level enforcement. This is also a silent data-inconsistency risk (matches the High severity definition).
- **Source-of-truth reference:** Acceptance criteria, package lines 19-20 (definition of `unavailable` as "not `ready` or already has an assignee").
- **Proposed fix:** Use a nullish check (`bead.assignee == null` or `!bead.assignee`) and, more importantly, fold the predicate into the DB-level conditional update from C1 so the check is expressed once, in the storage layer, with the schema's actual sentinel.

### Medium

#### M1. `claimedAt` is generated in application time, not database time
- **Citation:** `api/services/beads.ts` line 59 (package line 59).
- **Problem:** `claimedAt: new Date()` captures the wall clock of the API process. If multiple API replicas have skewed clocks, `claimedAt` ordering will not match the actual order of writes on the database. It is also susceptible to NTP step adjustments and to test-time mocking inconsistencies.
- **Why it matters:** Any downstream logic that orders, ages out, or times out claims by `claimedAt` (e.g., "reap claims older than 5 minutes") becomes unreliable across replicas. This is a correctness-in-some-inputs / silent-degradation issue rather than an outright bug.
- **Source-of-truth reference:** Acceptance criteria, package lines 24-25 ("`claimedAt` is the current time").
- **Proposed fix:** Have the database generate the timestamp (`now()` / `CURRENT_TIMESTAMP` / `$currentDate` depending on the engine) inside the same conditional update used for the fix in C1. Treat application-side `new Date()` as a fallback only when no DB-side primitive is available, and document the assumption.

#### M2. Idempotency of repeat calls by the same worker is not handled
- **Citation:** `api/services/beads.ts` lines 49-51 (package lines 49-51).
- **Problem:** The acceptance criteria (line 26) explicitly call out "idempotency of repeat calls" as something the tests cover, but the implementation treats *any* non-null assignee as `unavailable`. If `worker-A` successfully claims a bead and then retries the call (network retry, worker restart, at-least-once delivery), the second call will return `{ success: false, reason: 'unavailable' }` even though `worker-A` still owns the bead. That is the opposite of idempotent.
- **Why it matters:** Workers commonly retry on transient errors. A non-idempotent claim API forces every caller to special-case "I think I already own it" by doing an extra read, or it causes spurious failures and re-queuing. It also disagrees with the stated test coverage, suggesting either the implementation or the tests do not actually exercise the documented behavior.
- **Source-of-truth reference:** Acceptance criteria, package line 26 ("idempotency of repeat calls").
- **Proposed fix:** When a claim attempt finds the bead already assigned, compare the existing assignee to `workerId`; if they match, return `{ success: true, beadId, assignee: workerId }` (the caller already owns it). Otherwise return `unavailable`. This can be expressed in SQL by widening the precondition to `WHERE id = $beadId AND (status = 'ready' AND assignee IS NULL OR assignee = $workerId)` and `RETURNING` the row.

#### M3. No input validation on `beadId` / `workerId`
- **Citation:** `api/services/beads.ts` lines 41-44 (package lines 41-44).
- **Problem:** Neither argument is checked for empty string, whitespace, or obviously invalid format before being sent to the database. An empty `workerId` would happily be written into `assignee`, effectively "claiming" a bead to nobody, which is indistinguishable from "unassigned" if downstream code uses falsy checks (see H1).
- **Why it matters:** Silent acceptance of malformed input creates ghost claims that block other workers from picking up a bead until a human intervenes. It also undermines whatever invariant `assignee` is supposed to carry.
- **Source-of-truth reference:** Acceptance criteria implicitly assume valid identifiers (lines 16-25); the design does not contemplate empty inputs.
- **Proposed fix:** Validate at function entry — reject empty/whitespace-only `beadId` or `workerId` with a thrown `TypeError` or with a new `ClaimResult` reason (e.g., `'invalid_input'`) added to the union and documented.

#### M4. No error handling around the database calls
- **Citation:** `api/services/beads.ts` lines 45 and 54-61 (package lines 45 and 54-61).
- **Problem:** Both `db.beads.findOne` and `db.beads.update` can reject (network blip, timeout, constraint violation, optimistic-lock failure once the fix from C1 is applied). The current implementation lets those rejections propagate as raw exceptions, even though the public contract returns `Promise<ClaimResult>` with structured success/failure.
- **Why it matters:** Callers that pattern-match on `result.success` will not handle thrown exceptions, leading to unhandled promise rejections in the worker loop and inconsistent observability.
- **Source-of-truth reference:** The `ClaimResult` interface (lines 34-39) and the contract that the function "returns" specific shapes (lines 16-20).
- **Proposed fix:** Either (a) document that the function may throw on infrastructure errors and ensure the caller has a top-level handler, or (b) wrap the DB calls in `try/catch` and translate infra failures into a new `reason` (e.g., `'transient_error'`) so the caller can decide whether to retry.

### Low

#### L1. `ClaimResult` shape allows nonsensical combinations
- **Citation:** `api/services/beads.ts` lines 34-39 (package lines 34-39).
- **Problem:** `ClaimResult` is a single flat interface with all fields optional. Nothing in the type system prevents `{ success: true, reason: 'not_found' }` or `{ success: false, beadId: 'x', assignee: 'y' }`. Consumers must defensively branch on `success` and trust the implementer's discipline.
- **Why it matters:** It is easy for a future change to produce a malformed result; it is also easy for a consumer to read `result.beadId` on a failure path and silently get `undefined`.
- **Source-of-truth reference:** `ClaimResult` interface, lines 34-39.
- **Proposed fix:** Model the result as a discriminated union — e.g.,
  ```ts
  export type ClaimResult =
    | { success: true; beadId: string; assignee: string }
    | { success: false; reason: 'not_found' | 'unavailable' }
  ```
  This makes invalid states unrepresentable and lets TypeScript narrow downstream code automatically.

#### L2. New function appended at end of file, breaking any logical grouping
- **Citation:** `api/services/beads.ts` "(new function added at end of file)" — package line 32 comment.
- **Problem:** Appending to the end of a service file is convenient but tends to drift the file into a chronological log rather than a cohesive module. If `beads.ts` already groups read APIs vs. mutation APIs, `claimBead` should sit with the other mutating operations on bead lifecycle.
- **Why it matters:** Pure code-organization nit; affects future readability more than correctness.
- **Source-of-truth reference:** None (style).
- **Proposed fix:** Place `claimBead` near related lifecycle functions (e.g., `releaseBead`, `completeBead`) and re-export from any barrel file that exports the bead service surface.

#### L3. `success: boolean` plus optional `reason` invites stringly-typed checks
- **Citation:** `api/services/beads.ts` lines 35-36 (package lines 35-36).
- **Problem:** Callers will tend to write `if (result.reason === 'unavailable')` without first checking `success`, which works today but couples consumers to internal field names.
- **Why it matters:** Minor maintainability / API-clarity concern; subsumed by L1 if the discriminated-union refactor is taken.
- **Source-of-truth reference:** None (style).
- **Proposed fix:** Adopt the discriminated union from L1, then expose small type guards (`isClaimSuccess(result)`) for callers.
