---
name: rest-api-design
description: "Use when designing or reviewing HTTP REST APIs, endpoints, typed contracts (TS/Python/Go/Rust), pagination/error conventions, PRs at the network boundary. Covers resource-oriented URLs, PATCH for state transitions (not sub-resource verbs), domain-expressive error codes, flat error envelopes, idempotency, content negotiation. Symptoms, verbs in URLs, sub-resource action verbs (/complete) for state transitions, error codes echoing HTTP status, snake_case wire format, raw arrays from list endpoints, GET mutating state, missing idempotency on side-effectful POSTs."
---

# REST API Design

## Overview

Design stable, well-documented HTTP APIs that are hard to misuse. Good interfaces make the right thing easy and the wrong thing hard. This skill covers the generic principles, contract-first design, consistent error semantics, validation at boundaries, additive evolution, predictable naming, and layers concrete patterns on top: resource-oriented URLs, HTTP method semantics, pagination, sorting, searching, idempotency keys, rate limiting, and request correlation.

The skill is framework-agnostic. It doesn't mandate a specific pagination envelope or error catalog, it gives you the shape and lets your project lock in specific field names. Pair this skill with a project-specific skill (e.g., an internal `<project>-api` skill) that names the exact pagination envelope, error codes, and file locations your codebase uses.

Detail referenced from this skill body lives in [`references/`](references/):

- [Error semantics](references/error-semantics.md), the flat error envelope, domain-expressive codes vs. HTTP-status echoes, validation error shape, discriminated-union upgrade for strict codebases.
- [Operational requirements](references/operational.md), HTTPS, content-type discipline, request IDs, CORS, rate-limit headers, observability.
- [State transitions](references/state-transitions.md), why PATCH and not sub-resource verbs, side-effect discipline on transitions, when sub-resource POST is correct.
- [Patch formats](references/patch-formats.md), plain JSON / `merge-patch+json` / `json-patch+json` escalation with worked examples.
- [Typed contract patterns](references/typed-contracts.md), discriminated unions, input/output separation, branded IDs, with TS/Python/Go/Rust examples.

## When to Use

- Designing new API endpoints.
- Defining module boundaries or contracts between services.
- Creating typed interfaces (TS / Python / Go / Rust / etc.) that cross the client/server line.
- Establishing database schema that informs API shape.
- Changing existing public interfaces.
- Reviewing a PR that touches the HTTP surface.
- Deciding whether a list endpoint should paginate and which strategy fits.
- Symptoms: verbs in REST URLs (`/api/createTask`, `/api/getUsers`), inconsistent error formats, snake_case on the wire, raw arrays from list endpoints, bespoke envelope keys (`{ users: [] }`), validation scattered through internal code, `GET` used for state changes, URLs that expose DB schema, validation failures reported one field at a time, money-moving POSTs without idempotency.

## External references (inspiration, not binding)

- [`addyosmani/agent-skills@api-and-interface-design`](https://github.com/addyosmani/agent-skills), source of the generic interface-design principles (Hyrum's Law, One-Version Rule, Contract First, Error Semantics, Validate at Boundaries, Prefer Addition Over Modification, Predictable Naming, Common Rationalizations, Red Flags, Verification). Passages adapted from it are tagged `[via Osmani]`.
- [Postman REST API Best Practices](https://blog.postman.com/rest-api-best-practices/), source of operational conventions: sorting/searching syntax, HTTP status discipline (201+Location, 204 on DELETE), validation-errors-as-array, idempotency keys, rate-limit headers, field selection, request IDs, CORS, content negotiation. Passages adapted from it are tagged `[via Postman]`.
- [Google API Design Guide](https://cloud.google.com/apis/design), resource-oriented design inspiration.

## Core Principles

### Hyrum's Law [via Osmani]

> With a sufficient number of users of an API, all observable behaviors of your system will be depended on by somebody, regardless of what you promise in the contract.

Every public behavior, undocumented quirks, error message text, timing, ordering, becomes a de facto contract once users depend on it.

- **Be intentional about what you expose.** Every observable behavior is a potential commitment.
- **Don't leak implementation details.** Raw database rows, snake_case keys inherited from the DB, and `total` counts all become contracts by accident.
- **Plan for deprecation at design time.** Breaking changes need a deprecation window and `Sunset` header.
- **Tests are not enough.** Contract tests cover documented behavior; they don't cover the quirks consumers have already depended on.

### The One-Version Rule [via Osmani]

Avoid forcing consumers to choose between multiple versions of the same API. Diamond dependency problems arise when different consumers need different versions. Design for a world where only one version exists at a time, **extend rather than fork**.

Default to no URL version segment. Reserve `/v2/` for cases where an external consumer is locked to the current shape and an incompatible change ships alongside a deprecation window. Internal-only breaking changes are migrations, not versions.

### 1. Contract First [via Osmani, adapted]

Define the interface before implementing it. The contract is the spec, implementation follows.

```typescript
interface TasksAPI {
  listTasks(params: ListTasksParams): Promise<Paginated<Task>>
  getTask(id: string): Promise<Task>
  updateTask(id: string, input: UpdateTaskInput): Promise<Task>
  deleteTask(id: string): Promise<void>
}
```

Use a canonical `Paginated<T>` type alias shared across every list endpoint. Never define bespoke `PaginatedTasks`, `UsersList`, etc.

### 2. Consistent Error Semantics [via Osmani, adapted]

Every API error follows one shape. The flat envelope:

```typescript
interface APIError {
  code: string                                                         // Domain-specific reason, from a catalog
  message: string                                                      // Human-readable, client-safe
  details?: Record<string, unknown> | Array<Record<string, unknown>>   // Shape varies by code
  requestId: string                                                    // Matches X-Request-ID response header
}
```

Two load-bearing rules:

- **Don't wrap the body in `{ error: { ... } }`.** The HTTP status already classifies the response as an error; the wrapper is redundant indirection.
- **`code` names the domain reason; HTTP status classifies at the protocol layer.** `code: "NOT_FOUND"` on a 404 is two layers saying the same thing. Pick codes like `TaskNotFound`, `CardDeclined`, `InvalidRequestBody`, domain-expressive, never echoes the status.

Validation errors return all offending fields at once in `details: [{ field, message }, ...]`, never round-trip per field.

Full discussion (catalog discipline, `details` shape per code, the discriminated-union upgrade for strict codebases, validation example) is in [references/error-semantics.md](references/error-semantics.md).

### 3. Validate at Boundaries [via Osmani, adapted]

Trust internal code. Validate at system edges where external input enters.

```typescript
export default defineEventHandler(async (event) => {
  const result = CreateTaskSchema.safeParse(await readBody(event))
  if (!result.success) {
    return sendError(event, 422, {
      code: 'InvalidRequestBody',
      message: 'Invalid task data',
      details: result.error.flatten(),
    })
  }
  return await taskService.create(result.data)
})
```

Where validation belongs:
- API route handlers (external user input).
- Form submission handlers.
- External service response parsing (third-party APIs, webhooks, **always treat as untrusted**).
- Environment variable loading (configuration).

Where it does NOT belong: between internal functions that share type contracts, in utility functions called by already-validated code, or on data that just came from your own database via typed queries.

### 4. Prefer Addition Over Modification [via Osmani]

New fields must be optional. Removing or type-changing existing fields is a breaking change, use the deprecation path (new field added, old field marked deprecated in types + docs, `Sunset` header, removal window). Never silently change a shape.

```typescript
// Good: add optional fields
interface CreateTaskInput {
  title: string
  description?: string
  priority?: 'LOW' | 'MEDIUM' | 'HIGH'   // added later, optional
}

// Bad: change types or remove fields
interface CreateTaskInput {
  title: string
  priority: number   // changed from string, breaks consumers
}
```

### 5. Predictable Naming [via Osmani, adapted]

| Pattern | Convention | Example |
|---|---|---|
| REST paths | plural nouns, kebab-case, no verbs | `GET /api/tasks`, `POST /api/daf-accounts` |
| Query params | camelCase | `?sortBy=createdAt&pageSize=20&accountId=...` |
| Request body fields | camelCase | `{ "accountId": "...", "targetAmount": "1000.00" }` |
| Response fields | camelCase | `{ "createdAt": "...", "userId": "..." }` |
| Boolean fields | `is` / `has` / `can` prefix | `isComplete`, `hasAttachments`, `canEdit` |
| Enum string values | `UPPER_SNAKE_CASE` | `"IN_PROGRESS"`, `"COMPLETED"` |
| Error codes | domain-expressive, from a catalog (`PascalCase` or `UPPER_SNAKE_CASE`, pick one) | `TaskNotFound`, `IdempotencyKeyReused` |
| DB columns | snake_case (never leaked to wire) | `household_id`, `created_at` |
| HTTP header names | follow HTTP convention | `X-Request-ID`, `Idempotency-Key`, `Content-Type` |

**The wire is camelCase. The DB is snake_case. HTTP headers follow HTTP conventions.** The JSON camelCase rule applies to request/response *bodies* and query *parameters*, not to HTTP *header* names. Raw DB rows never ship to clients; services (or route adapters) perform the case map between DB and wire. Build a shared case-conversion utility; don't hand-map field by field.

If your project already uses snake_case on the wire, flipping to camelCase is a breaking change, pick your convention early.

## Operational requirements [via Postman, adapted]

Wire-level requirements every route meets: HTTPS, the right `Content-Type` per endpoint (with appropriate handling of streaming, binary, vendor media types, and patch formats), `X-Request-ID` on every response, explicit (never wildcard) CORS on credentialed endpoints, `X-RateLimit-*` headers + `Retry-After` on 429, structured per-request logs with method/path/status/latency/user/request-id.

Full detail in [references/operational.md](references/operational.md).

## REST API patterns

### Resource design [via Osmani, adapted]

```
GET    /api/tasks                → List tasks (query params for filtering)
POST   /api/tasks                → Create a task
GET    /api/tasks/:id            → Get a single task
PATCH  /api/tasks/:id            → Update a task (partial), includes state transitions
DELETE /api/tasks/:id            → Delete a task

GET    /api/tasks/:id/comments   → List comments (sub-resource collection)
POST   /api/tasks/:id/comments   → Add a comment (creates a new Comment resource)
```

**URL depth limit.** [via Postman] Keep nesting to at most two segments (`/api/parent/:id/child`). Three-plus levels (`/api/users/:uid/tasks/:tid/comments/:cid/flags`) is a signal the grandchild deserves its own top-level resource.

#### State transitions are `PATCH`, not sub-resource verbs

Changing a field on a resource, including a `status` field that drives side effects, is an update. Use `PATCH`. **Don't invent sub-resource verbs like `/complete`, `/cancel`, `/activate`, `/publish`**, they read as RPC bolted onto REST and fragment the URL space.

| Anti-pattern | Correct |
|---|---|
| `POST /api/tasks/:id/complete` | `PATCH /api/tasks/:id` with `{ "status": "COMPLETED" }` |
| `POST /api/orders/:id/cancel` | `PATCH /api/orders/:id` with `{ "status": "CANCELLED" }` |
| `POST /api/users/:id/activate` | `PATCH /api/users/:id` with `{ "status": "ACTIVE" }` |

Side effects (emails, audit rows, webhooks) belong to the transition in the service layer, not to the URL. Forbidden transitions return `409 CONFLICT` with a domain code (`InvalidStatusTransition`, `TaskAlreadyCompleted`).

`POST` to a sub-collection IS correct when a new resource with its own identity and lifecycle is created (Transfer, Refund, Comment, Approval). The test: does the operation produce a new resource, or just flip a field on the parent?

Full discussion (anti-pattern table, side-effect discipline, command-shaped endpoints, when sub-resource POST applies) in [references/state-transitions.md](references/state-transitions.md).

#### Status codes on write verbs [via Postman]

| Verb | Success status | Additional rules |
|---|---|---|
| `GET` (found) | `200 OK` | cacheable; no side effects |
| `POST` (created) | `201 Created` | include `Location: /api/<resource>/<id>` header |
| `PUT` (replaced) | `200 OK` with new body, or `204 No Content` | idempotent |
| `PATCH` (updated) | `200 OK` with updated body | idempotent in effect; side effects must deduplicate on real transitions |
| `DELETE` (removed) | `204 No Content`, or `200 OK` with a minimal body | idempotent, re-deleting returns `404` (domain code) |

Use these defaults unless the route has a documented reason to diverge. **Never use `GET` for operations that change server state.**

### Pagination

Every list endpoint paginates. Choose one strategy per project and use it everywhere.

- **Cursor-based (recommended for most cases)**, opaque cursor, `hasMore` flag. Best for feeds, high-write datasets, any list where items can be inserted between requests.
- **Offset / limit**, simpler but drifts on high-write datasets. Acceptable for bounded admin tables where `COUNT(*)` is cheap.
- **Page number**, UI-friendly when the consumer wants "page 3 of 15." Same drift caveats as offset; requires a `total`.

Cursor envelope:

```json
{
  "data": [...],
  "pagination": { "nextCursor": "eyJpZCI6MTQzfQ", "hasMore": true }
}
```

Cursors are opaque, clients pass back what the server returned. Sort order is part of the cursor contract; switching sort with an old cursor is a `400`.

**Decision tree, is this endpoint even a list?**

1. Naturally single (single row, aggregate, summary, stream) → flat domain object, no envelope.
2. Bounded by policy (≤ 10 items forever) → `{ data: [...] }` with documented bound.
3. Time-bucketed chart data (≤ 60 buckets) → `{ buckets, range, granularity }`, chart data is not a list.
4. Unbounded row array that can grow → paginate.

**Defaults:** default limit `20`, max limit `100`, clamped at the route handler. **Never return `total` on unbounded sets**, `COUNT(*)` on a growing table is expensive and tells the client nothing actionable. Reserve `total` for bounded sets where it's cheap.

### Filtering / Sorting / Searching [via Osmani + Postman]

Query parameters, camelCase, additive (AND). Multi-value uses repeated params:

```
GET /api/tasks?assigneeId=user_123&status=PENDING&status=IN_PROGRESS&createdAfter=2026-01-01
```

Sort uses a single `sort` param, colon-separated `field:direction`, comma-separated for multi-field (leftmost has highest precedence):

```
GET /api/tasks?sort=priority:desc,createdAt:asc
```

Direction is `asc` or `desc` (lowercase). Default direction if omitted is `asc`. Sortable fields are schema-validated; unknowns return `400`. Sort order is part of the cursor contract.

Search uses a single `q` param (preferred over `search` for brevity):

```
GET /api/tasks?q=launch+plan
```

If an endpoint supports both filter and search, filters apply first (AND); search runs on the filtered subset. Validate every filter with a schema at the route boundary.

### Partial updates and PATCH

`PATCH` accepts partial objects, only update what's provided, including state transitions:

```
PATCH /api/tasks/task_123
Content-Type: application/json
{ "status": "COMPLETED" }
```

Use `PATCH` (not `PUT`) for partial updates. Reserve `PUT` for whole-resource replacement (rare). `PATCH` is idempotent in effect, repeating the same body produces the same state. Side effects on transitions must deduplicate in the service layer (only fire on actual transition).

Three patch formats are common, each with a distinct `Content-Type` and semantics:

- **Plain JSON partial** (`application/json`), default; missing fields mean "don't change."
- **JSON Merge Patch** (`application/merge-patch+json`, RFC 7396), `null` means delete; explicit null-vs-missing semantics.
- **JSON Patch** (`application/json-patch+json`, RFC 6902), array of operations (`add`, `remove`, `replace`, `move`, `copy`, `test`); supports array-element ops and atomic multi-op with optimistic-concurrency `test`.

Most endpoints can start with plain JSON and escalate. Full discussion with worked examples (including the `test` op for optimistic concurrency) in [references/patch-formats.md](references/patch-formats.md).

### Idempotency [via Postman, adapted]

`GET`, `HEAD`, `PUT`, `DELETE` are idempotent by design. `POST` is not, two identical POSTs may create two resources. For POSTs with meaningful side effects (payments, transfers, outbound communications, legal actions), accept an `Idempotency-Key` header:

```
POST /api/payments
Idempotency-Key: d7f4c8b2-4e1f-4c0f-9d54-2a9b3c7e1f11
```

Server behavior:

- Persist the key alongside the canonical payload hash + response for a documented retention window (default 24h; longer for financial writes).
- Same key + same payload → return the original response exactly.
- Same key + different payload → `409 CONFLICT` with `code: "IdempotencyKeyReused"`.
- Required on any POST that writes to money-moving or externally-visible state. The route's schema should require the header.

Idempotency protects one client's retry loop; it doesn't deduplicate across distinct clients.

### Field selection (sparse fieldsets) [via Postman, adapted]

Optional per-endpoint. Trim response payloads with a `fields` query param, camelCase, comma-separated:

```
GET /api/tasks/123?fields=title,status,dueDate
GET /api/tasks/123?fields=id,owner.name        # nested via dot notation
```

Rules: server may always ship required fields (like `id`); unknown fields are silently ignored to keep clients resilient (log at DEBUG); only wire on endpoints with large payloads.

## Typed contract patterns

Patterns apply in any typed language, TypeScript, Python (Pydantic / dataclasses / `NewType`), Go (structs, named types), Rust (newtypes, sum-typed enums), Kotlin (data + sealed classes), Java (records + sealed interfaces). The shapes matter; the syntax is a detail.

Three patterns this skill teaches:

- **Discriminated unions for variants**, encode each variant explicitly so consumers get exhaustive type-narrowing.
- **Input/output separation**, never use the same type for "what the client sends" and "what the server returns." Inputs omit server-generated fields; outputs include them.
- **Branded / distinct types for IDs**, prevent accidentally passing a `UserId` where a `TaskId` is expected. Use for IDs that flow across many module boundaries.

Worked examples in TypeScript, Python, Go, and Rust are in [references/typed-contracts.md](references/typed-contracts.md).

## Common rationalizations [Osmani + Postman]

| Rationalization | Reality |
|---|---|
| "We'll document the API later" | The types ARE the documentation. Define them first. |
| "We don't need pagination for now" | You will the moment someone has 100+ items. Add it from the start. |
| "PATCH is complicated, let's just use PUT" | PUT requires the full object every time. PATCH is what clients actually want. |
| "Nobody uses that undocumented behavior" | Hyrum's Law: if it's observable, somebody depends on it. |
| "Internal APIs don't need contracts" | Internal consumers are still consumers. Contracts prevent coupling and enable parallel work. |
| "Let's just use snake_case since that's what the DB returns" | DB rows never ship to clients. The wire is camelCase regardless of what the ORM hands you. |
| "We'll just return the raw array, the client knows it's a list" | Bare arrays can't grow into paginated lists without breaking consumers. Wrap from day one. |
| "We'll add idempotency later if duplicates become a problem" | By "later" you already have duplicate payments. Wire it on money-moving POSTs from the start. |
| "Returning all validation errors at once is too much work" | One round-trip per field is actively worse UX. Your validator already has the full set, pass it through. |
| "`POST /tasks/:id/complete` is clearer, it names the action" | The HTTP method already names the action (PATCH = partial update). A URL verb duplicates that and fragments the URL space. |
| "We need `/complete` so we know when to send the email" | Emails are side effects of the state transition, not the URL. Detect the transition in the service layer. |
| "Our error codes should match the HTTP status for simplicity" | HTTP status and `code` do different jobs. `code: "NOT_FOUND"` on a 404 is two layers saying the same thing. |
| "Wrapping errors in `{error: {...}}` is 'the standard'" | The wrapper adds indirection that HTTP status already provides. If your type is `APIError`, the body IS the error. |
| "`application/json` is the only content type we'll need" | Streaming (NDJSON, SSE), binary (PDF, CSV), file uploads (multipart), and vendor types all have legitimate places. |

## Red flags

- Endpoints that return different shapes depending on conditions.
- Inconsistent error formats across endpoints.
- Validation scattered throughout internal code instead of at boundaries.
- Breaking changes to existing fields (type changes, removals).
- List endpoints without pagination.
- Verbs in REST URLs (`/api/createTask`, `/api/getUsers`).
- Sub-resource action verbs for state transitions (`/api/tasks/:id/complete`, `/api/orders/:id/cancel`) instead of `PATCH`.
- Error codes that echo the HTTP status (`NOT_FOUND` on a 404, `VALIDATION_ERROR` on a 422) instead of naming the domain reason.
- Error bodies nested under an `error:` key.
- `application/json` treated as the only content type when the endpoint clearly calls for streaming, binary, or vendor-versioned media.
- Third-party API responses used without validation or sanitization.
- `GET` used for operations that mutate state (`GET /api/users/123/delete`, `GET /api/cart/add?...`).
- URLs that expose internal implementation (`/api/user_table_v2/query`).
- Inconsistent naming, one endpoint camelCase, another snake_case.
- Validation failures reported one field at a time instead of all at once.
- `POST` on a money-moving endpoint without `Idempotency-Key` support.
- `X-Request-ID` missing from responses.
- Rate-limited endpoint that doesn't emit `X-RateLimit-*` headers or `Retry-After` on `429`.
- CORS configured with `Access-Control-Allow-Origin: *` on a credentialed endpoint.
- snake_case keys on the wire (`user_id`, `created_at`, `next_cursor`).
- Bespoke list envelope (`{ users: [] }`, `{ events, total, limit, offset }`).
- `total` in the pagination envelope on an unbounded set.
- Error code invented inline instead of added to the catalog first.

## Verification

After designing or reviewing an API:

**Contract + types**
- [ ] Every endpoint has typed input and output schemas.
- [ ] Error responses follow the flat envelope: top-level `{ code, message, details?, requestId }`, not wrapped in an `error:` key.
- [ ] Error `code` values are domain-expressive (`TaskNotFound`, `InsufficientFunds`), they do not merely echo the HTTP status.
- [ ] Validation happens at system boundaries only.
- [ ] List endpoints return a consistent pagination envelope.
- [ ] New fields are additive and optional (backward compatible).
- [ ] Naming follows the predictable-naming table across all endpoints.
- [ ] State transitions use `PATCH`; no sub-resource action verbs (`/complete`, `/cancel`, `/publish`).
- [ ] `POST` to a sub-collection only when a new resource with its own identity is created.
- [ ] `Content-Type` is declared per endpoint and enforced at the boundary; streaming and binary endpoints use appropriate media types.
- [ ] PATCH endpoints declare which patch format they accept (plain / merge-patch / json-patch).

**Status codes + headers**
- [ ] `POST` success returns `201 Created` with a `Location` header.
- [ ] `DELETE` success returns `204 No Content` (or `200 OK` with a minimal body).
- [ ] Validation failures return all offending fields in one response, `details` as `{field, message}[]`.
- [ ] `X-Request-ID` present on every response.
- [ ] Rate-limited surfaces emit `X-RateLimit-Limit` / `-Remaining` / `-Reset`.
- [ ] Money-moving / side-effectful POSTs accept `Idempotency-Key` and persist it.

**Testing discipline**
- [ ] 200 happy path (populated result).
- [ ] 200 empty-list shape.
- [ ] 400 invalid cursor / invalid limit / invalid sort field.
- [ ] 401 unauthenticated; 403 forbidden (if auth-sensitive); 404 not found (if applicable).
- [ ] 409 idempotency-key reuse with different payload.
- [ ] 429 rate limit triggers, `Retry-After` present.
- [ ] Retry loops with the same idempotency key don't double-write.

**Documentation**
- [ ] All endpoints documented with HTTP method, URL, params, request body, response body, status codes, auth.
- [ ] Working request/response examples included.
- [ ] Error cases and their meanings documented.

## How to present findings

When this skill produces an audit, review, or design output, three guardrails apply:

1. **Don't cite this skill in the output.** Argue from first principles in your own voice. The skill is a reference for *you*; the audience is the reader. Avoid phrases like "Listed as a red flag," "The skill requires…," "Per the skill's verification checklist."
2. **Stay strictly in lane, REST contracts only.** Out of scope: password hashing (security skill), OAuth flows (auth skill), SQL injection (data-access / security skill), file layout (architecture skill), test coverage (testing skill), rate-limiter implementation (the HTTP *surface* of rate limiting is in scope; the limiter algorithm is not). When a review touches an out-of-lane concern, name it in one sentence and defer.
3. **Tag findings with severity** (`Critical` / `High` / `Medium` / `Low`) when reviewing a PR or auditing an existing API. The reader should be able to scan severities down the left margin and triage.

For the canonical findings format (eight-field preamble, severity-tagged findings with file:line citations, `Source of truth:` per finding, no-findings-still-formal), compose with the **structured-code-review** skill. That skill governs *how to present*; this one governs *what to flag*.

Severity ladder for REST work:

| Severity | Criterion |
|---|---|
| **Critical** | Production-blocker. Security/data-integrity (`GET` mutating state, `SELECT *` shipping `password_hash`, destructive route with no auth, money-moving POST with no idempotency). |
| **High** | Contract break or correctness hazard (bare array from list endpoint, wrong HTTP method, snake_case wire format, bespoke envelope, validation round-trips, sub-resource verb for state transition). |
| **Medium** | Convention miss (missing `Location` header, missing `X-Request-ID`, wrong success status, error code echoes HTTP status, missing rate-limit headers, error wrapped under `error:`). |
| **Low** | Nit (minor wording, in-scope naming inconsistency, nice-to-have additions like ETag / sparse fieldsets). |

## Invocation examples

- "Audit these endpoints against rest-api-design. List violations with severity."
- "Design the URL + response shape for a new X endpoint."
- "Review this PR, does the new route conform to REST conventions? Tag findings with severity."
- "Why is `GET /api/users/:id/delete` wrong? Propose a correct alternative."
- "Draft the TypeScript interface for a new Y endpoint following our REST conventions."

## How to extend this skill for a specific project

Projects typically need a thin companion skill that locks in specifics this skill leaves open:

- Which pagination envelope (exact field names, nested vs. flat).
- The error code catalog (specific codes, their HTTP statuses, `details` shape per code).
- The canonical `Paginated<T>` type (module path + name).
- File locations for route handlers, services, schemas, and the case-conversion utility.
- Project-specific API laws (e.g., "BFF boundary absolute, no client → DB calls").
- Exceptions and ADR processes for the places the project diverges from defaults.

Name the companion skill something like `<project>-api` and have it reference this skill as its foundation.

## See also

- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md), composes with this skill: domain skill identifies REST violations; structured-code-review formats them with the canonical preamble + severity tags.
- [References](references/) for in-skill detail: error-semantics, operational, state-transitions, patch-formats, typed-contracts.
