- **Review Scope:** Cursor pagination implementation in `api/services/tasks.ts` (`listTasks`, `clampLimit`, related types) and the `GET /api/tasks` handler in `api/routes/tasks.ts`.
- **Process Used:** Manual static review against the supplied design / acceptance criteria, with line-level inspection of the diff embedded in the package. No execution, no test run.
- **Execution Context:** Closed-context review of a single self-contained package; no access to the surrounding repository, database driver, or test suite.
- **Integration Target:** Existing Express-based API service with a `db.tasks` query layer exposing `count`, `findOne`, and `findMany` (filter/sort/limit). Endpoint is `GET /api/tasks`.
- **Governing Documents:** "Paginated tasks list" design and acceptance criteria embedded in the package (limit defaults/clamping, response shape, ordering, error handling, required test coverage).
- **Reviewer:** Claude (Opus 4.7, 1M context), acting as cross-agent code reviewer.
- **Severity Scale:** Critical (data corruption / RCE / privesc), High (security risk, resource leak under common load, silent data inconsistency, design requirement violated), Medium (incorrect behavior on some inputs, unclear error handling, missing implied validation, perf), Low (style, naming, nits).
- **Date:** 2026-04-26.

## Findings

### Critical

_None._

### High

- **`api/services/tasks.ts:79` — Off-by-one in last-page detection drops the final item of every "exact fit" page.**
  Problem: The code requests `fetchSize = limit + 1` rows, then checks `if (fetched.length < limit)` to decide it is the last page. The boundary condition is wrong: when the database returns exactly `limit` rows (i.e. there are no further items), `fetched.length === limit`, which is **not** `< limit`, so the function falls through to the "there is a next page" branch. There it does `items = fetched.slice(0, limit)` (returns all `limit` rows, correct) but also sets `nextCursor = items[items.length - 1].id` — a non-null cursor pointing at the actual last row in the dataset. The next page request will then filter `createdAt < cursorTask.createdAt` and return zero items with `nextCursor: null`, but only after the client makes an extra round trip.
  Why it matters: Violates the acceptance criterion "`nextCursor` is null when there are no more items beyond this page." Clients that stop paginating only when `nextCursor === null` will perform an extra request on every exact-fit boundary; clients that surface `nextCursor` to a UI ("Load more" button) will show a button that yields an empty page. It is a silent correctness bug in the pagination contract.
  Source-of-truth reference: Acceptance criteria, lines 17–18 ("`nextCursor` is null when there are no more items beyond this page") and the `fetchSize = limit + 1` strategy described in the comment at line 60.
  Proposed fix: Compare against `fetchSize`, not `limit`. Replace line 79 with `if (fetched.length <= limit)` (equivalently `fetched.length < fetchSize`). The "more pages" branch is then only taken when `fetched.length === fetchSize`, i.e. the sentinel extra row was actually returned, which is the entire point of fetching `limit + 1`.

- **`api/services/tasks.ts:69,74` — Cursor filter uses only `createdAt`, breaking the documented `id` tiebreaker and causing skipped/duplicated rows when `createdAt` ties.**
  Problem: Sort is `[['createdAt', 'desc'], ['id', 'desc']]` (line 74), but the cursor filter is `filter.createdAt = { $lt: cursorTask.createdAt }` (line 69). For any two rows that share the same `createdAt`, the cursor jumps strictly past that timestamp, silently dropping every other row with the same `createdAt` that should have appeared on subsequent pages. Conversely, if the cursor row itself shares `createdAt` with later-sorted rows, those rows are skipped entirely.
  Why it matters: Violates the acceptance criterion "Items are ordered by `createdAt` descending, with `id` as a tiebreaker" (line 19). The tiebreaker only matters if the cursor respects it; otherwise pagination is silently lossy whenever timestamps collide (common with bulk inserts, seed data, or coarse-resolution clocks). This is silent data inconsistency under normal load.
  Source-of-truth reference: Acceptance criteria, line 19.
  Proposed fix: Use a compound keyset predicate matching the sort key, e.g.
  ```ts
  filter.$or = [
    { createdAt: { $lt: cursorTask.createdAt } },
    { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } },
  ]
  ```
  (or whatever equivalent the query layer supports). Add a regression test that inserts ≥3 rows sharing `createdAt` and walks the pages.

### Medium

- **`api/routes/tasks.ts:109` — Malformed-cursor handling relies on `Error.message` string matching, and "malformed" is conflated with "not found".**
  Problem: The service throws `new Error(\`Invalid cursor: ${query.cursor}\`)` for any cursor that does not resolve to a row (line 67), and the route discriminates it with `err.message.startsWith('Invalid cursor')` (line 109). String-prefix discrimination is fragile (any future log/format change silently downgrades the 400 to a 500), and a cursor that points to a since-deleted but otherwise well-formed `id` is reported as `InvalidCursor` rather than treated as an empty/last page or a distinct "stale cursor" error. The acceptance criteria call out a "malformed cursor" test, which suggests the route should distinguish well-formedness from existence.
  Why it matters: Brittle error plumbing and ambiguous semantics for legitimate clients. Also leaks the raw cursor value back to the caller in `message`, which is fine for opaque ids but worth flagging if cursors ever become structured tokens.
  Source-of-truth reference: Acceptance criteria, lines 20–21 (test list explicitly includes "malformed cursor").
  Proposed fix: Define a typed error (e.g. `class InvalidCursorError extends Error {}`) in the service, throw that, and `instanceof`-check it in the route. Optionally distinguish `MalformedCursor` (cursor fails a format check before any DB call) from `StaleCursor` (well-formed but `findOne` returned null), and decide per product whether the latter should be a 400 or simply return an empty page with `nextCursor: null`.

- **`api/services/tasks.ts:56–58` — `total` and the page query are not in a single snapshot, allowing `total` to disagree with `items` under concurrent writes.**
  Problem: `db.tasks.count({})` and `db.tasks.findMany(...)` run as two independent queries with no transaction or snapshot isolation. Under inserts/deletes between the two calls, `total` can be smaller than the running sum of `items.length` across pages, or larger than the number a client will ever observe. Also, `count({})` ignores any filter, so it always returns the global total, which is inconsistent with what a filtered-paginated endpoint typically means by `total` — but the acceptance criteria do not specify, so flagging as Medium rather than High.
  Why it matters: Visible inconsistency in client UIs ("Showing 26 of 25 results") and footgun for any future filter parameters added to `listTasks`.
  Source-of-truth reference: Acceptance criteria, line 17 (`total: number` in response shape — semantics unspecified).
  Proposed fix: Document `total` as "approximate global count, not snapshot-consistent with `items`" if that is acceptable; otherwise wrap both reads in a read-only transaction / snapshot. When filters are added, ensure the same filter is passed to `count`.

- **`api/routes/tasks.ts:103` — `Number(req.query.limit)` silently coerces nonsense to `NaN`, which `clampLimit` then maps to the default; "limit=abc" and "limit absent" become indistinguishable.**
  Problem: `req.query.limit ? Number(req.query.limit) : undefined` produces `NaN` for `?limit=abc`, `?limit=`, `?limit=foo`, etc. `clampLimit` treats `NaN` as "use default" (line 50). The acceptance criteria say "Clamp out-of-range values silently," which arguably covers numeric out-of-range, but garbage like `?limit=abc` is not "out of range," it is malformed. Silently defaulting is defensible but worth an explicit decision; it also means clients cannot tell from the response that their parameter was ignored.
  Why it matters: Loses signal for client-side bugs and makes the API harder to debug. Combined with the `Number()` coercion, `?limit=10.7` is also accepted and floored to `10` without complaint, while `?limit=1e3` becomes `1000` then clamped to `100`.
  Source-of-truth reference: Acceptance criteria, line 16 ("Default limit is 25, max is 100. Clamp out-of-range values silently").
  Proposed fix: Either (a) explicitly validate that `req.query.limit` matches `^\d+$` and 400 on parse failure, or (b) keep silent clamping but document it and add a test covering `?limit=abc`. Same treatment for non-string `cursor` (already partially handled at line 104).

- **`api/services/tasks.ts:65` — Cursor lookup performs an unconditional extra round trip per request.**
  Problem: Every paginated request with a cursor does `db.tasks.findOne({ id: query.cursor })` purely to read `cursorTask.createdAt`, then issues the actual page query. That is one extra DB round trip per page on every request — cheap in isolation but unnecessary if the cursor encodes `(createdAt, id)` directly (an opaque base64 of the tuple is the standard keyset pattern).
  Why it matters: Doubles DB calls on the hot path and creates the deletion-race issue called out above. Not a correctness bug on its own.
  Source-of-truth reference: Implementation comment at line 60 vs. standard keyset-pagination practice.
  Proposed fix: Encode the cursor as an opaque token containing `createdAt` and `id` (base64 of a small JSON or a `${ts}:${id}` string), decode it in `listTasks`, and skip the `findOne` entirely. This also fixes Medium #2 by making the cursor self-describing.

### Low

- **`api/services/tasks.ts:49–54` — `clampLimit` accepts a `number | undefined` but treats negative/zero values as "use default" rather than "clamp to 1." Either is defensible; the acceptance criteria say "clamp out-of-range values silently," which more naturally maps to clamping to the nearest valid value (1) than to substituting the default. Minor; document the chosen behavior in a comment or test.

- **`api/services/tasks.ts:74` — Sort tuple is typed implicitly as `string[][]`. Depending on the `db.tasks.findMany` signature this may not be type-safe; consider `as const` or a typed sort spec to prevent silent typos like `'desc'` → `'dsc'`.

- **`api/routes/tasks.ts:113` — `(req as any).id` casts away typing for the request id; if a request-id middleware exists, augment Express's `Request` type once (`declare module 'express-serve-static-core'`) instead of casting at every call site.

- **`api/services/tasks.ts:89` — `items[items.length - 1].id` is safe given the surrounding length check, but reads more clearly as `items.at(-1)!.id` on modern TS targets. Pure style.

- **`api/services/tasks.ts:46–47` — `DEFAULT_LIMIT` and `MAX_LIMIT` are module-private constants; if the route layer ever needs to advertise them (e.g. in an OpenAPI doc or an error message saying "max is 100"), consider exporting them so the limits are defined in exactly one place.

- **General — Tests:** The acceptance criteria require tests covering "first page, middle pages, last page, empty result, limit enforcement, malformed cursor, and a single-item-page edge case" (lines 20–21). The package states "Tests pass" but does not include the test file. Reviewer cannot verify the listed cases were written; in particular, the High #1 off-by-one and High #2 tiebreaker bugs would only be caught by a "last page exactly fills `limit`" test and a "rows sharing `createdAt`" test respectively. Recommend confirming both cases exist before merge.
