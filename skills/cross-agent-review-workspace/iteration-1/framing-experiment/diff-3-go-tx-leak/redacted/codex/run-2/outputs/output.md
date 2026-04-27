Review Scope: `services/orders/sync.go`, new `SyncOrderToWarehouse` implementation  
Process Used: Static review from provided package only; no tools or filesystem access  
Execution Context: Closed-context evaluation; tests/gates not assumed  
Integration Target: Order-to-warehouse sync behavior  
Governing Documents: Design / Acceptance criteria in package  
Reviewer: Codex second-pass reviewer  
Severity Scale: Critical / High / Medium / Low as defined in request  
Date: 2026-04-26

**Findings**

**Critical**

No findings.

**High**

1. `services/orders/sync.go:34`

Problem: The transaction is never rolled back on early returns after `BeginTx`. This occurs on pending update failure, marshal failure, request construction failure, HTTP failure, non-200 response, and final synced update failure.

Why it matters: The design requires all DB writes to happen in a single transaction and failures to leave the order retryable. Without rollback, the transaction can hold locks and connection resources until the connection is closed or reclaimed. Under normal failure load this can exhaust the DB pool and leave the earlier `pending` update unresolved inside an abandoned transaction.

Source-of-truth reference: “All DB writes happen in a single transaction”; “On any failure, the order's `sync_status` is left in a state that lets a retry succeed”; review instruction: “Resource leaks on early returns, cleanup ordering, defer/finally discipline.”

Proposed fix: Immediately after successful `BeginTx`, add a rollback defer that runs unless commit succeeds:

```go
committed := false
defer func() {
	if !committed {
		_ = tx.Rollback()
	}
}()
...
if err := tx.Commit(); err != nil {
	return fmt.Errorf("commit tx: %w", err)
}
committed = true
return nil
```

2. `services/orders/sync.go:30`

Problem: The implementation marks the order `pending` before doing the HTTP call, but on HTTP/client/non-200 failures it returns without explicitly moving the order out of `pending`.

Why it matters: The acceptance criteria explicitly says failures must not leave the order stuck in `pending` forever. If the transaction is later changed to commit failure state, or if rollback discipline is misunderstood, this code path violates the retryability requirement. The function lacks an explicit failure-state transition such as `failed` or `retryable`.

Source-of-truth reference: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever).”

Proposed fix: Define the intended retryable failure state and update it inside the same transaction before commit on failures after marking pending, or rollback the pending write consistently and document that the prior state is retryable. The implementation should make the retryability behavior explicit and covered by tests.

**Medium**

1. `services/orders/sync.go:69`

Problem: `tx.Commit()` errors are returned without context.

Why it matters: Commit failure is a DB write failure in the required transaction boundary. Returning the raw error makes diagnosis harder and inconsistent with every other error path in this function.

Source-of-truth reference: “All DB writes happen in a single transaction.”

Proposed fix:

```go
if err := tx.Commit(); err != nil {
	return fmt.Errorf("commit tx: %w", err)
}
return nil
```

2. `services/orders/sync.go:51`

Problem: `httpClient` is not validated before use.

Why it matters: A nil client causes a panic, not an error. The design describes a function that returns failures as errors and honors cancellation; a panic bypasses that contract.

Source-of-truth reference: Function acceptance criteria describes failure handling; “Honors context cancellation.”

Proposed fix: Either default nil to `http.DefaultClient` or return a clear error before starting the transaction.

**Low**

No findings.
