- **Review Scope:** `services/orders/sync.go` (new file) implementing `SyncOrderToWarehouse(ctx, db, httpClient, order)` per the supplied design / acceptance criteria.
- **Process Used:** Static review of the single Go source file shipped in the package against the stated acceptance criteria, with focus on transaction lifecycle, error paths, idempotency/retry semantics, context handling, and HTTP correctness.
- **Execution Context:** Closed-context review; only the package file was read. No execution, no test inspection, no repository exploration.
- **Integration Target:** Go service `services/orders` package, called against a `*sql.DB` (presumably Postgres given `$N` placeholders) and an outbound `*http.Client` to `https://warehouse.example.com/orders`.
- **Governing Documents:** The "Design / Acceptance criteria" section of the package (order-to-warehouse sync requirements: pending marker, POST, success marker, retry-safe failure state, single transaction, context honoring, 5 unit tests).
- **Reviewer:** Claude (Opus 4.7, 1M context), single-pass structured code review.
- **Severity Scale:** Critical (production data corruption, RCE, privilege escalation); High (significant security risk, resource leak under common load, silent data inconsistency, design requirement violated); Medium (incorrect behavior in some inputs, unclear error handling, performance degradation, missing implied validation); Low (style, naming, nits).
- **Date:** 2026-04-26.

## Findings

### Critical

#### C1. Transaction is never rolled back on any error path — connection leak and lock leak
- **Citation:** `services/orders/sync.go:52-97` (every `return fmt.Errorf(...)` between line 54 and line 93).
- **Problem:** `tx, err := db.BeginTx(ctx, nil)` opens a transaction, but no `defer tx.Rollback()` is registered. Every subsequent error path (`mark pending` at line 62, `marshal order` at line 67, `build request` at line 74, `warehouse request` at line 80, non-200 at line 85, `mark synced` at line 93) returns directly without calling `tx.Rollback()` or `tx.Commit()`. The only terminal call to the transaction is `tx.Commit()` on the happy path at line 96.
- **Why it matters:** An unfinalized `*sql.Tx` holds its underlying database connection out of the pool until the connection is reaped (GC finalizer or driver-specific timeout) and, on Postgres, holds row-level locks (and any acquired advisory locks) on the `orders` row. Under common production load — any flaky warehouse endpoint, any 5xx, any context cancellation, any network blip — this leaks a pooled connection and a row lock per failed call. The pool will saturate (`sql.DB.SetMaxOpenConns` default-unbounded but real deployments cap it), and concurrent retries against the same `order.ID` will block on the held lock, producing a cascading outage. This is a textbook resource leak that materializes under exactly the conditions the design says must be retry-safe.
- **Source-of-truth reference:** Acceptance criteria: "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)." Standard `database/sql` guidance: every `BeginTx` must be paired with a guaranteed `Rollback` (idempotent after `Commit`) — typically `defer tx.Rollback()` immediately after `BeginTx`.
- **Proposed fix:** Immediately after a successful `BeginTx`, add `defer func() { _ = tx.Rollback() }()`. `Rollback` after a successful `Commit` is a no-op error (`sql.ErrTxDone`) and is safe to ignore. This single change closes every leak path below as well.

#### C2. "Mark pending" write is rolled back on failure, leaving retry semantics broken
- **Citation:** `services/orders/sync.go:57-63` (the `UPDATE ... sync_status='pending'` inside the same transaction) combined with the missing rollback in C1.
- **Problem:** The `pending` marker is written inside the same transaction as the `synced` marker. If the HTTP call fails (line 80), the warehouse returns non-200 (line 85), or the final `mark synced` fails (line 93), the design intent is that the row reflects "we attempted this" so a retry can detect/clear it. But because everything is in one transaction, on any failure either (a) the transaction is rolled back (correct fix per C1) and the `pending` write disappears, or (b) the transaction leaks (current code) and the row is locked indefinitely. Neither outcome satisfies "left in a state that lets a retry succeed."
- **Why it matters:** This is a silent data-inconsistency / design-requirement violation. With C1's fix applied, the row will appear untouched after a failure — fine for retries but the `sync_started_at` audit signal is lost, and there is no way to distinguish "never attempted" from "attempted and failed." Worse, if the warehouse actually accepted the POST but the response was lost (network reset after the server processed), the next retry will POST again with no idempotency key (see H2), risking duplicate fulfillment.
- **Source-of-truth reference:** Acceptance criteria: "On any failure, the order's `sync_status` is left in a state that lets a retry succeed (not stuck in 'pending' forever)" and "All DB writes happen in a single transaction." These two requirements are in tension when an external side effect (HTTP POST) sits between the writes; the correct pattern is either (i) two transactions with the HTTP call between them, or (ii) an outbox pattern, not a single long transaction wrapping a network call.
- **Proposed fix:** Restructure into two short transactions around the HTTP call: TX1 commits `sync_status='pending'` + `sync_started_at`; then perform the HTTP POST (no DB connection held); then TX2 commits `sync_status='synced'` + `sync_completed_at`. On any HTTP/marshal failure, set `sync_status='failed'` (or leave it in `pending` with a bounded reaper) so retries can pick it up. If the literal "single transaction" requirement is binding, escalate the design contradiction to the author rather than ship the current code.

### High

#### H1. HTTP response body is not drained before `Close`, defeating connection reuse
- **Citation:** `services/orders/sync.go:78-86`.
- **Problem:** `defer resp.Body.Close()` is registered, but on the non-200 path (line 84-86) the body is returned/discarded without being read. Go's `net/http` transport requires the body to be fully read (or explicitly drained via `io.Copy(io.Discard, resp.Body)`) before `Close` for the underlying TCP connection to be returned to the keep-alive pool.
- **Why it matters:** Under sustained non-200 traffic from the warehouse, this forces the transport to tear down and re-establish TCP+TLS for every request, multiplying latency and CPU and exhausting ephemeral ports on the caller. Significant resource impact under common load.
- **Source-of-truth reference:** `net/http` documentation for `Response.Body`: "The default HTTP client's Transport may not reuse HTTP/1.x 'keep-alive' TCP connections if the Body is not read to completion and closed."
- **Proposed fix:** Before returning on the non-200 branch (and ideally before any error return after `httpClient.Do` succeeded), call `_, _ = io.Copy(io.Discard, resp.Body)`. Optionally cap with `io.LimitReader` to avoid unbounded reads on a malicious server.

#### H2. POST is not idempotent — retries can double-fulfill orders
- **Citation:** `services/orders/sync.go:70-76` (request construction) and the absence of any idempotency-key header.
- **Problem:** The POST to `https://warehouse.example.com/orders` carries no `Idempotency-Key` header (or equivalent). Combined with C2 (retry semantics) and H1 (connection churn under failure), any retry after a transport-level failure where the server actually processed the request will create a duplicate warehouse order.
- **Why it matters:** The acceptance criteria explicitly call for retry-safe failure handling. Retry safety at the DB layer is meaningless if the side-effecting POST is not idempotent at the protocol layer.
- **Source-of-truth reference:** Acceptance criteria: "On any failure, the order's `sync_status` is left in a state that lets a retry succeed." Industry standard for side-effecting POSTs (Stripe, AWS, etc.): include a deterministic `Idempotency-Key` derived from `order.ID`.
- **Proposed fix:** `req.Header.Set("Idempotency-Key", order.ID)` (or a hash of `order.ID` + a sync attempt nonce stored on the row). Confirm the warehouse contract supports it; if not, file a contract change.

#### H3. `time.Now()` captured inside SQL parameters bypasses DB clock and harms testability
- **Citation:** `services/orders/sync.go:59` and `services/orders/sync.go:90`.
- **Problem:** `sync_started_at` and `sync_completed_at` use the application process's wall clock, which (a) drifts relative to the DB server, (b) is not injectable for tests, and (c) records the wrong instant for `sync_completed_at` if the row's actual visibility is delayed by transaction commit latency. With C1+C2 fixed (split transactions), this becomes the time we *began the second tx*, not when the warehouse acknowledged.
- **Why it matters:** Audit/forensic timestamps that don't match DB ordering produce silent data inconsistency in dashboards and reconciliation jobs. Also blocks deterministic testing of the "5 unit tests" claim.
- **Source-of-truth reference:** Implied by acceptance criterion "5 unit tests cover happy path, http failure, db begin failure, marshal failure, and warehouse non-200" — deterministic tests over wall-clock fields require an injectable clock.
- **Proposed fix:** Either use `NOW()` / `CURRENT_TIMESTAMP` in the SQL itself, or inject a `clock func() time.Time` (or a `Clock` interface) into the function/struct so tests can pin time.

### Medium

#### M1. Non-2xx detection only catches exactly `200`, rejecting valid `2xx` responses
- **Citation:** `services/orders/sync.go:84`.
- **Problem:** `if resp.StatusCode != 200` treats `201 Created`, `202 Accepted`, and `204 No Content` as failures even though the design says "On 200, marks the order `sync_status='synced'`." Many warehouse APIs respond with `201` or `202` for resource creation/acceptance.
- **Why it matters:** False-positive failures will trigger retries (H2 risk) and leave rows in the wrong state. Whether this is a real bug depends on the warehouse contract; the design literally says "On 200" so the implementation matches the spec — but the spec is almost certainly under-specified.
- **Source-of-truth reference:** Acceptance criterion "POSTs the order ... On 200, marks the order `sync_status='synced'`" combined with HTTP/1.1 RFC 9110 §15.3 (any 2xx is a successful response).
- **Proposed fix:** Change to `if resp.StatusCode < 200 || resp.StatusCode >= 300`, and confirm with the warehouse contract owner. If the spec is binding at exactly `200`, leave a comment citing it.

#### M2. Error messages from the warehouse are discarded, making failures undiagnosable
- **Citation:** `services/orders/sync.go:84-86`.
- **Problem:** On non-200, the error returned is `fmt.Errorf("warehouse returned %d", resp.StatusCode)` — the response body, which typically contains the structured error reason, is never read or surfaced.
- **Why it matters:** Operators triaging a 4xx (e.g., validation failure) get only the status code, forcing log diving on the warehouse side. Compounds H1 (body not drained).
- **Source-of-truth reference:** General error-handling discipline; severity grading rubric calls out "unclear error handling" as Medium.
- **Proposed fix:** Read up to ~4 KiB of the body via `io.LimitReader` and include a sanitized prefix in the error: `fmt.Errorf("warehouse returned %d: %s", resp.StatusCode, bodySnippet)`. This also drains the body for keep-alive (see H1).

#### M3. No HTTP timeout / deadline beyond context, and no validation of `httpClient`
- **Citation:** `services/orders/sync.go:46-51` (signature accepts `*http.Client`) and `services/orders/sync.go:78` (`httpClient.Do(req)`).
- **Problem:** The function takes a caller-provided `*http.Client` with no contract about timeouts. If the caller passes `&http.Client{}` (the zero value), `Do` will wait indefinitely for headers/body when the warehouse hangs — `ctx` will eventually cancel it, but only if the caller actually plumbs a deadline-bearing context. There is no nil check either; a nil client panics on `Do`.
- **Why it matters:** Common operational footgun. Combined with C1, a hung warehouse hangs the transaction indefinitely.
- **Source-of-truth reference:** `net/http` `Client` zero-value docs: "A Client is an HTTP client. ... A Client is higher-level than a RoundTripper ..." — zero value has no `Timeout`.
- **Proposed fix:** Either document in the function godoc that callers must supply a timeout-bearing client, or guard with `if httpClient == nil { httpClient = &http.Client{Timeout: 10 * time.Second} }`. Add a per-request `context.WithTimeout` if the caller's `ctx` may be background.

#### M4. `marshal order` failure is unreachable in practice but still leaks the transaction
- **Citation:** `services/orders/sync.go:65-68`.
- **Problem:** `json.Marshal` of the `Order` struct (three plainly serializable fields) cannot fail under normal inputs, yet a unit test for marshal failure was claimed in the implementer note. That test must be using a different code path or a fake `Order` — which suggests the production code and the test are not exercising the same branch. Worth verifying. Independently, this branch suffers from C1 (transaction leak).
- **Why it matters:** Either the test is dead/fake, or there's an undisclosed indirection. Either way, the claim "5 unit tests pass including the error-path tests" is suspect for this branch.
- **Source-of-truth reference:** `encoding/json` `Marshal` documentation enumerates failure modes (channels, complex, functions, unsupported map keys, cyclic) — none apply to `Order` as defined at lines 40-44.
- **Proposed fix:** Confirm the marshal-failure test is meaningful; if not, remove or replace it with a test that fakes via a wrapper. Address C1 to prevent the leak regardless.

### Low

#### L1. Hardcoded warehouse URL
- **Citation:** `services/orders/sync.go:71`.
- **Problem:** `https://warehouse.example.com/orders` is baked in. No env / config plumbing.
- **Why it matters:** Blocks staging/prod separation and integration testing against a fake.
- **Source-of-truth reference:** Standard 12-factor configuration practice.
- **Proposed fix:** Accept the URL via function parameter, struct field, or config. Default acceptable for now if explicitly noted.

#### L2. `Content-Type` set after request construction, no `Accept` header
- **Citation:** `services/orders/sync.go:76`.
- **Problem:** Minor: no `Accept: application/json` header advertised; the warehouse may content-negotiate to a non-JSON error body.
- **Why it matters:** Cosmetic / defensive.
- **Proposed fix:** `req.Header.Set("Accept", "application/json")`.

#### L3. `Order` struct re-declared in service package
- **Citation:** `services/orders/sync.go:40-44`.
- **Problem:** A package named `orders` defining its own `Order` is fine, but if there's an existing canonical `Order` model elsewhere, this duplicates it. Not visible from this single file.
- **Why it matters:** Potential drift if a canonical model exists.
- **Proposed fix:** Confirm there is no existing `orders.Order` to import; if there is, reuse it.

#### L4. No structured logging or tracing span around the HTTP call
- **Citation:** `services/orders/sync.go:78-86`.
- **Problem:** No log line or span recording warehouse latency / status. Hard to operate.
- **Why it matters:** Observability gap for an outbound integration.
- **Proposed fix:** Add a span (e.g., OpenTelemetry) around `httpClient.Do` and a structured log on non-2xx including `order.ID` and status code.

#### L5. `bytes.NewReader` over a fresh `[]byte` is fine, but `GetBody` is unset
- **Citation:** `services/orders/sync.go:70-72`.
- **Problem:** `http.NewRequestWithContext` with `bytes.NewReader` sets `GetBody` automatically when the body type is recognized, so this is fine — flagging only because if the body source is ever swapped to a non-recognized `io.Reader`, request retries inside the transport will silently drop the body.
- **Why it matters:** Future-proofing.
- **Proposed fix:** Keep using `bytes.NewReader` (or `bytes.NewBuffer`); avoid generic `io.Reader` wrappers without setting `req.GetBody` explicitly.
