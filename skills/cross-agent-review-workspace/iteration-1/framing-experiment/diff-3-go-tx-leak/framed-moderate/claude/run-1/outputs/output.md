- **Review Scope:** `services/orders/sync.go` — new `SyncOrderToWarehouse` function (97 lines) that orchestrates a DB transaction around an HTTP POST to a warehouse endpoint.
- **Process Used:** Manual line-by-line inspection of the supplied diff against the stated acceptance criteria; no static analysis, no test execution, no repository-wide search.
- **Execution Context:** Closed-context single-pass review of the framed-moderate package only; no other files in the repository were consulted.
- **Integration Target:** Go service `services/orders` package, presumed to use `database/sql` against Postgres (positional `$N` placeholders) and a shared `*http.Client`.
- **Governing Documents:** The "Design / Acceptance criteria" block embedded in the package (atomic single-tx writes, retry-friendly failure state, context honored, 5 unit tests).
- **Reviewer:** Claude (Opus 4.7, 1M context), acting as cross-agent reviewer.
- **Severity Scale:** Critical (data corruption / RCE / privilege escalation) > High (resource leak under common load, silent inconsistency, design violation) > Medium (incorrect on some inputs, unclear errors, missing implied validation) > Low (style / nits).
- **Date:** 2026-04-26.

## Findings

### Critical

**F-C1 — Transaction is never rolled back on any error path; connection leaks and `pending` rows remain locked.**
- Citation: `services/orders/sync.go:52-96` (every `return fmt.Errorf(...)` between line 54 and line 93).
- Problem: `tx, err := db.BeginTx(...)` succeeds on line 52, but none of the seven subsequent error returns (lines 62, 67, 74, 80, 85, 93) call `tx.Rollback()`. There is no `defer tx.Rollback()` either. Every failure after `BeginTx` leaks the underlying `*sql.Tx` and its pooled connection.
- Why it matters: This is the headline bug. Under any non-happy path — marshal error, HTTP timeout, warehouse 500, second `ExecContext` error — the connection stays checked out from the pool until the driver eventually times it out (or never, depending on driver). On Postgres, the open transaction also holds a row-level lock on the `orders` row written at line 57, so subsequent retries (the very thing the design demands work) will block on that lock until the leaked tx is reaped. Repeated failures will exhaust `db.SetMaxOpenConns` and wedge the service. This is a textbook resource-leak-under-common-load and arguably data-availability corruption.
- Source-of-truth reference: Acceptance criterion *"On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)"* and *"All DB writes happen in a single transaction."* The Go `database/sql` contract (`*sql.Tx` docs) requires every `Begin` to be paired with exactly one of `Commit`/`Rollback`.
- Proposed fix: Add `defer func() { if err != nil { _ = tx.Rollback() } }()` immediately after the `BeginTx` check, and switch the function to a single named return `(err error)` so the deferred closure observes the final value. Critically, also reconsider F-H1 below — rollback alone does not satisfy the retry-friendliness criterion because the `pending` write will be undone, leaving `sync_status` unchanged but `sync_started_at` also reverted; that is acceptable for retry, but you must verify the schema's default state is itself retry-safe.

**F-C2 — The "pending" marker write is rolled back together with the success write, defeating the retry-state requirement.**
- Citation: `services/orders/sync.go:57-60` paired with `services/orders/sync.go:88-96`.
- Problem: Both the `pending` UPDATE and the `synced` UPDATE execute inside the same transaction. If the HTTP call fails, fixing F-C1 with a rollback will erase the `pending`/`sync_started_at` write, so observers can never tell whether a sync was attempted. Worse, if the HTTP POST *succeeds at the warehouse* but the response is lost (network blip after the warehouse persisted the order) or the second `ExecContext` (line 88) fails, the rollback hides the fact that the warehouse already accepted the order — the next retry will re-POST and produce a duplicate order at the warehouse.
- Why it matters: This is silent cross-system data inconsistency. The design says retries must succeed; it does not say retries are safe against double-submit. Without an idempotency key on the warehouse request and a separate "in-flight" record that survives rollback, the system can either lose evidence of attempts (rollback) or commit a `pending` row that never resolves (no rollback) — pick your poison. The current code achieves the worst of both.
- Source-of-truth reference: Acceptance criterion *"left in a state that lets a retry succeed (not stuck in 'pending' forever)."* Implicit correctness norm: external side effects (HTTP POST) must not be wrapped in a DB transaction whose outcome they cannot influence (the "dual-write problem").
- Proposed fix: Restructure as two transactions plus an idempotency key. (1) Tx-1 writes `sync_status='pending'`, `sync_started_at=now()`, and a fresh `idempotency_key` UUID, then commits. (2) POST to the warehouse with `Idempotency-Key: <uuid>` header. (3) Tx-2 writes `sync_status='synced'` (or `'failed'`) and commits. Recovery becomes "find rows stuck in `pending` past a threshold and re-issue with the same key." This also resolves F-C1's leak surface and the duplicate-POST risk.

### High

**F-H1 — HTTP POST happens *inside* the open transaction, holding a row lock for the duration of an external call.**
- Citation: `services/orders/sync.go:78` (`httpClient.Do(req)`) executed between `BeginTx` (line 52) and `Commit` (line 96).
- Problem: The `UPDATE` on line 57 acquires a row-level write lock on the `orders` row. That lock is held across `httpClient.Do`, which can block for the full client timeout (often tens of seconds, or indefinite if no timeout is set on `httpClient`). Concurrent reads/writes to the same order — including dashboard SELECTs that join `orders` and any retry attempt — will block.
- Why it matters: Under common load (warehouse latency spike, partial outage) every in-flight sync pins an `orders` row and a DB connection. This compounds with F-C1 to produce cascading lock contention. Even with rollback fixed, holding row locks across network I/O is a well-known anti-pattern.
- Source-of-truth reference: Standard distributed-systems guidance; cf. *"never hold a transaction open across a network call you do not control."* Also implied by criterion *"Honors context cancellation"* — context cancellation cannot release a Postgres lock until the tx ends.
- Proposed fix: Adopt the two-transaction structure from F-C2. Commit Tx-1 before issuing the POST.

**F-H2 — `httpClient` may be `nil` or have no timeout; the function trusts the caller for a critical safety property.**
- Citation: `services/orders/sync.go:49` (parameter), `services/orders/sync.go:78` (use).
- Problem: There is no nil-check on `httpClient`, and the function does not enforce a per-request timeout via `context.WithTimeout`. If the caller passes `http.DefaultClient` (zero timeout) and the warehouse hangs, `Do` blocks forever — and per F-H1, holds a row lock forever.
- Why it matters: Resource leak under common load; also a footgun for callers. Even sophisticated callers routinely forget timeouts.
- Source-of-truth reference: `net/http.Client` docs explicitly warn that the zero `Timeout` "means no timeout." Acceptance criterion *"Honors context cancellation"* is satisfied only if context cancellation actually unblocks `Do`, which requires the request context (it does here) — but defense-in-depth requires a bounded timeout.
- Proposed fix: At entry, `if httpClient == nil { return errors.New("nil http client") }`. Wrap the HTTP call in `reqCtx, cancel := context.WithTimeout(ctx, 30*time.Second); defer cancel()` and use `reqCtx` for `NewRequestWithContext`.

**F-H3 — Implementer's claim "All 5 unit tests pass including the error-path tests" cannot be true as written, or the tests do not assert what they should.**
- Citation: Implementer note in package; cross-referenced against `services/orders/sync.go:52-96`.
- Problem: The error-path tests listed (http failure, db begin failure, marshal failure, warehouse non-200) cannot detect F-C1 unless they explicitly assert on connection-pool stats or attempt a follow-up query against the same row. If the tests merely assert "function returned an error," they pass while leaking transactions. This is a meta-finding: the tests fail to enforce the acceptance criterion they were written for.
- Why it matters: A green test suite is being used to certify code that violates its own design contract. The reviewer cannot rely on the implementer's note.
- Source-of-truth reference: Acceptance criterion *"5 unit tests cover... db begin failure, marshal failure, and warehouse non-200"* — combined with *"left in a state that lets a retry succeed"* — implies the tests must verify post-failure DB state, not just the returned error.
- Proposed fix: Add assertions per error-path test that (a) `sqlmock.ExpectationsWereMet()` (or equivalent) confirms a `Rollback` occurred, and (b) a follow-up `SELECT sync_status FROM orders WHERE id=$1` returns the pre-call value, not `'pending'`. Also add a test for "second ExecContext fails after successful POST" — the current 5-test list omits it.

### Medium

**F-M1 — `time.Now()` is captured in application code rather than the database, producing clock-skew artifacts and untestable timestamps.**
- Citation: `services/orders/sync.go:59` and `services/orders/sync.go:90`.
- Problem: Two separate `time.Now()` calls; their values depend on the process clock and cannot be deterministically tested. If the app clock drifts from the DB clock, `sync_started_at` and `sync_completed_at` will be inconsistent with other DB-side timestamps (e.g., `created_at DEFAULT now()`).
- Why it matters: Reduces auditability and makes the unit tests brittle (any test that pins a timestamp will fail under clock drift in CI).
- Source-of-truth reference: General Postgres best practice — use `now()` / `CURRENT_TIMESTAMP` for transaction-time fields.
- Proposed fix: Replace `time.Now()` with the SQL function `now()`: `"UPDATE orders SET sync_status = $1, sync_started_at = now() WHERE id = $2"` and drop the parameter. For tests that need to control time, inject a `clock` interface or use a transaction-time SQL expression.

**F-M2 — Status check `resp.StatusCode != 200` rejects valid 2xx responses (201, 202, 204).**
- Citation: `services/orders/sync.go:84`.
- Problem: The design says "On 200" but real warehouse APIs commonly return `201 Created` for resource creation or `202 Accepted` for async processing. A literal `!= 200` will treat these as failures and (after F-C1 is fixed) roll back, even though the warehouse accepted the order.
- Why it matters: False negatives produce duplicate POSTs on retry. This is a Medium because the design literally says "200" — but a moderate review should flag the over-literal interpretation.
- Source-of-truth reference: RFC 9110 §15.3 — any 2xx "indicates that the client's request was successfully received, understood, and accepted." `net/http` provides no constant for "any 2xx" but the idiomatic check is `resp.StatusCode/100 == 2` or `>= 200 && < 300`.
- Proposed fix: `if resp.StatusCode < 200 || resp.StatusCode >= 300 { ... }`. Confirm the warehouse contract with the API owner; if it truly only ever returns 200, leave a comment citing that contract.

**F-M3 — The error from a non-2xx response discards the response body, making post-mortems painful.**
- Citation: `services/orders/sync.go:85`.
- Problem: `fmt.Errorf("warehouse returned %d", resp.StatusCode)` reports only the status code. The warehouse almost certainly returns a JSON or text body explaining *why* (e.g., "order ID already exists", "invalid total"). Discarding it forces operators to reproduce the failure to debug it.
- Why it matters: Operability. When this fails in production at 3 AM, the on-call engineer will have only "warehouse returned 422."
- Source-of-truth reference: Standard Go error-wrapping practice; cf. `errors.Is`/`errors.As` design notes — preserve enough context to act on the error.
- Proposed fix: Read up to N bytes of the body (`io.ReadAll(io.LimitReader(resp.Body, 4096))`) and include it in the error: `return fmt.Errorf("warehouse returned %d: %s", resp.StatusCode, string(bodyBytes))`. Consider also including `resp.Header.Get("X-Request-Id")` if the warehouse sets one.

**F-M4 — No validation of `order` input; an empty `order.ID` will silently update zero rows and then commit "successfully."**
- Citation: `services/orders/sync.go:57-60` and `services/orders/sync.go:88-91`.
- Problem: `tx.ExecContext` returns no error if the `WHERE id = $3` clause matches zero rows. The function will mark a non-existent order "synced" from the perspective of the caller — which then POSTs the (empty-ID) order to the warehouse and reports success.
- Why it matters: Silent data-integrity issue. Particularly bad if `order.ID` defaulting to `""` is a common upstream bug.
- Source-of-truth reference: Implicit from criterion *"missing validation that the design implies."* The design implies `order.ID` identifies an existing row.
- Proposed fix: Add `if order.ID == "" { return errors.New("order.ID is required") }` at function entry. Optionally check `result.RowsAffected()` after each UPDATE and return an error if it is zero.

**F-M5 — `defer resp.Body.Close()` is correctly placed but the body is never drained, defeating HTTP/1.1 connection reuse.**
- Citation: `services/orders/sync.go:82`.
- Problem: On a 200 path, the code does not read the response body before closing — so for HTTP/1.1, the underlying TCP connection is not returned to the pool. On the non-200 path (after fixing F-M3) the body is partially read; partial reads also defeat keep-alive.
- Why it matters: Modest performance/efficiency hit; matters under high sync rates. Combined with no `httpClient` timeout (F-H2), a slow body could prolong the transaction window from F-H1.
- Source-of-truth reference: `net/http.Response.Body` docs: *"The default HTTP client's Transport may not reuse HTTP/1.x 'keep-alive' TCP connections if the Body is not read to completion and closed."*
- Proposed fix: After the status check on the success path, `_, _ = io.Copy(io.Discard, resp.Body)` before letting the deferred `Close` fire; or move to `io.LimitReader` + full drain when reading the body for F-M3.

**F-M6 — Hard-coded warehouse URL prevents environment overrides and testing.**
- Citation: `services/orders/sync.go:71`.
- Problem: `"https://warehouse.example.com/orders"` is a string literal. Tests cannot point at a `httptest.Server` without monkey-patching, and there is no way to differentiate staging vs. production.
- Why it matters: Couples deployment topology to source code; the "http failure" unit test must necessarily intercept at the `httpClient` `Transport` layer rather than via URL — which is fine but more fragile.
- Source-of-truth reference: 12-factor config; standard Go convention is to inject endpoints.
- Proposed fix: Accept a `baseURL string` parameter, or define a `Syncer` struct holding `db`, `httpClient`, and `baseURL`, and turn this function into a method.

### Low

**F-L1 — `Order` struct lives in `sync.go` but is a domain type that other files in `services/orders` will likely also need.**
- Citation: `services/orders/sync.go:40-44`.
- Problem: Defining `Order` next to its first user is fine for a one-off, but it almost certainly belongs in `services/orders/order.go` or `services/orders/types.go`.
- Proposed fix: Move when the second consumer appears; flag for follow-up.

**F-L2 — Error messages use lowercase prefixes inconsistently with some Go projects' conventions, but they are consistent within this file — so this is purely a style nit.**
- Citation: `services/orders/sync.go:54, 62, 67, 74, 80, 85, 93`.
- Problem: All seven `fmt.Errorf` strings start lowercase, which matches the Go standard-library convention (`errors.New("...")` style). Calling out only because some org style guides prefer otherwise. No change required if this matches the repo's style.
- Proposed fix: None unless org style differs.

**F-L3 — `http.MethodPost` constant should be preferred over the string literal `"POST"`.**
- Citation: `services/orders/sync.go:71`.
- Problem: Magic string instead of `net/http` constant.
- Proposed fix: Replace `"POST"` with `http.MethodPost`.

**F-L4 — `Content-Type` header value should use `mime` constant or be defined once.**
- Citation: `services/orders/sync.go:76`.
- Problem: Stylistic; consider `req.Header.Set("Content-Type", "application/json; charset=utf-8")` to be explicit, or pull into a package constant.
- Proposed fix: Optional; low-impact.

**F-L5 — Function is doing four jobs (state transition, marshalling, HTTP, second state transition) and would benefit from extraction once the two-transaction refactor lands.**
- Citation: `services/orders/sync.go:46-97` (entire function).
- Problem: Once F-C2's restructure happens, helper functions like `markPending(ctx, db, id)`, `postToWarehouse(ctx, client, order, key)`, and `markSynced(ctx, db, id)` will read more clearly and test in isolation.
- Proposed fix: Defer until the structural fixes are in.
