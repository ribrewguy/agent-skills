# Paginated tasks list

Update `GET /api/tasks` and add a query helper to support cursor pagination.

## Acceptance criteria

- Query params: `?limit=N&cursor=ID`.
- Default limit is 25, max is 100. Clamp out-of-range values silently.
- Returns `{ items: Task[], nextCursor: string | null, total: number }`.
- `nextCursor` is null when there are no more items beyond this page.
- Items are ordered by `createdAt` descending, with `id` as a tiebreaker.
- Tests cover: first page, middle pages, last page, empty result, limit
  enforcement, malformed cursor, and a single-item-page edge case.
