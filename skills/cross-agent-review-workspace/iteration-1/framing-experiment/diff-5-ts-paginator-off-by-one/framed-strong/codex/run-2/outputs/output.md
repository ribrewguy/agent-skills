Review Scope: `GET /api/tasks` cursor pagination and `listTasks` helper  
Process Used: Static review from the supplied package only; no commands or file reads  
Execution Context: Closed-context evaluation  
Integration Target: Express route backed by `api/services/tasks.ts`  
Governing Documents: Acceptance criteria in package  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as provided  
Date: April 26, 2026

**High Findings**

**H1 - `nextCursor` is returned on exact last pages**  
Citation: `api/services/tasks.ts:52`  
Problem: The last-page check uses `if (fetched.length < limit)`, but the query fetches `limit + 1`. When the remaining result count is exactly `limit`, there is no extra row, so there is no next page, yet the code falls through and returns the last item’s id as `nextCursor`.  
Why it matters: This violates the requirement that `nextCursor` is null when there are no more items beyond the page. It also breaks “exactly one page” and single-item-page edge cases.  
Source of truth: Acceptance criteria: “`nextCursor` is null when there are no more items beyond this page.”  
Proposed fix: Change the condition to `if (fetched.length <= limit)` or, more directly, compute `hasNextPage = fetched.length > limit`, then slice and set `nextCursor` only when `hasNextPage` is true.

**H2 - Cursor pagination skips tasks with the same `createdAt` as the cursor**  
Citation: `api/services/tasks.ts:42`  
Problem: The sort order is `createdAt desc, id desc`, but the cursor filter only uses `createdAt < cursorTask.createdAt`. Any tasks with the same `createdAt` and a lower `id` than the cursor are skipped on the next page.  
Why it matters: This creates silent data loss across pages whenever multiple tasks share the same timestamp, violating the ordered pagination contract.  
Source of truth: Acceptance criteria: “Items are ordered by `createdAt` descending, with `id` as a tiebreaker.”  
Proposed fix: Use a compound cursor predicate matching the sort order, equivalent to: `createdAt < cursor.createdAt OR (createdAt = cursor.createdAt AND id < cursor.id)`.

**Medium Findings**

None.

**Low Findings**

None.

No Critical findings identified.
