- **Review Scope:** `services/orders/sync.go` — newly added `SyncOrderToWarehouse` function and the supporting `Order` type. Acceptance criteria from the design block (transactional behavior, retry safety, context handling, test matrix).
- **Process Used:** Cold static review of the single supplied diff against the acceptance criteria. Re-derived correctness claims from the code; did not execute any build, vet, race, or test gate. No tests were supplied in the package, so the "5 unit tests" requirement is treated as unsubstantiated.
- **Execution Context:** Read-only review of the contents of `packages/redacted.md`. No surrounding repository, no `go.mod`, no test files, no CI logs were available or consulted.
- **Integration Target:** `services/orders` Go package consuming `database/sql` against an `orders` table with columns `sync_status`, `sync_started_at`, `sync_completed_at`, `id`. External dependency: `https://warehouse.example.com/orders` over HTTP.
- **Governing Documents:** The "Design / Acceptance criteria" section embedded in the package (lines 25-38), in particular the requirements: single transaction for all DB writes, retry-safe failure state, context cancellation honored, and the five named unit tests.
- **Reviewer:** Cross-vendor second-pass reviewer (Claude, Opus 4.7, 1M context).
- **Severity Scale:** Critical = production data corruption / RCE / privilege escalation. High = significant security risk, resource leak under common load, silent data inconsistency, or design-requirement violation. Medium = incorrect behavior on some inputs, unclear error handling, perf degradation, missing implied validation. Low = style, naming, nits.
- **Date:** 2026-04-26.

## Findings

### Critical

#### C1. Transaction is never rolled back on any error path — connection / lock leak and indefinite "pending" rows
- **Citation:** `services/orders/sync.go:68-112` (every `return fmt.Errorf(...)` between `BeginTx` and `tx.Commit()`).
- **Problem:** `tx, err := db.BeginTx(ctx, nil)` opens a transaction, but there is no `defer tx.Rollback()` and no explicit `tx.Rollback()` on any of the seven intermediate error returns (mark-pending exec failure, marshal failure, request build failure, `httpClient.Do` failure, non-200 response, mark-synced exec failure). When any of these returns fires, the `*sql.Tx` is dropped on the floor with its underlying connection still checked out from the pool and any row locks acquired by the `UPDATE ... WHERE id = $3` still held until the database eventually times the session out (in Postgres that can be effectively forever absent `idle_in_transaction_session_timeout`).
- **Why it matters:** Under any sustained warehouse outage or marshal/HTTP/DB hiccup, the pool drains one connection per call and the affected order row stays write-locked. New invocations for the same order block on the lock; new invocations for *any* order eventually block on `BeginTx` once `MaxOpenConns` is exhausted. This is the classic Go `database/sql` transaction leak — production-impacting resource exhaustion and silent data inconsistency at the same time.
- **Source-of-truth reference:** Design line 35 — "All DB writes happen in a single transaction" — implies the transaction must also be *terminated* on every path. Go stdlib contract: `database/sql.(*Tx)` requires exactly one of `Commit` or `Rollback`; otherwise the connection is not returned to the pool (see `database/sql` package docs and the canonical `defer tx.Rollback()` idiom; `Rollback` after `Commit` is a documented no-op).
- **Proposed fix:** Immediately after a successful `BeginTx`, add `defer func() { _ = tx.Rollback() }()` (or capture the named return error and log a non-`ErrTxDone` rollback failure). All current `return ...` sites then become safe; `tx.Commit()` at the end short-circuits the deferred rollback.

#### C2. The HTTP call happens *inside* the open transaction — long-lived row locks and likely pool exhaustion
- **Citation:** `services/orders/sync.go:73-102` (UPDATE → marshal → `httpClient.Do` → status check, all between `BeginTx` and `Commit`).
- **Problem:** The `UPDATE orders SET sync_status='pending' ...` runs first, holding a row-level write lock on the order. The function then performs a synchronous outbound HTTP POST to `warehouse.example.com` *while still inside the transaction*. The DB connection is pinned for the full network round-trip (and any retry/timeout the HTTP client imposes — the function does not constrain `httpClient.Timeout`).
- **Why it matters:** Even on the happy path this serializes throughput on warehouse latency and pins one pool connection per in-flight sync. On the failure path (combined with C1) the lock is held essentially forever. This is data-corruption-adjacent: any concurrent reader/writer of that order row is blocked, and any other code path that opens a transaction can be starved of pool connections.
- **Source-of-truth reference:** Design line 34 — "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)" — implicitly forbids holding locks across slow external I/O. Standard Go/SQL guidance: do not perform network calls or unbounded waits inside an open `*sql.Tx`.
- **Proposed fix:** Restructure as two short transactions: (1) mark pending and commit; (2) perform the HTTP call outside any transaction; (3) open a second short transaction to mark `synced` (or reset to a retry-safe state) and commit. Alternatively, perform the HTTP call first (idempotency-keyed) and then a single transaction to record the result. Either way, no DB transaction may wrap the HTTP call.

### High

#### H1. Retry-safety requirement is violated: `pending` is the *only* terminal state on every failure path
- **Citation:** `services/orders/sync.go:73-110` (the mark-pending UPDATE and every subsequent error return).
- **Problem:** Because the transaction is leaked rather than rolled back (C1), the `pending` write is *not* undone on failure — the connection is dropped with the transaction uncommitted, so in most engines (Postgres, MySQL/InnoDB) the engine will eventually roll it back, but the application can give no guarantees about *when*. Even granting an eventual rollback, there is no code path that intentionally writes a retry-friendly status (`failed`, `retryable`, `null`, etc.) before returning. After `BeginTx` succeeds and the function returns an error, the caller has no reliable way to know whether the order is "still pending and will be retried" or "rolled back and clean for retry".
- **Why it matters:** The acceptance criterion explicitly says the order must not be "stuck in 'pending' forever". The current shape can leave it stuck (if the DB engine keeps the transaction open due to the leaked connection), and even after rollback, the status is silently the *previous* status, which a retry worker has no way to detect as "needs sync". This is a direct, silent design violation.
- **Source-of-truth reference:** Design line 33-34 — "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)."
- **Proposed fix:** After fixing C1/C2, either (a) commit the `pending` write first and, on failure, run a second statement that sets `sync_status` to a retry-eligible value (e.g. `'failed'` with `sync_started_at` cleared or a `last_attempt_at` set) so a retry worker can find it, or (b) do not write `pending` at all until the warehouse confirms — and keep an `attempts` counter the worker can drive off of. Either way, document and test the post-failure status explicitly.

#### H2. Missing `tx.Rollback()` on `tx.Commit()` failure (named-return + idempotent rollback discipline)
- **Citation:** `services/orders/sync.go:112` (`return tx.Commit()`).
- **Problem:** If `tx.Commit()` returns an error (e.g. serialization failure, network drop to DB at commit time), the function returns the error directly without any cleanup. While `Commit` failure normally releases the connection, code review hygiene and the Go stdlib idiom both expect a `defer tx.Rollback()` so the failure mode is uniformly handled. Without it, if the project later adds a `defer` on a derived resource or an `errors.Join`, the contract is fragile.
- **Why it matters:** Combined with C1 this is part of the same leak class; even after C1 is fixed, returning the raw `Commit` error without wrapping makes diagnosing commit-time failures (which look identical to begin-time failures in logs) substantially harder.
- **Source-of-truth reference:** Design line 35 (single transaction) plus standard `database/sql` usage — `Rollback` after a successful `Commit` is a no-op (`sql.ErrTxDone`), so the canonical pattern is always safe.
- **Proposed fix:** `if err := tx.Commit(); err != nil { return fmt.Errorf("commit: %w", err) }` and rely on the deferred rollback (added per C1) to clean up on the failure branch.

#### H3. HTTP response body not drained before close — connection-reuse / keep-alive degradation
- **Citation:** `services/orders/sync.go:98` (`defer resp.Body.Close()`) combined with `services/orders/sync.go:100-102` (early return on non-200 without reading the body).
- **Problem:** Go's `net/http` documentation is explicit: to allow the underlying TCP connection to be reused by the keep-alive pool, the caller must read the response body to EOF *and* close it. On non-200 responses (and on the happy path too — the body is never read) the body is closed without being drained. For small bodies the runtime can sometimes drain implicitly, but for larger error payloads this silently disables keep-alive for that connection.
- **Why it matters:** Under sustained warehouse 4xx/5xx (exactly the failure mode that retries amplify), every call costs a fresh TLS handshake. That is a real perf and capacity regression that will not show up in unit tests.
- **Source-of-truth reference:** Standard `net/http` package docs: "The client must close the response body when finished with it … If the Body is not both read to completion and closed, the Client's underlying RoundTripper (typically Transport) may not be able to re-use a persistent TCP connection for a subsequent 'keep-alive' request."
- **Proposed fix:** Before the `defer resp.Body.Close()` returns control, drain with `io.Copy(io.Discard, resp.Body)` (or read at least up to a small cap to capture the error message for logging). Idiom: `defer func() { io.Copy(io.Discard, resp.Body); resp.Body.Close() }()`.

#### H4. No HTTP timeout enforced; reliance on caller-supplied client and ctx alone
- **Citation:** `services/orders/sync.go:62-67` (signature accepts `*http.Client` with no precondition) and `services/orders/sync.go:86-94` (request built with `ctx`, no per-attempt deadline).
- **Problem:** The function trusts the caller's `*http.Client` to set a `Timeout`. If the caller passes `&http.Client{}` or `http.DefaultClient`, there is no timeout — only the supplied `ctx` will cancel the call, and many callers pass `context.Background()`. Combined with C2, a hung warehouse means the DB transaction is held indefinitely.
- **Why it matters:** "Honors context cancellation" (design line 36) is satisfied, but only conditionally on the caller. The function is a library-style API and a hostile/lazy caller can wedge the order pipeline.
- **Source-of-truth reference:** Design line 36 ("Honors context cancellation") plus the "retry succeeds" requirement on line 34. Standard `net/http` guidance recommends always setting `Client.Timeout` for clients that talk to external services.
- **Proposed fix:** Either document the precondition loudly (godoc + a runtime nil-check) or, defensively, derive a bounded child context: `reqCtx, cancel := context.WithTimeout(ctx, 30*time.Second); defer cancel()` and use `reqCtx` for `NewRequestWithContext`.

#### H5. No nil-guards on `db` or `httpClient`; no validation of `order.ID`
- **Citation:** `services/orders/sync.go:62-76`.
- **Problem:** A nil `*sql.DB` panics on `BeginTx`, a nil `*http.Client` panics on `Do`, and an empty `order.ID` happily executes `UPDATE orders ... WHERE id = ''` which silently affects zero rows (or, worse, every row with an empty id). None of these are checked.
- **Why it matters:** Empty-ID is a silent data-correctness footgun: the function reports success (0 rows affected is not an error in `database/sql`), the warehouse gets a request for a malformed order, and the row count is never inspected. The two nil cases convert ordinary programmer errors into panics that take down the worker.
- **Source-of-truth reference:** Design line 38 — implies a `marshal failure` test exists, but does not exercise empty-ID; the broader design intent ("retry succeeds") cannot hold if the row was never updated.
- **Proposed fix:** Add explicit guards at the top of the function (`if db == nil || httpClient == nil || order.ID == "" { return fmt.Errorf(...) }`), and inspect `result.RowsAffected()` after each UPDATE to catch the "no such order" case.

#### H6. Acceptance criterion of 5 unit tests is unmet in the supplied diff
- **Citation:** Package "Files changed" section — only `services/orders/sync.go` is included; no `*_test.go` files are present (`services/orders/sync.go:43-113` is the entirety of the change).
- **Problem:** The design requires "5 unit tests cover happy path, http failure, db begin failure, marshal failure, and warehouse non-200." None of those tests are in the diff. The reviewer cannot assume they exist elsewhere because the package was supplied as the complete change set.
- **Why it matters:** Three of the five mandated tests (db begin failure, marshal failure, warehouse non-200) are precisely the paths where the leaks in C1, C2, and H1 manifest. Without them, the implementer's own self-review cannot have caught these. Additionally, "marshal failure" is essentially untriggerable for the current `Order` struct — `id`, `total`, `status` are all trivially marshalable types — so the test as specified is either a no-op or requires a refactor (e.g. injecting a marshal function) that the diff does not provide.
- **Source-of-truth reference:** Design line 37-38.
- **Proposed fix:** Add `services/orders/sync_test.go` with a `sqlmock`-based DB and an `httptest.Server`-based warehouse, covering all five paths plus an explicit "transaction is rolled back on warehouse failure" assertion. For the "marshal failure" case, refactor to inject the marshaler (or assert via a custom type whose `MarshalJSON` returns an error) so the test is meaningful.

### Medium

#### M1. `time.Now()` baked into UPDATE statements — non-deterministic and untestable
- **Citation:** `services/orders/sync.go:75` and `services/orders/sync.go:106`.
- **Problem:** `time.Now()` is called inline. There is no clock injection, so tests cannot assert on exact timestamp values, and the two timestamps recorded for a single sync are taken at different wall-clock instants (so `sync_completed_at - sync_started_at` is HTTP latency rather than "transaction duration", which is fine, but it should be intentional).
- **Why it matters:** Combined with H6, the missing tests cannot pin behavior. Also, in environments where the DB and the app clocks drift, mixing application `time.Now()` with DB-side timestamps is a known footgun; consider `NOW()` / `CURRENT_TIMESTAMP` server-side.
- **Source-of-truth reference:** General Go testing best practice (clock injection); design implicitly requires testability via the 5 mandated tests.
- **Proposed fix:** Either accept a `clock func() time.Time` parameter (or struct field) or push timestamping into SQL with `NOW()` and read back via `RETURNING` if needed.

#### M2. Error-wrapping is inconsistent — some failure modes are unrecoverable for callers
- **Citation:** `services/orders/sync.go:69-101`.
- **Problem:** Every error is wrapped with `fmt.Errorf("...: %w", err)`, which is good, *but* the warehouse non-200 case at line 100-102 returns `fmt.Errorf("warehouse returned %d", resp.StatusCode)` with no sentinel and no wrapped error — callers cannot distinguish "warehouse rejected (4xx, do not retry)" from "warehouse failed (5xx, retry)" without string-parsing.
- **Why it matters:** Retry workers and metrics need to bucket failures. The current shape forces them to scrape error strings.
- **Source-of-truth reference:** Design line 34 (retry-safety) — implicitly requires that the caller can decide *whether* to retry.
- **Proposed fix:** Define typed errors (`var ErrWarehouseClient = errors.New(...)`, `var ErrWarehouseServer = errors.New(...)`) and return them with `%w` wrapping plus the status code. Optionally include the response body snippet (after draining per H3).

#### M3. Status check uses `!= 200` instead of `>= 200 && < 300`
- **Citation:** `services/orders/sync.go:100`.
- **Problem:** A `201 Created` or `202 Accepted` from the warehouse — common REST conventions for `POST /orders` — would be treated as a failure, leaving the order in the pending-leak state described in C1/H1.
- **Why it matters:** Brittle coupling to a single status code is a frequent source of "works in tests, breaks against the real service".
- **Source-of-truth reference:** Design line 32 says "On 200, marks the order ... synced", which is the literal contract; however, it also says non-200 is a failure that must be retry-safe. Any 2xx response should plausibly be considered success unless the warehouse owner has explicitly stated otherwise. Flag for clarification.
- **Proposed fix:** Use `if resp.StatusCode < 200 || resp.StatusCode >= 300` and document the decision; or, if the warehouse contract really is "exactly 200", at least add a comment citing that contract.

#### M4. `Content-Type` set; `Accept` not set; no `User-Agent` / request ID
- **Citation:** `services/orders/sync.go:92`.
- **Problem:** No `Accept: application/json` header and no `User-Agent` / correlation header. This is style-adjacent but matters for observability and for warehouses that content-negotiate.
- **Why it matters:** Operational visibility on failure (H1, M2) is strictly worse without a correlation id flowing through.
- **Source-of-truth reference:** General HTTP client hygiene; design has no explicit requirement.
- **Proposed fix:** Set `Accept: application/json`, a meaningful `User-Agent`, and propagate a request-id from `ctx` if the codebase has one.

#### M5. `RowsAffected` never inspected — silent no-op when order id is missing
- **Citation:** `services/orders/sync.go:73-79` and `services/orders/sync.go:104-110`.
- **Problem:** `tx.ExecContext` returns a `Result` whose `RowsAffected()` would reveal "0 rows updated, you sync'd a non-existent order". The code discards the result with `_, err = ...`.
- **Why it matters:** A typo, an order that was deleted between enqueue and sync, or a misrouted message all silently look like success. Especially severe given H5 (no validation of `order.ID`).
- **Source-of-truth reference:** Implicit in design line 31 ("Marks the order ...") — if no row is marked, the precondition is unmet.
- **Proposed fix:** Capture the `Result`, check `RowsAffected()`, and return an error if it is `0` (after checking that the driver supports it; `pgx`/`lib/pq` do).

### Low

#### L1. Magic literals: URL and status strings are inlined
- **Citation:** `services/orders/sync.go:75`, `:87`, `:106`.
- **Problem:** `"https://warehouse.example.com/orders"`, `"pending"`, `"synced"`, and the column names appear as bare strings. Promote to package-level constants.
- **Why it matters:** Refactor friction and a small risk of typos in future status values (e.g. an `H1` fix introducing `"failed"`).
- **Source-of-truth reference:** Standard Go style.
- **Proposed fix:** `const (statusPending = "pending"; statusSynced = "synced"; warehouseURL = "https://warehouse.example.com/orders")` (or take URL as config).

#### L2. `Order.Total` as `float64` for money
- **Citation:** `services/orders/sync.go:56-60`.
- **Problem:** `float64` for monetary values is a well-known footgun (rounding, JSON precision loss across systems).
- **Why it matters:** Outside the strict scope of this review, but the warehouse round-trip is exactly the place such bugs surface.
- **Source-of-truth reference:** General financial-software guidance; no design requirement.
- **Proposed fix:** Use a fixed-point or string-encoded decimal type; at minimum add a TODO and a unit test pinning the JSON shape.

#### L3. `POST` string literal instead of `http.MethodPost`
- **Citation:** `services/orders/sync.go:87`.
- **Problem:** Use `http.MethodPost` for vet-friendliness and grep-ability.
- **Why it matters:** Pure style.
- **Source-of-truth reference:** Standard Go style; `go vet` / `staticcheck` lint.
- **Proposed fix:** Replace `"POST"` with `http.MethodPost`.

#### L4. Hard-coded status code `200` instead of `http.StatusOK`
- **Citation:** `services/orders/sync.go:100-101`.
- **Problem:** Same as L3; readability and lint.
- **Source-of-truth reference:** Standard Go style.
- **Proposed fix:** `http.StatusOK` (and see M3 for the broader fix).

#### L5. Function does too much; consider splitting for testability
- **Citation:** `services/orders/sync.go:62-113`.
- **Problem:** Marshal, HTTP, and DB are all entangled in one function, which is part of why H6's "marshal failure" test is hard to write meaningfully.
- **Why it matters:** Smaller, injectable helpers (`postOrder(ctx, client, order) error`, `markPending(ctx, tx, id) error`, `markSynced(ctx, tx, id) error`) make every required test trivial.
- **Source-of-truth reference:** General Go/SOLID guidance; design implicitly via the 5 test buckets.
- **Proposed fix:** Extract three helpers and have `SyncOrderToWarehouse` orchestrate them.
