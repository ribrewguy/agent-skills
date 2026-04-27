Review Scope: `services/orders/sync.go` implementation of `SyncOrderToWarehouse` against stated acceptance criteria.  
Process Used: Static review from provided package only; no shell, filesystem, or external lookup used.  
Execution Context: Closed-context code review.  
Integration Target: Order-to-warehouse sync flow.  
Governing Documents: Design / Acceptance criteria in review package.  
Reviewer: Codex.  
Severity Scale: Critical / High / Medium / Low as defined in request.  
Date: 2026-04-27.

**Critical Findings**

None.

**High Findings**

**H1: Open transaction is not rolled back on failure**  
Citation: `services/orders/sync.go:25`, `services/orders/sync.go:30`, `services/orders/sync.go:51`, `services/orders/sync.go:57`

Problem: After `BeginTx` succeeds, every error path before `Commit` returns without calling `tx.Rollback()`. This includes pending update failure, marshal failure, request build failure, HTTP failure, warehouse non-200, and final synced update failure.

Why it matters: The transaction can remain open, holding a DB connection and potentially row locks after `sync_status='pending'` is written inside the transaction. Under common failure modes like warehouse errors, this can block retries and degrade production traffic.

Source of truth: Acceptance criteria require failures to leave the order retryable and all DB writes to happen in a transaction.

Proposed fix: Add rollback cleanup immediately after successful `BeginTx`:

```go
committed := false
defer func() {
	if !committed {
		_ = tx.Rollback()
	}
}()
```

Then set `committed = true` only after a successful commit, or use the common pattern `defer tx.Rollback()` and ignore `sql.ErrTxDone`.

**Medium Findings**

**M1: Commit error lacks contextual wrapping**  
Citation: `services/orders/sync.go:69`

Problem: `return tx.Commit()` returns the raw DB error, unlike the rest of the function’s contextual errors.

Why it matters: A commit failure is one of the most ambiguous and operationally important failure points. Without context, logs will not clearly show that the sync transaction commit failed.

Source of truth: Implementer note says every error path returns a wrapped error with context.

Proposed fix:

```go
if err := tx.Commit(); err != nil {
	return fmt.Errorf("commit sync transaction: %w", err)
}
return nil
```

**M2: Updates do not verify that the target order row exists**  
Citation: `services/orders/sync.go:30`, `services/orders/sync.go:61`

Problem: Both `UPDATE orders ... WHERE id = $3` calls ignore `RowsAffected`. If `order.ID` does not match a row, the function can still POST the order to the warehouse and return success after updating zero local rows.

Why it matters: That creates a silent consistency gap: the warehouse may receive an order the local database never marked pending or synced.

Source of truth: Acceptance criteria say the function marks “the order” pending and synced.

Proposed fix: Capture the `sql.Result` from each update and require exactly one affected row, returning a wrapped error otherwise.

**Low Findings**

None.
