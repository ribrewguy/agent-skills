**Review Scope:** New `claimBead(beadId, workerId)` function added at the end of `api/services/beads.ts` (lines 32-64 of the package diff). Review covers correctness against the stated acceptance criteria, concurrency/atomicity guarantees, error handling, and TypeScript type hygiene.

**Process Used:** Static review of the supplied diff against the design and acceptance criteria. No tests were executed and no surrounding repository context (DB driver semantics, schema definitions, existing helpers) was inspected; assumptions about `db.beads.findOne`/`update` semantics are stated where they affect findings.

**Execution Context:** Closed-context review based solely on the contents of `framed-mild.md`. Implementer asserts "Tests pass" but no test source was supplied for inspection.

**Integration Target:** `api/services/beads.ts` — service-layer module exposing a `claimBead` API to be consumed by worker processes that race to claim ready beads.

**Governing Documents:** The "Design / Acceptance criteria" section embedded in the package (lines 7-27), in particular the atomicity requirement on lines 21-23.

**Reviewer:** Claude (Opus 4.7, 1M context), acting as cross-agent reviewer.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

#### C1. Claim is not atomic — classic TOCTOU between `findOne` and `update`
- **Citation:** `api/services/beads.ts:45-61` (package lines 45-61).
- **Problem:** The implementation reads the bead with `db.beads.findOne({ id: beadId })`, evaluates `status === 'ready' && assignee === null` in application memory, and then issues an unconditional `db.beads.update({ id: beadId }, { status: 'in_progress', assignee: workerId, claimedAt: ... })`. Between the read (line 45) and the write (line 54), any number of concurrent callers can observe the same "ready, unassigned" snapshot and all proceed to overwrite each other. The update predicate matches on `id` only, so it has no protection against a stale snapshot.
- **Why it matters:** This violates the explicit acceptance criterion on lines 21-23: "under concurrent calls for the same beadId, exactly one caller gets `success: true`." In practice, every concurrent caller will return `{ success: true, beadId, assignee: workerId }`, but the row will end up owned by whichever update lands last. The other "successful" workers will then begin processing a bead that is actually assigned to someone else, producing duplicate work, double-billing, or corrupted bead state — the canonical TOCTOU bug. The implementer's "Tests pass" note is consistent with this bug going undetected, because none of the eight enumerated tests (not_found, unavailable, successful claim, idempotency, plus four edge cases) is required by the criteria to exercise true concurrency, and a serial "idempotency of repeat calls" test will actually pass against this buggy implementation while masking the race.
- **Source-of-truth reference:** Acceptance criteria, package lines 21-23 ("The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`.").
- **Proposed fix:** Make the claim a single conditional write and decide success from its result, e.g.:
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
  Alternatively use a transaction with `SELECT ... FOR UPDATE` (SQL) or `findOneAndUpdate` with the predicate inlined (Mongo). The key invariant: the predicate `status === 'ready' AND assignee IS NULL` must be evaluated by the database as part of the same write that flips the row, not in JS.

### High

#### H1. Idempotency of repeat calls is not actually idempotent for the original claimer
- **Citation:** `api/services/beads.ts:49-51` (package lines 49-51).
- **Problem:** The acceptance criteria require "idempotency of repeat calls" (line 26). With the current logic, when worker A calls `claimBead(b, A)` a second time after a successful first claim, the first branch returns `not_found` only when the row is missing, and the second branch returns `unavailable` because `bead.status !== 'ready'` (it is now `in_progress`). The check does not special-case `bead.assignee === workerId`, so the original successful claimer receives `{ success: false, reason: 'unavailable' }` on a repeat call rather than `{ success: true, beadId, assignee: workerId }`.
- **Why it matters:** This is a silent semantic violation of an explicit acceptance criterion. Workers that retry on transient network errors (the entire reason an API needs idempotency) will see their own successful claim as "lost" and either drop work or incorrectly mark the bead as taken by someone else.
- **Source-of-truth reference:** Acceptance criteria, package line 26 ("8 unit tests cover not_found, unavailable, successful claim, idempotency of repeat calls, and 4 edge cases.").
- **Proposed fix:** Before returning `unavailable`, short-circuit when the existing assignee equals `workerId`:
  ```ts
  if (bead.status === 'in_progress' && bead.assignee === workerId) {
    return { success: true, beadId, assignee: workerId }
  }
  if (bead.status !== 'ready' || bead.assignee !== null) {
    return { success: false, reason: 'unavailable' }
  }
  ```
  Apply the same idempotency check after the conditional update in the fix for C1.

#### H2. `bead.assignee !== null` may misclassify `undefined` as "claimed"
- **Citation:** `api/services/beads.ts:49` (package line 49).
- **Problem:** The check uses strict inequality against `null`. If the underlying store represents an unclaimed bead with `assignee: undefined` (or omits the field entirely on freshly-inserted documents), `bead.assignee !== null` is `true`, and a genuinely-ready bead is reported as `unavailable`.
- **Why it matters:** The schema/representation is not visible in the diff. Many ORMs (Prisma with optional columns, Mongo with sparse fields, custom serializers) round-trip "no value" as `undefined` rather than `null`, so this is a realistic failure mode that would silently make claims fail in production while passing tests that hand-construct `{ assignee: null }` fixtures.
- **Source-of-truth reference:** Acceptance criteria, package lines 19-20 ("Returns `{ success: false, reason: 'unavailable' }` if the bead exists but is not `ready` or already has an assignee.") — the contract is "has an assignee," not "assignee is literally `null`."
- **Proposed fix:** Test for "no assignee" using `== null` (covers both `null` and `undefined`) or `!bead.assignee`, or define a typed schema that guarantees the field is `null` when absent. Folding the predicate into the database query (per C1) avoids the question entirely if the DB-level filter is `{ assignee: null }` and the schema enforces it.

### Medium

#### M1. `ClaimResult` is structurally incoherent — success-only fields are typed as optional on failure paths
- **Citation:** `api/services/beads.ts:34-39` (package lines 34-39).
- **Problem:** `ClaimResult` is a single shape with every field optional. Callers cannot rely on the type system to know that `beadId`/`assignee` are present iff `success === true`, or that `reason` is present iff `success === false`. Both `success: true` with `reason` set and `success: false` with `assignee` set are accepted by the type checker.
- **Why it matters:** Callers must defensively check `result.beadId !== undefined` even on the happy path, and TypeScript will not flag a future regression that, for example, returns `{ success: true }` with no payload. This is a missed opportunity to use a discriminated union to enforce the contract the acceptance criteria describe.
- **Source-of-truth reference:** Acceptance criteria, package lines 16-20 (each return shape is precisely specified).
- **Proposed fix:** Replace with a discriminated union:
  ```ts
  export type ClaimResult =
    | { success: true; beadId: string; assignee: string }
    | { success: false; reason: 'not_found' | 'unavailable' }
  ```
  This matches the spec exactly and gives callers exhaustive narrowing.

#### M2. `claimedAt` is wall-clock `new Date()` rather than a server/DB timestamp
- **Citation:** `api/services/beads.ts:59` (package line 59).
- **Problem:** `claimedAt` is generated in the application process. If multiple API replicas have skewed clocks, ordering of claims by `claimedAt` (e.g., for audit, lease expiry, or "first claim wins" tie-breakers) becomes unreliable. It also makes the function impure and harder to test deterministically.
- **Why it matters:** Bead-claim systems frequently use `claimedAt` to drive lease expiry / re-queue logic. Using the DB clock (`NOW()`, `$$NOW`, `currentDate` operator) avoids skew and gives a single linearizable source for ordering. Lower severity than C1/H1 because the spec just says "the current time" without specifying source.
- **Source-of-truth reference:** Acceptance criteria, package line 25 ("`claimedAt` is the current time").
- **Proposed fix:** Where the driver supports it, set `claimedAt` via a DB-side expression (e.g., `{ $currentDate: { claimedAt: true } }` for Mongo, `claimedAt: sql\`NOW()\`` for SQL). Otherwise inject a `now: () => Date` clock for testability.

#### M3. No input validation on `beadId`/`workerId`
- **Citation:** `api/services/beads.ts:41-44` (package lines 41-44).
- **Problem:** The function accepts any string, including `''`, whitespace, or arbitrarily long values, and forwards them straight into the DB query. There is no rejection of empty IDs and no length/charset bound.
- **Why it matters:** An empty `beadId` will pattern-match nothing and silently return `not_found`, which is the wrong reason (the right answer is "bad input"). An empty `workerId` would, after the C1 fix, succeed in claiming a bead under an empty owner — an availability footgun. The spec's edge-case slot ("4 edge cases" on line 27) implies validation is in scope.
- **Source-of-truth reference:** Acceptance criteria, package line 27 (edge cases) and line 24 ("`assignee` is the workerId").
- **Proposed fix:** Validate at function entry: reject empty/whitespace inputs with a thrown `TypeError` (or a third `reason: 'invalid_input'`, with a corresponding update to the union and the spec).

### Low

#### L1. `findOne` then `update` is two round-trips even on the happy path
- **Citation:** `api/services/beads.ts:45,54` (package lines 45 and 54).
- **Problem:** Even setting aside C1, the code performs two DB round-trips per claim. A single conditional update plus a fallback read only on the failure path (per the C1 fix) saves one round-trip on the common case.
- **Why it matters:** Bead-claim is on the hot path of every worker; halving DB round-trips is a free win.
- **Source-of-truth reference:** None directly; performance hygiene.
- **Proposed fix:** Adopt the structure from C1.

#### L2. `Promise<ClaimResult>` return type does not document thrown errors
- **Citation:** `api/services/beads.ts:41-44` (package lines 41-44).
- **Problem:** The function awaits two DB calls but has no `try`/`catch`. Driver errors (timeout, connection lost, schema validation failure) propagate as rejected promises, which is fine — but the public interface and JSDoc do not mention this. Callers that build on the `ClaimResult` union may incorrectly assume "all outcomes are encoded in the result."
- **Why it matters:** Minor. Mostly a documentation / API-contract clarity issue.
- **Source-of-truth reference:** None; convention.
- **Proposed fix:** Add a JSDoc comment on `claimBead` noting that DB errors throw and only logical outcomes are encoded in `ClaimResult`.

#### L3. Magic strings for `status` and `reason` values
- **Citation:** `api/services/beads.ts:36, 49, 57` (package lines 36, 49, 57).
- **Problem:** `'ready'`, `'in_progress'`, `'not_found'`, `'unavailable'` are inline string literals. A typo in any of them is a silent bug, and there is no single place to evolve the status vocabulary.
- **Why it matters:** Style / maintainability.
- **Source-of-truth reference:** None; convention.
- **Proposed fix:** Define `const BeadStatus = { Ready: 'ready', InProgress: 'in_progress' } as const` (or a string-literal union type already in the schema) and reuse it both here and in the `ClaimResult` reason union.
