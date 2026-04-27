- **Review Scope:** New `claimBead(beadId, workerId)` function added at end of `api/services/beads.ts` (lines 32-64 of the package), implementing atomic-claim semantics for ready beads.
- **Process Used:** Static review of the single file diff supplied in the package, cross-checked line-by-line against the stated acceptance criteria. No execution, no test inspection beyond the implementer's claim of 8 passing unit tests.
- **Execution Context:** Closed-context review; only the package contents at `framed-moderate.md` were read. No surrounding repository, schema, db driver, or test source available.
- **Integration Target:** `api/services/beads.ts` — a service module presumed to back a multi-worker bead-claim workflow where concurrent workers may race on the same `beadId`.
- **Governing Documents:** The "Design / Acceptance criteria" section embedded in the package (lines 7-27): result shape, `not_found` / `unavailable` reasons, atomicity guarantee, and post-state invariants.
- **Reviewer:** Claude (Opus 4.7, 1M context), acting as code reviewer.
- **Severity Scale:** Critical = data corruption / RCE / privilege escalation; High = significant security risk, resource leak under common load, silent data inconsistency, or design requirement violated; Medium = incorrect behavior on some inputs, unclear error handling, missing implied validation; Low = style, naming, nits.
- **Date:** 2026-04-26.

## Findings

### Critical

#### C1. Check-then-act race violates the mandatory atomicity acceptance criterion
- **Citation:** `api/services/beads.ts` lines 45-61 (package lines 45-61).
- **Problem:** The implementation reads the bead with `db.beads.findOne({ id: beadId })`, then performs an unconditional `db.beads.update({ id: beadId }, { status: 'in_progress', assignee: workerId, claimedAt: new Date() })`. The update predicate filters only on `id` — it does NOT re-assert that `status === 'ready'` and `assignee === null`. Between the `findOne` and the `update`, another worker (or the same worker on a retry) can successfully claim the bead, and this caller will then silently overwrite the previous claim.
- **Why it matters:** Under concurrent calls for the same `beadId`, two (or more) callers can both observe `status: 'ready', assignee: null` in their `findOne`, both proceed past the guard at line 49, and both run the unconditional `update`. Both return `{ success: true, ... }`, but the persisted `assignee` is whichever update landed last. This is a textbook TOCTOU (time-of-check / time-of-use) bug. Concretely:
  1. The acceptance criterion "under concurrent calls for the same beadId, exactly one caller gets `success: true`" (package lines 21-23) is violated.
  2. The persisted `assignee` may not match the `assignee` returned to the "winner," so downstream work assignment becomes inconsistent (a worker believes it owns the bead while the database says someone else does). This is silent data corruption of a primary work-assignment invariant.
  3. The implementer's claim that "8 unit tests pass" does not refute this — single-process unit tests almost never exercise the interleaving required to expose a TOCTOU race; the bug is invisible without explicit concurrency tests against a real database.
- **Source-of-truth reference:** Acceptance criteria, package lines 21-25 ("The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`.").
- **Proposed fix:** Make the state transition itself the synchronization point by issuing a conditional update and branching on the row count, rather than gating on a prior read. Sketch:
  ```ts
  const result = await db.beads.update(
    { id: beadId, status: 'ready', assignee: null },
    { status: 'in_progress', assignee: workerId, claimedAt: new Date() },
  )
  if (result.matchedCount === 1) {
    return { success: true, beadId, assignee: workerId }
  }
  // Update did not match — distinguish not_found from unavailable
  const bead = await db.beads.findOne({ id: beadId })
  if (!bead) return { success: false, reason: 'not_found' }
  return { success: false, reason: 'unavailable' }
  ```
  The exact API depends on the `db.beads` driver (Mongo-style `updateOne`, a SQL `UPDATE ... WHERE id = ? AND status = 'ready' AND assignee IS NULL` returning affected row count, or a transaction with `SELECT ... FOR UPDATE`). Whichever shape is used, the predicate that determines claimability MUST live inside the same atomic write that performs the transition. Add an explicit concurrency test (e.g. `Promise.all` of N parallel `claimBead` calls for the same id, asserting exactly one `success: true`) so this regression cannot reappear.

### High

#### H1. `assignee !== null` guard may misclassify undefined / missing field as "unavailable"
- **Citation:** `api/services/beads.ts` line 49 (package line 49).
- **Problem:** The guard uses strict inequality `bead.assignee !== null`. If the underlying store represents an unassigned bead with `assignee: undefined`, with the field omitted entirely, or with an empty string (depending on schema and serializer), the strict `!== null` check will treat the bead as already assigned and return `unavailable` for a bead that is in fact claimable.
- **Why it matters:** This silently breaks the `not_found` / `unavailable` / claimable trichotomy required by the acceptance criteria (package lines 16-23). Workers will be told the bead is unavailable when it is actually free, leading to spurious retries and effectively starving the work queue. The bug is data-shape dependent and will not surface in unit tests that hand-construct fixtures with explicit `assignee: null`.
- **Source-of-truth reference:** Acceptance criteria, package lines 19-20 ("Returns `{ success: false, reason: 'unavailable' }` if the bead exists but is not `ready` or already has an assignee.") — the intent is "has an assignee," not "has any non-null value in the assignee slot."
- **Proposed fix:** Express the predicate in terms of "has an assignee" rather than "is strictly null": e.g. `bead.assignee != null` (loose) to cover both `null` and `undefined`, or better, use a truthiness check `!bead.assignee` paired with a typed schema that constrains the field to `string | null`. Once the C1 fix is applied, the canonical predicate moves into the `WHERE` clause of the conditional update and should match the storage representation exactly (e.g. `assignee IS NULL` in SQL).

#### H2. No validation of `workerId` allows empty / malformed claims
- **Citation:** `api/services/beads.ts` lines 41-61 (package lines 41-61), specifically the absence of any check on `workerId` before line 54.
- **Problem:** `workerId` is accepted as `string` and written into the row without validation. An empty string, a string of whitespace, or a value that conflicts with the schema's notion of "no assignee" (see H1) will be persisted. If `''` is treated as "no assignee" by other readers, the bead will appear unclaimed even though `status === 'in_progress'`.
- **Why it matters:** Combined with H1, an empty `workerId` can produce a bead that is simultaneously "in progress" and "unassigned," which is a silent data inconsistency. Even without that interaction, a malformed `workerId` defeats the design's premise that claimed beads can be attributed to a worker.
- **Source-of-truth reference:** Acceptance criterion, package lines 24-25 ("After a successful claim, the bead's `status` is `in_progress`, `assignee` is the workerId, and `claimedAt` is the current time.") — implies `assignee` must be a meaningful identifier.
- **Proposed fix:** Reject empty / whitespace `workerId` early with a thrown error or a typed error result, e.g. `if (!workerId || !workerId.trim()) throw new Error('workerId required')`. Apply the same minimal validation to `beadId`. If the project uses a validation library (zod, valibot), use it for consistency.

### Medium

#### M1. "Idempotency of repeat calls" acceptance criterion is not actually satisfied
- **Citation:** `api/services/beads.ts` lines 41-64 (package lines 41-64).
- **Problem:** The acceptance criteria call out "idempotency of repeat calls" as one of the tested behaviors (package line 26). With the current code, a second `claimBead(beadId, sameWorkerId)` call against a bead the worker already owns will hit the guard at line 49 (`bead.assignee !== null` is true), and return `{ success: false, reason: 'unavailable' }`. That is not idempotent — the worker is told its own claim failed.
- **Why it matters:** Workers commonly re-issue claims on retry or after a crash-recovery handshake. Returning `unavailable` for the worker's own bead either forces the caller to write fragile "did I already own this?" logic, or causes the worker to drop the bead. The fact that the implementer's tests pass suggests the test harness defines "idempotency" differently from the design (e.g. asserting the row is unchanged), so this is a spec-vs-implementation divergence worth surfacing.
- **Source-of-truth reference:** Acceptance criteria, package line 26 ("8 unit tests cover not_found, unavailable, successful claim, idempotency of repeat calls, and 4 edge cases.").
- **Proposed fix:** Decide and document the intended semantics. Either (a) treat "same workerId re-claiming" as success — return `{ success: true, beadId, assignee: workerId }` without mutating `claimedAt` — by adding a branch when `bead.assignee === workerId && bead.status === 'in_progress'`; or (b) clarify in the design that idempotency means "no state change," in which case the response shape should still be distinguishable from a genuine race loss (e.g. a third reason value like `'already_owned'`).

#### M2. `claimedAt` uses application-server clock and is non-deterministic / non-testable
- **Citation:** `api/services/beads.ts` line 59 (package line 59).
- **Problem:** `new Date()` is called inline, reading the application server's wall clock. This is non-deterministic in tests, drifts across servers, and means `claimedAt` is set by whichever node happened to run the update rather than by the database's authoritative clock.
- **Why it matters:** If `claimedAt` is later used to detect stuck claims (lease expiry, "claims older than N minutes are reclaimable"), clock skew between API nodes will produce subtly wrong reclaims. It also makes the function harder to unit-test deterministically, which is likely why the test count stops at 8 simple cases.
- **Source-of-truth reference:** Acceptance criterion, package line 25 ("`claimedAt` is the current time.") — "current time" is ambiguous, but a single source of truth (the DB) is the conventional read.
- **Proposed fix:** Either inject a `now: () => Date` clock into the service for testability, or push the timestamp into the database (`NOW()`, `CURRENT_TIMESTAMP`, server-side `$currentDate` for Mongo). Once C1 is fixed and the timestamp is set inside the conditional update, this becomes natural.

#### M3. No error handling around `db.beads.findOne` / `db.beads.update`
- **Citation:** `api/services/beads.ts` lines 45 and 54 (package lines 45 and 54).
- **Problem:** Both database calls are awaited without `try`/`catch`. Any driver-level failure (connection drop, write conflict, validation error) will propagate as an unhandled rejection to the caller, bypassing the typed `ClaimResult` contract entirely.
- **Why it matters:** The function's return type promises a structured discriminated result for every documented failure mode; a thrown exception is undocumented and forces every caller to wrap in `try`/`catch` defensively. It also means transient DB errors look identical to programmer errors at the call site.
- **Source-of-truth reference:** The `ClaimResult` interface at package lines 34-39 and the acceptance criteria at lines 16-25 — the contract enumerates `success`, `not_found`, and `unavailable` and is silent on thrown errors.
- **Proposed fix:** Decide a policy: either (a) document that `claimBead` may throw on infrastructure errors and let it propagate (and add a JSDoc `@throws`), or (b) catch and translate to a typed `{ success: false, reason: 'error', cause }` variant. Option (a) is usually right at the service layer; the key requirement is to make the choice explicit.

### Low

#### L1. `ClaimResult` is not a discriminated union; optional fields are loose
- **Citation:** `api/services/beads.ts` lines 34-39 (package lines 34-39).
- **Problem:** `ClaimResult` declares `reason`, `beadId`, and `assignee` all as optional. Nothing in the type prevents a caller from constructing or receiving `{ success: true, reason: 'not_found' }`, and TypeScript narrowing on `success` does not help recover the success-only fields.
- **Why it matters:** Callers cannot rely on the type system to enforce "if `success` then `beadId` and `assignee` are defined; if not `success` then `reason` is defined." This is purely an ergonomic / correctness-aid concern, not a runtime bug.
- **Source-of-truth reference:** Implicit contract from acceptance criteria, package lines 16-23.
- **Proposed fix:** Use a discriminated union:
  ```ts
  export type ClaimResult =
    | { success: true; beadId: string; assignee: string }
    | { success: false; reason: 'not_found' | 'unavailable' }
  ```

#### L2. Returned `beadId` echoes the input parameter verbatim
- **Citation:** `api/services/beads.ts` line 63 (package line 63).
- **Problem:** The success result returns the `beadId` argument rather than the value read back from the database. If the storage layer canonicalises ids (case-folding, trimming, ULID normalisation), the returned `beadId` may not equal the persisted one.
- **Why it matters:** Minor — the function does not currently look up by anything other than the raw input id, so any divergence already manifests at the `findOne` step. Still, returning a value sourced from the database is more defensive.
- **Source-of-truth reference:** Acceptance criterion, package lines 16-17.
- **Proposed fix:** Once C1 is implemented with a conditional update that returns the affected row, return that row's `id`.

#### L3. No JSDoc on the exported function
- **Citation:** `api/services/beads.ts` lines 41-44 (package lines 41-44).
- **Problem:** `claimBead` is a public service function with non-trivial concurrency semantics and no JSDoc explaining the contract, the atomicity guarantee, or the meaning of each `reason`.
- **Why it matters:** Future maintainers (and reviewers) have to re-derive the semantics from the body. Given the C1 race lurking in this exact area, an explicit comment about atomicity is cheap insurance.
- **Source-of-truth reference:** General code-hygiene practice; acceptance criteria, package lines 21-23.
- **Proposed fix:** Add a short JSDoc block stating the atomicity guarantee, the three result shapes, and that `claimedAt` is set on success.
