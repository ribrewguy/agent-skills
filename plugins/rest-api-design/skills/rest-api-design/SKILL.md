---
name: rest-api-design
description: Use when designing or reviewing HTTP REST APIs — adding new endpoints, modifying service return shapes, defining typed contracts (TypeScript, Python, Go, Rust, or any typed language), establishing pagination/sorting/filtering conventions, standardizing error envelopes, or reviewing PRs at the network boundary. Covers resource-oriented URL design, HTTP method semantics including PATCH for state transitions, status code discipline, domain-expressive error codes that don't echo HTTP statuses, validation-at-boundaries, additive evolution, predictable naming (camelCase wire format, UPPER_SNAKE enums), cursor and offset pagination patterns, idempotency keys, rate limiting headers, request IDs, CORS, content negotiation including vendor media types and streaming formats (NDJSON, SSE). Symptoms — verbs in URLs, sub-resource action verbs like /complete or /cancel for state transitions, error codes that merely echo HTTP status (NOT_FOUND, VALIDATION_ERROR), inconsistent error shapes, error envelopes nested under an `error:` key, snake_case on the wire (or mixed conventions), raw arrays from list endpoints, bespoke pagination envelopes, validation scattered in internal code, GET used for state changes, DB schema names leaked into URLs, per-field round-trip validation, missing idempotency on side-effectful POSTs, `application/json` treated as the only acceptable content type when the endpoint clearly needs streaming or binary.
---

# REST API Design

## Overview

Design stable, well-documented HTTP APIs that are hard to misuse. Good interfaces make the right thing easy and the wrong thing hard. [via Osmani] This skill covers the generic principles — contract-first design, consistent error semantics, validation at boundaries, additive evolution, predictable naming — and layers concrete patterns on top: resource-oriented URLs, HTTP method semantics, cursor/offset/page pagination, sorting, searching, idempotency keys, rate limiting, and request correlation.

The skill is framework-agnostic. It doesn't mandate a specific pagination envelope or error catalog — it gives you the shape and lets your project lock in specific field names. Pair this skill with a project-specific skill (e.g., an internal `<project>-api` skill) that names the exact pagination envelope, error codes, and file locations your codebase uses.

## When to Use

- Designing new API endpoints.
- Defining module boundaries or contracts between services.
- Creating TypeScript interfaces that cross the client/server line.
- Establishing database schema that informs API shape.
- Changing existing public interfaces. [via Osmani]
- Reviewing a PR that touches the HTTP surface.
- Deciding whether a list endpoint should paginate and which strategy fits.
- Symptoms: verbs in REST URLs (`/api/createTask`, `/api/getUsers`), inconsistent error formats, snake_case on the wire, raw arrays returned from list endpoints, bespoke envelope keys (`{ users: [] }`, `{ events, total, limit, offset }`), validation scattered through internal code, `GET` used for state changes, URLs that expose DB schema (`/api/user_table_v2/query`), validation failures reported one field at a time, money-moving POSTs without idempotency.

## External References (inspiration, not binding)

- `addyosmani/agent-skills@api-and-interface-design` — source of the generic interface-design principles (Hyrum's Law, One-Version Rule, Contract First, Error Semantics, Validate at Boundaries, Prefer Addition Over Modification, Predictable Naming, Common Rationalizations, Red Flags, Verification).
- Postman REST Best Practices (https://blog.postman.com/rest-api-best-practices/) — source of operational conventions: sorting/searching syntax, HTTP status discipline (201+Location, 204 on DELETE), validation-errors-as-array, idempotency keys, rate-limit headers, field selection, request IDs, CORS, content negotiation.
- Google API Design Guide (https://cloud.google.com/apis/design) — resource-oriented design inspiration.

Passages adapted from Osmani are tagged `[via Osmani]`. Passages adapted from Postman are tagged `[via Postman]`.

## Core Principles

### Hyrum's Law [via Osmani]

> With a sufficient number of users of an API, all observable behaviors of your system will be depended on by somebody, regardless of what you promise in the contract.

Every public behavior — including undocumented quirks, error message text, timing, and ordering — becomes a de facto contract once users depend on it.

- **Be intentional about what you expose.** Every observable behavior is a potential commitment.
- **Don't leak implementation details.** If users can observe it, they will depend on it. Raw database rows, snake_case keys inherited from the DB, and `total` counts all become contracts by accident.
- **Plan for deprecation at design time.** Breaking changes need a deprecation window and `Sunset` header.
- **Tests are not enough.** Contract tests cover documented behavior; they don't cover the quirks consumers have already depended on.

### The One-Version Rule [via Osmani]

Avoid forcing consumers to choose between multiple versions of the same API. Diamond dependency problems arise when different consumers need different versions of the same thing. Design for a world where only one version exists at a time — **extend rather than fork**.

Default to no URL version segment. Reserve `/v2/` for cases where an external consumer is locked to the current shape and an incompatible change ships alongside a deprecation window. Internal-only breaking changes are migrations, not versions.

### 1. Contract First [via Osmani, adapted]

Define the interface before implementing it. The contract is the spec — implementation follows.

```typescript
// Define the contract first
interface TasksAPI {
  // Returns paginated tasks matching filters
  listTasks(params: ListTasksParams): Promise<Paginated<Task>>

  // Returns a single task or throws NotFoundError
  getTask(id: string): Promise<Task>

  // Partial update — only provided fields change
  updateTask(id: string, input: UpdateTaskInput): Promise<Task>

  // Idempotent delete — succeeds even if already deleted
  deleteTask(id: string): Promise<void>
}
```

Use a canonical `Paginated<T>` type alias shared across every list endpoint. Never define bespoke `PaginatedTasks`, `UsersList`, etc.

### 2. Consistent Error Semantics [via Osmani, adapted]

Every API error follows one shape. Pick a format, document it, and use it everywhere.

```typescript
// The type name IS the abstraction — don't wrap contents in an `error` key.
// HTTP status tells the client this is an error; no extra nesting needed.
interface APIError {
  code: string                                                         // Domain-specific reason, from a catalog
  message: string                                                      // Human-readable, client-safe
  details?: Record<string, unknown> | Array<Record<string, unknown>>   // Shape varies by `code`; narrow on `code` to access specifics
  requestId: string                                                    // Always present; matches X-Request-ID response header
}
```

A note on typing `details`: the bounded `Record<string, unknown> | Array<Record<string, unknown>>` is a deliberate compromise. A raw `unknown` is the most honest type (shape genuinely depends on `code`) but triggers lint rules like `@typescript-eslint/no-unsafe-member-access` on every access. Using `any` anywhere — including `Record<any, any>` — silences both lint and the compiler, which defeats the point. The bounded form says "object-shaped or array-of-object-shaped, values still require narrowing" — enough structure for consumers to know it's keyed data, strict enough that lint stays quiet.

**For strict codebases, upgrade to a discriminated union on `code`** — the rigorous form that makes the catalog itself a type:

```typescript
type APIError =
  | { code: 'InvalidRequestBody'; message: string; details: Array<{ field: string; message: string }>; requestId: string }
  | { code: 'RateLimited';        message: string; details: { retryAfterSeconds: number; bucket: string };         requestId: string }
  | { code: 'CardDeclined';       message: string; details: { declineReason: string };                             requestId: string }
  | { code: 'TaskNotFound';       message: string; details?: { completedAt?: string };                             requestId: string }
  // ...one variant per code in the catalog
```

The union costs a type alias per code but makes every error handler exhaustiveness-checkable (`switch (err.code) { case 'InvalidRequestBody': ... }`), and `details` is pinned to its documented shape per variant — no narrowing required at the consumer. Worth it when the catalog is stable enough that adding a code is a deliberate act.

Equivalent in JSON on the wire:

```json
{
  "code": "TaskAlreadyCompleted",
  "message": "This task was already completed at 2026-04-23T14:05:00Z",
  "requestId": "req_abc123"
}
```

**HTTP status and `code` do different jobs — don't duplicate.** The HTTP status classifies the error at the protocol layer (4xx client, 5xx server) so generic clients, proxies, and retry libraries work without understanding your domain. The `code` names *the specific domain reason* the request failed, so programmatic clients can branch on cause — "card was declined" vs. "merchant is suspended" are both `402 Payment Required`, but the client handles them very differently.

**Codes that echo the HTTP status are redundant and waste the field.** Pick codes that express domain meaning:

| Anti-pattern (redundant with status) | Better (domain-expressive) |
|---|---|
| `NOT_FOUND` on a 404 | `TaskNotFound`, `AccountNotFound` |
| `VALIDATION_ERROR` on a 422 | `InvalidRequestBody`, `EmailFormatInvalid`, `AmountBelowMinimum` |
| `CONFLICT` on a 409 | `TaskAlreadyCompleted`, `IdempotencyKeyReused`, `UniqueConstraintViolated` |
| `FORBIDDEN` on a 403 | `AccountSuspended`, `PlanUpgradeRequired`, `InsufficientPermissions` |
| `UNAUTHENTICATED` on a 401 | `SessionExpired`, `InvalidCredentials`, `MfaRequired` |
| `RATE_LIMITED` on a 429 | Still `RateLimited` is fine — there's rarely a domain-specific "why" beyond "you sent too many." Acceptable exception. |

Codes are typically `PascalCase` or `UPPER_SNAKE_CASE` — pick one and be consistent. Maintain a catalog alongside your API docs; **adding a new code requires a catalog update first**, not inline invention. The catalog documents, for each code: the HTTP status it pairs with, the domain reason, and the shape of `details` when present.

**`details` is generic, not validation-specific.** Any error can carry additional context. The shape depends on the code and is documented per code in the catalog. Examples:

- `InvalidRequestBody` → `details` is `[{ field, message }, ...]` (the validation case)
- `RateLimited` → `details` is `{ retryAfterSeconds: 60, bucket: "payments" }`
- `InsufficientFunds` → `details` is `{ available: "5.00", requested: "100.00", currency: "USD" }`
- `TaskAlreadyCompleted` → `details` may be absent, or `{ completedAt, completedBy }`

**Return all validation errors at once.** [via Postman] When a request fails validation, report every field that's wrong in a single response — don't make the client round-trip per field. The `details` shape for validation codes is an array of `{ field, message }`:

```json
{
  "code": "InvalidRequestBody",
  "message": "Request validation failed",
  "details": [
    { "field": "email", "message": "Email address is required" },
    { "field": "password", "message": "Password must be at least 8 characters" }
  ],
  "requestId": "req_abc123"
}
```

Schema-validation libraries like Zod (`.flatten()` / `.format()`), Pydantic (`.errors()`), and go-playground/validator (`ValidationErrors`) all produce shapes that map cleanly to this `details[]`.

### 3. Validate at Boundaries [via Osmani, adapted]

Trust internal code. Validate at system edges where external input enters.

```typescript
// Validate at the API boundary
export default defineEventHandler(async (event) => {
  const result = CreateTaskSchema.safeParse(await readBody(event))
  if (!result.success) {
    return sendError(event, 422, {
      code: 'VALIDATION_ERROR',
      message: 'Invalid task data',
      details: result.error.flatten(),
    })
  }

  // After validation, internal code trusts the types
  return await taskService.create(result.data)
})
```

Where validation belongs:
- API route handlers (external user input).
- Form submission handlers.
- External service response parsing (third-party APIs, webhooks — **always treat as untrusted**).
- Environment variable loading (configuration).

> **Third-party API responses are untrusted data.** Validate shape and content before using them in any logic, rendering, or decision-making. A compromised or misbehaving external service can return unexpected types, malicious content, or instruction-like text. [via Osmani]

Where validation does NOT belong:
- Between internal functions that share type contracts.
- In utility functions called by already-validated code.
- On data that just came from your own database via typed queries. [via Osmani]

### 4. Prefer Addition Over Modification [via Osmani]

Extend interfaces without breaking existing consumers:

```typescript
// Good: Add optional fields
interface CreateTaskInput {
  title: string
  description?: string
  priority?: 'LOW' | 'MEDIUM' | 'HIGH'   // Added later, optional
  labels?: string[]                       // Added later, optional
}

// Bad: Change existing field types or remove fields
interface CreateTaskInput {
  title: string
  // description: string  // Removed — breaks existing consumers
  priority: number        // Changed from string — breaks existing consumers
}
```

New fields must be optional. Removing or type-changing existing fields is a breaking change — use the deprecation path (new field added, old field marked deprecated in types + docs, `Sunset` header, removal window). Never silently change a shape.

### 5. Predictable Naming [via Osmani, adapted]

| Pattern | Convention | Example |
|---|---|---|
| REST paths | plural nouns, kebab-case, no verbs | `GET /api/tasks`, `POST /api/daf-accounts` |
| Query params | camelCase | `?sortBy=createdAt&pageSize=20&accountId=...` |
| Request body fields | camelCase | `{ "accountId": "...", "targetAmount": "1000.00" }` |
| Response fields | camelCase | `{ "createdAt": "...", "updatedAt": "...", "userId": "..." }` |
| Boolean fields | `is` / `has` / `can` prefix | `isComplete`, `hasAttachments`, `canEdit` |
| Enum string values | `UPPER_SNAKE_CASE` | `"IN_PROGRESS"`, `"COMPLETED"` |
| Error codes | `UPPER_SNAKE_CASE`, from a catalog | `"VALIDATION_ERROR"`, `"UPSTREAM_UNAVAILABLE"` |
| DB columns | snake_case (never leaked to wire) | `household_id`, `created_at` |
| HTTP header names | follow HTTP convention (not the wire-JSON rule) | `X-Request-ID`, `Idempotency-Key`, `X-RateLimit-Limit`, `Content-Type` |

**The wire is camelCase. The DB is snake_case. HTTP headers follow HTTP conventions.** The JSON camelCase rule applies to request/response *bodies* and query *parameters* — not to HTTP *header* names, which follow the HTTP spec (kebab-case or the `X-Pascal-Case` convention for custom headers). Raw DB rows never ship to clients; services (or route adapters) perform the case map between DB and wire. Build a shared case-conversion utility; don't hand-map field by field in every service.

If your project already uses snake_case on the wire, flipping to camelCase is a breaking change — pick your convention early.

## Operational Requirements [via Postman, adapted]

These aren't design choices — they're wire-level requirements every route meets.

### Always HTTPS

All API traffic is HTTPS. Terminate TLS at the edge; routes never accept or emit plaintext. HTTP requests to production are redirected with `301` or rejected.

### Content types

`application/json; charset=utf-8` is the default for structured request and response bodies. The default is a starting point, not a cage — some endpoints legitimately need other representations. Pick the right content type per endpoint; declare it in the contract; enforce it at the boundary.

- **Structured bodies (default):** `application/json; charset=utf-8` on request and response.
- **File uploads:** `multipart/form-data` (with JSON metadata parts) or `application/octet-stream` for raw-binary uploads.
- **Binary downloads:** `application/pdf`, `image/png`, `image/jpeg`, `text/csv`, etc. — use the precise media type for the payload, not `application/octet-stream` as a dumping ground.
- **Streaming:** endpoints that yield records incrementally should use `application/x-ndjson` (one JSON object per line, aka JSONL) or `text/event-stream` (Server-Sent Events) rather than buffering a giant JSON array. Streaming is a different contract than a list endpoint — document it explicitly and clients must consume line-by-line or event-by-event.
- **Vendor / versioned media types:** `application/vnd.<org>.<product>+json` (optional `; version=2.0` parameter) is a legitimate tool when you need explicit format or version negotiation at the protocol layer — e.g., `Accept: application/vnd.mycompany.myapp.customer+json; version=2.0`. This pairs with the One-Version Rule: most APIs don't need it, but when an external consumer is locked to an older representation and a new one ships alongside, media-type versioning keeps both URLs the same while differentiating payloads.
- **Webhook receivers** may accept `application/x-www-form-urlencoded` if the upstream provider sends it (Twilio, some legacy providers). Convert at the boundary and treat as untrusted input.
- **Patch formats:** `application/merge-patch+json` (RFC 7396) for null-means-delete semantics on `PATCH` requests, and `application/json-patch+json` (RFC 6902) for array-element operations, conditional updates, and atomic multi-op. See the "Choosing a patch format" section for when to support each. An endpoint can accept multiple patch formats and branch on `Content-Type`; reject unsupported patch formats with `415`.
- **Content negotiation via `Accept`** is supported where an endpoint exposes multiple representations (`application/json` and `text/csv` for a report, for example). Return `406 NOT_ACCEPTABLE` when the client requests an unsupported type.
- **Reject unexpected request content types** with `415 UNSUPPORTED_MEDIA_TYPE`. Validate `Content-Type` against the endpoint's declared acceptable set — don't silently accept whatever the client sends.
- **`charset=utf-8`** on JSON is best practice (RFC 8259 prefers UTF-8 without a BOM; being explicit avoids ambiguity with middleboxes).

### Request IDs on every response

Every response includes an `X-Request-ID` header — a UUID generated by the request pipeline. This is the same `requestId` that appears inside error bodies, surfaced on the headers so successful responses are correlatable too:

```
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: req_f47ac10b-58cc-4372-a567-0e02b2c3d479
```

If the client supplies an `X-Request-ID` on the request, propagate it (don't overwrite) to allow tracing through gateways. Log the request ID alongside every log line the route emits.

### CORS

For same-origin APIs (web client calls `/api/*` on the same domain that serves the frontend), CORS usually does not apply. When a route is intentionally cross-origin (partner integrations, embedded widgets), configure CORS explicitly — never wildcard (`*`) on credentialed endpoints.

```
Access-Control-Allow-Origin: https://partner.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, Authorization, Idempotency-Key, X-Request-ID
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 86400
```

Allowed origins are configured from an explicit env-driven allowlist. No per-route CORS override unless documented.

### Rate limiting

Rate limits are enforced at the edge. Every response to a rate-limited surface carries three headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1640995200
```

When a limit is exceeded, return `429 TOO_MANY_REQUESTS` with a `RATE_LIMITED` error code. Include a `Retry-After` header (seconds until the window resets). Clients should back off exponentially and surface the error after a bounded number of retries.

### Observability

Log every request with: method, path, status code, latency (ms), authenticated user ID (if applicable), request id, rate-limit bucket. Track error rates and p95/p99 latency per route. Alert on anomalies (sudden `5xx` spike, latency regression).

## REST API Patterns

### Resource Design [via Osmani, adapted]

```
GET    /api/tasks                → List tasks (query params for filtering)
POST   /api/tasks                → Create a task
GET    /api/tasks/:id            → Get a single task
PATCH  /api/tasks/:id            → Update a task (partial) — includes state transitions
DELETE /api/tasks/:id            → Delete a task

GET    /api/tasks/:id/comments   → List comments (sub-resource collection)
POST   /api/tasks/:id/comments   → Add a comment (creates a new Comment resource)
```

**URL depth limit.** [via Postman] Keep nesting to at most two segments (`/api/parent/:id/child`). Three-plus levels (`/api/users/:uid/tasks/:tid/comments/:cid/flags`) is usually a signal that the grandchild deserves its own top-level resource. Flatten by exposing the grandchild at `/api/flags?commentId=...` and optionally keep the short nested POST for creation cohesion.

#### State transitions are `PATCH`, not sub-resource verbs

Changing a field on a resource — including a `status` field that drives side effects — is an update. Use `PATCH` on the resource URI. **Don't invent sub-resource verbs like `/complete`, `/cancel`, `/activate`, `/publish`**. They read as RPC bolted onto REST, they fragment the URL space (one per action × resource), and they push behavior that belongs in the service layer into the URL.

| Anti-pattern | Correct |
|---|---|
| `POST /api/tasks/:id/complete` | `PATCH /api/tasks/:id` with `{ "status": "COMPLETED" }` |
| `POST /api/orders/:id/cancel` | `PATCH /api/orders/:id` with `{ "status": "CANCELLED" }` |
| `POST /api/users/:id/activate` | `PATCH /api/users/:id` with `{ "status": "ACTIVE" }` |
| `POST /api/posts/:id/publish` | `PATCH /api/posts/:id` with `{ "status": "PUBLISHED" }` |

**Side effects (emails, audit rows, webhooks) belong to the transition, not to the URL.** If `task.status` moving from `IN_PROGRESS` to `COMPLETED` must send an email, that's the service's responsibility on the state change — it doesn't matter which URL or verb triggered the transition. The handler detects the actual transition (not every PATCH that sets status to COMPLETED) and fires side effects exactly once per real transition. This is more robust than URL-coded semantics: a client retrying a PATCH after a network blip does the right thing (no duplicate emails) without you inventing a new endpoint.

**Forbidden transitions → `409 CONFLICT` or `422` with a domain code.** Attempting to move from `COMPLETED` to `IN_PROGRESS` returns a clear error (`InvalidStatusTransition`, `TaskAlreadyCompleted`) so the client sees a real failure rather than a silent no-op.

#### When `POST` to a sub-collection is correct

`POST /api/parent/:id/children` is appropriate when **a new resource with its own identity and lifecycle is created**, not when a field on the parent is being flipped.

| Legitimate `POST` to sub-collection | Why |
|---|---|
| `POST /api/accounts/:id/transfers` | A `Transfer` resource is created; it has its own `id`, `status`, history, and URL |
| `POST /api/orders/:id/refunds` | A `Refund` resource is created with its own lifecycle |
| `POST /api/pulls/:id/approvals` | An `Approval` resource is created per reviewer |
| `POST /api/tasks/:id/comments` | A `Comment` is a distinct resource with its own ID |
| `POST /api/users/:id/email-verifications` | An `EmailVerification` resource tracks the one-off send |

**The test:** does the operation produce a new resource with its own identity, URL, and lifecycle? Then `POST` to a sub-collection is correct. If the operation only changes fields on the parent, it's `PATCH` on the parent.

Command-shaped endpoints that don't fit either pattern (e.g., "resend welcome email") are usually hiding a resource — `POST /api/email-sends` with a body naming the template and recipient creates an `EmailSend` resource. Model the noun.

**Response status codes on write verbs.** [via Postman]

| Verb | Success status | Additional rules |
|---|---|---|
| `GET` (found) | `200 OK` | cacheable; no side effects |
| `POST` (created) | `201 Created` | include a `Location` header pointing to the new resource: `Location: /api/tasks/task_abc` |
| `PUT` (replaced) | `200 OK` with new body, or `204 No Content` | idempotent |
| `PATCH` (updated) | `200 OK` with updated body | idempotent in effect — repeating the same patch produces the same state; side effects must deduplicate on real transitions |
| `DELETE` (removed) | `204 No Content`, or `200 OK` with a minimal body describing what was removed | idempotent — re-deleting a missing resource returns `404` (domain code `TaskNotFound` etc.) |

Use these defaults unless the route has a documented reason to diverge. Never use `GET` for operations that change server state.

### Pagination

Every list endpoint paginates. Choose one strategy per project and use it everywhere.

**Cursor-based (recommended for most cases)** — opaque cursor, `hasMore` flag. Best for feeds, high-write datasets, and any list where items can be inserted between requests.

```
GET /api/tasks?cursor=eyJpZCI6MTIzfQ&limit=20
```

```json
{
  "data": [...],
  "pagination": {
    "nextCursor": "eyJpZCI6MTQzfQ",
    "hasMore": true
  }
}
```

Cursors should be opaque to clients (typically `base64url(id|timestamp)`). Clients never construct cursors; they only pass back what the server returned. Sort order is part of the cursor contract — if a client changes sort while supplying a cursor from a different sort, treat it as invalid (`400`).

**Offset / limit** — simpler but has drift issues on high-write datasets (items inserted between page fetches get skipped or duplicated). Acceptable for bounded admin tables where a `COUNT(*)` is cheap and UI needs a total.

```
GET /api/tasks?limit=20&offset=40
```

**Page number** — UI-friendly when the consumer wants "page 3 of 15" semantics. Same drift caveats as offset. Requires a `total` count.

```
GET /api/tasks?page=3&pageSize=20
```

**Decision tree — is this endpoint even a list?**

1. Naturally single (single row, aggregate, summary, stream) → flat domain object, no envelope.
2. Bounded by policy (≤ 10 items forever) → `{ data: [...] }` with documented bound.
3. Time-bucketed chart data (≤ 60 buckets) → `{ buckets, range, granularity }` — chart data is not a list.
4. Unbounded row array that can grow → paginate with your chosen strategy (cursor recommended for user-facing).

**Defaults:** default limit `20`, max limit `100`. Clamp at the route handler; never trust the client to stay within bounds.

**Never return `total` on unbounded sets.** `{ total: 5_000_000 }` forces `COUNT(*)` on a growing table and tells the client nothing actionable. Reserve `total` for bounded sets where it's cheap.

### Filtering [via Osmani, adapted]

Query parameters, camelCase. Additive (AND). Multi-value uses repeated params.

```
GET /api/tasks?assigneeId=user_123&status=PENDING&status=IN_PROGRESS&createdAfter=2026-01-01
```

Validate every filter with a schema (Zod, Joi, etc.) at the route. Cast types at the boundary; services receive parsed/typed input.

### Sorting [via Postman, adapted]

Sort order travels on a single query param named `sort`, camelCase, colon-separated field+direction:

```
GET /api/tasks?sort=createdAt:desc
GET /api/users?sort=lastName:asc
```

Multi-field sort uses comma separation, leftmost field has highest precedence:

```
GET /api/tasks?sort=priority:desc,createdAt:asc
```

Direction is `asc` or `desc` (lowercase). Default direction if omitted is `asc`. The list of sortable fields is schema-validated at the route; unknown fields return `400 VALIDATION_ERROR`. Sort order is part of the cursor contract — see Pagination.

### Searching [via Postman, adapted]

Full-text or field-fuzzy search uses a single `q` query param:

```
GET /api/tasks?q=launch+plan
GET /api/users?q=jane+doe
```

Prefer `q` over `search` for brevity and consistency with PostgreSQL / most search backends. Multi-term queries are space-delimited (URL-encoded as `+` or `%20`). Search results are still paginated. If an endpoint supports both filter and search, filters apply first (AND) and search runs on the filtered subset.

### Partial Updates and State Transitions (PATCH) [via Osmani, adapted]

`PATCH` accepts partial objects — only update what's provided. This includes state transitions.

```
# Only title changes, everything else preserved
PATCH /api/tasks/task_123
Content-Type: application/json
{ "title": "Updated title" }
```

```
# State transition expressed as a field update
PATCH /api/tasks/task_123
Content-Type: application/json
{ "status": "COMPLETED" }
```

Use `PATCH` (not `PUT`) for partial updates. Reserve `PUT` for whole-resource replacement (rare in most codebases).

**Idempotency in `PATCH`.** `PATCH` is expected to be idempotent in effect: repeating the same body produces the same server state. A second `PATCH { "status": "COMPLETED" }` on an already-completed task is a no-op on the resource.

**Side effects on state transitions** — emails, audit rows, webhooks, outbound calls — must be idempotent in the service layer, not at the URL. The handler detects the actual transition (e.g., `old.status === 'IN_PROGRESS' && new.status === 'COMPLETED'`) and fires side effects exactly once per real transition. A second PATCH that doesn't change the state doesn't fire side effects again. This is cleaner than inventing a dedicated action endpoint: it composes with retries, with generic update clients, and with audit tooling that watches the resource.

**Client-retry safety.** For high-stakes transitions where a client might retry and you want byte-identical response replay, `PATCH` can accept `Idempotency-Key` with the same semantics as `POST` — store `(key, payloadHash, response)` for a retention window; same key + same payload returns the stored response; same key + different payload returns `409`. Stripe uses this pattern on `PATCH` for amount changes on subscriptions.

**Forbidden transitions return an error with a domain code.** Moving from `COMPLETED` back to `IN_PROGRESS` → `409 CONFLICT` with `code: "InvalidStatusTransition"` (or `"TaskAlreadyCompleted"`). Never silently no-op — the client needs to know.

#### Choosing a patch format

Three patch formats are common; each has a distinct `Content-Type` and semantics. Most endpoints can start with the first (it's what we've been showing above), and escalate to the others only when the endpoint genuinely needs what they offer. The `Content-Type` is the contract — clients and servers must agree, and servers should reject unexpected ones with `415 UNSUPPORTED_MEDIA_TYPE`.

| Format | Media type | When to use |
|---|---|---|
| **Plain JSON partial** | `application/json` | Default. Body is a partial of the resource shape; missing fields mean "don't change." This is the simple, common case and what most REST APIs mean by PATCH. Ambiguity: you can't tell "don't change" from "set to null" unless you document a convention. |
| **JSON Merge Patch (RFC 7396)** | `application/merge-patch+json` | When you need **explicit null-means-delete semantics**. The body is a JSON document; `null` on a field tells the server to delete it, missing keys mean "don't change," nested objects merge recursively, arrays replace wholesale. Well-defined, easy to implement, resolves the null ambiguity above. Use when clients need to clear fields and you want a standard. |
| **JSON Patch (RFC 6902)** | `application/json-patch+json` | When you need **array-element operations, conditional updates, or atomic multi-op**. Body is an array of operations (`add`, `remove`, `replace`, `move`, `copy`, `test`) referencing JSON Pointers into the resource. Use for resources with complex structure (documents, configurations, policies) or when clients need transactional compound edits. |

**Plain JSON partial — the default.** What most APIs mean by PATCH. Missing keys are "leave alone."

```
PATCH /api/tasks/task_123
Content-Type: application/json

{ "title": "Updated title", "priority": "HIGH" }
```

**JSON Merge Patch — when "delete a field" needs an explicit signal.** `null` means delete; missing means don't change.

```
PATCH /api/tasks/task_123
Content-Type: application/merge-patch+json

{ "description": null, "priority": "HIGH" }
```

This says: *delete the description, set priority to HIGH, leave everything else alone*. Clean convention when you have nullable optional fields and clients need to clear them. Arrays are replaced wholesale — no partial array updates.

**JSON Patch — when element-level array ops or atomic multi-step edits matter.**

```
PATCH /api/tasks/task_123
Content-Type: application/json-patch+json

[
  { "op": "replace", "path": "/title", "value": "Updated title" },
  { "op": "remove", "path": "/description" },
  { "op": "add", "path": "/labels/-", "value": "urgent" },
  { "op": "test", "path": "/version", "value": 7 }
]
```

This says: *replace title, remove description, append 'urgent' to labels, and (critically) verify version is still 7 — if not, the whole patch fails atomically with `409 CONFLICT`*. The `test` operation is how JSON Patch gives you optimistic concurrency: pair it with a `version` field on your resources and you get safe concurrent edits without server-side locks.

**Content negotiation.** An endpoint can accept multiple patch formats — declare the supported set in docs and branch on `Content-Type`. A reasonable progression:

- Ship with plain JSON partial to start.
- Add Merge Patch when the first nullable-field deletion comes up (or just start there if you know you'll need it).
- Add JSON Patch only when a specific resource genuinely needs array-element ops or atomic multi-op — don't default to it for simple resources, it's a heavier contract for clients to construct.

Don't try to emulate Merge Patch or JSON Patch semantics under `application/json` — clients won't know which dialect you're speaking. If you need those semantics, declare the media type.

**Validation stays at the boundary regardless of format.** Whichever format the endpoint accepts, parse into a typed representation and validate — Merge Patch still has to respect your schema's type rules; JSON Patch operations still have to pass schema validation on the *result* of applying the patch. Rejection returns the standard error envelope with a domain code like `InvalidPatchOperation`, `InvalidJsonPointer`, or `PreconditionFailed` (for a failed `test` op).

### Idempotency and Idempotency-Key [via Postman, adapted]

GET, HEAD, PUT, DELETE are idempotent by design — repeating them produces the same result. POST is not: two identical POSTs may create two resources. For POSTs that have meaningful side effects (payments, scheduled transfers, outbound communications, legal actions), accept an `Idempotency-Key` header from the client:

```
POST /api/payments
Idempotency-Key: d7f4c8b2-4e1f-4c0f-9d54-2a9b3c7e1f11
Content-Type: application/json

{ "amount": "100.00", "currency": "USD" }
```

Server behavior:
- Persist the idempotency key alongside the request's canonical payload hash + response for a documented retention window (default 24h; longer for financial writes).
- A retry with the same key and same payload returns the original response (status + body) exactly.
- A retry with the same key and a *different* payload returns `409 CONFLICT` with an error code like `IDEMPOTENCY_KEY_REUSED`.
- Idempotency keys are required on any POST that writes to money-moving or externally-visible state (payments, transfers, emails, agreement acceptance). The route's schema should require the header.

Idempotency is not the same as deduplication across distinct clients — it protects one client's retry loop, not a separate user submitting the same thing.

### Field Selection (sparse fieldsets) [via Postman, adapted]

Allow clients to trim response payloads with a `fields` query param, camelCase, comma-separated:

```
GET /api/tasks/123?fields=title,status,dueDate
```

Rules:
- `fields` is a server-honored *hint*, not a guarantee — the server may ship required fields (like `id`) regardless.
- Nested field selection uses dot notation: `?fields=id,owner.name`.
- Unknown fields are silently ignored (not `400`) — this keeps the client resilient as the schema evolves. Log unknown-field requests at DEBUG for visibility.
- Sparse fieldsets are optional per-endpoint; only wire them on endpoints with large payloads.

## Typed contract patterns (language-neutral)

The patterns below apply in any typed language. TypeScript reads cleanly on the page so the first example uses it, but equivalents exist in Python (Pydantic, dataclasses, `NewType`), Go (structs, named types), Rust (structs, enums, newtypes), Kotlin (data classes, sealed classes), and Java (records, sealed interfaces). The *shape* matters; the syntax is a detail.

### Discriminated unions for variants

Encode each variant explicitly so consumers get exhaustive type-narrowing.

**TypeScript:**
```typescript
type TaskStatus =
  | { type: 'pending' }
  | { type: 'in_progress'; assignee: string; startedAt: string }
  | { type: 'completed'; completedAt: string; completedBy: string }
  | { type: 'cancelled'; reason: string; cancelledAt: string }
```

**Python (Pydantic v2):**
```python
from pydantic import BaseModel
from typing import Literal, Union
from datetime import datetime

class Pending(BaseModel):
    type: Literal["pending"]

class InProgress(BaseModel):
    type: Literal["in_progress"]
    assignee: str
    started_at: datetime

class Completed(BaseModel):
    type: Literal["completed"]
    completed_at: datetime
    completed_by: str

TaskStatus = Union[Pending, InProgress, Completed]
```

**Go** (tagged struct with a discriminator — Go's type system doesn't have sum types, so runtime branching on `Type` is idiomatic):
```go
type TaskStatus struct {
    Type        string     `json:"type"`
    Assignee    *string    `json:"assignee,omitempty"`
    StartedAt   *time.Time `json:"startedAt,omitempty"`
    CompletedAt *time.Time `json:"completedAt,omitempty"`
    CompletedBy *string    `json:"completedBy,omitempty"`
}
```

**Rust:**
```rust
#[derive(Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum TaskStatus {
    Pending,
    InProgress { assignee: String, started_at: DateTime<Utc> },
    Completed { completed_at: DateTime<Utc>, completed_by: String },
    Cancelled { reason: String, cancelled_at: DateTime<Utc> },
}
```

### Input/output separation

Never use the same type for "what the client sends" and "what the server returns." Inputs are smaller (missing server-generated fields); outputs include `id`, timestamps, and derived fields.

**TypeScript:**
```typescript
interface CreateTaskInput {
  title: string
  description?: string
}

interface Task {
  id: string
  title: string
  description: string | null
  createdAt: string
  updatedAt: string
  createdBy: string
}
```

**Python:**
```python
class CreateTaskInput(BaseModel):
    title: str
    description: str | None = None

class Task(BaseModel):
    id: str
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str
```

**Go:**
```go
type CreateTaskInput struct {
    Title       string  `json:"title" validate:"required"`
    Description *string `json:"description,omitempty"`
}

type Task struct {
    ID          string    `json:"id"`
    Title       string    `json:"title"`
    Description *string   `json:"description"`
    CreatedAt   time.Time `json:"createdAt"`
    UpdatedAt   time.Time `json:"updatedAt"`
    CreatedBy   string    `json:"createdBy"`
}
```

### Branded / distinct types for IDs

Prevent accidentally passing a `UserId` where a `TaskId` is expected — cheap safety for IDs that flow across many module boundaries.

**TypeScript (branded):**
```typescript
type TaskId = string & { readonly __brand: 'TaskId' }
type UserId = string & { readonly __brand: 'UserId' }
```

**Python (`NewType` — runtime-thin, static-only):**
```python
from typing import NewType
TaskId = NewType("TaskId", str)
UserId = NewType("UserId", str)
```

**Go (named types):**
```go
type TaskId string
type UserId string
```

**Rust (newtype pattern):**
```rust
struct TaskId(String);
struct UserId(String);
```

Branded / distinct IDs are a judgment call — use them for IDs that cross module boundaries and where a mix-up would be silently accepted. Skip for internal-only IDs.

## Common Rationalizations [Osmani + Postman]

| Rationalization | Reality |
|---|---|
| "We'll document the API later" | The types ARE the documentation. Define them first. [via Osmani] |
| "We don't need pagination for now" | You will the moment someone has 100+ items. Add it from the start. [via Osmani] |
| "PATCH is complicated, let's just use PUT" | PUT requires the full object every time. PATCH is what clients actually want. [via Osmani] |
| "We'll version the API when we need to" | Breaking changes without versioning break consumers. Design for extension from the start. [via Osmani] |
| "Nobody uses that undocumented behavior" | Hyrum's Law: if it's observable, somebody depends on it. Treat every public behavior as a commitment. [via Osmani] |
| "We can just maintain two versions" | Multiple versions multiply maintenance cost and create diamond dependency problems. Prefer the One-Version Rule. [via Osmani] |
| "Internal APIs don't need contracts" | Internal consumers are still consumers. Contracts prevent coupling and enable parallel work. [via Osmani] |
| "Let's just use snake_case since that's what the DB returns" | DB rows never ship to clients. The wire is camelCase regardless of what the ORM hands you. Map at the service boundary. |
| "We'll just return the raw array — the client knows it's a list" | Bare arrays can't grow into paginated lists without breaking consumers. Wrap from day one. |
| "We'll add idempotency later if duplicates become a problem" | By "later" you already have duplicate payments. Wire idempotency keys on money-moving POSTs from the start. |
| "Returning all validation errors at once is too much work" | One round-trip per field is actively worse UX and more work. Your validator already has the full error set — just pass it through. |
| "`POST /tasks/:id/complete` is clearer — it names the action" | The HTTP method already names the action (PATCH = partial update). A URL verb duplicates what the method says and fragments the URL space. `PATCH /tasks/:id` with `{status:"COMPLETED"}` is the same operation without the RPC-on-REST smell. |
| "We need `/complete` so we know when to send the email" | Emails are side effects of the state transition, not of the URL. Detect the transition in the service layer and fire once per real transition — this is more robust (handles retries, generic clients, and audit replay) than URL-coded semantics. |
| "Our error codes should match the HTTP status for simplicity" | HTTP status and `code` do different jobs. The status classifies at the protocol layer; the code names the domain reason. `code:"NOT_FOUND"` on a 404 is two layers saying the same thing — waste the field. `code:"TaskNotFound"` or `code:"CardDeclined"` earns it. |
| "Wrapping errors in `{error: {...}}` is 'the standard'" | The wrapper adds a layer of indirection that HTTP status already provides. If your error type is `APIError`, the body *is* the error — no extra key needed. Popular doesn't mean right. |
| "`application/json` is the only content type we'll need" | Streaming endpoints (NDJSON, SSE), binary downloads (PDF, CSV), file uploads (multipart), and vendor-versioned types all have legitimate places. Declare per endpoint; enforce at the boundary. |

## Red Flags [Osmani + Postman]

- Endpoints that return different shapes depending on conditions. [via Osmani]
- Inconsistent error formats across endpoints. [via Osmani]
- Validation scattered throughout internal code instead of at boundaries. [via Osmani]
- Breaking changes to existing fields (type changes, removals). [via Osmani]
- List endpoints without pagination. [via Osmani]
- Verbs in REST URLs (`/api/createTask`, `/api/getUsers`). [via Osmani]
- Sub-resource action verbs for state transitions (`/api/tasks/:id/complete`, `/api/orders/:id/cancel`, `/api/posts/:id/publish`) instead of `PATCH` with a status field update.
- Error codes that echo the HTTP status (`NOT_FOUND` on a 404, `VALIDATION_ERROR` on a 422) instead of naming the domain reason (`TaskNotFound`, `EmailFormatInvalid`).
- Error bodies nested under an `error:` key — the type is already the error; the wrapper is redundant given HTTP status already classifies the response.
- `application/json` treated as the only content type when the endpoint clearly calls for streaming (NDJSON / SSE), binary (PDF / CSV), or vendor-versioned media types.
- Third-party API responses used without validation or sanitization. [via Osmani]
- `GET` used for operations that mutate state (`GET /api/users/123/delete`, `GET /api/cart/add?...`). [via Postman]
- URL exposes internal implementation (`/api/user_table_v2/query`, `/api/db_row_snapshot/...`). [via Postman]
- Inconsistent naming — one endpoint uses camelCase, another uses snake_case, another uses kebab in the body. [via Postman]
- Validation failures reported one field at a time across multiple round-trips instead of all at once. [via Postman]
- `POST` on a money-moving or side-effectful endpoint without `Idempotency-Key` support. [via Postman, adapted]
- `X-Request-ID` missing from responses.
- Rate-limited endpoint that doesn't emit `X-RateLimit-*` headers or `Retry-After` on `429`.
- CORS configured with `Access-Control-Allow-Origin: *` on a credentialed endpoint.
- snake_case keys on the wire (`user_id`, `created_at`, `next_cursor`, `has_more`).
- Bespoke list envelope (`{ users: [] }`, `{ events, total, limit, offset }`).
- `total` in the pagination envelope on an unbounded set.
- Error code invented inline instead of added to the catalog first.

## Verification [Osmani + Postman]

After designing an API:

**Contract + types** [via Osmani]
- [ ] Every endpoint has typed input and output schemas (any typed language — TS, Python, Go, etc.).
- [ ] Error responses follow the flat envelope: top-level `{ code, message, details?, requestId }` — not wrapped in an `error:` key.
- [ ] Error `code` values are domain-expressive (`TaskNotFound`, `InsufficientFunds`) — they do not merely echo the HTTP status.
- [ ] Validation happens at system boundaries only.
- [ ] List endpoints return a consistent pagination envelope.
- [ ] New fields are additive and optional (backward compatible).
- [ ] Naming follows the predictable-naming table across all endpoints.
- [ ] State transitions use `PATCH` on the resource URI; no sub-resource action verbs (`/complete`, `/cancel`, `/publish`).
- [ ] `POST` to a sub-collection is used only when a new resource with its own identity is created (Transfer, Refund, Comment).
- [ ] `Content-Type` is declared per endpoint and enforced at the boundary; streaming and binary endpoints use appropriate media types (NDJSON, SSE, PDF, CSV, vendor types).
- [ ] For PATCH endpoints, the patch format is explicit in `Content-Type`: plain `application/json` for simple partial updates, `application/merge-patch+json` when null-means-delete matters, `application/json-patch+json` for array-element ops or atomic multi-op with `test` preconditions.

**Status codes + headers** [via Postman, adapted]
- [ ] `POST` success returns `201 Created` with a `Location` header.
- [ ] `DELETE` success returns `204 No Content` (or `200 OK` with a minimal body).
- [ ] Validation failures return all offending fields in one response, `details` as `{field, message}[]`.
- [ ] `X-Request-ID` present on every response.
- [ ] Rate-limited surfaces emit `X-RateLimit-Limit` / `-Remaining` / `-Reset`.
- [ ] Money-moving / side-effectful POSTs accept `Idempotency-Key` and persist it.

**Testing discipline** [via Postman, adapted]
- [ ] 200 happy path (populated result).
- [ ] 200 empty-list shape.
- [ ] 400 invalid cursor / invalid limit / invalid sort field.
- [ ] 401 unauthenticated.
- [ ] 403 forbidden (if auth-sensitive).
- [ ] 404 not found (if applicable).
- [ ] 409 idempotency-key reuse with different payload.
- [ ] 429 rate limit triggers, `Retry-After` present.
- [ ] Retry loops with the same idempotency key don't double-write.

**Documentation** [via Postman, adapted]
- [ ] All endpoints documented with HTTP method, URL, required params, request body, response body, status codes, auth requirements.
- [ ] Working request/response examples included.
- [ ] Error cases and their meanings documented.

## How to present findings

When this skill is active on an audit, review, or design task, the output that reaches the user should read like a senior engineer's review — not a rule-enforcement report. Three guardrails govern the output itself (separate from the technical guidance above, which is input to your reasoning).

### 1. Don't cite the skill in the output

Explain reasoning directly in your own voice. A reviewer argues from first principles ("`GET` must be safe because browsers, caches, prefetchers, and link crawlers follow it freely — a `GET` that mutates state can be triggered by anything that sees the URL"); they don't cite a rulebook ("Listed as a red flag: '`GET` used for operations that mutate state'"). The skill is a reference *for you*; it is not the audience for your output.

Avoid phrases like:
- *"Red flag: ..."* or *"Listed as a red flag"*
- *"The skill requires / calls out / prescribes / mandates..."*
- *"Per the skill's naming table..."*
- *"The skill's verification checklist says..."*

Write the reasoning directly. If a rule is non-obvious, the explanation earns the reader's trust more than the citation does. If the user wants to know where a rule comes from, they'll ask.

### 2. Stay strictly in lane — compose with other skills, don't absorb them

This skill covers **HTTP REST contracts**: URL design, HTTP method semantics, status codes, request/response body shapes, error envelopes, pagination, idempotency, content types, response headers, typed contracts, patch formats. That is the full scope.

**In scope** — anything on the HTTP surface: what bytes travel on the wire, which headers go where, what status codes to return, how errors are shaped, how lists paginate, how patches are formatted.

**Out of scope — name the adjacent skill and defer; don't absorb its job:**

| Concern | Belongs to |
|---|---|
| Password hashing choices, KDF algorithms, credential storage | cryptography / security skill |
| OAuth flows, session lifecycle, MFA implementation, CSRF token mechanics | auth skill |
| SQL injection, prepared statements, ORM patterns, DB schema choices | data-access / security skill |
| File and module layout, handler organization inside the repo | architecture skill |
| Test coverage and test strategy | testing skill |
| Rate limiter *implementation* (token bucket vs leaky bucket, Redis vs in-memory) | infra / platform skill |
| Logging / tracing *implementation* (which library, sampling, retention) | observability skill |
| Performance tuning, caching strategy beyond response headers | performance skill |

Note what *is* in scope even when it looks adjacent: the HTTP *surface* of rate limiting (`429`, `Retry-After`, `X-RateLimit-*` headers) IS this skill's job; the limiter's internal algorithm is not. The error *envelope and code* ARE this skill's job; whether the specific error text is client-safe from a phishing-mitigation standpoint is the security skill's.

When a review touches something out of lane, name it in one line and defer — don't recenter the review around it:

> "Note: `hash(body.password)` is called synchronously in the handler — that's a concurrency concern for the crypto/perf skills to review, not a REST-conventions issue."

One sentence. Move on.

### 3. Tag findings with severity on audits and PR reviews

When the output lists violations, issues, or recommendations — PR reviews, API audits, design reviews — tag each one with a severity so the reader can triage at a glance. The final recommendation (block / approve-with-changes / approve) follows from the highest severity in the list.

| Severity | Criterion |
|---|---|
| **Critical** | Production-blocker. Security or data-integrity issue, or breaks existing consumers in a way that can't be reverted without a deploy. Examples: `GET` that mutates state, `SELECT *` shipping `password_hash` to the wire, destructive endpoint with no auth check, money-moving POST with no idempotency. |
| **High** | Contract break or correctness hazard — will confuse or constrain consumers, or produce silently wrong results. Examples: bare array from a list endpoint, wrong HTTP method (`POST` where `DELETE` fits), snake_case on the wire, bespoke pagination envelope, validation round-trips per field, state transition expressed as a sub-resource verb (`POST /complete` instead of `PATCH`). |
| **Medium** | Convention miss that's cheap to fix and has low blast radius. Examples: missing `Location` header on `POST`, missing `X-Request-ID`, wrong success status (`200` where `201` fits), error code echoes HTTP status (`NOT_FOUND` instead of `TaskNotFound`), missing rate-limit headers, error body wrapped in a redundant `error:` key. |
| **Low** | Nit. Minor wording, in-scope naming inconsistency, nice-to-have additions (ETag / sparse fieldsets / `Sunset` preemptive wiring). |

Format each finding with its severity prominent at the top of the block:

```
### Violation 3.1 — `GET` used to mutate state
**Severity:** Critical

[one paragraph explaining why — in your own voice, no skill citation]

**Correct alternative:** DELETE /api/users/:id
```

The reader should be able to scan severities down the left margin and know which items block merge without reading a single explanation.

## Invocation Examples

- "Audit these endpoints against rest-api-design. List violations with severity."
- "Design the URL + response shape for a new X endpoint."
- "Review this PR — does the new route conform to REST conventions? Tag findings with severity."
- "Why is `GET /api/users/:id/delete` wrong? Propose a correct alternative."
- "Draft the TypeScript interface for a new Y endpoint following our REST conventions."

## How to Extend This Skill for a Specific Project

Projects typically need a thin companion skill that locks in specifics this skill leaves open:

- Which pagination envelope (exact field names, nested vs flat).
- The error code catalog (specific codes, their HTTP statuses).
- The canonical `Paginated<T>` TypeScript type (module path + name).
- File locations for route handlers, services, schemas, and the case-conversion utility.
- Project-specific API laws (e.g., "BFF boundary absolute — no client → DB calls").
- Exceptions and ADR processes for the places the project diverges from defaults.

Name the companion skill something like `<project>-api` and have it reference this skill as its foundation.
