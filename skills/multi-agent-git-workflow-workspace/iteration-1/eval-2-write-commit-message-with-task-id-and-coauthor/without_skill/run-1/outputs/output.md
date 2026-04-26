Here's a commit message for the change:

```
Add idempotent retry on transient processor failures (task-100)

- Add retryWithBackoff helper in api/services/payments.ts
  - Retries 5xx and timeout errors up to 3 times
  - Backoff schedule: 250ms, 500ms, 1000ms
  - Does not retry 4xx responses
- Add api/db/idempotency_keys.ts persistence module
  - Stores Idempotency-Key so retries survive in-process state loss
- Add 8 new tests in api/services/payments.test.ts
  - retry success, retry exhaustion
  - 4xx-no-retry behavior
  - key-survives-restart scenarios
```

Let me know if you want a more concise version or a different style (e.g., conventional-commits-style with a `feat:` prefix).
