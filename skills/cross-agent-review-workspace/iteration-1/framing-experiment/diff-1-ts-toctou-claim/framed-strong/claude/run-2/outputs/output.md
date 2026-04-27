**Review Scope:** New `claimBead(beadId, workerId)` function added to `api/services/beads.ts` (lines 32-64 of the package), including the `ClaimResult` interface and the public claim API surface.

**Process Used:** Static code review against the stated acceptance criteria. Read the design contract, then traced the implementation line-by-line for correctness, concurrency, error handling, validation, and contract conformance. Cross-referenced each acceptance criterion against the implementation's observable behavior. No tests were executed; the implementer's claim of 8 passing tests was treated as an assertion to verify, not as evidence of correctness.

**Execution Context:** Closed-context review. Only the supplied package was read; no other repository files, tests, schema definitions, or DB driver source were inspected. Therefore claims about `db.beads.update` semantics and `db.beads.findOne` behavior are based on conventional ORM patterns and the visible API shape.

**Integration Target:** `api/services/beads.ts` in a backend service that exposes a bead-claim API to multiple concurrent workers.

**Governing Documents:** The "Design / Acceptance criteria" section of the package (lines 7-27), specifically the atomicity requirement at lines 21-23 and the post-claim state requirements at lines 24-25.

**Reviewer:** Claude (Opus 4.7, 1M context), automated structured code review.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior on some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

#### C1. Atomicity requirement violated — classic check-then-act TOCTOU race
- **Citation:** `api/services/beads.ts` lines 45-61 (package lines 45-61).
- **Problem:** The function performs a read (`db.beads.findOne`) at line 45, branches on the read state at lines 46-51, and then issues an unconditional write (`db.beads.update`) at lines 54-61. The update has no predicate beyond `{ id: beadId }` — it does not require `status === 'ready'` and `assignee === null`. Between the `findOne` and the `update`, another concurrent caller can claim the same bead, and this caller will then overwrite the assignee with its own `workerId`, producing a successful result for both callers.
- **Why it matters:** This directly violates the design's explicit atomicity acceptance criterion (package lines 21-23): "under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`." Under concurrent claims, two workers can both believe they own the same bead. The bead's `assignee` field will reflect only the last writer, so the first "successful" claimant has been silently dispossessed and may proceed to do duplicate work, mutate downstream state under a stale identity, or contend with the second worker over the same unit of work. This is silent data inconsistency at the core of a coordination primitive — exactly the failure mode the API exists to prevent.
- **Source-of-truth reference:** Design / Acceptance criteria, package lines 21-23 (atomicity clause); reinforced by lines 24-25 (post-claim state must reflect "the workerId" — singular).
- **Proposed fix:** Make the claim a single conditional write and decide success/failure from the write's affected-row count. For example:
  ```ts
  const result = await db.beads.update(
    { id: beadId, status: 'ready', assignee: null },
    { status: 'in_progress', assignee: workerId, claimedAt: new Date() },
  )
  if (result.modifiedCount === 1) {
    return { success: true, beadId, assignee: workerId }
  }
  // Disambiguate not_found vs unavailable with a follow-up read.
  const bead = await db.beads.findOne({ id: beadId })
  return { success: false, reason: bead ? 'unavailable' : 'not_found' }
  ```
  Equivalent SQL alternative: `UPDATE beads SET ... WHERE id = ? AND status = 'ready' AND assignee IS NULL RETURNING id`. The exact predicate API depends on the driver, but the invariant is that the predicate that gates the state transition must be evaluated atomically with the write — never in application code between two round trips. A unique partial index on `(id) WHERE status='in_progress'` or a serializable transaction is an acceptable alternative, but the present code provides neither.

#### C2. Implementer's "all 8 tests pass" claim does not (and cannot) demonstrate atomicity
- **Citation:** Implementer note, package line 5; acceptance criterion at package lines 21-23; test inventory at lines 26-27.
- **Problem:** The implementer states all 8 unit tests pass and that walked-through failure modes include "double-claim attempts." But the implementation contains a textbook TOCTOU race (see C1), which means either (a) the test suite does not actually exercise true concurrency (most "double-claim" unit tests serialize the two calls and so cannot observe the race), or (b) the tests rely on a mock `db` whose `findOne`/`update` cannot interleave. Either way, the green test suite is not evidence that the atomicity acceptance criterion is met; it is evidence that the tests do not measure what the criterion requires.
- **Why it matters:** This is a process/governance defect that masks C1. Treating a passing unit-test count as proof of a concurrency property is a recurring source of production incidents. The "production-ready" claim in the implementer note should not be relied upon for merge until the atomicity property is demonstrated either by a property/stress test against a real DB (or a DB-backed test container) or by a code-level argument grounded in a single atomic statement (per C1's fix).
- **Source-of-truth reference:** Design / Acceptance criteria, lines 21-23 (atomicity is a hard requirement, not a "best-effort"); review-instruction severity guidance, lines 76-78 ("silent data inconsistency, design requirement violated" = High or above).
- **Proposed fix:** After applying C1's fix, add at least one test that drives the race condition the design cares about. Two acceptable shapes: (1) an integration test that issues N concurrent `claimBead` calls for the same id against a real DB (or test container) and asserts exactly one `success: true`; (2) a unit test with an injectable `db` whose `findOne` returns the same available bead to two callers and whose `update` is observed to be called with the gating predicate (so the test fails if the predicate is missing). Until such a test exists, do not claim the atomicity criterion is satisfied.

### High

#### H1. No input validation on `beadId` or `workerId`
- **Citation:** `api/services/beads.ts` lines 41-44 (function signature and entry).
- **Problem:** The function accepts `beadId: string` and `workerId: string` and passes them straight to the DB layer. There is no rejection of empty strings, no length bound, no character-class check, and no null/undefined guard at runtime (TypeScript types are erased at runtime, so callers from JS, JSON-deserialized inputs, or untyped boundaries can pass anything). An empty `workerId` would, under the current code, successfully "claim" a bead to the empty-string assignee, satisfying the post-claim state check (`assignee !== null` would be true) and locking the bead out from all future legitimate claims.
- **Why it matters:** A bead claimed by `assignee === ''` (or by `assignee === undefined` coerced to a string) is effectively orphaned: it is not `ready`, it is not owned by anyone meaningful, and no `unavailable` retry will recover it without manual DB intervention. The design implies (lines 24-25) that `assignee` is "the workerId" — a meaningful identifier, not an empty token.
- **Source-of-truth reference:** Design / Acceptance criteria, lines 24-25 (`assignee` is the workerId — implies a non-empty, well-formed identifier); review-instruction severity guidance, lines 79-80 ("missing validation that the design implies" = Medium, escalated to High here because the failure mode silently corrupts the claim ledger).
- **Proposed fix:** At the top of `claimBead`, validate both arguments and reject with a clear error or a typed failure result. Minimum: `if (!beadId || typeof beadId !== 'string') throw new Error(...)` and the same for `workerId`. Better: add a third reason `'invalid_input'` to `ClaimResult.reason` or throw a typed `ValidationError` so callers can distinguish caller error from contention. If `workerId` has a known format (UUID, prefixed id, etc.), enforce it.

#### H2. Use of `assignee !== null` is brittle to "unset" representations
- **Citation:** `api/services/beads.ts` line 49.
- **Problem:** The availability check is `bead.assignee !== null`. If the underlying store returns `undefined` for an unset field (common in document stores, ORMs that omit unset columns, or freshly-inserted rows where the column has no default), `undefined !== null` is `true` and the bead will be reported as `unavailable` even though it is unowned. Conversely, if a previous bug or migration left an empty-string assignee on a `ready` bead, `'' !== null` is `true` and the bead is again unavailable. The implementation conflates "has an assignee" with "assignee field is non-null," and the two are not the same in practice.
- **Why it matters:** This produces silent unavailability — the bead is claimable per the design (`status === 'ready'`, no real owner) but the API refuses to claim it. Callers will see `unavailable` and back off, leaving work stranded. This is also a forward-compatibility hazard: any future migration that introduces a sentinel value other than `null` will break the gate.
- **Source-of-truth reference:** Design / Acceptance criteria, lines 19-20 ("not `ready` or already has an assignee") — the criterion is semantic ("has an assignee"), not syntactic ("`assignee !== null`").
- **Proposed fix:** After C1's fix (which moves the predicate into the DB), express the predicate in terms the storage layer understands: `assignee IS NULL` in SQL, or an explicit `$or: [{assignee: null}, {assignee: {$exists: false}}]` in a document store. In application code, prefer a helper like `isUnassigned(bead)` that handles `null`, `undefined`, and `''` consistently and is unit-tested.

### Medium

#### M1. `not_found` vs `unavailable` cannot be reliably distinguished after the fix, and is racy even today
- **Citation:** `api/services/beads.ts` lines 45-51.
- **Problem:** Even in the current (broken) implementation, the `findOne`/`update` pair can race against deletes: the bead can be deleted between `findOne` and `update`, and the update will silently affect zero rows while this code returns `success: true`. After applying C1's fix, distinguishing `not_found` from `unavailable` requires a second read, which is itself racy (the bead may be deleted between the failed conditional update and the disambiguation read). The current code papers over this by reading first, but at the cost of correctness (C1).
- **Why it matters:** The acceptance criteria list `not_found` and `unavailable` as distinct outcomes (lines 18-20). Under any correct implementation, the disambiguation is best-effort. Callers and operators should know this. Logging or metrics that key off `not_found` vs `unavailable` will be approximately, not exactly, correct under contention.
- **Source-of-truth reference:** Design / Acceptance criteria, lines 18-20.
- **Proposed fix:** Document the racy disambiguation in a code comment on `claimBead`. Optionally, collapse `not_found` and `unavailable` into a single "could not claim" reason if the design does not actually require callers to act differently on the two cases — clarify with the design owner before changing the contract.

#### M2. `claimedAt` uses application clock without an explicit contract
- **Citation:** `api/services/beads.ts` line 59.
- **Problem:** `claimedAt: new Date()` records the application server's wall clock at the moment the application code constructs the update payload. Under the current implementation that may be milliseconds before the DB even sees the write; under a corrected implementation it may differ from the row's actual commit time. There is no documented requirement about which clock or which point-in-time `claimedAt` should reflect, but if downstream code uses it for SLA timers, lease expiry, or ordering, the choice matters.
- **Why it matters:** Multiple application servers with clock skew will produce non-monotonic `claimedAt` values across beads, which can confuse lease-expiry logic and audit trails.
- **Source-of-truth reference:** Design / Acceptance criteria, line 25 ("`claimedAt` is the current time") — "current" is underspecified.
- **Proposed fix:** Prefer a server-side timestamp where the storage layer supports it (e.g., `NOW()` in SQL, `$$NOW` in MongoDB). At minimum, document that `claimedAt` is the application server's clock at request time and rely on NTP. If `claimedAt` is used as a lease, add a lease-expiry field with the same provenance.

#### M3. No idempotency on retry by the same worker
- **Citation:** `api/services/beads.ts` lines 49-51; acceptance criterion line 27 ("idempotency of repeat calls").
- **Problem:** The acceptance criteria mention "idempotency of repeat calls" as a tested behavior, but the current code returns `unavailable` when the same `workerId` re-calls `claimBead` for a bead it already owns (because `bead.assignee !== null` short-circuits). True idempotency would return `success: true` (or at least a distinct success-like outcome) when the existing assignee equals the requesting `workerId`. The implementation as written is not idempotent under retry.
- **Why it matters:** Network retries, at-least-once delivery, and worker restarts are normal. A worker that successfully claims a bead, loses the response, and retries will get `unavailable` — and may then conclude the bead is owned by a competitor, leading it to abandon work it actually owns.
- **Source-of-truth reference:** Design / Acceptance criteria, lines 26-27 (test inventory mentions "idempotency of repeat calls").
- **Proposed fix:** In the availability check, treat `bead.assignee === workerId` as a success path: return `{ success: true, beadId, assignee: workerId }` without re-writing `claimedAt`. Confirm with the design owner whether a same-worker re-claim should refresh `claimedAt` or preserve the original; the design is silent on this.

### Low

#### L1. `ClaimResult` is structurally loose; prefer a discriminated union
- **Citation:** `api/services/beads.ts` lines 34-39.
- **Problem:** `ClaimResult` declares `success: boolean` with all of `reason`, `beadId`, and `assignee` optional. This permits malformed values like `{ success: true, reason: 'not_found' }` to typecheck. Callers must defensively check `success` before using `beadId`/`assignee`, and TypeScript provides no narrowing help.
- **Why it matters:** Contract clarity at the type level prevents whole classes of caller bugs.
- **Source-of-truth reference:** Design / Acceptance criteria, lines 16-20 (the success and failure shapes are fully disjoint per the design).
- **Proposed fix:** Replace with a discriminated union:
  ```ts
  export type ClaimResult =
    | { success: true; beadId: string; assignee: string }
    | { success: false; reason: 'not_found' | 'unavailable' }
  ```
  Caller code on `if (result.success)` then narrows `beadId` and `assignee` to non-optional automatically.

#### L2. No structured logging or observability hooks
- **Citation:** `api/services/beads.ts` lines 41-64 (entire function body).
- **Problem:** The function emits no logs, metrics, or trace spans. Successful claims, unavailable outcomes, and not-found outcomes are all silent.
- **Why it matters:** A claim API is a coordination primitive; operators routinely need claim throughput, contention rates, and per-worker claim distributions to diagnose production issues. Silence here will mean instrumenting after the first incident.
- **Source-of-truth reference:** Not a design requirement; a standard operability concern.
- **Proposed fix:** Add a minimal structured log on each terminal branch (`info` on success, `debug` on `unavailable`/`not_found`) and a counter metric keyed by outcome. Wrap in a span if the service uses tracing.

#### L3. Function placement comment is a maintenance hazard
- **Citation:** `api/services/beads.ts` line 32 ("`// (new function added at end of file)`").
- **Problem:** The comment describes a one-time placement at the moment of the diff. Once merged, the comment is meaningless and will mislead future readers (the function may not be the last in the file after subsequent edits).
- **Why it matters:** Pure nit, but these comments accumulate.
- **Source-of-truth reference:** N/A (style).
- **Proposed fix:** Drop the comment from the committed source.
