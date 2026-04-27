Review Scope: `GET /api/tasks` cursor pagination helper and route handling  
Process Used: Closed-context code review from supplied package only  
Execution Context: No commands run, no files read, tests not independently verified  
Integration Target: `api/services/tasks.ts`, `api/routes/tasks.ts`  
Governing Documents: Paginated tasks list acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as provided  
Date: 2026-04-27  

**Critical Findings**

None.

**High Findings**

**H-1: `nextCursor` is returned on exact-size last pages**  
Citation: `api/services/tasks.ts:57`

Problem: The last-page check uses `fetched.length < limit`, but the query fetches `limit + 1` rows. If the final page contains exactly `limit` items, there is no extra row, but the code still treats it as having another page and returns the last item’s id as `nextCursor`.

Why it matters: This violates the requirement that `nextCursor` is `null` when there are no more items beyond the page. It also breaks the required single-item-page edge case when `limit=1` and only one item exists.

Source of truth: Acceptance criteria: “`nextCursor` is null when there are no more items beyond this page” and tests must cover “last page” and “single-item-page edge case.”

Proposed fix: Change the condition to `if (fetched.length <= limit)` and return all fetched items with `nextCursor: null`. Only set `nextCursor` when `fetched.length > limit`.

**H-2: Cursor filtering drops tasks that share the cursor timestamp**  
Citation: `api/services/tasks.ts:47`

Problem: Pagination is sorted by `createdAt desc, id desc`, but the cursor filter only uses `createdAt < cursorTask.createdAt`. If multiple tasks have the same `createdAt`, any remaining tasks with the same timestamp and lower `id` than the cursor are skipped.

Why it matters: This silently omits tasks from paginated results and violates the required deterministic ordering with `id` as a tiebreaker.

Source of truth: Acceptance criteria: “Items are ordered by `createdAt` descending, with `id` as a tiebreaker.”

Proposed fix: Use a compound cursor predicate matching the sort order, equivalent to: `createdAt < cursor.createdAt OR (createdAt == cursor.createdAt AND id < cursor.id)` for descending `id`.

**Medium Findings**

None.

**Low Findings**

None.
