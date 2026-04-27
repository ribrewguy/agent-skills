Review Scope: `GET /api/tasks` cursor pagination and `listTasks` helper  
Process Used: Static review of provided package only  
Execution Context: Closed-context evaluation; no shell commands or file reads used  
Integration Target: Express API route and task service pagination behavior  
Governing Documents: Paginated tasks list acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as provided  
Date: April 27, 2026

**High Findings**

**api/services/tasks.ts:42**

Problem: Cursor filtering only uses `createdAt < cursorTask.createdAt`, but the required ordering is `createdAt desc` with `id desc` as a tiebreaker.

Why it matters: If multiple tasks share the same `createdAt`, any task that should appear after the cursor by `id` is skipped entirely. That violates the ordering requirement and can silently omit tasks from paginated results.

Source of truth: Acceptance criteria: “Items are ordered by `createdAt` descending, with `id` as a tiebreaker.”

Proposed fix: Use tuple cursor semantics matching the sort:

```ts
filter.$or = [
  { createdAt: { $lt: cursorTask.createdAt } },
  { createdAt: cursorTask.createdAt, id: { $lt: cursorTask.id } },
]
```

assuming `id desc` ordering.

**api/services/tasks.ts:52**

Problem: The “last page” check uses `fetched.length < limit`, but with the fetch-one-extra pattern it should check whether fewer than `limit + 1` rows were fetched.

Why it matters: When the result set has exactly `limit` items remaining, there is no next page, but this code returns a non-null `nextCursor`. That violates “`nextCursor` is null when there are no more items beyond this page” and breaks the exactly-one-page / full-last-page case.

Source of truth: Acceptance criteria: “`nextCursor` is null when there are no more items beyond this page.”

Proposed fix:

```ts
if (fetched.length <= limit) {
  return { items: fetched, nextCursor: null, total }
}
```

or compare against `fetchSize`:

```ts
if (fetched.length < fetchSize) {
  return { items: fetched, nextCursor: null, total }
}
```

**Medium Findings**

None.

**Low Findings**

None.
