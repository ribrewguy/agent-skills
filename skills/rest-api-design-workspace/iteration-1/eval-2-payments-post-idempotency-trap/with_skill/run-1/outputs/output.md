# Review of `POST /api/payments` — Yes, something significant is missing

Short answer: **the draft is missing an `Idempotency-Key` header on a money-moving POST**. Without it, any client retry — network blip, gateway timeout, mobile app reconnect, queue redelivery — risks creating a duplicate charge. This is the single most important thing to add before this endpoint goes anywhere near production.

## Why this matters specifically for payments

`POST` is not idempotent by default. Two identical requests can — and at scale, will — create two payments. The standard failure mode looks like this:

1. Client sends `POST /api/payments` with `{ amount: 100.00 }`.
2. Server processes the charge, sends a `201 Created` response.
3. Response is dropped before reaching the client (network reset, load balancer timeout, app crash).
4. Client retries with the same body.
5. Server has no way to recognize this as the same logical request and creates a second payment.

You now have a duplicate charge, a confused customer, a chargeback risk, and a manual reconciliation problem. Idempotency keys are the contract that prevents this.

## The contract to add

Require the header on this route:

```http
POST /api/payments
Content-Type: application/json
Idempotency-Key: 9b1c4e6a-1a82-4a0e-b56b-2f2c2e0f9c7d
```

- **Format.** A client-generated UUIDv4 (or any sufficiently unique string) — the server doesn't pick it. Keys must be unique per logical operation; clients reuse the *same* key on retries of the *same* request.
- **Required.** Reject the request with `400` and `code: "IdempotencyKeyRequired"` if absent. Don't make it optional on this route — money-moving endpoints can't afford "well, the client forgot."

## Server semantics

Three scenarios the handler must support:

### 1. First time the key is seen

Process the request normally, persist the result, return `201 Created` with the new `Payment`. From this point the key is "claimed."

### 2. Same key arrives again with the same payload

This is a retry. **Replay the original response byte-for-byte** — same status, same body, same `Location` header. The server must not process the payment twice. From the client's perspective the retry succeeded; from the ledger's perspective only one charge happened.

The "same payload" check is done by hashing the canonical body (sorted keys, normalized whitespace) and comparing to the hash stored against the key.

### 3. Same key arrives with a different payload

Something is wrong on the client side — the same key is being reused for a different operation. Reject with:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json
X-Request-ID: req_01HX...

{
  "code": "IdempotencyKeyReused",
  "message": "This Idempotency-Key was previously used for a different request",
  "details": {
    "previousRequestAt": "2026-04-26T18:02:11Z",
    "previousPaymentId": "pay_01HX..."
  },
  "requestId": "req_01HX..."
}
```

Note the error envelope: flat at the top level (`code`, `message`, `details`, `requestId`), no `error:` wrapper, and `code` is domain-expressive (`IdempotencyKeyReused`) — not the generic `CONFLICT` that just echoes the HTTP status.

## What the server has to persist

A single row keyed by `(merchant_id, idempotency_key)` with these columns:

| Column            | Notes |
|-------------------|-------|
| `merchant_id`     | Scope keys to the tenant so two merchants can pick the same UUID by chance. |
| `idempotency_key` | The header value. |
| `request_hash`    | SHA-256 of the canonicalized request body — cheap "did the payload change?" check. |
| `response_status` | HTTP status to replay (201, 422, 409, etc — yes, replay errors too). |
| `response_body`   | Serialized response body, including the original `requestId`. |
| `response_headers`| At minimum `Location`. |
| `created_at`      | For retention sweeping. |
| `state`           | `IN_FLIGHT` / `COMPLETED` (so concurrent retries of the *same* key wait or reject — see "in-flight" below). |

### Retention window

**At least 24 hours**, and significantly longer for payments — most processors recommend 7–30 days, and Stripe keeps keys for 24h *of inactivity* on a sliding window. For financial writes I'd default to **at least 7 days**, document the value, and bump it if a retry storm has ever crossed the window. The longer the window, the more confidently a client can replay an old retry; the trade-off is storage and a slow background sweeper.

### In-flight requests

If the same key arrives while the first is still processing, the second request should **wait** (briefly, with a timeout) for the first to finish, then replay its response — or, if your infra can't easily wait, return `409 IdempotencyRequestInFlight` and let the client retry after a short backoff. Don't process the second request in parallel; that's the duplicate-charge bug the whole pattern exists to prevent.

## What this changes in the route schema

The schema for `POST /api/payments` should require the header:

```ts
const headersSchema = z.object({
  'idempotency-key': z.string().uuid(),
  'content-type': z.literal('application/json'),
})

const bodySchema = z.object({
  amount: z.string().regex(/^\d+\.\d{2}$/),       // string-decimal, never float for money
  currency: z.enum(['USD', 'EUR', 'GBP']),
  source: z.string(),                             // payment source reference
  description: z.string().max(500).optional(),
  metadata: z.record(z.string()).optional(),
})
```

And validation runs at the route boundary — both header and body — returning all violations at once if the body is malformed:

```json
{
  "code": "InvalidRequestBody",
  "message": "Request validation failed",
  "details": [
    { "field": "amount", "message": "Must be a decimal string with two places (e.g. \"100.00\")" }
  ],
  "requestId": "req_01HX..."
}
```

## What idempotency keys do *not* protect against

A few clarifications worth pinning down so the team isn't surprised later:

- **They protect one client's retry loop.** They do not deduplicate requests across two distinct clients (mobile app on phone A, mobile app on phone B). That's a domain-level dedup problem — solved with a unique constraint on something the user controls (e.g. an order ID).
- **They do not replace audit logging.** The persisted response is a cache for replay, not a record of what happened — keep your normal audit / ledger writes.
- **They are not optional once you've shipped them.** Removing the header requirement after clients depend on it is a breaking change; document it in the contract and treat it like any other public field.

## TL;DR — the gap and the fix

| Gap | Fix |
|-----|-----|
| `POST /api/payments` accepts no idempotency key | Require `Idempotency-Key` header (UUID) |
| Retries can produce duplicate charges | Persist `(merchantId, key, requestHash, status, body, headers)` and replay on retry |
| Same key + different payload silently overwrites | Return `409` with `code: "IdempotencyKeyReused"` and the previous payment id in `details` |
| In-flight retries race | Mark in-flight; second arrival waits or returns `409 IdempotencyRequestInFlight` |
| Retention undefined | Document the window — 7+ days for financial writes |
| Catalog | Add `IdempotencyKeyRequired`, `IdempotencyKeyReused`, `IdempotencyRequestInFlight` to the error catalog |

Once those are wired, the contract is safe to retry from any client — which is what every well-designed money-moving endpoint promises.
