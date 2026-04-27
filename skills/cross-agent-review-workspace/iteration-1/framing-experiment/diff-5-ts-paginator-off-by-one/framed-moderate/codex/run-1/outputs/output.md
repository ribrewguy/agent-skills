**Review Scope:** `GET /api/tasks` pagination behavior and `listTasks` helper  
**Process Used:** Closed-context structured code review of supplied package only  
**Execution Context:** No tools, filesystem reads, or shell commands used  
**Integration Target:** Express route backed by `api/services/tasks.ts`  
**Governing Documents:** Paginated tasks list acceptance criteria in package  
**Reviewer:** Codex  
**Severity Scale:** Critical, High, Medium, Low as provided  
**Date:** 2026-04-26

**Findings - High**

**api/services/tasks.ts:52**  
Problem: Last-page detection uses `fetched.length < limit`, but the fetch-one-extra pattern requires checking whether more than `limit` rows were fetched. If exactly `limit` rows are returned, there is no extra row, so `nextCursor` should be `null`.

Why it matters: This violates the required `nextCursor` contract and creates false next pages, especially when the page size exactly matches the remaining item count, including the single-item-page edge case.

Source of truth: Acceptance criteria: “`nextCursor` is null when there are no more items beyond this page.”

Proposed fix: Change the branch to detect no extra item:

```ts
if (fetched.length <= limit) {
  return { items: fetched, nextCursor: null, total }
}
```

Then only set `nextCursor` when `fetched.length > limit`.

**api/services/tasks.ts:42**  
Problem: Cursor pagination filters only by `createdAt < cursorTask.createdAt`, but sorting uses `createdAt desc` with `id desc` as a tiebreaker. Items with the same `createdAt` but lower `id` than the cursor are skipped.

Why it matters: This causes silent data loss across pages whenever multiple tasks share the same timestamp. The ordering contract includes `id` as a tiebreaker, so the cursor comparison must include both fields.

Source of truth: Acceptance criteria: “Items are ordered by `createdAt` descending, with `id` as a tiebreaker.”

Proposed fix: Use a compound cursor predicate equivalent to:

```ts
createdAt < cursor.createdAt
OR (createdAt == cursor.createdAt AND id < cursor.id)
```

using the database query syntax supported by this project.

**Findings - Medium**

**api/routes/tasks.ts:7**  
Problem: `req.query.limit ? Number(req.query.limit) : undefined` treats an empty string as absent, but arrays or other query parser shapes can still become `Number(...)` values unexpectedly. For example, repeated `?limit=10&limit=20` may produce an array, and `Number(array)` can produce surprising results.

Why it matters: The API accepts `?limit=N`; malformed inputs should be clamped predictably. This is not a security issue, but it leaves behavior dependent on Express query parsing details.

Source of truth: Acceptance criteria: “Default limit is 25, max is 100. Clamp out-of-range values silently.”

Proposed fix: Parse `limit` only when `typeof req.query.limit === 'string'`; otherwise pass `undefined` or a deliberately malformed numeric value that `clampLimit` handles consistently.
