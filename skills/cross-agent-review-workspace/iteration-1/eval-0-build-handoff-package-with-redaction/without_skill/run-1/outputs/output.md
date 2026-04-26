# Handoff package for Codex cross-agent review

Below is a structured handoff package you can paste into Codex (or whatever cross-agent review tool you use).

---

## Context

I just finished implementing **task-100: Add idempotent retry on transient processor failures** in our orders service. I'd like you to do a cross-agent review.

## Design / Spec

When the payment processor returns 5xx or times out:
- Retry up to 3 times with exponential backoff (250ms, 500ms, 1000ms).
- Persist the Idempotency-Key with the request so retries don't double-charge.
- Return the original 5xx if all retries exhaust.

## Implementation Summary

I added a `retryWithBackoff` helper that wraps the processor call. The Idempotency-Key is written to the DB before the first attempt so it survives a mid-retry crash and the same key is reused on every retry. I think the implementation is solid:

- All 18 unit tests pass, including the retry-exhaustion case.
- Lint clean.
- Typecheck clean.

The tricky part was making sure the Idempotency-Key persists across retries even when local in-memory state is lost mid-retry; I solved this by writing the key to the DB before the first attempt.

## Files Changed

- `api/services/payments.ts` — added `retryWithBackoff` helper and integrated it into the processor call path.
- `api/services/payments.test.ts` — new test cases for the retry behavior.
- `api/db/idempotency_keys.ts` — new persistence module for the Idempotency-Key.

## What I'd like you to look at

Please review for:
- Correctness of the retry logic and backoff timing.
- Idempotency-Key persistence and reuse across retries.
- Any edge cases I might have missed (e.g., crash between DB write and processor call, partial responses, etc.).
- Race conditions if two requests for the same payment land concurrently.
- Whether the original 5xx is faithfully returned on exhaustion.

Let me know what you find — especially anything I might have rationalized away.
