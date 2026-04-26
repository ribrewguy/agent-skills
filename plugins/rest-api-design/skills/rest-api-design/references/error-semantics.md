# Error Semantics — Detail

Reference for [the Error Semantics principle](../SKILL.md#2-consistent-error-semantics-via-osmani-adapted) in the main SKILL.md. Read when you need the catalog discipline, the `details` shape per code, the discriminated-union upgrade for strict codebases, or the validation-error worked example.

## The flat envelope

```typescript
// The type name IS the abstraction — don't wrap contents in an `error` key.
// HTTP status tells the client this is an error; no extra nesting needed.
interface APIError {
  code: string                                                         // Domain-specific reason, from a catalog
  message: string                                                      // Human-readable, client-safe
  details?: Record<string, unknown> | Array<Record<string, unknown>>   // Shape varies by `code`
  requestId: string                                                    // Always present; matches X-Request-ID response header
}
```

Equivalent JSON on the wire:

```json
{
  "code": "TaskAlreadyCompleted",
  "message": "This task was already completed at 2026-04-23T14:05:00Z",
  "requestId": "req_abc123"
}
```

## A note on typing `details`

The bounded `Record<string, unknown> | Array<Record<string, unknown>>` is a deliberate compromise. A raw `unknown` is the most honest type (shape genuinely depends on `code`) but triggers lint rules like `@typescript-eslint/no-unsafe-member-access` on every access. Using `any` anywhere — including `Record<any, any>` — silences both lint and the compiler, which defeats the point. The bounded form says "object-shaped or array-of-object-shaped, values still require narrowing" — enough structure for consumers to know it's keyed data, strict enough that lint stays quiet.

## Discriminated-union upgrade for strict codebases

Make the catalog itself a type:

```typescript
type APIError =
  | { code: 'InvalidRequestBody'; message: string; details: Array<{ field: string; message: string }>; requestId: string }
  | { code: 'RateLimited';        message: string; details: { retryAfterSeconds: number; bucket: string };         requestId: string }
  | { code: 'CardDeclined';       message: string; details: { declineReason: string };                             requestId: string }
  | { code: 'TaskNotFound';       message: string; details?: { completedAt?: string };                             requestId: string }
  // ...one variant per code in the catalog
```

The union costs a type alias per code but makes every error handler exhaustiveness-checkable (`switch (err.code) { case 'InvalidRequestBody': ... }`), and `details` is pinned to its documented shape per variant — no narrowing required at the consumer. Worth it when the catalog is stable enough that adding a code is a deliberate act.

## HTTP status and `code` do different jobs — don't duplicate

The HTTP status classifies the error at the protocol layer (4xx client, 5xx server) so generic clients, proxies, and retry libraries work without understanding your domain. The `code` names *the specific domain reason* the request failed, so programmatic clients can branch on cause — "card was declined" vs. "merchant is suspended" are both `402 Payment Required`, but the client handles them very differently.

Codes that echo the HTTP status are redundant and waste the field:

| Anti-pattern (redundant with status) | Better (domain-expressive) |
|---|---|
| `NOT_FOUND` on a 404 | `TaskNotFound`, `AccountNotFound` |
| `VALIDATION_ERROR` on a 422 | `InvalidRequestBody`, `EmailFormatInvalid`, `AmountBelowMinimum` |
| `CONFLICT` on a 409 | `TaskAlreadyCompleted`, `IdempotencyKeyReused`, `UniqueConstraintViolated` |
| `FORBIDDEN` on a 403 | `AccountSuspended`, `PlanUpgradeRequired`, `InsufficientPermissions` |
| `UNAUTHENTICATED` on a 401 | `SessionExpired`, `InvalidCredentials`, `MfaRequired` |
| `RATE_LIMITED` on a 429 | Still `RateLimited` is fine — there's rarely a domain-specific "why" beyond "you sent too many." Acceptable exception. |

Codes are typically `PascalCase` or `UPPER_SNAKE_CASE` — pick one and be consistent.

## The catalog

Maintain a catalog alongside your API docs. **Adding a new code requires a catalog update first**, not inline invention. The catalog documents, for each code:

- The HTTP status it pairs with
- The domain reason
- The shape of `details` when present

## `details` is generic, not validation-specific

Any error can carry additional context. The shape depends on the code and is documented per code in the catalog:

- `InvalidRequestBody` → `details` is `[{ field, message }, ...]` (the validation case)
- `RateLimited` → `details` is `{ retryAfterSeconds: 60, bucket: "payments" }`
- `InsufficientFunds` → `details` is `{ available: "5.00", requested: "100.00", currency: "USD" }`
- `TaskAlreadyCompleted` → `details` may be absent, or `{ completedAt, completedBy }`

## Return all validation errors at once [via Postman]

When a request fails validation, report every field that's wrong in a single response — don't make the client round-trip per field. The `details` shape for validation codes is an array of `{ field, message }`:

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

Schema-validation libraries map cleanly to this shape:

- **Zod** — `.flatten()` or `.format()`
- **Pydantic** — `.errors()`
- **go-playground/validator** — `ValidationErrors` (iterate and collect)
- **ajv** — `errors` array (transform to `{field, message}` per entry)
