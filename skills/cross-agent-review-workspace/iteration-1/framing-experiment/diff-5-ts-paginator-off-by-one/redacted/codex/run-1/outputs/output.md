**Review Scope:** `GET /api/tasks` cursor pagination implementation and helper logic  
**Process Used:** Cold second-pass review from supplied package only  
**Execution Context:** No commands run; no filesystem or external context used  
**Integration Target:** Express route `GET /api/tasks` and `listTasks` service  
**Governing Documents:** Paginated tasks list acceptance criteria in package  
**Reviewer:** Codex cross-vendor reviewer  
**Severity Scale:** Critical / High / Medium / Low as defined in request  
**Date:** 2026-04-26

**Findings - High**

**H-1: `nextCursor` is wrong when exactly one full page remains**  
Citation: `api/services/tasks.ts:52`  
Problem: The last-page check uses `if (fetched.length < limit)`, but the query fetches `limit + 1` rows. The correct “no next page” condition is `fetched.length <= limit`. As written, if exactly `limit` rows remain, the function returns a non-null `nextCursor` even though there are no more items.  
Why it matters: This directly violates “`nextCursor` is null when there are no more items beyond this page” and creates a bogus extra page. It also fails the single-item-page edge case when `limit=1` and only one item exists.  
Source-of-truth reference: Acceptance criteria: `nextCursor` is null when there are no more items beyond this page; tests must cover last page and single-item-page edge case.  
Proposed fix: Change the boundary condition to:

```ts
if (fetched.length <= limit) {
  return { items: fetched, nextCursor: null, total }
}
```

**H-2: Cursor pagination skips tasks that share the cursor’s `createdAt`**  
Citation: `api/services/tasks.ts:42`  
Problem: The cursor filter only uses `createdAt < cursorTask.createdAt`, but the required ordering is `createdAt` descending with `id` as a tiebreaker. For rows with the same `createdAt` as the cursor, later rows in the ordered sequence should still be returned based on `id`. This implementation drops them entirely.  
Why it matters: This causes silent data loss across pages whenever multiple tasks have identical timestamps, which is common under batch inserts or coarse timestamp precision.  
Source-of-truth reference: Acceptance criteria: Items are ordered by `createdAt` descending, with `id` as a tiebreaker.  
Proposed fix: Use a composite cursor predicate matching the sort order:

```ts
filter.$or = [
  { createdAt: { $lt: cursorTask.createdAt } },
  { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } },
]
```

assuming `id` is sorted descending as implemented.

**Findings - Medium**

**M-1: Malformed multi-value cursor is silently treated as no cursor**  
Citation: `api/routes/tasks.ts:9`  
Problem: If `cursor` is present but not a string, for example `?cursor=a&cursor=b`, the route sets it to `undefined` and returns the first page instead of rejecting the malformed cursor.  
Why it matters: The acceptance criteria explicitly call out malformed cursor coverage. Silently ignoring malformed cursor input can produce confusing duplicate first-page responses and hides client bugs.  
Source-of-truth reference: Acceptance criteria: Tests cover malformed cursor.  
Proposed fix: If `req.query.cursor !== undefined && typeof req.query.cursor !== 'string'`, return `400 InvalidCursor`.

**Findings - Critical**

None.

**Findings - Low**

None.
