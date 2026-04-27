**Review Scope:** New file `services/orders/sync.go` implementing `SyncOrderToWarehouse(ctx, db, httpClient, order)` per the supplied design/acceptance criteria.

**Process Used:** Static read of the supplied diff against the stated acceptance criteria; transactional and resource-lifecycle reasoning against Go `database/sql` and `net/http` semantics; severity assigned per the rubric in the request.

**Execution Context:** Single-file code review in a closed context. No build, test execution, repository exploration, or external lookups performed. Only the supplied package contents were read.

**Integration Target:** Go service code in package `orders`, located at `services/orders/sync.go`. Targets a Postgres-style SQL backend (placeholders `$1`, `$2`, `$3`) and an external HTTP warehouse endpoint at `https://warehouse.example.com/orders`.

**Governing Documents:** The "Design / Acceptance criteria" section of the submitted package — specifically the requirements that (a) failures must leave `sync_status` retry-safe and not stuck in `'pending'`, (b) all DB writes happen in a single transaction, (c) context cancellation is honored, and (d) the five enumerated unit tests exist.

**Reviewer:** Claude (Opus 4.7, 1M context), acting as cross-agent code reviewer.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

**1. Transaction is never rolled back on any error path — connection/transaction leak and acceptance-criteria violation**
- File:line — `services/orders/sync.go:52-95` (every early `return` between `BeginTx` and `tx.Commit()`).
- Problem — `tx, err := db.BeginTx(ctx, nil)` is called at line 52, but there is no `defer tx.Rollback()` and no explicit rollback on any of the seven intermediate error returns (lines 62, 67, 74, 80, 85, 93). When any of these fires, the `*sql.Tx` is abandoned without `Commit` or `Rollback`.
- Why it matters — In Go's `database/sql`, an abandoned `*sql.Tx` holds its underlying connection until garbage-collected (and until `Rollback`/`Commit` runs); the connection is not returned to the pool. Under normal failure rates (warehouse 5xx, marshal errors, second `UPDATE` failure) this exhausts the connection pool and stalls the service — squarely the "resource leak under common load" case in the rubric, and arguably "silent data inconsistency" because the row sits with `sync_status='pending'` while the in-flight transaction holding the row-level lock is leaked. This also directly violates the acceptance criterion "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)" — without rollback, the `UPDATE … sync_status='pending'` from line 57-60 is never persisted *and* never released until the conn is GC'd; once it is finally rolled back, the row reverts to its prior status (acceptable), but until then the row is locked and any retry blocks. Worse, if the process crashes between `BeginTx` and the implicit GC-driven cleanup, Postgres will eventually reap the connection, but during the window the row is unavailable. This is a correctness-and-resource bug serious enough to warrant Critical under the supplied rubric.
- Source-of-truth reference — Acceptance criteria bullets "On any failure, the order's `sync_status` is left in a state that lets a retry succeed" and "All DB writes happen in a single transaction" (lines 17-19); Go `database/sql` documented contract that every `BeginTx` must be paired with `Commit` or `Rollback`.
- Proposed fix — Immediately after a successful `BeginTx`, add `defer func() { _ = tx.Rollback() }()`. `Rollback` on an already-committed `Tx` returns `sql.ErrTxDone` and is safe to ignore, so the deferred call is a no-op on the success path. Example:

  ```go
  tx, err := db.BeginTx(ctx, nil)
  if err != nil {
      return fmt.Errorf("begin tx: %w", err)
  }
  defer func() { _ = tx.Rollback() }()
  ```

### High

**2. HTTP call is performed *inside* the open database transaction — long-held row lock and connection pool pressure**
- File:line — `services/orders/sync.go:52-96` (transaction spans the entire function, including `httpClient.Do` at line 78).
- Problem — `BeginTx` opens a transaction at line 52; the very next statement (lines 57-60) issues `UPDATE orders … WHERE id = $3`, which takes a row-level lock on that order. The transaction is then held open while the code marshals JSON, builds the request, and performs a network round-trip to `https://warehouse.example.com/orders` (line 78). Only after the HTTP response returns does the second `UPDATE` run and `tx.Commit()` execute (line 96).
- Why it matters — Holding a DB transaction across a network call is a well-known anti-pattern: the row lock is held for the full warehouse latency (and for the full HTTP client timeout on the slow path), one DB connection is pinned out of the pool for the same duration, and any concurrent `SyncOrderToWarehouse` call (or any other writer of that row) blocks. Under common load with even moderate warehouse latency, this can saturate the DB pool while leaving CPU/HTTP capacity idle. It also makes the "all DB writes in a single transaction" requirement actively harmful: the transaction provides no atomicity benefit here (the external POST is non-transactional and not undone by rollback), but it imposes the cost.
- Source-of-truth reference — Acceptance criteria bullet "All DB writes happen in a single transaction" (line 19) — the literal reading is satisfied, but the design intent (atomicity of the two status writes) does not require holding the tx across the HTTP call.
- Proposed fix — Restructure to: (1) `UPDATE … sync_status='pending'` in its own short transaction (or a single statement) and commit; (2) perform the HTTP POST with no DB transaction open; (3) on success, `UPDATE … sync_status='synced'` in a second short transaction; on failure, `UPDATE … sync_status='failed'` (or similar retry-safe terminal state) so the row is not left as `'pending'`. If the two status writes truly must be atomic, restructure so the HTTP call happens before `BeginTx` and only the final state-write is transactional.

**3. Acceptance criterion "retry-safe on failure" is violated — the row is left as `'pending'` whenever the warehouse call fails after the first UPDATE was attempted to be persisted**
- File:line — `services/orders/sync.go:57-85` (first UPDATE then warehouse POST then non-200/error returns).
- Problem — The flow is: mark `pending` → POST → on 200 mark `synced` → commit. On the failure paths at lines 80 ("warehouse request") and 85 ("warehouse returned %d"), the function returns without committing, so the `pending` write is in fact rolled back implicitly by connection cleanup (see Finding 1) — but only eventually. Conversely, if the author *had* added a rollback (the obvious fix), the row would revert to its prior status with no record of the attempt. There is no `failed` (or similar) terminal state, no `sync_attempts` counter, and no clearing of `sync_started_at`. The criterion "not stuck in 'pending' forever" is met only by accident, via never committing the `pending` row.
- Why it matters — A retry policy needs to know (a) that an attempt occurred, (b) whether it failed, and (c) whether it is safe to re-try. With the current design, two concurrent callers would both see the prior status, both flip to `pending` in their own transactions, and both POST — duplicating the warehouse call. The acceptance criterion implies a deliberate retry-safe state machine; the implementation does not encode one.
- Source-of-truth reference — Acceptance criteria bullet "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)" (lines 17-18).
- Proposed fix — Define an explicit failure state (`'failed'` or `'pending_retry'`) and write it in a dedicated short transaction on each failure branch. Better, persist `sync_attempts` and `last_sync_error` columns so the retry loop has the metadata it needs. Use `UPDATE … WHERE id = $1 AND sync_status NOT IN ('synced','syncing')` to make the initial transition idempotent against concurrent callers.

**4. Non-2xx detection is too narrow — only HTTP 200 is treated as success**
- File:line — `services/orders/sync.go:84`.
- Problem — `if resp.StatusCode != 200` rejects 201 Created, 202 Accepted, and 204 No Content, all of which are conventional success responses for a POST that creates a remote resource. The acceptance criterion ("On 200, marks the order `sync_status='synced'`") is literal here, but most warehouse APIs return 201 for `POST /orders`.
- Why it matters — If the warehouse returns 201 (the most common convention for resource creation), the function will mark the order failed/leave it pending and likely re-POST, creating duplicate orders downstream — silent data inconsistency.
- Source-of-truth reference — Acceptance criterion line 16 ("On 200…") and idiomatic HTTP semantics (RFC 9110 success class 2xx).
- Proposed fix — Use `if resp.StatusCode < 200 || resp.StatusCode >= 300`. If the design truly requires only 200, document that explicitly and request confirmation from the warehouse contract.

**5. Response body is not drained before close — connection cannot be reused (keep-alive leak)**
- File:line — `services/orders/sync.go:82` (and the early return at line 85 without draining).
- Problem — `defer resp.Body.Close()` is set, but on the non-200 path at line 85 the body is closed without first being read to EOF. Go's `net/http` documentation explicitly states that for the connection to be returned to the keep-alive pool the body must be both read to completion and closed. Closing without draining causes the underlying TCP connection to be discarded.
- Why it matters — Under steady warehouse error rates (5xx flapping), this forces a fresh TCP+TLS handshake for every call, increasing latency and consuming ephemeral ports. This is the classic "resource leak under common load" pattern.
- Source-of-truth reference — `net/http.Response.Body` documentation: "The default HTTP client's Transport may not reuse HTTP/1.x connections … if the Body is not both read to completion and closed."
- Proposed fix — Before `return` on the non-200 branch, drain with `io.Copy(io.Discard, resp.Body)`; or change the deferred call to a helper that drains then closes. Capping the drain (e.g. `io.CopyN(io.Discard, resp.Body, 1<<20)`) avoids unbounded reads from a malicious server.

### Medium

**6. `time.Now()` is captured at statement-execution time inside the function — not testable and not consistent across the two writes**
- File:line — `services/orders/sync.go:59` and `services/orders/sync.go:90`.
- Problem — Both UPDATEs call `time.Now()` directly. The two timestamps are computed at different wall-clock moments (separated by the warehouse round-trip), and there is no way for tests or callers to inject a clock.
- Why it matters — The acceptance criteria call for `sync_started_at` and `sync_completed_at`, which is fine. But the implementation makes deterministic unit tests of those values impossible (the "happy path" test cannot assert exact timestamps), and it precludes use of a shared clock for distributed tracing/correlation.
- Source-of-truth reference — Acceptance criterion bullets on `sync_started_at` / `sync_completed_at`; idiomatic Go testability guidance.
- Proposed fix — Inject a `clock` interface (or `now func() time.Time`) into the package or the function. At minimum, capture `start := time.Now()` once at the top so the column semantics are unambiguous.

**7. Context cancellation is honored mid-flight but not pre-checked, and cancellation after the first UPDATE leaves the row in `pending` (compounding Finding 3)**
- File:line — `services/orders/sync.go:52-96`.
- Problem — `ctx` is correctly passed to `BeginTx`, both `ExecContext` calls, and `NewRequestWithContext`, so cancellation will surface as an error. However, there is no early `if err := ctx.Err(); err != nil { return err }` at the top, and on cancellation between the first UPDATE and the warehouse POST the function returns without the explicit failure-state write described in Finding 3.
- Why it matters — Acceptance bullet "Honors context cancellation" is satisfied in the narrow sense that operations abort, but combined with Finding 1 and Finding 3 the row's observable state on cancellation is undefined.
- Source-of-truth reference — Acceptance criterion line 20 ("Honors context cancellation").
- Proposed fix — Add an early `ctx.Err()` check; ensure the rollback path of Finding 1 covers cancellation; ensure the failure-state write of Finding 3 is itself executed with a fresh, non-cancelled context (e.g. `context.WithoutCancel(ctx)` if Go 1.21+) so the bookkeeping write still lands.

**8. No HTTP timeout is enforced by the function; relies entirely on the caller's `httpClient`**
- File:line — `services/orders/sync.go:78`.
- Problem — The function accepts an `*http.Client` from the caller but does not set a per-request deadline (no `context.WithTimeout` wrapping `ctx`). If the caller passes `http.DefaultClient` (no timeout), the request can hang indefinitely, holding the DB transaction (Finding 2) and any DB row lock open.
- Why it matters — Defense in depth against a misconfigured caller; bounds the worst-case duration of the transactional window.
- Source-of-truth reference — Go `net/http` documentation: "Clients and Transports … For control over HTTP client headers, redirect policy, and other settings, create a Client" — i.e., `http.DefaultClient` has no timeout.
- Proposed fix — Wrap `ctx` with `context.WithTimeout(ctx, warehouseTimeout)` before constructing the request, and `defer cancel()`. Make the timeout configurable.

**9. SQL writes use string-literal column names but no allowlist of `sync_status` values; magic strings spread across the function**
- File:line — `services/orders/sync.go:59` (`"pending"`) and `services/orders/sync.go:90` (`"synced"`).
- Problem — The status enum is encoded as inline string literals at two call sites with no shared constant. A typo ("syned"/"penidng") is a silent bug; a future state ("failed"/"retrying") will be added as a third literal.
- Why it matters — The retry state machine described in the acceptance criteria deserves an explicit type. This also makes Finding 3's fix harder than it should be.
- Source-of-truth reference — Acceptance criteria's implicit state machine (`pending` → `synced` / failure-recoverable).
- Proposed fix — Define `type SyncStatus string` with `const (StatusPending SyncStatus = "pending"; StatusSynced SyncStatus = "synced"; StatusFailed SyncStatus = "failed")` and use those constants.

**10. `Order.Total float64` for currency — precision risk**
- File:line — `services/orders/sync.go:42`.
- Problem — Representing monetary totals as `float64` is a well-known footgun: 0.1 + 0.2 ≠ 0.3, summation errors compound, and JSON round-trips can drift.
- Why it matters — The warehouse may store the value verbatim, leading to off-by-cent discrepancies that surface only in reconciliation.
- Source-of-truth reference — Common Go style guidance and any internal "money handling" doc (not provided here, so flagged Medium rather than High).
- Proposed fix — Use a fixed-precision type (`int64` cents, or a `decimal.Decimal`-style library) and serialize as a string.

### Low

**11. Test coverage list does not include a transaction-rollback / connection-leak test**
- File:line — package-level (acceptance criteria line 21-22).
- Problem — The five enumerated tests cover the *return values* on each failure path but not the side effect that matters most: that the DB connection / transaction is released. A test using `sqlmock` with `ExpectRollback()` would have caught Finding 1 immediately.
- Why it matters — Without it, the regression in Finding 1 is invisible to CI.
- Source-of-truth reference — Acceptance criterion bullet on the five tests (lines 21-22).
- Proposed fix — Add a sixth test that asserts `sqlmock.ExpectationsWereMet()` after each failure scenario; this enforces both `ExpectBegin()` and `ExpectRollback()`.

**12. Hard-coded warehouse URL**
- File:line — `services/orders/sync.go:71`.
- Problem — `https://warehouse.example.com/orders` is a literal in the function body.
- Why it matters — Untestable against a fake server without monkey-patching the HTTP client transport, and unconfigurable per environment (staging vs prod).
- Source-of-truth reference — General configurability/testability hygiene.
- Proposed fix — Inject the base URL via a config struct or function parameter; default it from an env var at the composition root.

**13. `fmt.Errorf("warehouse returned %d", resp.StatusCode)` discards the response body**
- File:line — `services/orders/sync.go:85`.
- Problem — On a non-200 the warehouse usually returns a JSON error body explaining why; the current error message contains only the status code.
- Why it matters — Operational debuggability — repeated 400s with no body context are painful to triage.
- Source-of-truth reference — General error-wrapping hygiene.
- Proposed fix — Read up to ~4 KiB of the body with `io.ReadAll(io.LimitReader(resp.Body, 4096))` and include a redacted snippet in the error.

**14. Naming and request construction nit — `http.MethodPost` over `"POST"`**
- File:line — `services/orders/sync.go:71`.
- Problem — Uses the string literal `"POST"` rather than the typed constant `http.MethodPost`.
- Why it matters — Style only; aligns with `gofmt`/`golint` conventions.
- Source-of-truth reference — Standard Go style.
- Proposed fix — Replace with `http.MethodPost`.
