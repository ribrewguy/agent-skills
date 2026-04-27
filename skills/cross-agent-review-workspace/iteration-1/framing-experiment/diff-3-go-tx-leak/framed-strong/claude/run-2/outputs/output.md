**Review Scope:** `services/orders/sync.go` — new file implementing `SyncOrderToWarehouse`, a function that marks an order pending in the database, POSTs it to a warehouse HTTP endpoint, and marks it synced on success. All DB writes are intended to occur within a single transaction.

**Process Used:** Static line-by-line review of the supplied source against the stated design/acceptance criteria. Traced every error/return path to evaluate transaction lifecycle, resource ownership, and side-effect ordering. No execution or test runs.

**Execution Context:** Closed-context single-file review; only the code and design statement provided in the package were available. No surrounding repository, schema, retry harness, or test code inspected.

**Integration Target:** Production order-sync subsystem in `services/orders/`. Function is invoked per-order with a shared `*sql.DB` and `*http.Client`. Side effects: writes to `orders` table; outbound HTTPS POST to `warehouse.example.com`.

**Governing Documents:** Design / acceptance criteria reproduced in the package: atomic DB writes in a single transaction, retry-safe `sync_status`, context honored, 5 unit tests covering happy path / http failure / db begin failure / marshal failure / warehouse non-200. Go stdlib contracts: `database/sql` (`BeginTx`, `Tx.Rollback`, `Tx.Commit`) and `net/http` (`Response.Body` ownership on `Do` error).

**Reviewer:** Claude (Opus 4.7, 1M context), structured-code-review pass.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior on some inputs, unclear error handling, performance degradation, missing implied validation.
- Low: style, naming, minor refactoring.

**Date:** 2026-04-26

## Findings

### Critical

**1. Transaction is never rolled back on any error path — connection leak and indefinite row locks.**
- Citation: `services/orders/sync.go:52-96` (every `return fmt.Errorf(...)` between the successful `BeginTx` and the final `tx.Commit()`).
- Problem: After `tx, err := db.BeginTx(ctx, nil)` succeeds at line 52, there is no `defer tx.Rollback()` and no explicit `Rollback` on any of the seven intermediate error returns (lines 62, 67, 74, 80, 85, 93). When any of these errors fire, the function returns and the `*sql.Tx` is abandoned. The underlying connection is pinned to that transaction and is not returned to the pool until the connection's session is reset by the driver — which for many drivers happens only when the connection is reused or the context is cancelled. The row touched by the `UPDATE ... sync_status='pending'` at lines 57-60 holds a row-level write lock for the lifetime of that abandoned transaction.
- Why it matters: This is the canonical Go transaction leak. Under any non-trivial failure rate (warehouse 5xx, network blips, marshal errors on malformed orders, context cancellation), the pool drains, every subsequent `BeginTx` blocks, and concurrent workers attempting to sync (or any other writer touching the same `orders` row) block on the stuck row lock. The implementer's claim that "all 5 unit tests pass" does not exercise this — the tests assert on returned errors, not on `db.Stats().OpenConnections` or pool exhaustion under load. This directly violates the "All DB writes happen in a single transaction" criterion in spirit (the transaction is opened but never closed) and the "lets a retry succeed (not stuck in 'pending' forever)" criterion: because the row lock is held by the orphaned tx and the `pending` write is uncommitted, a retry cannot even read consistent state, and once the tx is finally reaped the `pending` write is rolled back — leaving the row in its prior state, which may also be `pending` from an earlier abandoned attempt.
- Source-of-truth reference: `database/sql` documentation for `(*DB).BeginTx` and `(*Tx).Rollback`: "After a call to Commit or Rollback, all operations on the transaction fail with ErrTxDone" — the inverse contract is that until one of those is called, the transaction (and its connection) is held. Standard Go idiom, e.g. `database/sql` package overview and `go.dev/doc/database/execute-transactions`: open a transaction, then `defer tx.Rollback()` immediately; `Rollback` after a successful `Commit` is a documented no-op.
- Proposed fix: Immediately after a successful `BeginTx`, add `defer func() { _ = tx.Rollback() }()` (or capture and log the rollback error if it is anything other than `sql.ErrTxDone`). This makes every early return safe and is idiomatic. Example:
  ```go
  tx, err := db.BeginTx(ctx, nil)
  if err != nil {
      return fmt.Errorf("begin tx: %w", err)
  }
  defer func() { _ = tx.Rollback() }() // no-op after Commit
  ```

### High

**2. HTTP call is performed while the database transaction is open — long-lived tx pinning a pool connection across a network round trip.**
- Citation: `services/orders/sync.go:52` (BeginTx) through `services/orders/sync.go:78` (`httpClient.Do(req)`) and on to `:96` (`tx.Commit()`).
- Problem: The transaction is opened at line 52, an `UPDATE` runs at lines 57-60, and then the function makes an outbound HTTPS POST at line 78 *while still holding the transaction*. The commit only happens at line 96, after the response is fully received and a second `UPDATE` runs.
- Why it matters: Even when nothing errors, every in-flight sync ties up one DB pool connection for the duration of the warehouse round trip (DNS, TLS handshake, server processing, response). Under modest concurrency this saturates the connection pool and starves unrelated queries. It also extends the row-lock window on the `orders` row across an arbitrary external latency, and means any warehouse slowdown directly degrades unrelated DB users. This pattern is widely cited as the most common cause of "the database is down" incidents that turn out to be pool exhaustion.
- Source-of-truth reference: Go `database/sql` guidance ("Avoid holding a transaction open across network calls or user think-time"); general distributed-systems guidance against I/O inside DB transactions.
- Proposed fix: Restructure so the DB transaction does not span the HTTP call. Two reasonable patterns: (a) Use two short transactions: tx1 marks `pending` and commits; perform HTTP; tx2 marks `synced` (or a failure status) and commits. (b) Use the outbox pattern: in tx1 insert into an `outbox` table and mark the order; a separate worker drains the outbox and POSTs to the warehouse. Pattern (a) is the minimum viable change for this PR; pattern (b) is the durable solution and also resolves finding #3.

**3. Retry-safety requirement is violated: on warehouse failure the order is left as `pending` forever.**
- Citation: `services/orders/sync.go:78-85` (HTTP error / non-200 returns) combined with `services/orders/sync.go:57-60` (the `pending` UPDATE).
- Problem: The acceptance criterion says: "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)." With the current code there are exactly two possible end states for a failed sync:
  1. If finding #1 is fixed by adding `defer tx.Rollback()`, then on every failure the `pending` UPDATE is rolled back — the row stays in its prior status, which may be the desired state but means there is no record that a sync was attempted, no `sync_started_at`, and no idempotency anchor.
  2. As currently written, the transaction is abandoned and eventually rolled back by the driver, with the same observable result plus a connection leak — see finding #1.
  Neither matches the spec's requirement of leaving a status that "lets a retry succeed." Worse, the implementer appears to have intended `pending` to be the durable failure state — but `pending` semantically means "in flight," not "failed." A future retry worker has no way to distinguish a sync currently in flight from a sync that died mid-flight, which is exactly the "stuck in `pending` forever" scenario the spec calls out.
- Why it matters: This is the central business requirement of the diff and it is not met. Silent data inconsistency: orders that failed sync look identical to orders mid-sync, so a naive retry job will either double-POST (idempotency hazard at the warehouse) or never retry. Combined with finding #2, a retry could also POST while the original tx still holds the row lock.
- Source-of-truth reference: Acceptance criterion in the package, lines 17-18: "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)."
- Proposed fix: Adopt the two-transaction structure from finding #2's fix and explicitly write a terminal failure status. Concretely:
  - tx1: `UPDATE orders SET sync_status='pending', sync_started_at=NOW(), sync_attempts=sync_attempts+1 WHERE id=$1 AND sync_status IN ('new','failed','pending') AND (sync_started_at IS NULL OR sync_started_at < NOW() - INTERVAL '5 minutes')`. Commit. (The predicate provides idempotency and reclaims rows whose prior attempt died.)
  - HTTP POST with an idempotency key derived from `order.ID` so the warehouse deduplicates retries.
  - tx2 on success: `sync_status='synced', sync_completed_at=NOW()`. On failure: `sync_status='failed', sync_last_error=$1`. Commit.

**4. `httpClient.Do` error path dereferences `resp` semantics incorrectly — `defer resp.Body.Close()` is unreachable on the very path the implementer claims to handle, but on success the body is not drained.**
- Citation: `services/orders/sync.go:78-82`.
- Problem: Two related issues. First, on a 200 response the code does `defer resp.Body.Close()` (good) but never reads the body — for HTTP/1.1 keep-alive and HTTP/2, the underlying connection is only returned to the idle pool if the body is fully drained before `Close`. Closing without draining forces the transport to discard the connection. Second, on non-200 (line 84-86) the error is returned without including any of the response body, so an operator debugging a warehouse rejection has no signal about *why* the warehouse rejected the order.
- Why it matters: Connection-pool churn against `warehouse.example.com` at scale; loss of operational signal on warehouse failures (which the design explicitly enumerates as a tested error path). Not catastrophic but is a "common load" resource issue.
- Source-of-truth reference: `net/http` `Response.Body` documentation: "The default HTTP client's Transport may not reuse HTTP/1.x connections until the Body is read to completion and is closed." Standard Go idiom: `io.Copy(io.Discard, resp.Body)` before `Close`, or read the body and include a snippet in the error.
- Proposed fix: After `defer resp.Body.Close()`, on the non-200 path read the body (capped, e.g. `io.LimitReader(resp.Body, 4096)`) and include it in the wrapped error: `return fmt.Errorf("warehouse returned %d: %s", resp.StatusCode, body)`. On the success path, ensure the body is drained (the second `UPDATE` will run between the read and the close, so an explicit `io.Copy(io.Discard, resp.Body)` is appropriate).

### Medium

**5. Status-code check is too strict: only `200` is accepted; valid 2xx responses are treated as failures.**
- Citation: `services/orders/sync.go:84` — `if resp.StatusCode != 200`.
- Problem: REST APIs commonly return `201 Created`, `202 Accepted`, or `204 No Content` for successful POSTs. Hard-coding `200` will treat a perfectly successful warehouse response as a failure, triggering retries (and double-creates at the warehouse) for every 201/202.
- Why it matters: Silent integration drift if the warehouse changes its success code, and a meaningful chance the warehouse already returns 201/202 today (the spec says "On 200" but real warehouse APIs frequently return 201).
- Source-of-truth reference: RFC 9110 §15.3 — all 2xx codes denote success. Go idiom: `resp.StatusCode/100 == 2` or `resp.StatusCode >= 200 && resp.StatusCode < 300`.
- Proposed fix: `if resp.StatusCode < 200 || resp.StatusCode >= 300 { ... }`. Confirm with the warehouse API contract whether 2xx is the intended success class; if the spec truly means "exactly 200," document that decision in a comment.

**6. `time.Now()` is called twice and stored in DB without timezone discipline; clock source is not injectable for tests.**
- Citation: `services/orders/sync.go:59` and `services/orders/sync.go:90`.
- Problem: `time.Now()` returns local time. Storing local time in `sync_started_at` / `sync_completed_at` produces inconsistent timestamps across hosts in different time zones and breaks comparisons. There is also no clock injection, so the unit tests can only assert "some time," not exact values, and cannot test ordering.
- Why it matters: Subtle timestamp bugs in audit/observability data; harder-to-write deterministic tests.
- Source-of-truth reference: General Go practice — store UTC (`time.Now().UTC()`); inject a `Clock` interface for testability.
- Proposed fix: Use `time.Now().UTC()` (or rely on Postgres `now()` server-side and drop the parameter entirely). Optionally accept a `clock func() time.Time` parameter or struct field.

**7. Order is marshalled and POSTed with no validation, no size cap, and no request timeout independent of `ctx`.**
- Citation: `services/orders/sync.go:65-68` (marshal), `:70-78` (request build and Do), and the function signature at `:46-51` (no timeout, no validation).
- Problem: There is no validation that `order.ID` is non-empty (an empty ID would silently update zero rows in the `pending` UPDATE — and because there is no `RowsAffected` check, the function would happily proceed to POST a phantom order). There is no upper bound on `order` size before sending it to the warehouse. There is no request-scoped timeout — if the caller passes a `context.Background()`, an unresponsive warehouse can hang forever.
- Why it matters: The "missing validation that the design implies" bucket. Empty-ID is a real risk: the function takes `order Order` by value and trusts it. Silent zero-row updates plus an outbound POST is a subtle data-integrity bug.
- Source-of-truth reference: General defensive-programming and `database/sql` `(Result).RowsAffected`.
- Proposed fix: Validate `order.ID != ""` at function entry. Check `RowsAffected` on the `pending` UPDATE and return an error if zero (likely indicates a deleted or non-existent order). Either require the caller to set a deadline on `ctx` and assert it (`if _, ok := ctx.Deadline(); !ok { ... }`) or wrap with `context.WithTimeout` internally for the HTTP call.

**8. Hard-coded warehouse URL and no idempotency key on the POST.**
- Citation: `services/orders/sync.go:71` — `"https://warehouse.example.com/orders"`.
- Problem: The endpoint URL is baked into the function. There is no `Idempotency-Key` header, which combined with finding #3's retry semantics means retries can create duplicates at the warehouse.
- Why it matters: Hard-coded URLs prevent staging/canary deploys against a non-prod warehouse and make tests rely on httptest URL rewriting tricks. No idempotency key is a correctness risk for any retried sync.
- Source-of-truth reference: Stripe-style `Idempotency-Key` convention; standard config-from-environment practice.
- Proposed fix: Inject the warehouse base URL via a config struct or function parameter. Set `req.Header.Set("Idempotency-Key", order.ID)` (or a UUID derived from `order.ID + sync_attempt`) so the warehouse can deduplicate.

**9. Test plan does not exercise the actual failure modes of the implementation.**
- Citation: Acceptance criterion lines 21-22 and the implementer note at line 5.
- Problem: The five enumerated tests (happy path, http failure, db begin failure, marshal failure, warehouse non-200) cover the *return values* of the function but cannot detect (a) the transaction leak from finding #1, (b) the HTTP-inside-tx pool starvation from finding #2, (c) the "stuck in pending" semantic from finding #3, or (d) the body-drain issue from finding #4. The implementer's claim that walking error paths and seeing wrapped errors is sufficient is the exact failure mode the leak relies on — Go transaction leaks do not manifest as wrong return values, they manifest as pool exhaustion and stuck rows under concurrency.
- Why it matters: This is a process/coverage finding but the package explicitly invites severity grading on missing validation that the design implies. The design implies durability under retry; the test plan does not test durability under retry.
- Source-of-truth reference: Implementer note line 5; acceptance criteria 17-22.
- Proposed fix: Add a test that, after each error path, asserts `db.Stats().InUse == 0` (or uses a fake driver counting BeginTx vs Commit+Rollback). Add a test that calls `SyncOrderToWarehouse` N times with an httptest server that returns 500 and then asserts the same row is in a retriable state and that no connection has leaked. Add a test that runs two concurrent syncs of the same order and asserts the warehouse receives at most one POST (or that the second cleanly reports a conflict).

### Low

**10. Marshal-failure error message is misleading because it cannot fire for the declared `Order` struct.**
- Citation: `services/orders/sync.go:65-68`.
- Problem: `json.Marshal` of a struct whose fields are `string`, `float64`, and `string` cannot return a non-nil error in practice. The "marshal failure" branch is essentially dead code, but the test plan claims to cover it (line 22). This either means the test is faking the marshal error (and the production branch is unreachable), or the `Order` type is expected to grow fields that *can* fail (channels, functions, NaN floats with custom marshallers), in which case the error message should hint at what to look for.
- Why it matters: Cosmetic / clarity. Worth noting because the implementer flagged "every error path" as walked and verified.
- Source-of-truth reference: `encoding/json` documentation on which types can return marshal errors.
- Proposed fix: Either drop the branch and document that the struct cannot fail to marshal, or keep it and improve the wrap: `fmt.Errorf("marshal order %s: %w", order.ID, err)`.

**11. Errors do not include the order ID, hampering debugging.**
- Citation: `services/orders/sync.go:54, 62, 67, 74, 80, 85, 93`.
- Problem: Every wrapped error gives a stage name but never the order ID. In production logs, "warehouse request: dial tcp ... i/o timeout" without the order ID is hard to triage.
- Why it matters: Operability nit.
- Proposed fix: Include `order.ID` in each wrap: `fmt.Errorf("mark pending order %s: %w", order.ID, err)`.

**12. SQL is inline and uses positional parameters without a named constant; minor maintainability nit.**
- Citation: `services/orders/sync.go:57-60` and `:88-91`.
- Problem: Two near-identical UPDATE statements differing only in column names and status string. Easy to drift; easy to typo a column name.
- Why it matters: Style/maintainability.
- Proposed fix: Extract a small helper `updateSyncStatus(ctx, tx, id, status, tsColumn string, ts time.Time) error` or use a query builder.

**13. `Content-Type` header is set after `NewRequestWithContext`; consider also setting `Accept`.**
- Citation: `services/orders/sync.go:76`.
- Problem: Cosmetic — `Accept: application/json` would let the warehouse return JSON errors that the (proposed) body-reading code in finding #4 can parse cleanly.
- Why it matters: Minor.
- Proposed fix: `req.Header.Set("Accept", "application/json")`.
