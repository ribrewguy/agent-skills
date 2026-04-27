Review Scope: `services/orders/sync.go`, focused on the new `SyncOrderToWarehouse` behavior against the stated acceptance criteria.

Process Used: Static review of the provided package only; no tools, shell commands, file reads, or test execution.

Execution Context: Closed-context evaluation. Implementer states tests pass.

Integration Target: Order-to-warehouse sync flow.

Governing Documents: Acceptance criteria in the review package.

Reviewer: Codex.

Severity Scale: Critical = data corruption/RCE/privilege escalation; High = security risk, resource leak under common load, silent data inconsistency, design violation; Medium = incorrect behavior for some inputs or unclear handling; Low = style/nits.

Date: 2026-04-27.

**Findings: High**

**H1: Transaction is leaked on every error after `BeginTx`**
Citation: `services/orders/sync.go:25`, `services/orders/sync.go:35`, `services/orders/sync.go:40`, `services/orders/sync.go:47`, `services/orders/sync.go:53`, `services/orders/sync.go:58`, `services/orders/sync.go:66`

Problem: After opening a transaction, the function returns from multiple error paths without calling `Rollback`.

Why it matters: This can hold DB connections and row locks until cleanup, causing resource exhaustion or blocked retries under load. It also makes the order’s persisted sync state ambiguous on failures.

Source of truth: Acceptance criteria require all DB writes to happen in a single transaction and failures to leave the order retryable.

Proposed fix: Add `defer tx.Rollback()` immediately after successful `BeginTx`; ignore `sql.ErrTxDone` semantics as usual. Only `Commit` should finalize the transaction.

```go
tx, err := db.BeginTx(ctx, nil)
if err != nil {
    return fmt.Errorf("begin tx: %w", err)
}
defer tx.Rollback()
```

**H2: Failure paths after marking `pending` do not deliberately leave a retryable state**
Citation: `services/orders/sync.go:30`, `services/orders/sync.go:51`, `services/orders/sync.go:57`

Problem: The function marks the order `pending`, then performs JSON/request/HTTP work. If any later step fails, it returns without explicitly transitioning the order back to a retryable status or rolling back the pending write.

Why it matters: The design explicitly says failures must not leave the order stuck in `pending` forever. Current behavior relies on implicit transaction cleanup that is not performed by the function.

Source of truth: “On any failure, the order’s `sync_status` is left in a state that lets a retry succeed.”

Proposed fix: Roll back the transaction on all failures so the pending update is not persisted, or update to a retryable failure state such as `sync_status='failed'` within the same transaction before commit. Given “all DB writes happen in a single transaction,” rollback-on-failure is the simplest fit.

**Findings: Medium**

**M1: Successful warehouse POST followed by failed commit can create duplicate warehouse syncs**
Citation: `services/orders/sync.go:51`, `services/orders/sync.go:69`

Problem: The external POST happens before the DB transaction commits. If the warehouse accepts the order but `tx.Commit()` fails, the caller sees an error and may retry, potentially sending the same order again.

Why it matters: This is a silent consistency risk between the local database and warehouse system.

Source of truth: Acceptance criteria require marking synced on 200 and retry-safe failure behavior.

Proposed fix: Use an idempotency key, ideally the order ID, in the warehouse request so retries are safe. For a more robust architecture, use an outbox pattern where the DB transaction records work to send and a worker performs idempotent delivery.

**Findings: Low**

No low-severity findings.
