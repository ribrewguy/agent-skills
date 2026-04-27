- **Review Scope:** Cursor-pagination changes to `GET /api/tasks` and the new `listTasks` query helper, as packaged in `redacted.md` (two TypeScript files: `api/services/tasks.ts` and `api/routes/tasks.ts`).
- **Process Used:** Cold cross-vendor second-pass review. Re-derived all behavior and quality claims from the diff against the stated acceptance criteria; no test execution, no repo exploration beyond the supplied package.
- **Execution Context:** Static read of the package only. No build, lint, type-check, or test runs were performed; gates are treated as un-run.
- **Integration Target:** Express HTTP layer (`api/routes/tasks.ts`) plus a service layer (`api/services/tasks.ts`) backed by a `db.tasks` document-store-style client supporting `count`, `findOne`, and `findMany({ filter, sort, limit })`.
- **Governing Documents:** "Paginated tasks list" design / acceptance-criteria block embedded in the package (query params, default/max limit, response shape, ordering, `nextCursor` semantics, required test coverage).
- **Reviewer:** Cross-vendor reviewer (Claude), single-pass.
- **Severity Scale:** Critical = data corruption / RCE / privilege escalation; High = significant security risk, resource leak under common load, silent data inconsistency, or violated design requirement; Medium = incorrect behavior on some inputs, unclear error handling, perf degradation, or missing implied validation; Low = style / naming / minor refactor / nit.
- **Date:** 2026-04-26.

## Findings

### Critical

_None._

### High

- **`api/services/tasks.ts:95` — Off-by-one in last-page detection drops the final item on full pages.**
  - Problem: `listTasks` fetches `limit + 1` rows (`fetchSize`) specifically to detect a next page, but the guard is `if (fetched.length < limit)`. When the database returns exactly `limit` rows (i.e. there are exactly `limit` matching rows remaining and no more), `fetched.length === limit`, so the code skips the early-return branch, falls through to `items = fetched.slice(0, limit)`, and sets `nextCursor = items[items.length - 1].id` even though there is no next page. The very next request with that cursor returns an empty page, but the client has already been told (via a non-null `nextCursor`) that more items exist.
  - Why it matters: Silent data inconsistency at every page boundary where the remaining row count equals `limit` — including the common case where `total` is a multiple of `limit`. Clients that loop "while nextCursor != null" will perform an extra round-trip on every paginated traversal and, worse, naive UIs will render a "Next page" affordance that leads to an empty page. This directly violates the acceptance criterion "`nextCursor` is null when there are no more items beyond this page."
  - Source-of-truth reference: Acceptance criteria, package lines 33-34 ("Returns `{ items, nextCursor, total }`" and "`nextCursor` is null when there are no more items beyond this page").
  - Proposed fix: Compare against `fetchSize`, not `limit`. Replace the guard with `if (fetched.length <= limit) { return { items: fetched, nextCursor: null, total } }` and then `const items = fetched.slice(0, limit)` for the "more pages" branch. Equivalently: `const hasMore = fetched.length > limit; const items = hasMore ? fetched.slice(0, limit) : fetched; const nextCursor = hasMore ? items[items.length - 1].id : null;`.

- **`api/services/tasks.ts:85` — Cursor filter ignores the `id` tiebreaker, causing skipped or duplicated rows when `createdAt` collides.**
  - Problem: Sort order is `[['createdAt', 'desc'], ['id', 'desc']]`, but the cursor filter is `filter.createdAt = { $lt: cursorTask.createdAt }`. Strict `$lt` on `createdAt` alone means: (a) any other tasks that share the cursor row's `createdAt` are silently skipped on the next page, and (b) if the cursor row itself shares its `createdAt` with siblings that sort after it under the `id desc` tiebreaker, those siblings are dropped from the results entirely. Conversely, switching to `$lte` would re-include the cursor row and any earlier-sorted siblings. The only correct keyset condition for `(createdAt desc, id desc)` is `createdAt < c.createdAt OR (createdAt = c.createdAt AND id < c.id)`.
  - Why it matters: Silent data loss / duplication during normal pagination whenever two tasks share a `createdAt` (bulk inserts, seed data, fixtures, sub-second collisions on coarse timestamps). The design explicitly calls out "`id` as a tiebreaker," so this is a violated design requirement, not a corner case.
  - Source-of-truth reference: Acceptance criteria, package line 35 ("Items are ordered by `createdAt` descending, with `id` as a tiebreaker").
  - Proposed fix: Build a compound keyset filter, e.g. `filter.$or = [{ createdAt: { $lt: cursorTask.createdAt } }, { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } }]`. Drop the bare `filter.createdAt` assignment.

- **`api/services/tasks.ts:83` & `api/routes/tasks.ts:125` — Malformed-cursor handling is brittle string-matching and surfaces the raw cursor value.**
  - Problem: The service throws `new Error(\`Invalid cursor: ${query.cursor}\`)` and the route distinguishes the 400 path with `err.message.startsWith('Invalid cursor')`. (1) Any future refactor or i18n of that message silently breaks the 400 mapping and starts returning 500s for a user-input error. (2) The acceptance criteria require a test for "malformed cursor"; the current implementation only handles "well-formed cursor that points to a non-existent row." A genuinely malformed cursor (e.g. one that the DB rejects, or a non-string after some upstream coercion) will reach `findOne`, potentially throw a different error, and bypass the 400 branch entirely. (3) Echoing the attacker-controlled cursor verbatim in the response body is a minor reflected-content concern and complicates log hygiene.
  - Why it matters: Silent classification failures (user errors served as 500s), and a "malformed cursor" test that only exercises the "not found" path is not actually exercising malformed input. This is a design-requirement gap with operational consequences.
  - Source-of-truth reference: Acceptance criteria, package line 37 ("Tests cover: ... malformed cursor ...").
  - Proposed fix: Define a typed sentinel (`class InvalidCursorError extends Error {}` exported from the service), validate cursor shape before the DB lookup (e.g. non-empty string, matches expected ID format), throw `InvalidCursorError` for both shape failures and not-found, and have the route check `err instanceof InvalidCursorError` rather than string-matching. Return `{ code: 'InvalidCursor', message: 'Invalid or expired cursor' }` without echoing the raw value.

### Medium

- **`api/services/tasks.ts:74` — `total` is computed without the cursor filter and is racy against the page query.**
  - Problem: `total` is a global `db.tasks.count({})` that ignores any future filtering and is issued as a separate query from `findMany`. (1) If the caller ever adds a status / owner filter to `listTasks`, `total` will silently disagree with the items list. (2) Even today, `count({})` and `findMany({...})` are not atomic; concurrent inserts/deletes can produce a `total` that is inconsistent with the page (e.g. `items.length > total`). (3) On large `tasks` collections, a `count` on every paginated request is an unbounded scan and a real perf hazard.
  - Why it matters: Misleading `total` undermines client UIs that render "X of N" or compute page counts; the mismatch is silent. Adding any filter later is a footgun. Performance degrades linearly with table size on every request.
  - Source-of-truth reference: Acceptance criteria, package line 33 (`total: number` in the response shape).
  - Proposed fix: At minimum, document and test that `total` is the unfiltered collection size; better, derive `total` from the same filter that produces `items` (without the cursor predicate), and consider caching or an estimated count for large collections. If "total" only ever means "matching the user-visible filter," fold the filter (minus cursor) into the `count` call.

- **`api/routes/tasks.ts:119` — `Number(req.query.limit)` accepts garbage and silently coerces to defaults instead of validating.**
  - Problem: `req.query.limit` may be a string, an array (Express parses `?limit=1&limit=2` as `['1','2']`), or an object (`?limit[a]=1`). `Number(['1','2'])` → `NaN`, `Number({a:'1'})` → `NaN`, `Number('1.7')` → `1.7`, `Number('-3')` → `-3`, `Number('1e9')` → `1000000000`. `clampLimit` then maps all of these to `DEFAULT_LIMIT` or `MAX_LIMIT` silently, per the design's "clamp silently" rule — but the design's intent is "out-of-range values," not "non-numeric / array / object." Silently treating `?limit=abc` the same as `?limit=25` masks integration bugs in callers.
  - Why it matters: Hides client bugs, makes the API harder to debug, and makes the "limit enforcement" test trivially passable without exercising the genuinely hostile inputs Express will deliver in production.
  - Source-of-truth reference: Acceptance criteria, package lines 31-32 ("Query params: `?limit=N&cursor=ID`. Default limit is 25, max is 100. Clamp out-of-range values silently.").
  - Proposed fix: Parse `req.query.limit` defensively — reject array/object types with 400 (or coerce to undefined), use `Number.parseInt(value, 10)` instead of `Number(...)` so floats are normalized, and keep silent clamping only for finite integers outside `[1, 100]`. Add explicit unit tests for `?limit=abc`, `?limit=1.7`, `?limit=-1`, `?limit=0`, and `?limit=1&limit=2`.

- **`api/services/tasks.ts:65-70` — `clampLimit` silently maps `0`, negatives, and floats inconsistently with the stated rule.**
  - Problem: `limit < 1` → `DEFAULT_LIMIT` (25), but `limit > MAX_LIMIT` → `MAX_LIMIT` (100). The asymmetry is surprising: an out-of-range high value clamps to the boundary, but an out-of-range low value jumps to the default rather than to `1`. The design says "clamp out-of-range values silently," which most readers interpret as clamping to the nearest in-range value (i.e. `1` for `limit < 1`). Additionally, `Math.floor` is applied only on the success path, so `clampLimit(0.5)` returns `DEFAULT_LIMIT` rather than `1`, and `clampLimit(NaN)` is handled but `clampLimit(Infinity)` returns `MAX_LIMIT` (probably fine, but worth a test).
  - Why it matters: Behavior diverges from the natural reading of the spec, and the difference is invisible to callers. A test that asserts "limit=0 returns default 25" locks in a debatable interpretation.
  - Source-of-truth reference: Acceptance criteria, package line 32.
  - Proposed fix: Decide explicitly. Either clamp `< 1` to `1` (recommended, symmetric with the upper bound) or document the "fallback to default" behavior in code and tests. Apply `Math.floor` (or `Math.trunc`) before the range checks so fractional inputs are normalized first.

- **`api/services/tasks.ts:81-86` — Cursor lookup adds an extra round-trip per paginated request and leaks existence of arbitrary task IDs.**
  - Problem: Every cursor request issues a `findOne({ id: query.cursor })` purely to read `cursorTask.createdAt`. (1) That doubles the DB round-trips for the hot path. (2) The 400 vs 500 distinction in the route effectively turns the endpoint into an oracle: an unauthenticated/limited caller can probe arbitrary `id` values and learn from the response (`InvalidCursor` vs `200 OK`) whether a given task ID exists. Depending on the auth model, this is an information disclosure.
  - Why it matters: Latency on every paginated request scales with cursor lookups, and the existence oracle is a real concern for any tenant-scoped or permission-filtered task store.
  - Source-of-truth reference: Acceptance criteria, package line 31 (cursor is `ID`, but no statement that arbitrary IDs should be probeable); general API security hygiene.
  - Proposed fix: Encode the cursor as an opaque, signed (or at least base64-encoded) token containing `{ createdAt, id }` so the server does not need a lookup and cannot be used as an existence oracle. Reject tokens with bad signatures / malformed payloads as `InvalidCursor`. This also fixes the malformed-cursor test gap above.

- **`api/services/tasks.ts:105` — `nextCursor = items[items.length - 1].id` will throw on an empty `items` array if the early-return guard is ever weakened.**
  - Problem: The current guard happens to make `items.length === 0` impossible on this branch, but only because of the (buggy) `< limit` check. After fixing the off-by-one (see High finding above), this line is still safe, but it depends on `limit >= 1`, which `clampLimit` guarantees only if its asymmetry above is preserved. Worth asserting explicitly to prevent regressions.
  - Why it matters: Defense in depth; a future refactor that allows `limit = 0` would crash the handler with `TypeError: Cannot read properties of undefined`.
  - Source-of-truth reference: Acceptance criteria, package line 33 (response shape always returns a string or null `nextCursor`).
  - Proposed fix: After computing `items`, branch explicitly: `const nextCursor = items.length > 0 && hasMore ? items[items.length - 1].id : null;`.

### Low

- **`api/routes/tasks.ts:129` — `(req as any).id` defeats type safety to read a request-id field that is not declared anywhere in the diff.**
  - Problem: Casting to `any` to read `id` papers over a missing module augmentation for `Express.Request`. If the request-id middleware is not actually installed, `requestId` will be `undefined` in error responses without any compile-time warning.
  - Why it matters: Style / maintainability; also makes it easy to ship a build where error responses silently lose their correlation IDs.
  - Source-of-truth reference: General TypeScript hygiene; not specified in the design.
  - Proposed fix: Declare `declare global { namespace Express { interface Request { id?: string } } }` (or import the type from the middleware package) and drop the `as any`.

- **`api/services/tasks.ts:90` — Sort tuple typing relies on a string literal, which is fragile.**
  - Problem: `sort: [['createdAt', 'desc'], ['id', 'desc']]` will be widened to `string[][]` unless the `db.tasks.findMany` signature uses a literal-typed tuple. If the DB client expects `'asc' | 'desc'`, this will either fail to compile or — worse — be silently accepted and broken at runtime.
  - Why it matters: Minor type-safety nit; depends on the DB client's typings, which are not in the package.
  - Source-of-truth reference: N/A.
  - Proposed fix: Use `as const` on each tuple, or declare a `SortSpec` type and pass typed values.

- **`api/services/tasks.ts:79` — `filter` typed as `Record<string, unknown>` loses all type-safety for the query DSL.**
  - Problem: The filter DSL (`{ $lt: ... }`, future `$or`) is hand-rolled with `unknown`. Typos like `$It` (capital i) will compile and produce wrong results.
  - Why it matters: Maintainability / correctness ceiling; same class of issue as the `as any` above.
  - Source-of-truth reference: N/A.
  - Proposed fix: Introduce a typed `TaskFilter` interface (or use the DB client's exported filter type) and type `filter` as `TaskFilter`.

- **`api/routes/tasks.ts:117` — Route is mounted at the absolute path `/api/tasks` inside the router itself.**
  - Problem: Defining `tasksRouter.get('/api/tasks', ...)` instead of `tasksRouter.get('/', ...)` (with the router mounted at `/api/tasks` in the app) couples the router to its mount point and will produce `/api/tasks/api/tasks` if anyone later mounts it under a prefix. This is style, not correctness, but it is a common Express smell.
  - Why it matters: Refactoring footgun.
  - Source-of-truth reference: N/A.
  - Proposed fix: Use `tasksRouter.get('/', ...)` and mount the router at `/api/tasks` in the app entry point.

- **Test coverage gap vs. acceptance criteria — "single-item-page edge case" and "empty result" interact with the off-by-one bug.**
  - Problem: The package contains no test code. The acceptance criteria require seven specific test scenarios (first page, middle pages, last page, empty result, limit enforcement, malformed cursor, single-item page). Two of those (last page where `total % limit == 0`, and single-item-page where the single item is also the last item) are exactly the inputs that would catch the High-severity off-by-one. Their absence — combined with the bug — means a green test suite would falsely signal correctness.
  - Why it matters: The reviewer cannot verify the implementation against the design without these tests; the bugs above survive precisely because they are in the gap.
  - Source-of-truth reference: Acceptance criteria, package lines 36-37.
  - Proposed fix: Add tests that (a) seed exactly `limit` rows and assert `nextCursor === null`, (b) seed `2 * limit` rows and assert the last page returns `nextCursor === null`, (c) seed two rows with identical `createdAt` and verify the tiebreaker is honored across a page boundary, (d) pass a syntactically malformed cursor (not just a non-existent one) and assert HTTP 400 with `code: 'InvalidCursor'`.
