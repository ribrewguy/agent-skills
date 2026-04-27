Review Scope: `services/orders/sync.go`, new `SyncOrderToWarehouse` implementation  
Process Used: Closed-context static review of the supplied package only; no tools or filesystem access used  
Execution Context: Go service code using `database/sql`, `net/http`, and caller-provided context  
Integration Target: Order-to-warehouse sync workflow  
Governing Documents: Supplied design / acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as defined in request  
Date: 2026-04-26

**Findings: High**

**services/orders/sync.go:28**  
Problem statement: The transaction is never rolled back on error paths after `BeginTx` succeeds. Errors from `mark pending`, JSON marshal, request construction, HTTP request failure, warehouse non-200, `mark synced`, and even commit failure all return without `tx.Rollback()`.

Why it matters: This can leave the transaction open, pin a DB connection, hold locks, and make retries block or fail under normal failure conditions. That directly violates the requirement that failures leave the order in a state where retry can succeed, and creates a resource leak under common load.

Source-of-truth reference: Acceptance criteria: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed” and “All DB writes happen in a single transaction.”

Proposed fix: Add a rollback-on-error guard immediately after `BeginTx`, then disable it only after a successful commit. For example, use a `committed := false` defer that calls `tx.Rollback()` unless committed, or explicitly rollback before every return after begin.

**Findings: Medium**

**services/orders/sync.go:66**  
Problem statement: `tx.Commit()` is returned directly without error wrapping.

Why it matters: The implementer note says error wrapping is consistent throughout, but this path loses operation context. Commit failures are especially important because the warehouse POST may already have succeeded while the local transaction failed to persist.

Source-of-truth reference: Implementer note: “Error wrapping is consistent throughout.”

Proposed fix: Capture and wrap the commit error:

```go
if err := tx.Commit(); err != nil {
	return fmt.Errorf("commit sync transaction: %w", err)
}
return nil
```

**services/orders/sync.go:48**  
Problem statement: A nil `httpClient` will panic at `httpClient.Do(req)`.

Why it matters: The function accepts the client as an argument and does not document or enforce non-nil input. This is incorrect behavior for one plausible caller input and can turn a recoverable configuration problem into a process crash.

Source-of-truth reference: Function contract implied by `SyncOrderToWarehouse(ctx, db, httpClient, order)` accepting dependencies as parameters.

Proposed fix: Either validate `httpClient != nil` and return an error, or default to `http.DefaultClient`.

**Findings: Low**

**services/orders/sync.go:35**  
Problem statement: `time.Now()` is called separately for `sync_started_at` and `sync_completed_at`, with no injectable clock.

Why it matters: This is acceptable operationally, but it can make tests less deterministic and makes timestamp assertions harder than necessary.

Source-of-truth reference: Acceptance criteria require timestamp writes for start and completion.

Proposed fix: If tests need exact timestamp assertions, introduce a small clock abstraction or package-level `now` variable. Otherwise, no change required.
