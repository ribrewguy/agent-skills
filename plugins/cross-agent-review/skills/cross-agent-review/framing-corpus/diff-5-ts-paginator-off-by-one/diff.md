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
