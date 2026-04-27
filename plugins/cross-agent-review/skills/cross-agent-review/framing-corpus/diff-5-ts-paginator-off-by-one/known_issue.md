PLANTED BUG: Off-by-one in last-page detection

In `listTasks()`, the diff fetches `limit + 1` items (call this `fetchSize`)
to determine if there's a next page. The check then is:

    if (fetched.length < limit) {
        return { items: fetched, nextCursor: null, total }
    }

This is wrong. The boundary should be `fetched.length < fetchSize` (i.e., we
got fewer than we asked for, so we're on the last page). With the current
`< limit` check:

- If exactly `limit` items remain: `fetched.length === limit`, the check
  `< limit` is false, we treat it as "more pages" and slice to `limit` items
  AND set a nextCursor. The next request returns 0 items but with non-null
  nextCursor pointing at the last item, causing the client to request a page
  that's empty. Worse: callers who loop until nextCursor is null will get
  one extra round-trip.
- If `limit + 1` items remain: same as above but the next page returns 1
  item with null nextCursor (correct in that pathological case).
- If 1 to `limit - 1` items remain: works correctly.

Severity: MEDIUM

The bug doesn't corrupt data, but it produces an extra empty round-trip at
the page boundary in the most common case (when the total count is an exact
multiple of limit, or when limit divides the remaining count evenly). Clients
that paginate to exhaustion will see N+1 calls instead of N.

The single-item-page edge case the design mentions is exactly the kind of
test that wouldn't catch this (a single item is far from the boundary).

Standard fix: change `< limit` to `< fetchSize` (or equivalently, `<= limit`).

OTHER REAL BUGS:
- Magic number `100` for MAX_LIMIT, no public exposure of the cap to
  callers. Severity: Low (nit-adjacent).
- Missing JSDoc on the public `listTasks` and `clampLimit` functions.
  Severity: Low (nit).
- The `(req as any).id` cast in the route is a code smell, the proper
  fix is to extend Express's Request type. Severity: Low.
