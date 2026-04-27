Review Scope: `GET /api/tasks` pagination and `listTasks` query helper  
Process Used: Static review of the provided package only  
Execution Context: Closed-context evaluation; no shell commands or filesystem reads used  
Integration Target: Express API route plus task service query helper  
Governing Documents: Provided acceptance criteria for paginated tasks list  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-26

**High Findings**

**H1: Cursor filter drops tasks that share the cursor `createdAt`**  
Citation: `api/services/tasks.ts:42`

Problem: Pagination sorts by `createdAt desc, id desc`, but the cursor filter only applies `createdAt < cursorTask.createdAt`. If multiple tasks have the same `createdAt`, any remaining tasks with the same timestamp and lower `id` than the cursor are skipped.

Why it matters: This violates the required ordering contract: “Items are ordered by `createdAt` descending, with `id` as a tiebreaker.” Cursor pagination must use the full ordering key, or pages can silently omit tasks.

Source of truth: Acceptance criteria: ordered by `createdAt` descending, with `id` as tiebreaker.

Proposed fix: Use a compound cursor predicate matching the sort:

```ts
filter.$or = [
  { createdAt: { $lt: cursorTask.createdAt } },
  { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } },
]
```

Adjust to the database query syntax actually supported by `db.tasks.findMany`.

**Medium Findings**

**M1: `nextCursor` can be set when there is no next page**  
Citation: `api/services/tasks.ts:52`

Problem: The “last page” check uses `fetched.length < limit`, but with fetch-one-extra pagination the correct check is whether `fetched.length <= limit`. If exactly `limit` records are fetched, there is no extra row proving another page exists, so `nextCursor` should be `null`.

Why it matters: A page with exactly `limit` remaining items returns a non-null `nextCursor`, causing clients to request an unnecessary next page. This violates “`nextCursor` is null when there are no more items beyond this page.”

Source of truth: Acceptance criteria: `nextCursor` is null when there are no more items beyond this page.

Proposed fix:

```ts
if (fetched.length <= limit) {
  return {
    items: fetched,
    nextCursor: null,
    total,
  }
}
```

Then keep the existing slice and cursor assignment for the `fetched.length > limit` case.
