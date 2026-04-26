# PR Audit: REST Surface Violations

The PR introduces four routes that each break a different REST convention. I'll go through them in order, then close with the cross-cutting issues. Findings are tagged with severity so you can scan and triage.

---

## Finding 1 — `GET /api/users` returns a raw array — `High`

**Why it matters.** A bare `[...]` body cannot grow into a paginated list without breaking every consumer that wrote `response.json().then(arr => arr.map(...))`. Since users is an unbounded set (it grows over time), this becomes a contract problem the moment the table reaches a few thousand rows. Bare arrays also block adding sibling metadata (cursors, flags) without a major version bump.

**Correct alternative.**

```http
GET /api/users?cursor=<opaque>&limit=20
```

```json
{
  "data": [{ "id": "user_01HX...", "email": "..." }],
  "pagination": { "nextCursor": "eyJp...", "hasMore": true }
}
```

- Cursor-based pagination (opaque `nextCursor`, `hasMore` boolean). Cursors are server-defined; clients pass back whatever they received.
- Default `limit=20`, max `limit=100`, clamped at the route handler.
- **Do not return `total`.** A `COUNT(*)` on a growing table is expensive and tells the client nothing actionable. Reserve `total` for bounded sets.

---

## Finding 2 — `POST /api/createUser` puts a verb in the URL — `High`

**Why it matters.** REST URLs name resources, not actions; the HTTP method names the action. `POST /api/createUser` duplicates the verb in two places and fragments the URL space — the next dev will reach for `/api/deleteUser`, `/api/updateUser`, and the surface area explodes.

**Correct alternative.**

```http
POST /api/users
Content-Type: application/json
```

The method (`POST`) means "create"; the path names the collection.

---

## Finding 3 — `POST` returns `200` with no `Location` header — `Medium`

**Why it matters.** `200 OK` does not communicate "a new resource was created at a discoverable URL." Clients (and proxies) lose the cue that the response represents a fresh resource and have to parse the body to find the new ID.

**Correct alternative.**

```http
HTTP/1.1 201 Created
Location: /api/users/user_01HX...
Content-Type: application/json
X-Request-ID: req_01HX...

{ "id": "user_01HX...", "email": "...", "createdAt": "2026-04-26T...Z" }
```

- `201 Created` on successful create.
- `Location: /api/users/<id>` so the client can follow up with a `GET`.

---

## Finding 4 — Wire format is snake_case (`user_id`, `created_at`, `password_hash`) — `High`

**Why it matters.** snake_case on the wire is usually a sign that raw DB rows are being serialized straight to the response — meaning your DB schema is now part of the public contract (Hyrum's Law). Renaming a column becomes a breaking change.

**Bonus — `password_hash` in the response is a `Critical` data-leak issue.** Password hashes (or any cryptographic credential material) should never leave the database. Even bcrypt hashes are sensitive: they let an attacker run an offline dictionary attack at their leisure. Strip them at the service boundary. (This is a security concern, not strictly a REST one — handing it to the security review for confirmation, but call it out now because it's also visible from the contract.)

**Correct alternative.** camelCase on the wire. The DB stays snake_case; route adapters do the case map.

```json
{
  "id": "user_01HX...",
  "email": "ada@example.com",
  "createdAt": "2026-04-26T...Z",
  "updatedAt": "2026-04-26T...Z"
}
```

Use a shared `dbToWire` / `wireToDb` utility — don't hand-map field by field.

---

## Finding 5 — `GET /api/users/:id/delete` for a destructive action — `Critical`

**Why it matters.** This is the most serious finding in the diff. `GET` is *defined* by RFC 9110 as safe and idempotent — meaning intermediaries (browsers, proxies, link prefetchers, anti-virus URL scanners, search engine crawlers if the URL ever leaks) feel free to fetch it speculatively. Using `GET` to delete a user means a logged-in user hovering over a link in a chat client can trigger a deletion. Same for any caching layer that warms URLs.

**Correct alternative.**

```http
DELETE /api/users/user_01HX...
```

- `DELETE` method.
- `204 No Content` on success (or `200` with a minimal body if you want to return an audit reference).
- Re-deleting an already-deleted user returns `404` with a domain code (`UserNotFound`) — this is the idempotency contract for `DELETE`.

---

## Finding 6 — URL exposes DB implementation (`user_table_v2`) — `Medium`

**Why it matters.** `/api/user_table_v2/query` (or anything similar in the diff) leaks an internal physical-storage detail into the public URL. Once consumers depend on `user_table_v2`, the next migration to `user_table_v3` is a breaking change — even though it's purely an internal refactor.

**Correct alternative.** URLs name *domain* resources, not storage tables. `/api/users` (or a domain-meaningful sub-resource) regardless of which backend table holds the data.

---

## Finding 7 — Bespoke list envelope `{ events, total, limit, offset }` — `High`

**Why it matters.** Two distinct problems live in this one shape:

1. **Resource-named top-level key (`events`).** Every list endpoint having a different top-level key (`users`, `events`, `tasks`...) means clients can't share a single "unwrap a list response" helper. A canonical `data` key makes generic pagination handling possible.
2. **`total` on an unbounded set.** `events` is a growing log — `COUNT(*)` over an unbounded set is expensive and the answer drifts between request and use. Don't return it.

**Correct alternative.**

```json
{
  "data": [{ "id": "evt_01HX...", "type": "user.created", "createdAt": "..." }],
  "pagination": { "nextCursor": "...", "hasMore": true }
}
```

Use the same `{ data, pagination: { nextCursor, hasMore } }` envelope as `GET /api/users`. One shape across every list endpoint, one client helper. Switch from `offset/limit` to cursor-based pagination — the events log is high-write, so offset pagination drifts (rows shift between page reads).

---

## Finding 8 — Validation reports one field at a time — `High`

**Why it matters.** Returning the *first* validation error per request forces the user into a "submit, fix, submit again" round-trip per field. The validator already has the full set; surfacing them all in one response is strictly less work.

**Correct alternative.**

```json
{
  "code": "InvalidRequestBody",
  "message": "Request validation failed",
  "details": [
    { "field": "email", "message": "Email address is required" },
    { "field": "password", "message": "Password must be at least 8 characters" }
  ],
  "requestId": "req_01HX..."
}
```

`details` is an array of `{ field, message }` so the client can render every error inline at once.

---

## Finding 9 — Error envelope is wrapped under `error: {...}` — `Medium`

**Why it matters.** `{ "error": { "code": ..., "message": ... } }` adds a layer of nesting that the HTTP status already provides. The HTTP status classifies the response as an error; the body *is* the error payload.

**Correct alternative — flat envelope.**

```json
{
  "code": "TaskNotFound",
  "message": "No task with id task_01HX...",
  "details": { "id": "task_01HX..." },
  "requestId": "req_01HX..."
}
```

Top-level fields: `code`, `message`, `details?`, `requestId`. No `error:` wrapper.

---

## Finding 10 — Error codes echo the HTTP status (`NOT_FOUND`, `VALIDATION_ERROR`, `CONFLICT`) — `Medium`

**Why it matters.** HTTP status and `code` do different jobs:

- HTTP status classifies for *generic* clients, proxies, and retry libraries (4xx / 5xx).
- `code` names *the specific domain reason* the request failed, so programmatic clients can branch on cause.

`code: "NOT_FOUND"` on a 404 is two layers saying the same thing — it wastes the field. The interesting question is "*what* is missing?" — `UserNotFound`, `TaskNotFound`, `WebhookNotFound` — and the client cares which.

**Correct alternative.** Domain-expressive codes from a maintained catalog:

| HTTP | Anti-pattern | Use instead |
|------|--------------|-------------|
| 404  | `NOT_FOUND` | `UserNotFound`, `TaskNotFound` |
| 422  | `VALIDATION_ERROR` | `InvalidRequestBody`, `EmailFormatInvalid` |
| 409  | `CONFLICT` | `IdempotencyKeyReused`, `EmailAlreadyTaken`, `InvalidStatusTransition` |
| 403  | `FORBIDDEN` | `AccountSuspended`, `InsufficientPermissions` |

Use one consistent style (`PascalCase` or `UPPER_SNAKE_CASE`) and add new codes via a catalog, not inline in handlers.

---

## Finding 11 — No `X-Request-ID` on responses; error bodies have no `requestId` — `Medium`

**Why it matters.** When a customer reports an error, the only way to find their request in your logs is a request ID. Without it, support traces bounce around for hours.

**Correct alternative.** Every response (success and error) sets:

```http
X-Request-ID: req_01HX...
```

Every error body includes the same value as `requestId` so the customer-paste from a UI error message is enough to locate the request server-side.

---

## What I am NOT recommending

A few changes that look natural at first glance but are deliberate non-recommendations:

- **No `/v1/` URL prefix.** Default to no version segment; reserve `/v2/` for the rare case where you need to ship an incompatible change alongside a deprecation window for an external consumer that's locked to the old shape. Internal-only breaking changes are migrations, not versions.
- **No `total` field on the events list.** It's an unbounded set; the count is expensive and not actionable. (Repeated from finding 7 because reviewers often try to add it back.)

---

## Out of lane

These touched the diff but belong to other reviews. Calling them out so they aren't dropped, but not prescribing fixes here:

- `password_hash` exposure — this is a security review issue first, REST contract second. Owner: security skill.
- The implementation of CORS, session handling, and rate-limit *algorithms* — REST contract covers the headers (`X-RateLimit-*`, `Retry-After`, `Access-Control-Allow-Origin` discipline), not the limiter itself.

---

## Summary

| # | Severity | Finding |
|---|----------|---------|
| 5 | Critical | `GET` for destructive action |
| 4 | High     | snake_case on the wire (and `password_hash` exposure — security) |
| 1 | High     | Bare-array list response |
| 2 | High     | Verb in URL (`/createUser`) |
| 7 | High     | Bespoke list envelope + `total` on unbounded set |
| 8 | High     | Validation round-tripped per field |
| 3 | Medium   | `POST` returning 200, no `Location` |
| 6 | Medium   | DB implementation in URL |
| 9 | Medium   | Error wrapped under `error:` |
| 10 | Medium  | Error codes echo HTTP status |
| 11 | Medium  | Missing `X-Request-ID` / `requestId` |
