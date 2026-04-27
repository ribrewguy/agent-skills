Review Scope: `services/orders/sync.go`, `SyncOrderToWarehouse`
Process Used: Static review from provided package only; no tools or file reads used.
Execution Context: Closed-context evaluation.
Integration Target: Order-to-warehouse sync acceptance criteria.
Governing Documents: Design / Acceptance criteria in package.
Reviewer: Codex second-pass cross-vendor reviewer.
Severity Scale: Critical, High, Medium, Low as defined in request.
Date: 2026-04-26

**Findings: High**

**High: transaction is leaked on every early return after `BeginTx`**
Citation: `services/orders/sync.go:25`, `services/orders/sync.go:35`, `services/orders/sync.go:40`, `services/orders/sync.go:53`, `services/orders/sync.go:58`, `services/orders/sync.go:66`

Problem: The function begins a transaction but never rolls it back when later work fails. Every return after line 25 exits with an open transaction unless `Commit` is reached.

Why it matters: This can pin a DB connection, hold locks, and exhaust the pool under common failure modes such as warehouse downtime or non-200 responses. It also leaves cleanup behavior driver-dependent.

Source-of-truth reference: Acceptance criteria: “All DB writes happen in a single transaction” and review instruction: “Resource leaks on early returns, cleanup ordering, defer/finally discipline.”

Proposed fix: Add rollback cleanup immediately after a successful `BeginTx`, and suppress it after successful commit, e.g. `defer tx.Rollback()` with explicit handling around `Commit`.

---

**High: failure path does not leave an explicit retryable sync state**
Citation: `services/orders/sync.go:30`, `services/orders/sync.go:57`

Problem: The function marks the order `pending`, then returns on HTTP failure or non-200 without writing a failure/retryable terminal state such as `failed` or clearing `pending`.

Why it matters: If rollback cleanup is added correctly, the pending write disappears and retry may be possible, but the implementation still does not record that the sync attempt failed. If cleanup is later changed or partial state escapes through driver/application behavior, the order can remain `pending` indefinitely, directly violating the requirement.

Source-of-truth reference: Acceptance criteria: “On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever).”

Proposed fix: Define and persist an explicit retryable failure state inside the same transaction on failures after the initial pending mark, or ensure the transaction is rolled back and document that unchanged prior state is the retryable state. Tests should assert the resulting DB state for HTTP failure, marshal failure, and non-200.

---

**Findings: Medium**

**Medium: no validation for nil `httpClient`**
Citation: `services/orders/sync.go:51`

Problem: The function calls `httpClient.Do(req)` without checking whether `httpClient` is nil.

Why it matters: A nil client causes a panic instead of returning an error. The function’s contract is error-returning, and dependency injection of an HTTP client makes nil input plausible in tests or callers.

Source-of-truth reference: Acceptance criteria imply failure modes should be handled by returning errors and leaving retryable state.

Proposed fix: Either default nil to `http.DefaultClient` or return a clear error before starting the transaction.

---

**Medium: transaction spans external network I/O**
Citation: `services/orders/sync.go:25`, `services/orders/sync.go:51`, `services/orders/sync.go:69`

Problem: The DB transaction is opened before the warehouse request and remains open while the network call is in flight.

Why it matters: Slow or hanging warehouse calls hold DB transaction resources and possibly row locks for the duration. Under load, this can degrade DB availability even though the external call is unrelated to DB consistency until completion.

Source-of-truth reference: Acceptance criteria require all DB writes in one transaction, but do not require the external HTTP call to occur while the transaction is open.

Proposed fix: Consider marshalling and sending before opening the write transaction, then perform the required DB writes in one short transaction. If the design requires marking `pending` before POST, add strict HTTP timeouts and rollback discipline.

---

**Findings: Low**

**Low: commit errors are not wrapped**
Citation: `services/orders/sync.go:69`

Problem: `tx.Commit()` is returned directly while other errors are wrapped with operation context.

Why it matters: Commit failures are often the hardest DB failures to diagnose; losing context makes logs less actionable.

Source-of-truth reference: Existing implementation pattern wraps operational errors throughout the function.

Proposed fix: Wrap commit errors: `if err := tx.Commit(); err != nil { return fmt.Errorf("commit sync tx: %w", err) }`.
