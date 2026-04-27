**Review Scope:** `services/orders/sync.go` — new `SyncOrderToWarehouse` function implementing order-to-warehouse sync with transactional DB writes and HTTP delivery.

**Process Used:** Static review against the stated design/acceptance criteria; manual trace of control flow for resource lifecycle, transaction state, and error-path correctness; cross-check that test coverage claims map to observable behavior in the code.

**Execution Context:** Single-file Go service module. External dependencies: `database/sql` (Postgres-style placeholders), `net/http`, `encoding/json`. Caller supplies `*sql.DB` and `*http.Client`; function is invoked per order.

**Integration Target:** `services/orders` package, presumably called from a sync worker/queue consumer or scheduler. Postgres backend implied by `$1/$2/$3` placeholders.

**Governing Documents:** Design / Acceptance criteria embedded in the request (transactional writes, retry-safe failure states, context honoring, 5 named unit tests).

**Reviewer:** Claude (Opus 4.7, 1M context).

**Severity Scale:** Critical (data corruption, RCE, privesc) / High (significant security risk, resource leak under common load, silent data inconsistency, design requirement violated) / Medium (incorrect behavior on some inputs, unclear error handling, missing implied validation) / Low (style, naming, nits).

**Date:** 2026-04-26.

## Findings

### Critical

**1. Transaction is never rolled back on any error path — connection leak and stuck `pending` state.**
- File:line: `services/orders/sync.go:52-97` (every `return` between line 54 and line 94 except the final `tx.Commit()`).
- Problem: `db.BeginTx` acquires a connection and opens a transaction, but the function never calls `tx.Rollback()`. There is no `defer tx.Rollback()` after `BeginTx` succeeds. Every error return after line 55 (mark-pending failure, marshal failure, request build failure, HTTP failure, non-200 response, mark-synced failure) abandons the transaction without releasing it. The `database/sql` connection pool will hold the connection open until the server-side transaction times out (or forever, depending on driver/DB config), and pool exhaustion follows under any sustained failure.
- Why it matters: This is a textbook connection/transaction leak. Under any non-trivial error rate (warehouse 5xx, network blip, context cancellation) the pool will exhaust within minutes of normal traffic, taking the whole service down. It also means the `UPDATE orders SET sync_status='pending'` written at line 57 is never committed *and* never rolled back from the application's perspective — but more importantly, when the warehouse call succeeds and the *second* UPDATE is then committed, the first UPDATE only became visible at commit time, so the "stuck in pending" requirement is also violated by accident in the success path (see finding 2 for the inverse problem).
- Source-of-truth reference: Acceptance criterion "All DB writes happen in a single transaction" combined with "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)." The Go `database/sql` documentation explicitly states transactions must be terminated by `Commit` or `Rollback`; idiomatic pattern is `defer tx.Rollback()` immediately after `BeginTx`, where `Rollback` after `Commit` is a documented no-op.
- Proposed fix: Immediately after a successful `BeginTx`, add `defer func() { _ = tx.Rollback() }()`. This makes every error path safe and is a no-op after a successful `Commit`.

**2. "Not stuck in pending forever" requirement is structurally unsatisfiable with the current transaction shape.**
- File:line: `services/orders/sync.go:57-60` (mark-pending UPDATE) and `services/orders/sync.go:88-96` (mark-synced UPDATE + Commit).
- Problem: Both the `pending` write and the `synced` write happen inside the same transaction. On the success path, both UPDATEs are flushed atomically at `tx.Commit()` — meaning the row jumps directly from its prior state to `synced`, and `sync_started_at` is set in the same instant as `sync_completed_at`. On any failure path (with the rollback fix from finding 1 applied), the `pending` write is rolled back, so the row never enters `pending` at all. In neither branch does the database ever observably hold `sync_status='pending'`. This means: (a) the "lets a retry succeed" criterion is satisfied only because the marker is never persisted, not because the design works; (b) any external observer (dashboard, retry worker, deduper) that relies on `sync_status='pending'` to detect "in flight" requests will never see one; (c) the `sync_started_at` timestamp written at line 59 is meaningless because it is committed simultaneously with `sync_completed_at`.
- Why it matters: The acceptance criteria conflate two incompatible designs. A "pending" marker is only useful if it is committed *before* the external HTTP call (so a crash/retry sees it); but committing it before the HTTP call means it is no longer in the same transaction as the `synced` write. As written, the function silently violates the spirit of both the "pending marker" and the "single transaction" requirements.
- Source-of-truth reference: Acceptance criteria lines 14-19 of the request package.
- Proposed fix: Decide which property matters. Two viable shapes: (a) Two transactions: commit the `pending` UPDATE before the HTTP call, then in a second transaction write `synced`; on failure of the HTTP call, run a separate UPDATE to revert/clear `sync_status` so retry is unambiguous. (b) Drop the `pending` marker from this function and rely on a status of `null`/`queued` set by the enqueuer; the single transaction then only contains the `synced` write after the HTTP call returns 200. Either way, raise this back to the design owner before implementing — the current spec is internally inconsistent.

### High

**3. HTTP response body is not fully drained before close, leaking keep-alive connections.**
- File:line: `services/orders/sync.go:78-86`.
- Problem: `defer resp.Body.Close()` is correct, but for `http.Client` connection reuse the body must also be *fully read* before close. On the non-200 branch (line 84-86) the body is closed without being read. Go's `net/http` will not return the underlying TCP connection to the keep-alive pool unless the body is drained, so each non-200 response from the warehouse silently burns a connection.
- Why it matters: Under sustained warehouse error rates (5xx during incidents, 429 during throttling), the HTTP client's connection pool fills with half-read connections and new requests start paying full TCP+TLS handshake cost — exactly when the system is already under stress.
- Source-of-truth reference: `net/http` package documentation: "The client must close the response body when finished with it… If the Body is not both read to EOF and closed, the Client's underlying RoundTripper… may not be able to re-use a persistent TCP connection."
- Proposed fix: Before returning on the non-200 branch, drain the body: `_, _ = io.Copy(io.Discard, resp.Body)`. Better: read a bounded prefix into an error message so failures are debuggable (`body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))`).

**4. Context cancellation is not honored between DB write and HTTP send (and the `pending` UPDATE will be committed even if the context is already cancelled at HTTP time, once finding 1 is fixed in the wrong direction).**
- File:line: `services/orders/sync.go:57-78`.
- Problem: The function does pass `ctx` to `BeginTx`, `ExecContext`, and `NewRequestWithContext`, which is correct as far as it goes. But there is no explicit `ctx.Err()` check between operations, and — more importantly — the order of operations means a cancellation that arrives between the mark-pending write and the HTTP request still results in a partial side effect (the warehouse may receive a duplicate POST on retry while the DB never recorded `pending` because of the rollback).
- Why it matters: The acceptance criterion "Honors context cancellation" is satisfied at the call-site level but not at the semantic level — there is no point in the function where cancellation cleanly aborts without risking a duplicate warehouse POST on the next retry attempt.
- Source-of-truth reference: Acceptance criterion "Honors context cancellation" (line 20 of the request).
- Proposed fix: Add an explicit `if err := ctx.Err(); err != nil { return err }` immediately before `httpClient.Do(req)`. Combine with finding 2's redesign (commit the `pending` marker first) so that an interrupted sync is recoverable by a retry worker that scans for stale `pending` rows.

**5. `time.Now()` is called at two different instants but written as if they are paired.**
- File:line: `services/orders/sync.go:59` and `services/orders/sync.go:90`.
- Problem: `sync_started_at` and `sync_completed_at` are both `time.Now()` evaluated at separate moments, but because both UPDATEs are committed atomically (finding 2), the database sees them committed simultaneously while their *values* differ by however long the HTTP call took. That is actually the correct intent for these columns — but the code path also uses `time.Now()` directly, making the function non-deterministic and untestable without a clock injection.
- Why it matters: The "5 unit tests" criterion includes a happy-path test, which presumably asserts on the column values. Without a clock abstraction, that assertion is either flaky or omitted, and the test can only verify that *some* timestamp was written, not that the right one was.
- Source-of-truth reference: Acceptance criterion line 22 ("5 unit tests cover happy path…").
- Proposed fix: Inject a `clock func() time.Time` (or accept a `Clock` interface) and call `clock()` instead of `time.Now()`. Default to `time.Now` at the construction site.

### Medium

**6. Any 2xx status other than 200 is treated as failure.**
- File:line: `services/orders/sync.go:84`.
- Problem: `resp.StatusCode != 200` rejects 201 Created, 202 Accepted, 204 No Content, etc. The warehouse spec is not visible, but most REST POSTs that create or enqueue resources return 201 or 202, not 200.
- Why it matters: Either the warehouse never returns anything other than 200 (in which case the check is fine but brittle to API changes), or it sometimes returns 202 (in which case every async-accepted order is treated as a failure and the transaction is leaked per finding 1).
- Source-of-truth reference: Acceptance criterion line 16 ("On 200, marks the order …") — the criterion is written narrowly, but the implementation should match the actual warehouse contract.
- Proposed fix: Use `resp.StatusCode >= 200 && resp.StatusCode < 300`, or — preferably — confirm the warehouse contract with the API owner and pin the exact accepted codes with a comment citing the source.

**7. URL is hard-coded; no environment, retry, or timeout configuration.**
- File:line: `services/orders/sync.go:71`.
- Problem: `https://warehouse.example.com/orders` is a string literal in production code. There is no way to point this at a staging environment, a mock, or a different region without recompiling. The supplied `httpClient` carries timeout/retry configuration, which is good, but the URL itself is not injected.
- Why it matters: Test fixture for the "warehouse non-200" and "http failure" cases must either use an `httptest.Server` and somehow override the URL (which is impossible as written), or the tests are stubbing at a lower level than the function exposes — meaning the claimed test coverage cannot exist as written.
- Source-of-truth reference: Acceptance criterion line 22 (specifically "warehouse non-200" test).
- Proposed fix: Accept the warehouse URL as a parameter (or as a field on a `Syncer` struct that holds the URL, client, and clock). This also makes the function unit-testable with `httptest.NewServer`.

**8. Error from the `pending` UPDATE swallows row-not-found.**
- File:line: `services/orders/sync.go:57-63`.
- Problem: `tx.ExecContext` returns no error if the UPDATE matches zero rows. If `order.ID` does not exist in the `orders` table (race with deletion, bug in caller, wrong shard), the function proceeds to POST to the warehouse anyway, marking a phantom order as synced.
- Why it matters: Silent data inconsistency — the warehouse receives an order the DB no longer recognizes, and on the success path the second UPDATE also matches zero rows and the function returns nil.
- Source-of-truth reference: Implied by the design's mention of `sync_status` columns on a real `orders` row.
- Proposed fix: Check `result.RowsAffected()` after each UPDATE; if zero, return a typed error (e.g., `ErrOrderNotFound`) and abort before the HTTP call.

**9. No request timeout independent of the caller-supplied client.**
- File:line: `services/orders/sync.go:78`.
- Problem: The function relies entirely on the caller to configure `httpClient.Timeout` (or to use a context with deadline). If neither is set, `httpClient.Do(req)` can block indefinitely while holding an open transaction — compounding finding 1.
- Why it matters: Defensive robustness. Even if every current caller does the right thing, the function's contract should not require it.
- Source-of-truth reference: Best practice for `net/http` clients in long-lived services.
- Proposed fix: Document the requirement on the function's godoc, or wrap the inbound `ctx` with `context.WithTimeout(ctx, defaultSyncTimeout)` before the HTTP call.

### Low

**10. `Order` struct is defined in the same file as the function and exposes only three fields.**
- File:line: `services/orders/sync.go:40-44`.
- Problem: The struct probably should live in a `types.go` or `model.go` next to other domain types in the `orders` package; defining it inline next to the sync function suggests this file owns the type, which it almost certainly does not in a real codebase.
- Why it matters: Code organization; minor.
- Proposed fix: Move `Order` to the canonical model file for the package.

**11. Error wrapping uses `%w` consistently — good — but error messages are lowercase and unprefixed.**
- File:line: `services/orders/sync.go:54, 62, 67, 74, 80, 85, 93`.
- Problem: Messages like `"begin tx: %w"` are fine per Go convention (lowercase, no trailing punctuation), but they lack any package/function context. When these surface in logs they will be ambiguous (e.g., "begin tx" could come from any service).
- Why it matters: Operational debuggability.
- Proposed fix: Prefix with the operation name, e.g., `"sync order to warehouse: begin tx: %w"`, or rely on a structured logger at the caller.

**12. `json.Marshal` of `Order` cannot fail in practice.**
- File:line: `services/orders/sync.go:65-68`.
- Problem: `Order` has only `string`, `float64`, and `string` fields, none of which can fail to marshal. The "marshal failure" test from the acceptance criteria is therefore impossible to write against this struct without injecting a fault — the test either does not exist or tests a different code path.
- Why it matters: The claimed test coverage ("marshal failure") cannot be exercised. Either the test is fake (asserting on an unreachable error branch) or the implementer misread the criterion.
- Source-of-truth reference: Acceptance criterion line 22.
- Proposed fix: Either drop the marshal-failure test and document that the branch is defensive, or change the contract to accept a `json.Marshaler` so a fault-injecting fake can be passed in tests. Flag back to the design owner.

**13. `Status` field on `Order` is sent to the warehouse but never read or written by this function.**
- File:line: `services/orders/sync.go:43`.
- Problem: The struct includes `Status string`, which is serialized into the POST body, but the function only operates on `sync_status` columns. It's unclear whether `Status` reflects the order's lifecycle state, the previous sync state, or something else.
- Why it matters: Naming ambiguity adjacent to `sync_status` invites bugs.
- Proposed fix: Document the field's meaning, or rename for clarity (e.g., `OrderStatus`, `FulfillmentState`).
