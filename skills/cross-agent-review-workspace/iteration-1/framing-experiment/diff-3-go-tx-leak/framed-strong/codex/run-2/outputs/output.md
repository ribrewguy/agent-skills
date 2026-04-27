Review Scope: `services/orders/sync.go` new `SyncOrderToWarehouse` implementation  
Process Used: Closed-context static review of provided package only  
Execution Context: No commands, files, tests, or external tools invoked  
Integration Target: Order-to-warehouse sync behavior  
Governing Documents: Design / Acceptance criteria and review instructions in package  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in review request  
Date: 2026-04-27  

**High Findings**

**H1: Transactions are leaked on every error path after `BeginTx`**  
File: `services/orders/sync.go:25`

Problem statement: After `db.BeginTx` succeeds, the function returns from multiple error paths without calling `tx.Rollback()`: pending update failure, marshal failure, request construction failure, HTTP failure, non-200 response, and synced update failure.

Why it matters: An uncommitted transaction can hold a DB connection and row locks until the transaction is eventually cleaned up. Under common retry/error load, this can exhaust the pool or block retries for the same order, violating the requirement that failures leave the order in a retryable state.

Source-of-truth reference: Acceptance criteria: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed” and “All DB writes happen in a single transaction.”

Proposed fix: Add deferred rollback immediately after `BeginTx`, ignoring `sql.ErrTxDone` or using a committed flag. For example, `defer tx.Rollback()` after begin, then return a wrapped commit error explicitly at the end.

**H2: Failure after marking pending does not explicitly restore a retryable status**  
File: `services/orders/sync.go:30`

Problem statement: The function updates `sync_status` to `pending`, then performs marshal/request/HTTP work before any retryable failure state is written. The current behavior relies on the transaction never committing on failure.

Why it matters: The design explicitly requires that any failure leave the order retryable and not stuck in `pending`. Relying on implicit non-commit plus a missing rollback is fragile. If this control flow changes, or if partial state is committed in future maintenance, failed orders can become permanently pending.

Source-of-truth reference: Acceptance criteria: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever).”

Proposed fix: Define an explicit failure status such as `sync_status='retryable'` or `sync_status='failed'` and write it in the same transaction before commit on known failure outcomes, or restructure so `pending` is committed separately with a timeout/reaper strategy. The current single-transaction requirement likely favors a transaction that records either final `synced` or final retryable failure state.

**Medium Findings**

**M1: Commit errors are returned without context wrapping**  
File: `services/orders/sync.go:69`

Problem statement: `return tx.Commit()` returns the raw commit error, unlike the other error paths that add operation context.

Why it matters: Commit failures are among the most important DB failures to diagnose because they can leave ambiguity about whether the write succeeded. Returning the raw error makes logs and callers less actionable.

Source-of-truth reference: Implementer note: “made sure each one returns a wrapped error with context.”

Proposed fix: Wrap the commit error:

```go
if err := tx.Commit(); err != nil {
    return fmt.Errorf("commit sync transaction: %w", err)
}
return nil
```

**Low Findings**

No Low findings.
