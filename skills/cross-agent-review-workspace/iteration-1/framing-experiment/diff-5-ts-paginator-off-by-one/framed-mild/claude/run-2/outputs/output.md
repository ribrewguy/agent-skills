**Review Scope:** Cursor pagination implementation for `GET /api/tasks` — `listTasks()` query helper in `api/services/tasks.ts` and updated route handler in `api/routes/tasks.ts`.

**Process Used:** Static read-through against the stated acceptance criteria; trace of edge-case execution (first page, exactly-N-items page, last page, single-item page, malformed cursor, limit clamping); type/contract analysis of the public response shape.

**Execution Context:** Single closed-context review of the supplied package only; no repository checkout, no test execution, no runtime tracing. Tests reportedly pass per implementer note but were not inspected.

**Integration Target:** Express-based Node API exposing `GET /api/tasks` with cursor pagination, backed by a `db.tasks` data layer that supports `count`, `findOne`, and `findMany` with sort + filter + limit semantics.

**Governing Documents:** "Paginated tasks list" design / acceptance criteria embedded in the request (limit defaults/clamping, response shape, ordering by `createdAt desc, id desc`, malformed cursor handling, edge cases).

**Reviewer:** Claude (Opus 4.7, 1M context), automated structured code review.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

_None._

### High

**1. Off-by-one in "last page" detection drops the last item silently.** — `api/services/tasks.ts:79`

- **Problem:** The branch reads `if (fetched.length < limit)` but the fetch size is `limit + 1`. When the database returns exactly `limit` rows (i.e., there are no further pages, but the page is full), `fetched.length === limit`, so the condition is false. Execution falls through to the `slice(0, limit)` branch, which returns all `limit` items but also sets `nextCursor = items[items.length - 1].id` — a non-null cursor pointing past the real end of the data. A subsequent request with that cursor will return an empty page with `nextCursor: null`. Conversely, when there truly is a next page, `fetched.length === limit + 1`, which also satisfies "not less than limit", so that case is handled — but only by coincidence. The intended guard is `if (fetched.length <= limit)` (or equivalently `if (fetched.length < fetchSize)`).
- **Why it matters:** Violates the acceptance criterion "`nextCursor` is null when there are no more items beyond this page." Clients that paginate to completion will make one extra round-trip per traversal and receive a misleading non-null cursor on what is actually the last page. Any client that treats a non-null `nextCursor` as "more data exists" (e.g., for an infinite-scroll spinner or a "Load more" button) will display incorrect UI state. This is a silent data-shape inconsistency at the contract boundary, not a crash.
- **Source of truth:** Acceptance criteria, bullet "`nextCursor` is null when there are no more items beyond this page."
- **Proposed fix:** Change line 79 to `if (fetched.length <= limit)` and return `fetched` (which is at most `limit` items) as `items`. Equivalently, rewrite as:
  ```ts
  const hasMore = fetched.length > limit
  const items = hasMore ? fetched.slice(0, limit) : fetched
  const nextCursor = hasMore ? items[items.length - 1].id : null
  return { items, nextCursor, total }
  ```
  Add a regression test for the case where the total result set size is an exact multiple of `limit` (the implementer's listed "single-item-page edge case" does not exercise this).

**2. Cursor-based filter uses only `createdAt`, ignoring the `id` tiebreaker — duplicates and gaps under non-unique timestamps.** — `api/services/tasks.ts:69,74`

- **Problem:** Sort order is `[['createdAt', 'desc'], ['id', 'desc']]`, which correctly defines a total order. But the cursor filter is `filter.createdAt = { $lt: cursorTask.createdAt }`, which only resumes strictly before the cursor's `createdAt`. If two or more tasks share the same `createdAt` timestamp (common with bulk inserts, fixtures, or coarse-resolution timestamps), the boundary tasks at `createdAt === cursorTask.createdAt` that sort *after* the cursor (smaller `id`) are skipped entirely on the next page, and the cursor task itself is never re-emitted (which is correct), but its sibling rows with equal timestamp and smaller `id` are dropped.
- **Why it matters:** Silent data loss across page boundaries. Acceptance criteria explicitly call out `id` as a tiebreaker, which only matters if it can actually break ties — implying the implementation must handle equal `createdAt` values. As written, the tiebreaker affects ordering within a page but is invisible to the cursor filter.
- **Source of truth:** Acceptance criteria, bullet "Items are ordered by `createdAt` descending, with `id` as a tiebreaker."
- **Proposed fix:** Use a compound (lexicographic) cursor predicate matching the sort order:
  ```ts
  filter.$or = [
    { createdAt: { $lt: cursorTask.createdAt } },
    { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } },
  ]
  ```
  Adjust to the actual query DSL of `db.tasks`. Add a test with two tasks sharing a `createdAt` value that span a page boundary.

### Medium

**3. Malformed cursor maps to 400 only when the cursor is a syntactically valid ID that does not exist; truly malformed cursors will surface as a 500 from the DB layer.** — `api/services/tasks.ts:65`, `api/routes/tasks.ts:109`

- **Problem:** `db.tasks.findOne({ id: query.cursor })` is called with whatever string the client sent. If the underlying driver validates IDs (e.g., expects a Mongo ObjectId or a UUID), passing `"not-a-real-id"` may throw a `CastError`/validation error before the `if (!cursorTask)` check runs. That error has a different message and will not match `err.message.startsWith('Invalid cursor')`, so it falls through to `next(err)` and the global error handler — typically a 500.
- **Why it matters:** Acceptance criteria require tests for "malformed cursor", which strongly implies a 4xx contract for any client-supplied bad cursor, not just unknown-but-well-formed ones. Today the contract is inconsistent depending on the shape of the cursor string.
- **Source of truth:** Acceptance criteria, "Tests cover: ... malformed cursor".
- **Proposed fix:** Validate cursor shape before the DB call (regex/UUID/ObjectId check), or wrap the `findOne` in `try/catch` and rethrow as `Error('Invalid cursor: ...')`. Alternatively, define a typed error class (`InvalidCursorError`) and `instanceof`-check it in the route handler instead of string-matching `err.message`.

**4. `total` is computed without applying the cursor filter and on every page — both a contract ambiguity and a performance issue.** — `api/services/tasks.ts:58`

- **Problem:** `total = await db.tasks.count({})` returns the total task count in the table, regardless of cursor position. This is a defensible interpretation of `total`, but (a) it is unspecified by the design — `total` could equally mean "total matching the current query" or "total remaining after cursor" — and (b) `count({})` runs on every page request, which on large tables can dominate latency and stress the DB. Combined with the off-by-one in finding 1, clients cannot derive an authoritative "are we done?" signal from either `nextCursor` or `total`.
- **Why it matters:** Performance degradation under common load (every paginated traversal triggers N+1 full counts), and an under-specified field in the public contract.
- **Source of truth:** Acceptance criteria, response shape `{ items, nextCursor, total }` (semantics undefined).
- **Proposed fix:** (a) Document what `total` means in a code comment and ideally in the API spec. (b) If the dataset is large, consider an estimated count, caching the count for a short TTL, or only returning `total` on the first page (when `cursor` is absent). (c) If `total` is meant to reflect a filtered subset, pass `filter` (sans cursor predicate) to `count`.

**5. `clampLimit` accepts `0` and negative values by silently substituting the default, but rejects fractional limits via `Math.floor` only after the range check.** — `api/services/tasks.ts:49-54`

- **Problem:** Acceptance criterion says "Clamp out-of-range values silently." The current logic returns `DEFAULT_LIMIT` for `limit < 1`, which means a client requesting `limit=0` gets 25 items rather than an empty page or a clamped 1. More subtly, `Math.floor(99.9)` returns `99` (fine), but `Math.floor(0.5)` returns `0` — except the `< 1` check catches `0.5` first and returns the default. So `?limit=0.5` quietly returns 25 items, which is unlikely to match user intent. Also, `Number(req.query.limit)` in the route returns `NaN` for non-numeric strings, which `clampLimit` correctly maps to the default — good — but `Number('')` returns `0`, which would also map to the default; again, defensible but undocumented.
- **Why it matters:** Edge-case input handling that may surprise clients and is hard to test against without a written spec. "Clamp" most naturally means "snap to the nearest allowed value", which would map `0` and negatives to `1`, not to `25`.
- **Source of truth:** Acceptance criteria, "Default limit is 25, max is 100. Clamp out-of-range values silently."
- **Proposed fix:** Decide and document: clamp `< 1` to `1` (true clamping) versus fall back to `DEFAULT_LIMIT` (current behavior). If clamping, change to `if (limit < 1) return 1`. Also `Math.floor` first, then range-check, to give consistent treatment to fractional inputs.

**6. Route handler leaks an internal error message and uses an `(req as any).id` cast.** — `api/routes/tasks.ts:112-113`

- **Problem:** The 400 response echoes `err.message`, which includes the raw cursor value (`Invalid cursor: ${query.cursor}`). For most APIs this is fine, but if cursor strings are ever derived from internal IDs you'd rather not echo (or contain control characters), reflecting them back is a minor information-disclosure / log-injection vector. Additionally, `(req as any).id` defeats type safety; if the request-id middleware is missing, this silently becomes `undefined` rather than a compile-time error.
- **Why it matters:** Defense-in-depth and code-quality. Not exploitable on its own.
- **Source of truth:** General API hygiene; no explicit acceptance criterion.
- **Proposed fix:** Return a generic message (`message: 'The provided cursor is not valid.'`) and include the offending cursor only in server logs. Augment the Express `Request` type with a `id?: string` property via module augmentation rather than `as any`.

### Low

**7. Magic strings for sort order and ad-hoc filter typing.** — `api/services/tasks.ts:63,74`

- **Problem:** `filter` is typed `Record<string, unknown>`, which throws away all type information and makes finding 2 (the cursor predicate bug) easier to miss. The sort tuple `[['createdAt', 'desc'], ['id', 'desc']]` is repeated implicitly between the sort and the filter; if the ordering ever changes, the cursor predicate must change in lockstep.
- **Why it matters:** Maintainability. A typed filter shape would catch shape mismatches when the cursor predicate is corrected per finding 2.
- **Source of truth:** General TypeScript hygiene.
- **Proposed fix:** Define a `TaskFilter` type matching the data layer's query DSL. Extract the sort order into a named constant (`const TASK_SORT = ...`) used by both the sort argument and any cursor-predicate construction.

**8. `nextCursor` is the last item's `id`, but the schema only guarantees `id` is a `string`.** — `api/services/tasks.ts:89`

- **Problem:** Cursors are opaque identifiers tied to a specific encoding and ordering. Returning the raw `id` works today but couples client cursor handling to internal schema choices and prevents future migration to compound cursors (e.g., once finding 2 is fixed, the natural cursor is `${createdAt}|${id}`, base64-encoded).
- **Why it matters:** API evolvability.
- **Source of truth:** Common cursor-pagination patterns; not in the acceptance criteria.
- **Proposed fix:** Wrap cursor encoding/decoding in `encodeCursor(task)` / `decodeCursor(s)` helpers. Treat cursors as opaque base64 strings.

**9. `clampLimit`'s `isNaN` check should be `Number.isNaN`.** — `api/services/tasks.ts:50`

- **Problem:** Global `isNaN` coerces its argument (`isNaN('foo') === true`). Since `limit` is typed `number | undefined`, this works in practice, but `Number.isNaN` is the modern, type-safe equivalent and is preferred by `eslint`'s `no-restricted-globals`.
- **Why it matters:** Stylistic.
- **Source of truth:** Lint convention.
- **Proposed fix:** Use `Number.isNaN(limit)`.

**10. Implicit `db` import.** — `api/services/tasks.ts:58,65,72`

- **Problem:** The snippet uses `db.tasks` but the file shows no import for `db`. Likely an omission from the diff excerpt; flagged so the reviewer of the actual PR can confirm the import exists and is the expected client (typed, not a default `any`).
- **Why it matters:** Hygiene; an untyped `db` import would mask findings 2 and 7.
- **Source of truth:** N/A.
- **Proposed fix:** Confirm `import { db } from '...'` exists with a typed surface.
