**Review Scope:** New `claimBead(beadId, workerId)` function added at the end of `api/services/beads.ts`, including its `ClaimResult` interface and accompanying acceptance criteria for atomic bead claiming.

**Process Used:** Cold cross-vendor structured code review. Re-derived correctness claims directly from the supplied diff and acceptance criteria. No tests, linters, type checks, or runtime gates were executed; all findings are derived statically from the provided source.

**Execution Context:** Closed-context single-pass review. Only the contents of the supplied package were available; no surrounding repository, no `db` driver source, no test files, no schema, no migrations, and no CI logs were consulted.

**Integration Target:** `api/services/beads.ts` (Node/TypeScript backend service, async DB-backed bead/task queue with worker-claim semantics).

**Governing Documents:** The "Bead claim API" design / acceptance criteria included in the package (lines 25-43): atomicity under concurrency, three return shapes (`success:true` / `not_found` / `unavailable`), state mutation to `in_progress` with `assignee` and `claimedAt`, and the 8-test coverage requirement.

**Reviewer:** Cross-vendor second-pass reviewer (Claude).

**Severity Scale:** Critical = data corruption / RCE / privesc; High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated; Medium = incorrect behavior on some inputs, unclear error handling, missing validation implied by design; Low = style / naming / nits.

**Date:** 2026-04-26.

## Findings

### Critical

#### C1. TOCTOU race: read-then-write claim is not atomic, violating the core acceptance criterion
- **Citation:** `api/services/beads.ts:61-77` (the `findOne` on line 61 followed by the unconditional `update` on lines 70-77).
- **Problem:** The implementation reads the bead with `db.beads.findOne({ id: beadId })`, validates `status === 'ready' && assignee === null` in application memory, then issues an `update` whose filter is `{ id: beadId }` only. Between the read and the write, any other concurrent `claimBead` call (or any other writer) can mutate the row. Two workers calling `claimBead(beadId, w1)` and `claimBead(beadId, w2)` simultaneously can both observe `status='ready', assignee=null`, both pass the guard on line 65, and both execute the `update` on line 70. The second write silently overwrites the first: the row ends up assigned to the later writer, the earlier writer also receives `{ success: true }`, and `claimedAt` is clobbered. Two workers now believe they own the same bead.
- **Why it matters:** This is the exact scenario the acceptance criteria call out as the atomicity requirement ("under concurrent calls for the same beadId, exactly one caller gets `success: true`"). It is the headline guarantee of the function. Violating it produces double-assignment, duplicated work, and — depending on what downstream consumers do with `assignee` — lost results, conflicting commits, or corrupted bead state. This is silent data inconsistency in the hot path of a work-queue primitive, which qualifies as production data corruption.
- **Source-of-truth reference:** Acceptance criteria, package lines 37-39: "The claim must be atomic: under concurrent calls for the same beadId, exactly one caller gets `success: true`. The others get `success: false` with reason `unavailable`."
- **Proposed fix:** Push the predicate into the write itself so the database — not application memory — enforces the guard. Use a conditional update and branch on the affected-row count, e.g.:
  ```ts
  const res = await db.beads.update(
    { id: beadId, status: 'ready', assignee: null },
    { status: 'in_progress', assignee: workerId, claimedAt: new Date() },
  )
  if (res.modifiedCount === 1) return { success: true, beadId, assignee: workerId }
  // Lost the race or never eligible — disambiguate by re-reading.
  const bead = await db.beads.findOne({ id: beadId })
  if (!bead) return { success: false, reason: 'not_found' }
  return { success: false, reason: 'unavailable' }
  ```
  Equivalent SQL form: `UPDATE beads SET status='in_progress', assignee=$1, claimed_at=NOW() WHERE id=$2 AND status='ready' AND assignee IS NULL RETURNING id;` and treat zero rows returned as the "lost the race / unavailable / not_found" branch (disambiguated by a follow-up existence check or by adding the existence check into the same query via CTE). Either approach makes the claim a single atomic DB operation.

### High

#### H1. Idempotency requirement is silently violated: a re-claim by the same worker returns `unavailable`
- **Citation:** `api/services/beads.ts:65-67`.
- **Problem:** The acceptance criteria explicitly call for "idempotency of repeat calls" (package line 42). After a successful `claimBead(b, w1)`, the row has `status='in_progress'` and `assignee=w1`. A subsequent `claimBead(b, w1)` will fail the guard `bead.status !== 'ready' || bead.assignee !== null` and return `{ success: false, reason: 'unavailable' }`. There is no special-casing for "already claimed by this same worker," so retries by the legitimate owner — common after a transient network error or a client-side retry — will look identical to "another worker stole it."
- **Why it matters:** Without idempotency, a worker that retries its own claim on a flaky connection will believe the bead is gone and either drop the work or escalate. This is one of the four behaviors the test plan was supposed to cover; the implementation as written cannot satisfy it.
- **Source-of-truth reference:** Acceptance criteria, package line 42: "8 unit tests cover not_found, unavailable, successful claim, idempotency of repeat calls, and 4 edge cases."
- **Proposed fix:** Before returning `unavailable`, check whether the bead is already `in_progress` and `assignee === workerId`; if so, return `{ success: true, beadId, assignee: workerId }` (and do not bump `claimedAt`). Equivalently, broaden the conditional update predicate to also match `(status='in_progress' AND assignee=$workerId)` and treat that as a successful no-op claim.

#### H2. `assignee !== null` check is fragile against `undefined` / missing field
- **Citation:** `api/services/beads.ts:65`.
- **Problem:** The guard is strict-equality `bead.assignee !== null`. Many document and ORM stores represent "no assignee" as the field being absent (`undefined`) rather than literal `null`, and TypeScript-side optional fields commonly come through as `undefined`. A bead that has never been assigned would then have `assignee === undefined`, the guard `undefined !== null` evaluates `true`, and the function returns `unavailable` for a perfectly valid ready bead. Conversely, if the schema uses `undefined` for "cleared" and `null` is reserved for something else, the same bug appears in mirror.
- **Why it matters:** This produces a silent "no beads are ever claimable" regression depending on driver/schema semantics, and the bug is invisible in tests that hand-construct fixtures with `assignee: null`. It is the kind of mismatch a typical implementer's own review will not catch because their local test fixtures match their guard.
- **Source-of-truth reference:** Acceptance criteria, package lines 32-36 ("if the bead was claimable", "exists but is not `ready` or already has an assignee").
- **Proposed fix:** Use `bead.assignee == null` (loose equality, matches both `null` and `undefined`) or `!bead.assignee` if empty-string is also disallowed. Better: encode the predicate in the DB query (see C1) and remove the in-memory guard altogether.

#### H3. No error handling around `findOne` / `update`; partial failure leaks an inconsistent state to the caller
- **Citation:** `api/services/beads.ts:61` and `api/services/beads.ts:70-77`.
- **Problem:** Both DB calls are unawaited-from-try. If `db.beads.update` rejects after the row was actually mutated (driver retry, network reset on the response, etc.), the function's promise rejects but the row may still be `in_progress` with `assignee=workerId`. The caller has no signal whether the claim took effect, so the next step (likely a retry) compounds with H1 to produce a permanent stuck bead. Conversely, if `findOne` throws, the function rejects with a raw driver error rather than a typed `ClaimResult`, breaking the API contract that promises one of three discriminated shapes.
- **Why it matters:** In a work-queue, the difference between "claim failed cleanly" and "claim threw mid-write" is the difference between a worker retrying safely and a bead being silently orphaned in `in_progress` with no live owner. Production load makes both branches reachable.
- **Source-of-truth reference:** Acceptance criteria implicit contract, package lines 32-36 (function returns one of three `ClaimResult` shapes); review-instructions emphasis on "Failure modes that tests don't catch" (package line 88).
- **Proposed fix:** Wrap the DB calls in `try { ... } catch (err) { ... }` and decide deliberately whether to (a) rethrow with a typed error, (b) return a fourth `reason` like `'error'`, or (c) treat the post-write failure as best-effort success once `modifiedCount === 1`. Combined with the conditional-update fix in C1, the post-write ambiguity disappears: the database has either modified one row or zero, full stop.

#### H4. `claimedAt` is set from application-server clock (`new Date()`) rather than database time
- **Citation:** `api/services/beads.ts:75`.
- **Problem:** `claimedAt: new Date()` records the wall-clock time of the API process. With multiple API replicas (or even one replica with NTP skew), `claimedAt` becomes non-monotonic across rows, breaks ordering invariants, and can travel backwards relative to other timestamps written by the same DB. It also makes "claim timeout" / "reclaim stale claim" logic — a near-certain follow-on feature for any work queue — race against clock skew.
- **Why it matters:** Once any reaper job uses `claimedAt` to expire stuck claims, server-clock skew translates directly into prematurely-reclaimed live work or zombie claims that never expire. The acceptance criteria say the timestamp must be "the current time" (line 41); in a distributed system, "the current time" is the DB's, not a worker's.
- **Source-of-truth reference:** Acceptance criteria, package line 41: "`claimedAt` is the current time."
- **Proposed fix:** Have the database set the timestamp (`NOW()` / `CURRENT_TIMESTAMP` / driver-equivalent server-side default) inside the same conditional update, instead of passing a JS `Date` from the API process.

### Medium

#### M1. No input validation on `beadId` / `workerId`
- **Citation:** `api/services/beads.ts:57-60`.
- **Problem:** Both arguments are typed `string` but never validated. Empty string, whitespace, oversized strings, or strings containing characters that the underlying store treats specially are passed straight to `findOne` and `update`. `findOne({ id: '' })` will typically return `null`, so the function happily returns `not_found` for what is actually a programmer error.
- **Why it matters:** Invalid input is collapsed into a legitimate-looking response (`not_found`), masking bugs in callers and making support diagnosis harder. The acceptance criteria imply validation by saying `not_found` is for "the bead doesn't exist" — not "the caller passed garbage."
- **Source-of-truth reference:** Acceptance criteria, package line 34, and review instructions, package line 89 ("missing validation that the design implies").
- **Proposed fix:** Add explicit guards at the top of the function: throw `TypeError` (or return a typed `invalid_argument` reason) when either id is empty / non-string / exceeds a sane length bound.

#### M2. `ClaimResult` interface is too loose for a discriminated union, weakening type safety
- **Citation:** `api/services/beads.ts:50-55`.
- **Problem:** All four fields (`reason`, `beadId`, `assignee`) are optional on a single shape, so TypeScript will not narrow them based on `success`. A caller that does `if (result.success) { use(result.assignee) }` gets `string | undefined` and has to non-null-assert. Conversely, `if (!result.success) { use(result.reason) }` also yields `string | undefined`. The shape technically allows nonsense like `{ success: true, reason: 'not_found' }`.
- **Why it matters:** The function's whole point is to communicate one of three crisply distinguishable outcomes; the type should make wrong combinations unrepresentable.
- **Source-of-truth reference:** Acceptance criteria, package lines 32-36 (three mutually-exclusive return shapes).
- **Proposed fix:** Replace with a discriminated union:
  ```ts
  export type ClaimResult =
    | { success: true; beadId: string; assignee: string }
    | { success: false; reason: 'not_found' | 'unavailable' }
  ```

#### M3. Same-worker self-claim of an already-`in_progress` bead is indistinguishable from a foreign claim in `unavailable`
- **Citation:** `api/services/beads.ts:65-67`.
- **Problem:** Related to H1 but distinct: even if the operator decides idempotent self-reclaim should not return `success: true`, the API today provides no way for a worker to discover whether the bead is held by *itself* vs. someone else. Both paths return `{ success: false, reason: 'unavailable' }`, which is operationally ambiguous (retry? back off? alert?).
- **Why it matters:** Operators chasing duplicate-work incidents have no first-class signal; they have to read the row separately, defeating the point of a single atomic claim API.
- **Source-of-truth reference:** Review instructions, package line 88 ("Failure modes that tests don't catch").
- **Proposed fix:** Either implement H1's idempotent-success branch, or extend the `reason` union with `'already_claimed_by_self'` as a distinct outcome.

#### M4. The eight-test coverage requirement cannot be re-derived from the diff (no tests included)
- **Citation:** Package as a whole; the "Files changed" section ends at `api/services/beads.ts:80` and contains no test file.
- **Problem:** The acceptance criteria require 8 unit tests covering specific scenarios (line 42). The package contains zero test code. Per the prompt's instruction to re-derive quality claims, this gate is not satisfied by the supplied work.
- **Why it matters:** The atomicity claim in particular is exactly the kind of property that needs a concurrent-execution test to be credible. Without one, C1 and H1 ship undetected.
- **Source-of-truth reference:** Acceptance criteria, package lines 42-43.
- **Proposed fix:** Add tests covering: (1) `not_found`, (2) `unavailable` because `status !== 'ready'`, (3) `unavailable` because already assigned to a different worker, (4) successful claim mutates `status`/`assignee`/`claimedAt`, (5) idempotent self-reclaim, (6) concurrent claim by two workers — exactly one returns success (use `Promise.all` of N parallel calls and assert exactly one truthy result), (7) claim of an `in_progress` bead by a foreign worker, (8) input-validation rejection. The concurrency test is the load-bearing one and should be run with N >= 50 to make the race in C1 reproducible in CI.

### Low

#### L1. `claimBead` does not log or instrument failed-claim outcomes
- **Citation:** `api/services/beads.ts:62-67`.
- **Problem:** Both failure branches return silently. In a busy queue, knowing the rate of `unavailable` vs. `not_found` is operationally important.
- **Why it matters:** Diagnosing "why is throughput low" later requires this signal; adding it after the fact is harder.
- **Source-of-truth reference:** N/A (operational best-practice; not in acceptance criteria).
- **Proposed fix:** Emit a counter / structured log event with `{ outcome, beadId, workerId }` at each return site.

#### L2. `ClaimResult.reason` literal string union is duplicated between interface and return sites
- **Citation:** `api/services/beads.ts:52` vs. `api/services/beads.ts:63` and `api/services/beads.ts:66`.
- **Problem:** The literal `'not_found'` / `'unavailable'` strings appear in three places; a typo at any return site silently widens the type if the interface is later relaxed.
- **Why it matters:** Style / refactor hazard.
- **Source-of-truth reference:** N/A.
- **Proposed fix:** Extract `const NOT_FOUND = 'not_found' as const` / `UNAVAILABLE = 'unavailable' as const` (or a small enum-like object) and reference those at both the type and return sites.

#### L3. Mixing `ready` / `in_progress` magic strings without a shared enum
- **Citation:** `api/services/beads.ts:65, 73`.
- **Problem:** The status values are bare string literals scattered across the function. A typo (`'in-progress'` vs. `'in_progress'`) is a runtime bug that the type system cannot catch.
- **Why it matters:** Style / safety.
- **Source-of-truth reference:** N/A.
- **Proposed fix:** Define a `BeadStatus` union or const object and use it both here and in the underlying schema.

#### L4. Function does not return the full bead, forcing callers to re-read
- **Citation:** `api/services/beads.ts:79`.
- **Problem:** On success the function returns only `{ success, beadId, assignee }`. Most callers will immediately want `claimedAt`, the bead payload, and the version/etag for any subsequent CAS operation, and will have to do a second `findOne`.
- **Why it matters:** Mild inefficiency, mild API ergonomics nit.
- **Source-of-truth reference:** N/A (acceptance criteria specify the minimum success shape but do not forbid more).
- **Proposed fix:** When migrating to the conditional `update ... RETURNING *` form (per C1), surface the returned row on success, e.g. `{ success: true, beadId, assignee, claimedAt, bead }`.
