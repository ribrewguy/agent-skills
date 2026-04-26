# PR Review: API Endpoint Issues

This PR has several REST and API design issues. Let me walk through each one.

## 1. `GET /api/users` returns a raw array

**Problem.** A bare array is hard to evolve. If you later need to add pagination, metadata, or any other top-level field, you have to do a v2 migration to avoid breaking clients.

**Fix.** Wrap the response in an envelope and add pagination from day one.

```json
{
  "users": [...],
  "page": 1,
  "pageSize": 20,
  "total": 1234
}
```

This way you can add fields like `nextPage`, filters, or summary stats without a breaking change.

## 2. `POST /api/createUser` — verb in the URL

**Problem.** REST URLs name resources, not actions. `createUser` is the HTTP method's job (`POST`).

**Fix.** Use `POST /v1/users` — and consider versioning the prefix (`/v1/`) so you have a clear migration path later.

## 3. `POST` returning `200` with snake_case payload

**Problem.** Two issues here:

1. The conventional success status for a `POST` that creates a resource is `201 Created` with a `Location` header pointing to the new resource.
2. `snake_case` on the wire is unusual for a JSON API; most teams pick camelCase or PascalCase for consistency with JavaScript clients.

**Fix.**

```http
HTTP/1.1 201 Created
Location: /v1/users/abc123

{
  "id": "abc123",
  "userName": "ada",
  "createdAt": "2026-04-26T..."
}
```

If you have any reason to keep snake_case (some Python / Ruby shops do), be consistent across all endpoints. Mixing styles is the worst outcome.

## 4. `GET /api/users/:id/delete` for a destructive action

**Problem.** `GET` should be safe and idempotent. Using `GET` to delete a resource:

- Causes browsers, caches, and prefetchers to delete users speculatively.
- Won't be cached correctly.
- Is not how anybody expects a REST API to work.

**Fix.**

```http
DELETE /v1/users/:id
```

with `204 No Content` on success.

## 5. Bespoke `{events, total, limit, offset}` envelope

**Problem.** Bespoke per-endpoint envelopes are inconsistent — clients can't share a generic pagination helper across endpoints. Better to have *one* pagination shape for the whole API.

**Fix.** Pick a shape and use it everywhere. For example:

```json
{
  "data": [...],
  "pagination": {
    "page": 2,
    "pageSize": 20,
    "total": 437
  }
}
```

Use the same envelope for `GET /api/users` and any other list endpoint.

## 6. Validation errors reported one field at a time

**Problem.** Returning only the first validation error means the user has to round-trip each fix one at a time. Bad UX.

**Fix.** Return all validation failures in one response:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "fields": {
      "email": "Email is required",
      "password": "Password must be at least 8 characters"
    }
  }
}
```

Most validation libraries (Zod, Yup, Joi, Pydantic, validator) collect all errors automatically — pass them through.

## 7. `password_hash` is in the response

**Problem.** Hashes should never leave the database. Even bcrypt hashes give attackers an offline cracking surface.

**Fix.** Strip from the response model. Use a sanitizer / DTO at the boundary.

## Summary

| Endpoint | Issue | Fix |
|---|---|---|
| `GET /api/users` | bare array, no pagination | wrap in envelope, paginate |
| `POST /api/createUser` | verb in URL, returns 200, snake_case | `POST /v1/users` returning 201 |
| `GET /api/users/:id/delete` | destructive GET | `DELETE /v1/users/:id` |
| listEvents | bespoke envelope | canonical `{data, pagination}` |
| validation | one error at a time | return all |
| response | leaks `password_hash` | drop from response |

Adopting `/v1/` as a prefix from the start gives you room to evolve. And establishing one error envelope (`{ error: { code, message, fields? } }`) and one pagination envelope across the whole API will save a lot of pain later.
