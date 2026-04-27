- **Review Scope:** `services/orders/sync.go` — newly added `SyncOrderToWarehouse` function and its conformance to the design / acceptance criteria.
- **Process Used:** Cold structured code review against the supplied design contract; manual re-derivation of failure modes (no compilation, no test execution, no static analyzers run).
- **Execution Context:** Single-file Go change reviewed in isolation; no surrounding repo, build, or test harness available.
- **Integration Target:** `services/orders` package within a Go service that posts orders to `https://warehouse.example.com/orders` and persists sync state in a SQL database.
- **Governing Documents:** Inline "Order-to-warehouse sync" design / acceptance criteria provided in the package (lines 25-38).
- **Reviewer:** Cross-vendor second-pass reviewer (Claude).
- **Severity Scale:** Critical (data corruption / RCE / privilege escalation), High (significant security risk, resource leak under common load, silent data inconsistency, design requirement violated), Medium (incorrect behavior on some inputs, unclear error handling, missing validation implied by design), Low (style, naming, nits).
- **Date:** 2026-04-26.

## Findings

### Critical

#### C1. Transaction is never rolled back on any error path — `*sql.Tx` and its underlying connection leak on every failure
- **Citation:** `services/orders/sync.go:68-112` (every `return fmt.Errorf(...)` between line 77 and line 109).
- **Problem:** `tx, err := db.BeginTx(ctx, nil)` (line 68) acquires a connection from the pool and starts a transaction, but the function never calls `tx.Rollback()` and there is no `defer` to guarantee cleanup. Every error path between marking pending (line 77), marshalling (line 82), building the request (line 89), executing the HTTP call (line 95), and the warehouse non-200 (line 100) returns without rolling back. The HTTP path between lines 73 and 104 holds the DB transaction open across a network round-trip, so any HTTP error, marshal error, or non-200 leaves the transaction dangling.
- **Why it matters:** Each leaked transaction holds a pooled connection plus row-level locks on the `orders` row. Under common load (warehouse latency, transient HTTP errors, 4xx/5xx responses), the connection pool will be exhausted within minutes and unrelated queries will block or time out. On Postgres, the held row lock will also block any other writer touching that order. This is a classic resource leak under common load and qualifies as Critical because the service will lock up in production rather than degrade gracefully.
- **Source-of-truth reference:** Design line 35 ("All DB writes happen in a single transaction") implies correct transaction lifecycle management; Go `database/sql` contract — `Tx.Commit` or `Tx.Rollback` MUST be called to release the underlying connection (per `database/sql` docs).
- **Proposed fix:** Immediately after a successful `BeginTx`, defer a rollback that is a no-op once committed:
  ```go
  tx, err := db.BeginTx(ctx, nil)
  if err != nil {
      return fmt.Errorf("begin tx: %w", err)
  }
  defer func() { _ = tx.Rollback() }() // safe to call after Commit
  ```
  Additionally, restructure so the HTTP call does not happen while the transaction is open (see H1).

### High

#### H1. Acceptance criterion violated: failure leaves `sync_status='pending'` forever, blocking retry
- **Citation:** `services/orders/sync.go:73-102`.
- **Problem:** The function writes `sync_status='pending'` inside the transaction (line 73) and then performs the HTTP POST (line 94) before any commit. If the HTTP call fails (line 95), returns a non-200 (line 100), or the marshal fails (line 81), the function returns an error without commit and without rollback. With the missing `Rollback` (C1), the pending update is also never persisted — so depending on whether the connection later returns the transaction as rolled back or partially applied, the row may either retain the previous status or, after the leaked transaction is eventually killed, be left in an indeterminate state. More importantly, if the design intent is that the row is observable as `pending` during the sync, the only way to honor "left in a state that lets a retry succeed" is to actively reset it. The current code does neither: there is no compensating UPDATE that sets the status back to a retryable value (e.g., `'failed'` or the prior status) on failure.
- **Why it matters:** Design line 33-34 explicitly requires that on any failure the status is "left in a state that lets a retry succeed (not stuck in 'pending' forever)." A naïve retry checking `WHERE sync_status != 'pending'` would skip these rows; a retry that races with the leaked transaction may also be blocked by the held row lock. This is silent data inconsistency plus a direct design-requirement violation.
- **Source-of-truth reference:** Design lines 31-34.
- **Proposed fix:** Two correct patterns:
  1. Move the HTTP call outside the transaction. Open a tx only to mark pending and commit; on HTTP success, open a second tx to mark synced; on any failure, run an UPDATE that resets the row to a retryable status (e.g., `'failed'`) with the failure timestamp.
  2. Or: never write `pending` until the HTTP call succeeds, and on success open a single tx that writes only `synced` + `sync_completed_at`. The current "single transaction wrapping the HTTP call" approach cannot satisfy both "single transaction" and "retry-friendly on failure" simultaneously without explicit compensating writes.

#### H2. HTTP response body is leaked when `httpClient.Do` returns a non-nil response with a non-nil error
- **Citation:** `services/orders/sync.go:94-98`.
- **Problem:** The code does `resp, err := httpClient.Do(req)`; if `err != nil`, it returns immediately at line 96 without closing `resp.Body`. Per Go's `net/http` documentation, when `Do` returns an error, the response may still be non-nil (e.g., on redirect failures and some transport errors), and the caller is responsible for closing `resp.Body` to release the underlying TCP connection back to the transport's idle pool.
- **Why it matters:** Under repeated transient HTTP errors, this leaks file descriptors and TCP connections, eventually exhausting the transport's connection pool and/or the process's FD limit. This is a resource leak under common load.
- **Source-of-truth reference:** `net/http` package docs: "On error, any Response can be ignored. A non-nil Response with a non-nil error only occurs when CheckRedirect failed, and even then the returned Response.Body is already closed." In practice, defensive code is widely recommended (see also `errcheck`/`bodyclose` linters).
- **Proposed fix:**
  ```go
  resp, err := httpClient.Do(req)
  if err != nil {
      if resp != nil {
          _ = resp.Body.Close()
      }
      return fmt.Errorf("warehouse request: %w", err)
  }
  defer resp.Body.Close()
  ```

#### H3. Response body is never drained before close, defeating HTTP keep-alive
- **Citation:** `services/orders/sync.go:98-102`.
- **Problem:** On the non-200 path (line 100), the function returns without reading the body. Go's HTTP transport only returns a connection to the keep-alive pool if the body is fully read and closed. `defer resp.Body.Close()` alone closes the connection rather than reusing it.
- **Why it matters:** Under steady non-2xx traffic (e.g., warehouse rejects malformed orders with 4xx), every request opens a new TCP connection, which causes connection churn, latency spikes, and possible ephemeral-port exhaustion against `warehouse.example.com`.
- **Source-of-truth reference:** `net/http` Client documentation on connection reuse: the body must be read to EOF and closed for the connection to be reused.
- **Proposed fix:** Before returning on the non-200 path, do `_, _ = io.Copy(io.Discard, resp.Body)` (with a sane size limit via `io.LimitReader`) and surface the body snippet in the error message for diagnostics.

#### H4. Status code check accepts only HTTP 200, rejecting other valid 2xx responses
- **Citation:** `services/orders/sync.go:100`.
- **Problem:** `if resp.StatusCode != 200` rejects 201, 202, 204, etc., which the warehouse may legitimately return (especially 201 Created or 202 Accepted for write endpoints).
- **Why it matters:** A perfectly successful sync that returns 201 will be treated as a failure, the order will not be marked `synced`, and (combined with H1) the row will be left in an unrecoverable `pending` state. The design says "On 200" literally — this is a borderline interpretation issue, but production systems virtually always treat the entire 2xx range as success. At minimum, this deserves an explicit clarification in code.
- **Source-of-truth reference:** RFC 9110 §15.3 (2xx semantics); design line 32.
- **Proposed fix:** `if resp.StatusCode < 200 || resp.StatusCode >= 300` and document the intent. If the design strictly means "200 only", add a comment and a test that asserts 201 is rejected.

### Medium

#### M1. `time.Now()` is captured per-statement and is not injectable, making timestamps untestable and inconsistent
- **Citation:** `services/orders/sync.go:75, 106`.
- **Problem:** Two separate `time.Now()` calls produce timestamps that are not derivable in tests and that drift between the "started" and "completed" markers (the started time also drifts vs. when the function was actually invoked, since it is taken after `BeginTx` returns). There is no `clock`/`now func() time.Time` injection.
- **Why it matters:** Tests that assert on timestamps cannot pass deterministically; auditing windows ("how long did the sync take?") will include connection-acquisition latency.
- **Source-of-truth reference:** Design line 37 requires unit tests across multiple paths; deterministic timestamps are part of standard testability.
- **Proposed fix:** Accept a `clock` (or `now func() time.Time`) parameter or struct field; capture `start := now()` once at the top.

#### M2. Context cancellation is honored only opportunistically and is undermined by the leaked transaction
- **Citation:** `services/orders/sync.go:62-113`.
- **Problem:** The function passes `ctx` to `BeginTx`, `ExecContext`, and `NewRequestWithContext`, which is good, but on cancellation the leaked transaction (C1) is never explicitly rolled back, so the connection-cleanup behavior depends entirely on the driver's reaction to a cancelled context. Some drivers (e.g., `pgx` stdlib wrapper, older `lib/pq`) handle this differently, and the connection may remain in a "broken" state until the keep-alive sweeper notices.
- **Why it matters:** Design line 36 ("Honors context cancellation") is technically partially met, but cancellation can still produce the same leak as in C1.
- **Source-of-truth reference:** Design line 36.
- **Proposed fix:** Same as C1 — `defer tx.Rollback()` ensures cancellation paths also clean up.

#### M3. No request timeout independent of context; relies on caller-supplied `httpClient` and `ctx`
- **Citation:** `services/orders/sync.go:65, 86-94`.
- **Problem:** The HTTP call is bounded only by `ctx` and whatever timeout the injected `httpClient` happens to have. If the caller passes `context.Background()` and an `http.Client{}` with zero timeout (Go's default), a hung warehouse will hold the transaction open indefinitely (compounded with C1).
- **Why it matters:** Production failure mode where the warehouse is slow but not dead — the worst kind of incident.
- **Source-of-truth reference:** Implied by design line 36 (cancellation) and general Go HTTP best practice.
- **Proposed fix:** Wrap the HTTP call in a derived context with an explicit timeout: `reqCtx, cancel := context.WithTimeout(ctx, syncTimeout); defer cancel()`. Document the assumption about `httpClient` configuration.

#### M4. `order.ID` is interpolated unsanitized into log/error messages and used as the only identity key without validation
- **Citation:** `services/orders/sync.go:73-77, 104-109`.
- **Problem:** `order.ID` is passed as a parameterized SQL bind, which is safe, but no validation is done. An empty `order.ID` will silently update zero rows; the function will not detect that no row was updated and will still proceed to POST and commit.
- **Why it matters:** A bad input (empty/unknown order ID) silently no-ops the DB writes while still calling the warehouse and committing — silent data inconsistency.
- **Source-of-truth reference:** Design line 31 ("Marks the order ...") implies the order must exist.
- **Proposed fix:** Inspect `Result.RowsAffected()` from each `ExecContext` and return an error if zero rows were affected. Validate `order.ID != ""` at the entry point.

#### M5. Test coverage list does not include the most important failure mode this code suffers from
- **Citation:** Design line 37-38.
- **Problem:** The five mandated tests (happy path, http failure, db begin failure, marshal failure, warehouse non-200) do not include a test that asserts the row is left in a retryable state after each failure mode, nor a test that asserts the transaction is rolled back / connection is returned to the pool. This is precisely why C1, H1, H2 went undetected.
- **Why it matters:** The acceptance criteria on line 33-34 ("not stuck in 'pending' forever") cannot be verified by any of the listed tests as written. The tests will pass while the production behavior is broken.
- **Source-of-truth reference:** Design lines 33-34, 37-38.
- **Proposed fix:** Add tests that:
  - After each failure path, query the row and assert `sync_status` is a retryable value.
  - After each failure path, assert `db.Stats().InUse == 0` (or equivalent) to catch connection leaks.
  - Use `httptest.Server` plus a slow handler with a short context to exercise cancellation.

#### M6. `json.Marshal(order)` cannot fail for the declared `Order` struct, but error path still leaks the transaction
- **Citation:** `services/orders/sync.go:81-84`.
- **Problem:** `Order` only contains `string` and `float64` fields, none of which can produce a marshal error in practice. The "marshal failure" test required by the design (line 38) is therefore impossible to write without modifying the type. More importantly, even if it could fail, this branch also leaks the transaction (C1).
- **Why it matters:** Either the test is dead/synthetic, or the type will need to grow a field that can fail to marshal. Either way, the design's test list does not align with the implementation.
- **Source-of-truth reference:** Design line 38 ("marshal failure") and `encoding/json` documentation on which types can fail to marshal (channels, funcs, complex, cyclic structures).
- **Proposed fix:** Either drop the marshal-failure test from the design, or accept a `json.Marshaler` / change the type so failure is reachable, and ensure the path rolls back the transaction.

### Low

#### L1. URL is hardcoded
- **Citation:** `services/orders/sync.go:87`.
- **Problem:** `https://warehouse.example.com/orders` is hardcoded inside the function. This prevents per-environment configuration and makes the test for "happy path" require either monkey-patching or running against the literal URL.
- **Why it matters:** Couples the function to one environment; tests will need an indirection (e.g., `httptest.Server`) which then cannot be wired without a parameter.
- **Proposed fix:** Accept the base URL (or full endpoint) as a parameter or via a config struct.

#### L2. Error wrapping is inconsistent and loses HTTP body context
- **Citation:** `services/orders/sync.go:101`.
- **Problem:** `fmt.Errorf("warehouse returned %d", resp.StatusCode)` does not include any body content or correlation info, making production debugging hard.
- **Proposed fix:** Read a bounded prefix of the body and include it; consider a typed error so callers can branch on warehouse failure vs. local failure.

#### L3. Magic strings for status values
- **Citation:** `services/orders/sync.go:75, 106`.
- **Problem:** `"pending"` and `"synced"` appear as string literals; a typo will silently break downstream consumers.
- **Proposed fix:** Define constants (`syncStatusPending`, `syncStatusSynced`, `syncStatusFailed`) at package scope.

#### L4. `Content-Length` / `Accept` headers not set
- **Citation:** `services/orders/sync.go:92`.
- **Problem:** Only `Content-Type` is set. Some warehouse APIs and intermediaries care about `Accept` and authentication headers; none are present here.
- **Proposed fix:** Set `Accept: application/json`. If the warehouse requires auth, accept credentials via the function signature or a configured client.

#### L5. `float64` for `Total` is a poor choice for monetary values
- **Citation:** `services/orders/sync.go:58`.
- **Problem:** `Total float64` exposes the order amount to floating-point rounding, which the warehouse may then reject or persist incorrectly.
- **Proposed fix:** Use a fixed-point or decimal type (e.g., `*big.Rat`, `decimal.Decimal`, or a string like `"12.34"`). Out of scope for this diff but worth flagging.
