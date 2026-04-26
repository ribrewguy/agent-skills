# Task Management API Design

Here is a clean HTTP contract for your task-management backend. I'll spell out URL, method, status codes, params, request/response bodies, and TypeScript types for each endpoint, then hit edge cases at the end.

## Conventions

- Base path: `/api/v1`
- All bodies are JSON, snake_case-free (camelCase on the wire).
- Auth: assume a `Authorization: Bearer <token>` header on every request.
- Error response shape:

```ts
interface ApiErrorResponse {
  error: {
    code: string         // e.g. "VALIDATION_ERROR"
    message: string
    fields?: Record<string, string>  // for validation errors
  }
}
```

- Common shared types:

```ts
type ISO8601 = string

type TaskStatus = "todo" | "in_progress" | "done"
type TaskPriority = "low" | "medium" | "high" | "urgent"

interface User {
  id: string
  name: string
  email: string
}

interface Task {
  id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assignee: User | null
  createdAt: ISO8601
  updatedAt: ISO8601
  completedAt: ISO8601 | null
  createdById: string
}

interface Comment {
  id: string
  taskId: string
  authorId: string
  body: string
  createdAt: ISO8601
}
```

---

## 1. List tasks

**`GET /api/v1/tasks`**

Supports search, filter, sort, and offset/limit pagination.

### Query parameters

| Name        | Type                          | Notes                                        |
|-------------|-------------------------------|----------------------------------------------|
| `search`    | string                        | Free-text over title + description           |
| `assignee`  | string (userId)               | Filter by assignee. Repeat for multiple      |
| `status`    | `TaskStatus`                  | Filter by status. Repeat for multiple        |
| `sort`      | string                        | e.g. `-priority,createdAt` (leading `-` = desc) |
| `page`      | integer (default `1`)         | 1-indexed                                    |
| `pageSize`  | integer (default `25`, max `100`) |                                          |

### Response — `200 OK`

```ts
interface ListTasksResponse {
  tasks: Task[]
  total: number          // total matching rows
  page: number
  pageSize: number
}
```

### TypeScript request type

```ts
interface ListTasksQuery {
  search?: string
  assignee?: string | string[]
  status?: TaskStatus | TaskStatus[]
  sort?: string
  page?: number
  pageSize?: number
}
```

### Status codes
- `200 OK` — list returned
- `400 Bad Request` — bad query (e.g. invalid sort field)
- `401 Unauthorized`

---

## 2. Create a task

**`POST /api/v1/tasks`**

### Request body

```ts
interface CreateTaskRequest {
  title: string                       // required, 1..200 chars
  description?: string                // optional
  priority?: TaskPriority             // default "medium"
  assigneeId?: string                 // user id
  status?: TaskStatus                 // default "todo"
}
```

### Response — `200 OK`

The created `Task` resource.

### Status codes
- `200 OK` — created
- `400 Bad Request` — malformed JSON
- `422 Unprocessable Entity` — VALIDATION_ERROR with field-by-field messages
- `401 Unauthorized`

### Validation errors

Return one field at a time so the client can highlight individual inputs:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "title is required",
    "fields": { "title": "required" }
  }
}
```

---

## 3. Get a single task

**`GET /api/v1/tasks/:id`**

### Response — `200 OK`
The `Task` resource.

### Status codes
- `200 OK`
- `404 NOT_FOUND` — `{ error: { code: "NOT_FOUND", message: "Task <id> not found" } }`
- `401 Unauthorized`

---

## 4. Mark task complete

**`POST /api/v1/tasks/:id/complete`**

Why a dedicated endpoint? Completion is a *distinct domain operation* — it sends emails, writes audit rows, and may trigger webhooks. Separating it from a generic update keeps that side-effect contract explicit, and the URL is self-documenting in logs (`POST /tasks/abc/complete` is unambiguous in tracing tools).

### Request body

Empty (or optional `note` for the audit row):

```ts
interface CompleteTaskRequest {
  note?: string
}
```

### Response — `200 OK`
Returns the updated `Task` (with `status: "done"` and a populated `completedAt`).

### Status codes
- `200 OK`
- `404 NOT_FOUND`
- `409 CONFLICT` — task is already completed
- `401 Unauthorized`, `403 Forbidden`

### Side-effect summary
- Sends completion email to `task.createdBy` and `task.assignee`.
- Writes an `audit_log` row.

---

## 5. Add a comment to a task

**`POST /api/v1/tasks/:id/comments`**

### Request body

```ts
interface CreateCommentRequest {
  body: string         // required, 1..5000 chars
}
```

### Response — `200 OK`

The created `Comment` resource.

### Status codes
- `200 OK`
- `404 NOT_FOUND` — task does not exist
- `422 Unprocessable Entity` — empty body
- `401 Unauthorized`

### Bonus: list comments

`GET /api/v1/tasks/:id/comments` → `{ comments: Comment[], total, page, pageSize }`.

---

## Edge cases

1. **Pagination beyond the end** — return `{ tasks: [], total, ... }`, not a 404.
2. **Sorting on unknown field** — `400 Bad Request` with VALIDATION_ERROR.
3. **Deleting / unassigning user** — preserve `assigneeId` but the `assignee` object becomes `null` if hard-deleted; better to soft-delete users.
4. **Race on completion** — second `POST /complete` returns `409 CONFLICT`.
5. **Comment on completed task** — allowed by default; flag it if your product wants to lock comments after completion.
6. **Filter combinations** — multiple `status` values OR within the param, AND across different params.
7. **Search index lag** — note that newly created tasks may take a moment to appear in `search` queries if you're using async indexing.
8. **Auth scope** — only the assignee, creator, or an admin can complete a task; otherwise `403 Forbidden`.
