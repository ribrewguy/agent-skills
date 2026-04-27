# Cross-vendor review request

You are acting as a second-pass cross-vendor reviewer. The work below is
purported to implement the design that follows. Your job is to find what
is wrong, missed, or risky.

Treat this work cold. Re-derive any quality claims yourself; do not
assume any gates have been run.

Apply the structured-code-review format: an 8-field preamble, then
findings tagged with severity Critical / High / Medium / Low, each with
a file:line citation and a Source-of-truth reference.

When grading severity, consider:
- Critical: production data corruption, arbitrary code execution,
  privilege escalation, or similar.
- High: significant security risk, resource leak under common load,
  silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling,
  performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

## Design / Acceptance criteria

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


## Files changed

// api/services/tasks.ts (new functions)

export interface Task {
  id: string
  title: string
  status: string
  createdAt: Date
}

export interface PageResult<T> {
  items: T[]
  nextCursor: string | null
  total: number
}

export interface PageQuery {
  limit?: number
  cursor?: string
}

const DEFAULT_LIMIT = 25
const MAX_LIMIT = 100

function clampLimit(limit: number | undefined): number {
  if (limit === undefined || isNaN(limit)) return DEFAULT_LIMIT
  if (limit < 1) return DEFAULT_LIMIT
  if (limit > MAX_LIMIT) return MAX_LIMIT
  return Math.floor(limit)
}

export async function listTasks(query: PageQuery): Promise<PageResult<Task>> {
  const limit = clampLimit(query.limit)
  const total = await db.tasks.count({})

  // Fetch one extra to determine if there's a next page
  const fetchSize = limit + 1

  const filter: Record<string, unknown> = {}
  if (query.cursor) {
    const cursorTask = await db.tasks.findOne({ id: query.cursor })
    if (!cursorTask) {
      throw new Error(`Invalid cursor: ${query.cursor}`)
    }
    filter.createdAt = { $lt: cursorTask.createdAt }
  }

  const fetched = await db.tasks.findMany({
    filter,
    sort: [['createdAt', 'desc'], ['id', 'desc']],
    limit: fetchSize,
  })

  // If we got fewer than fetchSize, this is the last page
  if (fetched.length < limit) {
    return {
      items: fetched,
      nextCursor: null,
      total,
    }
  }

  // We got at least `limit` items, so there's a next page
  const items = fetched.slice(0, limit)
  const nextCursor = items[items.length - 1].id
  return { items, nextCursor, total }
}


// api/routes/tasks.ts (existing file, GET handler updated)

import { Router } from 'express'
import { listTasks } from '../services/tasks'

export const tasksRouter = Router()

tasksRouter.get('/api/tasks', async (req, res, next) => {
  try {
    const limit = req.query.limit ? Number(req.query.limit) : undefined
    const cursor = typeof req.query.cursor === 'string' ? req.query.cursor : undefined

    const result = await listTasks({ limit, cursor })
    res.json(result)
  } catch (err) {
    if (err instanceof Error && err.message.startsWith('Invalid cursor')) {
      return res.status(400).json({
        code: 'InvalidCursor',
        message: err.message,
        requestId: (req as any).id,
      })
    }
    next(err)
  }
})


## Review instructions

Find what is wrong. Look specifically for issues a typical implementer
would not have noticed during their own review:
- Off-by-one at page boundaries, behavior at total-count multiples of limit, cursor edge cases
- Failure modes that tests don't catch
- Mismatch between the implementation and the design's specific requirements

Use the structured-code-review format. Be specific about file paths and
line numbers in citations. Do not soften findings.
