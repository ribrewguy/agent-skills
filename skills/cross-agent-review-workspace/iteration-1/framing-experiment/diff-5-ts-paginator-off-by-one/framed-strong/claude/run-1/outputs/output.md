- **Review Scope:** `api/services/tasks.ts` (new `listTasks` + helpers) and `api/routes/tasks.ts` (updated `GET /api/tasks` handler) implementing cursor-based pagination per the supplied design.
- **Process Used:** Static review of the diff against the stated acceptance criteria; manual trace of the fetch-one-extra pagination boundary on representative inputs (empty result, single item, exactly `limit` items, `limit + 1` items, multiple pages); review of error/validation handling against design; no test execution performed (tests were not provided in package).
- **Execution Context:** Closed-context single-pass review; only the supplied package was read; no other repository files consulted.
- **Integration Target:** Express-based HTTP API exposing `GET /api/tasks` backed by a `db.tasks` data layer with `findMany`/`findOne`/`count` semantics; cursor pagination contract `{ items, nextCursor, total }`.
- **Governing Documents:** The "Design / Acceptance criteria" section embedded in the request package (cursor pagination contract, default/max limits, ordering, error behaviors, test coverage list).
- **Reviewer:** Claude (Opus 4.7, 1M context), acting as code reviewer.
- **Severity Scale:** Critical = production data corruption / RCE / privilege escalation; High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated; Medium = incorrect behavior on some inputs, unclear error handling, perf regression, missing validation implied by design; Low = style, naming, minor refactor, nits.
- **Date:** 2026-04-26.

## Findings

### Critical

_None._

### High

- **`api/services/tasks.ts:79` — Off-by-one in last-page detection drops a real item.**
  - Problem: The branch `if (fetched.length < limit)` decides "this is the last page." Because the query asks for `fetchSize = limit + 1` rows (line 61), the actual "last page" condition is `fetched.length <= limit` (i.e., we got `limit` or fewer). When `fetched.length === limit` exactly — meaning the DB returned exactly `limit` rows even though we asked for `limit + 1`, which is precisely the signal "no more rows beyond this page" — control falls through to the `else` branch at lines 87–90. There it slices `fetched.slice(0, limit)` (which is identical to `fetched`), then sets `nextCursor = items[items.length - 1].id`, advertising a next page that does not exist.
  - Why it matters: A client that follows `nextCursor` will issue a request whose cursor points at the very last task already shown. The server will then filter `createdAt < cursorTask.createdAt` and return zero (or fewer) items, with `nextCursor: null`. The user-visible symptoms are (a) an extra empty/short page at the tail of every result set whose total size is an exact multiple of `limit`, and (b) `nextCursor` lying about the existence of more data — a silent contract violation of "`nextCursor` is null when there are no more items beyond this page" (acceptance criteria, line 18). This will also break naive clients that loop `while (nextCursor)` by adding one wasted round-trip per pagination run, and will confuse UI components that show a "Next" affordance based on `nextCursor != null`.
  - Source of truth: Acceptance criteria, package lines 17–18: `Returns { items, nextCursor, total }. nextCursor is null when there are no more items beyond this page.` Combined with the implementer's own comment at line 60: `// Fetch one extra to determine if there's a next page` — the intent is clearly the standard `limit + 1` pattern, which requires comparing against `fetchSize` (or equivalently `<=  limit`), not `< limit`.
  - Proposed fix: Change the guard to compare against `fetchSize` (clearer) or flip the operator:
    ```ts
    if (fetched.length <= limit) {
      return { items: fetched, nextCursor: null, total }
    }
    // fetched.length === fetchSize, so there IS a next page
    const items = fetched.slice(0, limit)
    const nextCursor = items[items.length - 1].id
    return { items, nextCursor, total }
    ```
    Add a regression test for "exactly `limit` items remaining" — the implementer's listed coverage ("first page, middle pages, last page, … single-item-page edge case") does not appear to exercise the `total % limit === 0` boundary, which is exactly what this bug hits. The implementer note's claim that "all 7 tests pass" is consistent with this gap: the tests almost certainly use totals that are not multiples of the page size.

- **`api/services/tasks.ts:89` — Cursor uses only `createdAt` even though sort is `(createdAt, id)`, breaking pagination on ties.**
  - Problem: Sort order is `[['createdAt', 'desc'], ['id', 'desc']]` (line 74), but the cursor filter on the next request is `filter.createdAt = { $lt: cursorTask.createdAt }` (line 69) — strictly less-than on `createdAt` alone. If two tasks share the same `createdAt` (which is common when rows are inserted in batch, in tests, or via fixtures with second-resolution timestamps), the page boundary will silently drop every same-timestamp row that was on the *next* side of the boundary, and may also drop the boundary row itself.
  - Why it matters: This is a silent data-loss bug — items simply never appear in any page. It directly violates the acceptance criterion "Items are ordered by `createdAt` descending, with `id` as a tiebreaker" (line 19), because the tiebreaker is used for *ordering* but not honored when *resuming*. The consequence is that two clients paginating the same dataset can see a different number of total items than `total` claims.
  - Source of truth: Acceptance criteria line 19 (composite sort with `id` tiebreaker) implies a composite cursor.
  - Proposed fix: Use a composite cursor `(createdAt, id)` and a composite filter, e.g.:
    ```ts
    filter.$or = [
      { createdAt: { $lt: cursorTask.createdAt } },
      { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } },
    ]
    ```
    Optionally encode the cursor as an opaque base64 string so clients cannot confuse it with a raw ID. Add a test that inserts ≥2 tasks with identical `createdAt` and walks pages.

### Medium

- **`api/routes/tasks.ts:109` — String-prefix matching on `err.message` to classify errors is fragile.**
  - Problem: The handler distinguishes "invalid cursor" from other failures by checking `err.message.startsWith('Invalid cursor')`. Any future refactor that rewords the thrown message (or any localization) silently downgrades a 400 to whatever `next(err)` produces (typically 500). It also conflates user input errors with programmer errors at the call site.
  - Why it matters: The design implies a graceful response for malformed cursors (acceptance criterion mentions a "malformed cursor" test, line 21). The current coupling is implicit and order-dependent.
  - Source of truth: Acceptance criteria line 21 (tests must cover "malformed cursor"); general error-handling hygiene.
  - Proposed fix: Define a typed error in `services/tasks.ts` (e.g., `class InvalidCursorError extends Error { code = 'InvalidCursor' }`), throw it from the cursor lookup, and `instanceof`-check it in the route. Bonus: the route can stop reaching into `(req as any).id`.

- **`api/services/tasks.ts:65-68` — Cursor handling treats "unknown ID" as malformed, and adds an extra round-trip.**
  - Problem: The cursor is the `id` of the last item the client saw. The implementation does an additional `findOne({ id: cursor })` purely to read its `createdAt`, then throws "Invalid cursor" if the row is missing. A row that has been deleted between page fetches is a perfectly normal condition, not malformed input — the appropriate response is "resume from where you can" or at minimum a clearer error class (see also the previous finding). It also adds a second DB round-trip per paginated request.
  - Why it matters: (a) Performance: every page fetch after the first does an extra point-lookup. (b) UX: users get a 400 if the anchor task was deleted, which is noisy and recoverable. (c) Coupling: the cursor format is now "any valid Task id," with no opacity or signing — a client can construct cursors that point at arbitrary rows.
  - Source of truth: Acceptance criteria line 17 (cursor in/out contract) is silent on cursor format, so any reasonable opaque encoding satisfies it; criterion line 21 calls out "malformed cursor" testing, implying a distinction between malformed and stale.
  - Proposed fix: Encode the cursor as `base64({ createdAt, id })` (opaque) so the service does not need a second query at all. Decode-failure → 400 `InvalidCursor`; missing row → not applicable since you no longer query by ID. This also pairs naturally with the composite-cursor fix above.

- **`api/services/tasks.ts:58` — `count({})` runs on every request and can dominate latency on large tables.**
  - Problem: `total` is computed via `db.tasks.count({})` for every page request. On a sizeable `tasks` table, an unindexed/exact `COUNT(*)` is O(N) and will dominate pagination latency, especially as the data set grows.
  - Why it matters: The endpoint will appear to "get slower" as data grows even though pagination itself is bounded. It also applies to every page, including deep pages where the user is unlikely to care about an exact total.
  - Source of truth: Acceptance criterion line 17 requires `total` in the response; it does not specify exactness or per-request recomputation.
  - Proposed fix: Options, in increasing order of effort: (1) cache the count for a short TTL; (2) use an approximate count from PG stats / collection metadata; (3) make `total` opt-in via a query param (`?includeTotal=true`) and omit it on subsequent pages.

- **`api/routes/tasks.ts:103` — `Number(req.query.limit)` silently coerces non-numeric input to `NaN`, then `clampLimit` defaults it.**
  - Problem: Strings like `?limit=abc` or `?limit=` produce `NaN`, which `clampLimit` quietly turns into `DEFAULT_LIMIT`. The acceptance criteria say "Clamp out-of-range values silently" (line 16), which speaks to numeric out-of-range — it is debatable whether non-numeric junk should also be silently defaulted or rejected with a 400. Currently the behavior is "always default," which masks client bugs.
  - Why it matters: A client passing `?limit=undefined` (a common JS bug stringifying `undefined`) silently gets 25 items instead of an error, making the bug hard to spot.
  - Source of truth: Acceptance criteria line 16 ("Clamp out-of-range values silently") is intentionally narrow; non-numeric is not "out-of-range," it is malformed.
  - Proposed fix: In the route, treat a present-but-non-numeric `limit` as 400 `InvalidLimit`; pass through only valid numbers (or `undefined`) to `listTasks`. Keep `clampLimit` for clamping semantics only.

- **`api/services/tasks.ts:88` — `items[items.length - 1].id` would crash if `items` were empty; reachable via the off-by-one bug above.**
  - Problem: Once the High-severity off-by-one is fixed, this line is safe; in the *current* code it is also safe only because `fetched.length >= limit` and `limit >= 1`. However, if future refactoring lowers the minimum limit or changes the predicate, this becomes a `TypeError: Cannot read properties of undefined`. A defensive guard (or relying on the corrected `fetched.length > limit` predicate) is worth adding.
  - Why it matters: Hardening against regression; minor today, ugly when triggered.
  - Source of truth: General defensive coding around array indexing.
  - Proposed fix: After fixing the off-by-one, add `if (items.length === 0) return { items, nextCursor: null, total }` before the `nextCursor` assignment, or simply derive `nextCursor` only when `fetched.length > limit`.

### Low

- **`api/services/tasks.ts:49-54` — `clampLimit` accepts `undefined` and `NaN` together, mixing two distinct concerns.**
  - Problem: `clampLimit(undefined)` and `clampLimit(NaN)` both return the default. Splitting "missing" from "invalid" makes the route layer's job clearer (see the Medium finding on `Number(...)`).
  - Proposed fix: Change `clampLimit` to take `number` only and handle `undefined`/`NaN` at the route boundary.

- **`api/services/tasks.ts:53` — `Math.floor(limit)` after the range checks means `limit = 0.5` becomes `DEFAULT_LIMIT`, but `limit = 1.9` becomes `1`.**
  - Problem: Inconsistent treatment of fractional inputs (one gets defaulted, the other gets floored). Probably fine; worth a comment if intentional.
  - Proposed fix: Either floor first then range-check, or document the intent.

- **`api/services/tasks.ts:63` — `filter` typed as `Record<string, unknown>` loses type safety with the underlying `db.tasks.findMany` signature.**
  - Problem: A typed filter (e.g., `Partial<Pick<Task, 'createdAt'>> & { createdAt?: { $lt: Date } }`) catches typos at compile time. Minor.
  - Proposed fix: Introduce a dedicated `TaskFilter` type.

- **`api/routes/tasks.ts:113` — `(req as any).id` casts away the type system for `requestId`.**
  - Problem: Using `as any` defeats the purpose of TypeScript and is easy to grep for during audits. Augment Express's `Request` type once with the request-id middleware's contract instead.
  - Proposed fix: Add a `declare module 'express-serve-static-core' { interface Request { id?: string } }` in a typings file.

- **`api/services/tasks.ts:74` — Sort tuple uses positional pairs `['createdAt', 'desc']` rather than an object form.**
  - Problem: Stylistic; if the underlying driver supports `{ createdAt: -1, id: -1 }`, that form is more idiomatic. Pure nit.
  - Proposed fix: None required; flag for consistency with the rest of the codebase if applicable.

- **`api/services/tasks.ts:67` — Error message includes the raw cursor value.**
  - Problem: For most apps this is fine since cursors are non-sensitive. If cursors ever become opaque/signed, echoing them back in errors and logs becomes mildly noisy. Tiny nit.
  - Proposed fix: Drop the value from the message, keep it in structured log fields if needed.

- **Implementer note vs. test coverage gap.**
  - Problem: The implementer states "All 7 tests pass" and lists boundary conditions covered, but the High-severity off-by-one and the composite-cursor data-loss bug both require *specific* boundary tests that don't appear in the listed set: (a) `total % limit === 0` (e.g., 50 items, limit 25); (b) two items with identical `createdAt` straddling a page boundary. Worth flagging because confidence statements like "the fetch-one-extra pattern is well-tested" are precisely where reviewers should push back hardest — the named pattern is correct, but this implementation doesn't actually use it correctly.
  - Proposed fix: Add the two missing tests; consider a property-based test that paginates an arbitrary dataset and asserts (i) every item appears exactly once across all pages, (ii) the union equals `total`, (iii) `nextCursor` is null iff the last page was returned.
