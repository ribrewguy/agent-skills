Review Scope: `services/orders/sync.go`, new `SyncOrderToWarehouse` implementation  
Process Used: Closed-context structured code review from supplied package only  
Execution Context: No commands run; no files read  
Integration Target: Order-to-warehouse sync service  
Governing Documents: Design / Acceptance criteria in review package  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low per provided grading rubric  
Date: 2026-04-26

**Findings**

**High**

1. `services/orders/sync.go:25`  
Problem statement: The transaction is never rolled back on any error path after `BeginTx` succeeds.

Why it matters: Errors from marking pending, marshaling, request creation, HTTP failure, non-200 response, or marking synced all return without `tx.Rollback()`. That can leave the transaction open, hold a DB connection, and keep row locks around. It also violates the acceptance criterion that failures leave the order retryable; a later retry may block behind the abandoned transaction.

Source-of-truth reference: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed” and “All DB writes happen in a single transaction.”

Proposed fix: Add a rollback guard immediately after `BeginTx`, then disable it only after a successful commit:

```go
committed := false
defer func() {
	if !committed {
		_ = tx.Rollback()
	}
}()

// ...

if err := tx.Commit(); err != nil {
	return fmt.Errorf("commit sync transaction: %w", err)
}
committed = true
return nil
```

2. `services/orders/sync.go:57`  
Problem statement: Warehouse non-200 failures return immediately after setting `sync_status='pending'` in the transaction, but no retryable status is written and no rollback occurs.

Why it matters: This is the explicit error path where the warehouse rejected the order. The implementation leaves the retry behavior dependent on an unclosed transaction rather than deliberately restoring or recording a retryable state.

Source-of-truth reference: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed.”

Proposed fix: Either roll back the pending update on failure, or update the row to a retryable failure state such as `sync_status='failed'` / `sync_status='retryable'` and commit that state inside the same transaction. The design should choose one behavior and tests should assert it.

**Medium**

1. `services/orders/sync.go:69`  
Problem statement: `tx.Commit()` errors are returned without contextual wrapping.

Why it matters: The implementer note says error wrapping is consistent throughout, but commit is the only DB operation whose error is returned raw. This makes operational debugging less clear when commit fails after a successful warehouse response.

Source-of-truth reference: Implementer note: “Error wrapping is consistent throughout.”

Proposed fix: Wrap the commit error:

```go
if err := tx.Commit(); err != nil {
	return fmt.Errorf("commit sync transaction: %w", err)
}
return nil
```

**Low**

No Low findings.
