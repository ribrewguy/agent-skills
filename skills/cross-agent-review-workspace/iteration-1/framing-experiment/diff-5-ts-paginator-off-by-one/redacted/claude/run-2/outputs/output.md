**Review Scope:** Cursor-pagination implementation for `GET /api/tasks` consisting of `listTasks` in `api/services/tasks.ts` and the route handler in `api/routes/tasks.ts`, evaluated against the supplied acceptance criteria for cursor pagination, ordering, clamping, response shape, and error handling.

**Process Used:** Cold static review of the supplied diff. Re-derived correctness by tracing page-boundary scenarios (single-item pages, exact-multiple totals, empty results, malformed/expired cursors, duplicate `createdAt`), independently checked clamp behavior against the spec, and audited the response contract against the declared `PageResult<T>` shape.

**Execution Context:** Single-pass review against only the supplied package contents; no test execution, no repository exploration, no external lookups.

**Integration Target:** `api/services/tasks.ts` (new helpers) and `api/routes/tasks.ts` (existing Express GET handler). MongoDB-style `db.tasks` driver with `count`, `findOne`, `findMany`.

**Governing Documents:** The "Paginated tasks list" design / acceptance-criteria block embedded in the package (lines 25-37): query params, default/max limit with silent clamping, response shape `{ items, nextCursor, total }`, `nextCursor` semantics, ordering `createdAt desc, id desc`, and the enumerated test cases.

**Reviewer:** Cross-vendor second-pass reviewer (Claude).

**Severity Scale:** Critical = data corruption / RCE / privilege escalation; High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated; Medium = incorrect behavior on some inputs, unclear error handling, perf degradation, missing validation implied by the design; Low = style, naming, nits.

**Date:** 2026-04-26

## Findings

### Critical

#### C1. Off-by-one drops the last item of the final page when the result count is an exact multiple of `limit`
- **Citation:** `api/services/tasks.ts:88-101` (the `findMany` call with `limit: fetchSize` and the subsequent `if (fetched.length < limit)` branch).
- **Problem:** The code requests `fetchSize = limit + 1` rows in order to peek at whether a next page exists, but the "is this the last page?" test is `fetched.length < limit` rather than `fetched.length <= limit` (equivalently `< fetchSize`). When the remaining number of matching rows equals exactly `limit`, the driver returns `limit` rows (because there are not `limit+1` of them). `limit < limit` is false, so the code falls through to the "there is a next page" branch, slices to `limit` items, and emits `nextCursor = items[items.length - 1].id`. There is no next page; the next request will return zero items but a non-null cursor on this one. Worse, when the remaining count is exactly `limit` and the call is the final page of an exact-multiple total (e.g., 50 tasks with `limit=25` on page 2), the response advertises a cursor that points past the end, and any consumer that paginates "until `nextCursor === null`" will issue an extra request and may also display a misleading "more results" affordance. Conversely, on the page *before* the final one (e.g., 51 rows total, `limit=25`, second page) the same logic returns `limit` items, sets `nextCursor` to the 25th id, and a subsequent fetch starting at that cursor returns the remaining row(s) — but the original page silently *drops* nothing here because `fetchSize=26` and 26 rows came back. The corruption is specifically the equality case: any page where the residual matches `limit` exactly mis-reports `nextCursor`. Combined with the response promise that "`nextCursor` is null when there are no more items beyond this page," this is a silent contract violation that surfaces as a phantom empty page and, depending on UI, an off-by-one in pagination controls.
- **Why it matters:** Violates the design's explicit `nextCursor` semantics, produces user-visible incorrect pagination on the exact boundary case the design tests call out ("last page", "single-item-page edge case"), and will cause downstream consumers that rely on `nextCursor === null` as a termination signal to perform unbounded extra requests in the worst case (one extra request per terminal page; with caching layers keyed on cursor this can also pollute caches with empty pages).
- **Source of truth:** Acceptance criteria, `redacted.md:34` ("`nextCursor` is null when there are no more items beyond this page.") and `redacted.md:36-37` (tests must cover "last page" and "single-item-page edge case"). The peek-one-extra pattern requires the comparison to be against `fetchSize` (or `<=` against `limit`).
- **Proposed fix:** Compare against `fetchSize`, not `limit`:
  ```ts
  const hasMore = fetched.length > limit          // equivalently fetched.length === fetchSize
  const items = hasMore ? fetched.slice(0, limit) : fetched
  const nextCursor = hasMore ? items[items.length - 1].id : null
  return { items, nextCursor, total }
  ```
  Add a regression test where the total is an exact multiple of `limit` (e.g., 50 tasks, `limit=25`) and assert that the second page has `nextCursor === null`.

### High

#### H1. Tiebreaker on `id` is declared in the sort but not applied to the cursor predicate, producing duplicate or skipped rows when `createdAt` ties span a page boundary
- **Citation:** `api/services/tasks.ts:80-92` (the cursor filter `filter.createdAt = { $lt: cursorTask.createdAt }` together with `sort: [['createdAt', 'desc'], ['id', 'desc']]`).
- **Problem:** The design mandates ordering by `createdAt` desc with `id` as a tiebreaker (`redacted.md:35`). The sort honors that, but the cursor predicate uses a strict `$lt` on `createdAt` only. When two or more rows share the same `createdAt` value and that value straddles a page boundary, the next page filter strictly excludes every row with that `createdAt`, including the rows that the tiebreaker would have placed *after* the cursor. Result: those tiebroken rows are silently skipped. Conversely, if the predicate were `$lte` it would return the cursor row itself plus all of its tied siblings, producing duplicates. Neither plain `$lt` nor plain `$lte` on `createdAt` alone is correct given a compound sort; the predicate must be a lexicographic comparison over `(createdAt, id)`.
- **Why it matters:** Silent data loss across page boundaries whenever timestamps collide (common with bulk imports, fixture seeds, or coarse `Date` truncation). This violates the ordering acceptance criterion and is undetectable from response shape alone.
- **Source of truth:** `redacted.md:35` ("Items are ordered by `createdAt` descending, with `id` as a tiebreaker.").
- **Proposed fix:** Use a tuple comparison consistent with the sort:
  ```ts
  filter.$or = [
    { createdAt: { $lt: cursorTask.createdAt } },
    { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } },
  ]
  ```
  Add a test that seeds two rows with identical `createdAt` straddling a page boundary and asserts no duplication and no loss.

#### H2. Total count is computed without the cursor filter, so `total` describes the unfiltered table rather than the iteration set; combined with the cursor model this is racy and misleading
- **Citation:** `api/services/tasks.ts:74` (`const total = await db.tasks.count({})`).
- **Problem:** The `count({})` call is unconditional — it does not apply the cursor filter (which is fine, since `total` should describe the full result set, not the remaining tail) and it is not constrained to a snapshot. Two issues: (1) The `count` is performed *before* the `findMany`, so concurrent inserts/deletes between the two queries can produce a `total` that is inconsistent with the page contents (e.g., `items.length > total`, or `nextCursor` non-null while `total === items.length`). (2) Because `count({})` runs on every page request, paginating through a large collection imposes N collection scans / index counts. On Mongo-style backends `count({})` on an unindexed predicate is O(N) per call; on a 10M-row collection, paginating end-to-end at `limit=25` costs 400k full-collection counts. The design requires `total` in the response but does not specify that it must be exact for every page; even so, this is a foreseeable performance and consistency hazard.
- **Why it matters:** Silent data inconsistency under concurrent writes, plus a concrete N²-style cost when pagination is the common access pattern. The handler currently has no guardrails.
- **Source of truth:** `redacted.md:34` (response shape requires `total`); the design implies a coherent snapshot but does not waive performance.
- **Proposed fix:** At minimum, compute `total` once for a paginated traversal by accepting a `total` hint via the cursor (encode it alongside the id) so subsequent pages skip the count. If exactness is mandatory, run `count` and `findMany` in a session/snapshot. Add an index on `createdAt desc, id desc` and confirm `count({})` uses a covered count.

#### H3. Cursor is an opaque `id` looked up against the live table; deleting the cursor row breaks pagination mid-traversal with a 400
- **Citation:** `api/services/tasks.ts:80-86` (the `findOne({ id: query.cursor })` lookup that throws "Invalid cursor" when the row is missing) and `api/routes/tasks.ts:124-132` (the handler that converts that error into HTTP 400 `InvalidCursor`).
- **Problem:** Cursors are raw task ids. If a client receives `nextCursor = "abc"` and then row `abc` is deleted before the next request arrives, the follow-up request returns HTTP 400 even though pagination *could* continue from the next-older row. This conflates "client supplied a syntactically bogus cursor" with "the cursor is valid but the anchor row was deleted." The design's `malformed cursor` test case is satisfied semantically only for the malformed case — not for the deleted-anchor case, which is far more common in production. Additionally, every page request now performs an extra round-trip (`findOne`) just to fetch the anchor's `createdAt`; encoding `(createdAt, id)` into the cursor would eliminate that round-trip and make the cursor self-describing.
- **Why it matters:** Common-load failure mode — any task deletion between page fetches breaks live pagination for any client mid-scroll. The implementation also leaks internal ids as the public cursor token, making cursor forgery / row-existence probing trivial.
- **Source of truth:** `redacted.md:31-37`. The design does not require that cursors be raw ids; it requires that pagination work and that malformed cursors are handled. Current behavior fails on a benign concurrent delete.
- **Proposed fix:** Encode the cursor as a base64 of `{ createdAt, id }` (optionally signed/HMAC). Use it directly in the `(createdAt, id)` predicate without any extra lookup. Reserve 400 for cursors that fail to decode/verify; a missing-anchor case becomes a non-event because no lookup is performed.

#### H4. `clampLimit` silently coerces `limit=0`, negative numbers, and `NaN` to the default of 25, which is "silent clamp" for negatives but *expansion* for zero — not the spec's "clamp"
- **Citation:** `api/services/tasks.ts:65-70`.
- **Problem:** The acceptance criterion says "Default limit is 25, max is 100. Clamp out-of-range values silently." A reasonable reading is: missing → default; below min → min; above max → max. The implementation instead routes `limit=0`, negatives, and `NaN` to the *default* (25), which is materially different from clamping to the minimum (1). For `limit=0` callers (e.g., metadata-only queries trying to fetch just `total`), this returns 25 rows when the caller asked for none — a footgun that wastes bandwidth and contradicts the request. For very large negative numbers, the client's intent is plainly malformed; returning 25 is acceptable but not what the word "clamp" describes. Additionally, `Number(req.query.limit)` (`api/routes/tasks.ts:119`) passes through `Infinity` unchanged; `clampLimit(Infinity)` correctly clamps to `MAX_LIMIT`, but `clampLimit(-Infinity)` returns `DEFAULT_LIMIT`. Non-integer floats (e.g., `limit=10.7`) are accepted and floored — fine, but undocumented.
- **Why it matters:** Behavior diverges from the spec's "clamp" wording on common edge inputs (`0`, `-1`); silent coercion of `0` to `25` is the kind of mismatch a careful reviewer would flag because it returns more data than asked for.
- **Source of truth:** `redacted.md:32` ("Default limit is 25, max is 100. Clamp out-of-range values silently.").
- **Proposed fix:** Distinguish missing/non-numeric (→ default) from out-of-range (→ clamp to nearest bound):
  ```ts
  function clampLimit(limit: number | undefined): number {
    if (limit === undefined || Number.isNaN(limit)) return DEFAULT_LIMIT
    if (!Number.isFinite(limit)) return limit > 0 ? MAX_LIMIT : 1
    const n = Math.floor(limit)
    if (n < 1) return 1
    if (n > MAX_LIMIT) return MAX_LIMIT
    return n
  }
  ```
  Add tests for `limit=0`, `limit=-5`, `limit=NaN`, `limit=Infinity`, `limit=10.7`, `limit=101`.

### Medium

#### M1. Error string-matching for `InvalidCursor` is brittle and couples the route to the service's error-message wording
- **Citation:** `api/routes/tasks.ts:125` (`err.message.startsWith('Invalid cursor')`) and `api/services/tasks.ts:83` (the throw site).
- **Problem:** The route classifies "this is a 400, not a 500" by string-matching the message. Any future log-cleanup, i18n, or refactor of the service's error wording silently demotes the response from 400 to 500. The classification belongs in a typed error.
- **Why it matters:** Unclear error handling per the severity rubric; makes it easy to break the public error contract during unrelated edits.
- **Source of truth:** General error-handling hygiene; the design implies "malformed cursor" is a tested case (`redacted.md:37`).
- **Proposed fix:** Define `class InvalidCursorError extends Error {}` in the service and throw it; the route uses `err instanceof InvalidCursorError`.

#### M2. `req.query.limit` accepts arrays and unexpected shapes; `Number(['1','2'])` becomes `NaN` silently
- **Citation:** `api/routes/tasks.ts:119`.
- **Problem:** Express's default query parser accepts repeated keys as arrays (`?limit=1&limit=2`). `Number(['1','2'])` → `NaN`, which `clampLimit` silently turns into the default. The user's intent (one of the two limits, or a 400) is hidden. Same for nested objects when `extended` query parsing is enabled. Cursor handling is partially defended (`typeof === 'string'`), but limit is not.
- **Why it matters:** Missing input validation that the design implies (the test list includes "limit enforcement" and "malformed cursor" — limit malformation is the symmetric case).
- **Source of truth:** `redacted.md:31-37`.
- **Proposed fix:** Validate that `req.query.limit` is `string | undefined`; reject array/object forms with 400.

#### M3. `count({})` may not match the filter set used by `findMany` once additional filters are added later (e.g., status filter, soft-delete)
- **Citation:** `api/services/tasks.ts:74-92`.
- **Problem:** `total` is computed with an empty filter; `findMany` is computed with the cursor filter only. The design today implies a flat list, but the schema includes `status: string`, suggesting a likely near-future filter. Once a status (or soft-delete `deletedAt`) filter is added, `total` will continue to count *all* rows and disagree with `items` semantics. Easy to forget at the point of adding the filter.
- **Why it matters:** Latent bug; the response field is named `total` and consumers will read it as "total matching."
- **Source of truth:** `redacted.md:34` (response shape).
- **Proposed fix:** Factor the predicate into a `baseFilter` used by both `count` and `findMany`; keep the cursor filter as a separate AND on top of `baseFilter` for `findMany`.

#### M4. `Task.createdAt` is typed as `Date`, but the JSON response will serialize it to an ISO string; no contract is documented for the wire format
- **Citation:** `api/services/tasks.ts:44-49` and `api/routes/tasks.ts:122-123`.
- **Problem:** `res.json(result)` runs `JSON.stringify`, converting `Date` to an ISO-8601 string. Clients and tests need to be told this. There is no schema/serializer.
- **Why it matters:** Mild contract ambiguity; tests that compare to `Date` instances will fail.
- **Source of truth:** General API hygiene; design does not specify the wire format.
- **Proposed fix:** Either type `Task.createdAt` as `string` at the boundary (with a separate domain type) or document the wire format and serialize explicitly.

#### M5. `db.tasks.findMany` parameter order/shape is undocumented and worth asserting
- **Citation:** `api/services/tasks.ts:88-92`.
- **Problem:** The call passes `{ filter, sort, limit }` as a single options object; this is plausible but the shape is not part of the supplied design. If the underlying driver uses a different convention (e.g., `findMany(filter, options)`), the service silently no-ops the sort or limit.
- **Why it matters:** Easy regression source; without a unit test that asserts the actual call shape against the driver, a typo here is invisible until production.
- **Source of truth:** N/A; package omits the driver interface.
- **Proposed fix:** Add a unit test that mocks `db.tasks` and asserts the exact arguments.

### Low

#### L1. `Math.floor(limit)` is applied after the range checks, so `limit=100.9` becomes 100 but `limit=100.0001` is treated as `> MAX_LIMIT` and clamped to 100 anyway — fine, but `limit=0.5` becomes default (25) rather than 1
- **Citation:** `api/services/tasks.ts:67-69`.
- **Problem:** Because the integer coercion is the last step, the comparisons run against the raw float. `0.5 < 1` triggers the default branch. Minor surprise.
- **Why it matters:** Edge-case clarity.
- **Source of truth:** N/A.
- **Proposed fix:** Floor first, then compare (see C1/H4 fix).

#### L2. `(req as any).id` to access request id leaks through TypeScript; should use a typed augmentation
- **Citation:** `api/routes/tasks.ts:129`.
- **Problem:** `as any` bypasses the type system for what is presumably a request-id middleware.
- **Why it matters:** Style/safety nit.
- **Source of truth:** N/A.
- **Proposed fix:** Augment `Express.Request` in a `types/express.d.ts` and drop the cast.

#### L3. `PageQuery.cursor` is typed `string` but the route narrows non-string forms to `undefined` silently rather than 400
- **Citation:** `api/routes/tasks.ts:120`.
- **Problem:** When a client sends `?cursor=` (empty) or `?cursor[]=a&cursor[]=b`, the request silently degrades to "first page." The design's "malformed cursor" test should arguably cover this.
- **Why it matters:** Minor input-validation gap; aligns with M2.
- **Source of truth:** `redacted.md:37`.
- **Proposed fix:** Reject non-string and empty-string cursors with 400 `InvalidCursor`.

#### L4. No upper bound on cursor length; raw ids passed back through the query string allow trivial probing
- **Citation:** `api/services/tasks.ts:81`.
- **Problem:** `findOne({ id: query.cursor })` runs an indexed lookup with whatever string the client supplied. With no size cap, a hostile client can send extremely long cursors. Low risk given an indexed primary-key lookup, but worth a length cap.
- **Why it matters:** Defensive nit.
- **Source of truth:** N/A.
- **Proposed fix:** Cap cursor length at a sensible max (e.g., 256 chars) and reject longer with 400.

#### L5. The acceptance criteria call out "empty result" as a tested case; the implementation handles it but inadvertently issues a `count({})` even when no items will be returned
- **Citation:** `api/services/tasks.ts:74`.
- **Problem:** Minor wasted work. Could short-circuit when the filter is known to be empty post-cursor, but probably not worth the complexity.
- **Why it matters:** Trivial perf nit.
- **Source of truth:** `redacted.md:36-37`.
- **Proposed fix:** Optional; ignore unless profiling shows it.
