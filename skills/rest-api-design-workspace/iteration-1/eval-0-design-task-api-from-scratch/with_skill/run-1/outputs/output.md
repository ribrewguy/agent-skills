# Task Management API — HTTP Contract

Below is the contract for the five operations. Conventions used throughout: paths are plural nouns with no verbs, request/response bodies and query params are camelCase, list endpoints return a `{ data, pagination }` envelope, error bodies are flat (`{ code, message, details?, requestId }`), every response carries `X-Request-ID`.

---

## Shared types

```ts
// Branded IDs prevent passing a UserId where a TaskId is expected.
type TaskId   = string & { readonly __brand: 'TaskId' }
type UserId   = string & { readonly __brand: 'UserId' }
type CommentId = string & { readonly __brand: 'CommentId' }

type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED'
type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'

interface Task {
  id: TaskId
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assigneeId: UserId | null
  createdAt: string   // ISO-8601
  updatedAt: string
  completedAt: string | null
  createdBy: UserId
}

interface Paginated<T> {
  data: T[]
  pagination: {
    nextCursor: string | null
    hasMore: boolean
  }
}

interface APIError {
  code: string                                   // e.g. "TaskNotFound"
  message: string
  details?: Record<string, unknown> | Array<Record<string, unknown>>
  requestId: string
}
```

Every error response uses `APIError` at the top level. There is no `{ error: { ... } }` wrapper — the HTTP status already classifies the response as an error.

---

## 1. List tasks

**`GET /api/tasks`**

### Query parameters

| Param         | Type                  | Notes |
|---------------|-----------------------|-------|
| `q`           | string                | Free-text search across `title` and `description`. |
| `assigneeId`  | string (UserId)       | Filter by assignee. Repeat to OR-match (`assigneeId=u_1&assigneeId=u_2`). |
| `status`      | `TaskStatus`          | Repeat to OR-match. |
| `sort`        | string                | `field:direction` pairs, comma-separated. Allowed fields: `priority`, `createdAt`. Direction: `asc` \| `desc`. Default `createdAt:desc`. Example: `sort=priority:desc,createdAt:asc`. |
| `cursor`      | string (opaque)       | From previous response's `pagination.nextCursor`. |
| `limit`       | integer               | Default `20`, max `100`. Server clamps; out-of-range rejected with `InvalidRequestParam`. |

### Status codes

- `200 OK` — list (possibly empty).
- `400 Bad Request` — invalid sort field, malformed cursor, sort change with stale cursor, limit out of range.
- `401 Unauthorized` — missing/expired session.

### Response

```ts
type ListTasksResponse = Paginated<Task>
```

Sample (200):

```json
{
  "data": [
    {
      "id": "task_01HXY...",
      "title": "Ship invoicing v2",
      "description": "Cut over the old engine.",
      "status": "IN_PROGRESS",
      "priority": "HIGH",
      "assigneeId": "user_01HX...",
      "createdAt": "2026-04-20T13:04:11Z",
      "updatedAt": "2026-04-25T08:15:02Z",
      "completedAt": null,
      "createdBy": "user_01HW..."
    }
  ],
  "pagination": { "nextCursor": "eyJpZCI6InRhc2tfMDFI...", "hasMore": true }
}
```

### TypeScript types

```ts
interface ListTasksParams {
  q?: string
  assigneeId?: UserId | UserId[]
  status?: TaskStatus | TaskStatus[]
  sort?: string                  // 'priority:desc,createdAt:asc'
  cursor?: string
  limit?: number                 // 1..100, default 20
}
```

### Edge cases

- **Empty result** — `data: []`, `nextCursor: null`, `hasMore: false`. Same envelope shape — no special-case 404.
- **Cursor + sort change** — switching `sort` while reusing an old cursor returns `400` with `code: "CursorSortMismatch"`. Cursors are bound to the sort under which they were issued.
- **No `total`.** The set is unbounded; we never `COUNT(*)` it. If a UI needs "page X of Y," it shouldn't be on this endpoint.
- **Free-text + filter** — filters apply first (AND), search runs on the filtered subset.

---

## 2. Create a task

**`POST /api/tasks`**

### Headers

- `Content-Type: application/json` (required)

### Request body

```ts
interface CreateTaskInput {
  title: string                         // required, 1..200 chars
  description?: string                  // optional, ≤ 4000 chars
  priority?: TaskPriority               // default 'MEDIUM'
  assigneeId?: UserId                   // must reference an existing user
  status?: Extract<TaskStatus, 'PENDING' | 'IN_PROGRESS'>  // initial status; default 'PENDING'
}
```

Note: `id`, `createdAt`, `updatedAt`, `completedAt`, `createdBy` are server-generated. They are not on `CreateTaskInput` and may not be sent by the client.

### Status codes

- `201 Created` — body is the new `Task`. Response includes `Location: /api/tasks/<id>` header.
- `400 Bad Request` — malformed JSON.
- `422 Unprocessable Entity` — schema validation failed. Returns *all* offending fields in `details: Array<{field, message}>`.
- `401 Unauthorized`, `403 Forbidden` — auth issues.

### Sample error (422)

```json
{
  "code": "InvalidRequestBody",
  "message": "Request validation failed",
  "details": [
    { "field": "title", "message": "Title is required" },
    { "field": "priority", "message": "Must be one of LOW, MEDIUM, HIGH, URGENT" }
  ],
  "requestId": "req_01HXY..."
}
```

### Edge cases

- **Unknown `assigneeId`** — `422` with `code: "AssigneeNotFound"`.
- **Trailing whitespace / casing** — server normalises `title` (trim) on input; document the rule so clients don't depend on echo equality.
- **Duplicate titles** are allowed; the server doesn't enforce uniqueness on free text.

---

## 3. Get a single task

**`GET /api/tasks/:id`**

### Status codes

- `200 OK` — body is `Task`.
- `404 Not Found` — `code: "TaskNotFound"`.
- `401 Unauthorized`, `403 Forbidden`.

### Edge cases

- **Soft-deleted tasks** — return `404` with `code: "TaskNotFound"`. Do not leak existence.
- **Caching** — return `ETag`; clients may send `If-None-Match` for `304 Not Modified`. Optional but cheap.

---

## 4. Mark a task complete (and other state transitions)

**`PATCH /api/tasks/:id`** — same endpoint, with a status field in the body.

Completion is a state transition on the task — it changes `status` from a non-terminal value to `COMPLETED`. There is no `/complete` sub-resource. Treating completion as a verb in the URL would fragment the URL space (we'd need `/cancel`, `/reopen`, `/archive` next), and the side-effect work doesn't actually depend on the URL — it depends on the transition.

### Headers

- `Content-Type: application/json`
- `Idempotency-Key: <uuid>` (recommended for completion because side effects are externally visible)

### Request body

```ts
interface UpdateTaskInput {
  title?: string
  description?: string | null         // null clears
  priority?: TaskPriority
  assigneeId?: UserId | null          // null unassigns
  status?: TaskStatus                 // 'COMPLETED' to complete
}
```

To complete:

```http
PATCH /api/tasks/task_01HXY...
Content-Type: application/json
Idempotency-Key: 88a3b...

{ "status": "COMPLETED" }
```

### Status codes

- `200 OK` — body is the updated `Task`.
- `400 Bad Request`, `422 Unprocessable Entity` — validation.
- `404 Not Found` — `TaskNotFound`.
- `409 Conflict` — `InvalidStatusTransition` (e.g. `COMPLETED → IN_PROGRESS`) or `TaskAlreadyCompleted` if you explicitly forbid no-op recompletes.

### Side-effect discipline

Side effects (completion email, audit row, webhook fire) attach to the **actual transition**, not to the URL. The handler reads the existing task, applies the patch, and only fires side effects when `oldStatus !== 'COMPLETED' && newStatus === 'COMPLETED'`:

```ts
async function patchTask(id: TaskId, input: UpdateTaskInput): Promise<Task> {
  const old = await tasks.findOne(id)
  if (!old) throw new TaskNotFoundError(id)

  const next = { ...old, ...input }
  validateTransition(old.status, next.status)   // throws on forbidden moves
  await tasks.update(id, next)

  const isCompletion = old.status !== 'COMPLETED' && next.status === 'COMPLETED'
  if (isCompletion) {
    await emailer.sendCompletionEmail(next)
    await audit.write({ event: 'task.completed', taskId: id, actorId: ctx.userId })
  }

  return next
}
```

This makes a retried PATCH safe — re-PATCHing `{ status: 'COMPLETED' }` on an already-completed task is a no-op and does not double-send the email. Combine with `Idempotency-Key` to give the client byte-identical response replay across retries.

### Edge cases

- **Already completed** — repeated `PATCH { status: 'COMPLETED' }` returns `200 OK` with the same body, no new emails. (Or `409 TaskAlreadyCompleted` if your domain prefers an explicit error — pick one and document it.)
- **Forbidden transition** — `409 InvalidStatusTransition`, `details: { from, to }`.
- **Concurrent updates** — to enforce optimistic concurrency, accept `If-Match: <etag>` and return `412 Precondition Failed`.

---

## 5. Add a comment to a task

**`POST /api/tasks/:id/comments`**

A comment is a new resource with its own identity, lifecycle, and URL — sub-resource POST is the right tool here (unlike completion, which is a field flip on the parent).

### Request body

```ts
interface CreateCommentInput {
  body: string                          // required, 1..10_000 chars
}

interface Comment {
  id: CommentId
  taskId: TaskId
  body: string
  authorId: UserId
  createdAt: string
  updatedAt: string
  editedAt: string | null
}
```

### Status codes

- `201 Created` — body is `Comment`. `Location: /api/comments/<id>` header (or `/api/tasks/:id/comments/<id>` if you don't expose comments at the top level).
- `400`, `422` — body validation.
- `404` — `TaskNotFound`.

### Listing comments

**`GET /api/tasks/:id/comments`** — same `Paginated<Comment>` envelope and cursor rules as tasks.

### Edge cases

- **Empty body** — `422 InvalidRequestBody` with `details: [{ field: 'body', message: 'Body is required' }]`.
- **Comment on a deleted task** — `404 TaskNotFound`.

---

## Error catalog (used above)

| HTTP status | Code                      | When |
|-------------|---------------------------|------|
| 400         | `InvalidRequestParam`     | Malformed query (bad cursor, bad sort, bad limit). |
| 400         | `CursorSortMismatch`      | Reused a cursor under a different `sort` than the one it was issued for. |
| 401         | `SessionExpired`          | Missing or expired session. |
| 403         | `InsufficientPermissions` | Authenticated, but not allowed to act on this task. |
| 404         | `TaskNotFound`            | No such task (or soft-deleted). |
| 409         | `InvalidStatusTransition` | Forbidden state transition. |
| 409         | `TaskAlreadyCompleted`    | (Optional) explicit error on no-op recomplete. |
| 409         | `IdempotencyKeyReused`    | Same `Idempotency-Key` arrived with a different payload hash. |
| 422         | `InvalidRequestBody`      | Schema validation failed. `details: Array<{field, message}>`. |
| 429         | `RateLimited`             | Throttled. `Retry-After` and `X-RateLimit-*` headers set. |

Codes are domain-expressive — none of them just echo the HTTP status word. `code` and HTTP status do different jobs: HTTP classifies for proxies and generic clients, `code` names the precise domain reason.

---

## Cross-cutting requirements

- **Headers on every response** — `X-Request-ID` (correlates with `requestId` inside any error body), `Content-Type: application/json; charset=utf-8`.
- **Rate limiting** — emit `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on success; `Retry-After` on `429`.
- **Validation at the boundary only.** Internal services trust their inputs. Validators run inside the route handler (Zod / Pydantic / your-pick) and produce the `InvalidRequestBody` array shape on failure.
- **Wire convention** — body fields and query params are camelCase. The DB is snake_case under the hood; route adapters do the case map. Do not let `created_at` or `assignee_id` reach the client.
