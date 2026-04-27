Review Scope: `GET /api/tasks` cursor pagination implementation and helper behavior against the provided acceptance criteria  
Process Used: Closed-context static review of the supplied package only  
Execution Context: No commands run, no files read, no external context used  
Integration Target: `api/services/tasks.ts`, `api/routes/tasks.ts`  
Governing Documents: “Paginated tasks list” design / acceptance criteria in package  
Reviewer: Cross-vendor second-pass reviewer  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-26

**High Findings**

**H1: Last page detection is off by one and returns a false `nextCursor`**  
Citation: `api/services/tasks.ts:52`  
Problem: The code checks `if (fetched.length < limit)` to decide that there is no next page. Because it fetches `limit + 1`, the correct condition is `fetched.length <= limit`. When the remaining item count is exactly equal to `limit`, this implementation incorrectly reports a `nextCursor`.  
Why it matters: This violates the requirement that `nextCursor` is null when there are no more items beyond the page. It fails common boundary cases, including total count exactly divisible by limit and single-item pages.  
Source-of-truth reference: Acceptance criteria: “`nextCursor` is null when there are no more items beyond this page”; tests must cover “last page” and “single-item-page edge case.”  
Proposed fix: Change the condition to `if (fetched.length <= limit)` and return all fetched items with `nextCursor: null` in that branch.

**H2: Cursor filtering drops tasks that share the cursor timestamp**  
Citation: `api/services/tasks.ts:42`  
Problem: The cursor filter uses only `createdAt < cursorTask.createdAt`. The required ordering is `createdAt` descending with `id` as a tiebreaker, but the cursor predicate ignores `id`. Any task with the same `createdAt` as the cursor and a lower `id` in the sort order will be skipped.  
Why it matters: This causes silent data loss across pages whenever multiple tasks have identical timestamps. The implementation’s sort and cursor semantics are inconsistent.  
Source-of-truth reference: Acceptance criteria: “Items are ordered by `createdAt` descending, with `id` as a tiebreaker.”  
Proposed fix: Use a compound cursor predicate matching the sort order, such as: items where `createdAt < cursor.createdAt` OR `createdAt = cursor.createdAt AND id < cursor.id`, assuming `id desc`.

**Medium Findings**

**M1: Malformed cursor handling only covers nonexistent IDs, not malformed cursor values**  
Citation: `api/routes/tasks.ts:8` and `api/services/tasks.ts:38`  
Problem: The route accepts any string as a cursor and passes it directly to `findOne({ id: query.cursor })`. There is no validation of cursor shape or type beyond being a string.  
Why it matters: The acceptance criteria explicitly require malformed cursor coverage. A random malformed value may be treated the same as a well-formed-but-nonexistent ID, producing ambiguous behavior and possibly leaking the raw cursor in the error message.  
Source-of-truth reference: Acceptance criteria: “Tests cover ... malformed cursor.”  
Proposed fix: Define and validate the expected cursor format before querying. Return a stable `400 InvalidCursor` response for invalid syntax without embedding the raw cursor in the message.

**M2: Limit parsing allows fractional limits, creating inconsistent fetch sizes**  
Citation: `api/routes/tasks.ts:6` and `api/services/tasks.ts:26`  
Problem: `clampLimit` floors the returned limit, but `fetchSize` is computed after flooring, so the final limit is integer. However, malformed numeric strings like `1.9` silently become `1`, while the acceptance criteria only says clamp out-of-range values, not coerce fractional values.  
Why it matters: This is ambiguous behavior that tests may not catch. If API consumers expect `limit=N` to mean an integer page size, accepting fractional input can produce surprising pagination.  
Source-of-truth reference: Acceptance criteria: “Query params: `?limit=N&cursor=ID`”; “Default limit is 25, max is 100. Clamp out-of-range values silently.”  
Proposed fix: Treat non-integer numeric limits as malformed or default them to 25. Document the choice and test it.

**Low Findings**

**L1: Invalid cursor error response exposes raw cursor text**  
Citation: `api/routes/tasks.ts:14`  
Problem: The response message includes `err.message`, which contains the raw cursor value.  
Why it matters: This is unnecessary echoing of client input in an error payload. It is minor here, but avoidable.  
Source-of-truth reference: Acceptance criteria require malformed cursor coverage but do not require echoing cursor input.  
Proposed fix: Return a stable message such as `"Invalid cursor"` and log details server-side if needed.
