# Review of `POST /api/payments`

The draft looks reasonable on the surface, but for a money-moving endpoint there are a few things I'd want to see before we ship. Here's my review:

## 1. Authentication and authorization

Make sure the route requires a verified caller (API key, OAuth bearer, signed request, etc). For internal admin operations vs. public client-initiated payments, the auth model can differ — call out which is which.

## 2. Input validation

- Validate the `amount` server-side. Don't trust the client. Also use a decimal type or string-encoded decimal rather than a JS float.
- Validate the currency against an allowlist.
- Reject negative amounts, zero, or amounts above a per-merchant limit.
- Validate the customer reference / payment source.

## 3. Error responses

Define error response shape:

```json
{
  "error": {
    "code": "INSUFFICIENT_FUNDS",
    "message": "Card declined: insufficient funds"
  }
}
```

Map the common decline codes from your processor to your own error codes so clients have a stable contract.

## 4. PCI / compliance

If the endpoint accepts raw card details, you're in PCI scope — typically you want to take a tokenized payment source instead (e.g. a Stripe / Braintree token) so the card data never touches your servers.

## 5. Logging

Log the request and response (excluding card numbers) with a request ID for support traceability.

## 6. Rate limiting

Payment endpoints are attractive targets for card-testing attacks. Rate limit aggressively per IP and per customer, and consider 3DS / step-up auth on suspicious patterns.

## 7. Webhook / async handling

If the payment can be asynchronous (3DS challenge, ACH, etc), the synchronous response should clearly indicate `pending` vs `succeeded`, and you'll want a webhook to inform the merchant when the final state lands.

## 8. Status codes

- `201 Created` on successful payment creation, with `Location` pointing at `/api/payments/{id}`.
- `422 Unprocessable Entity` for validation errors.
- `402 Payment Required` for processor declines (card declined, insufficient funds, etc).
- `429 Too Many Requests` when rate limits trigger.

## Summary

Tighten up auth, server-side validation, and error mapping. Take tokenized payment sources rather than raw card details. Decide synchronous vs. async behavior and set up webhooks for the async case. Beyond that the shape looks fine.
