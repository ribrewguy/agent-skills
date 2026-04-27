Review Scope: `services/orders/sync.go`, new `SyncOrderToWarehouse` implementation  
Process Used: Closed-context static review of the supplied package only  
Execution Context: Tests are reported passing by implementer; no commands run  
Integration Target: Order-to-warehouse sync service  
Governing Documents: Supplied design / acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-26  

**High Findings**

**H1: Transaction is leaked on every error path after `BeginTx`**  
Citation: `services/orders/sync.go:25`, `services/orders/sync.go:35`, `services/orders/sync.go:40`, `services/orders/sync.go:53`, `services/orders/sync.go:58`, `services/orders/sync.go:66`

Problem statement: After `db.BeginTx` succeeds, the function returns on later failures without calling `tx.Rollback()`. This leaves the transaction open until the connection is reclaimed, and may hold locks or pin a DB connection.

Why it matters: Under common failure modes such as warehouse errors, non-200 responses, marshal failures, or DB update failures, this can exhaust the DB pool and block other order updates. It also weakens the retry guarantee because the attempted pending update remains in an unresolved transaction instead of being cleanly rolled back.

Source-of-truth reference: Acceptance criteria: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed” and “All DB writes happen in a single transaction.”

Proposed fix: Add a rollback guard immediately after `BeginTx`, then clear it after a successful commit, for example:

```go
tx, err := db.BeginTx(ctx, nil)
if err != nil {
	return fmt.Errorf("begin tx: %w", err)
}
defer tx.Rollback()
```

Then keep `return tx.Commit()` at the end, ideally wrapping its error.

**Medium Findings**

**M1: Updates do not verify that the order row exists**  
Citation: `services/orders/sync.go:30`, `services/orders/sync.go:61`

Problem statement: Both `UPDATE orders ... WHERE id = $3` calls ignore `RowsAffected`. If `order.ID` does not match a row, the function can still POST to the warehouse and return success even though no local order was marked pending or synced.

Why it matters: This creates incorrect behavior for missing or stale order IDs and can silently put the warehouse ahead of the local database.

Source-of-truth reference: Acceptance criteria: “Marks the order `sync_status='pending'`...” and “On 200, marks the order `sync_status='synced'`...”

Proposed fix: Capture the `sql.Result`, call `RowsAffected`, and return an error before the POST unless exactly one row was updated.

**Low Findings**

**L1: Commit errors are returned without context**  
Citation: `services/orders/sync.go:69`

Problem statement: `tx.Commit()` is returned directly, unlike the other failure paths that wrap errors with operation context.

Why it matters: This makes production logs and test failures less actionable when commit fails.

Source-of-truth reference: General implementation quality implied by the acceptance criteria’s DB transaction requirement.

Proposed fix: Wrap the commit error:

```go
if err := tx.Commit(); err != nil {
	return fmt.Errorf("commit sync transaction: %w", err)
}
return nil
```
