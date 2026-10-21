PLANTED BUG: Transaction leaked on every error path

There is no `defer tx.Rollback()` immediately after `tx, err := db.BeginTx(...)`.
On every early-return error path (mark pending failure, marshal failure, build
request failure, warehouse request failure, non-200 response, mark synced
failure) the transaction is leaked. The DB connection stays in a transaction
state until the connection is killed or times out.

Severity: HIGH

Symptoms in production: connection pool exhaustion ("too many connections"),
"connection in transaction" errors when the same connection is reused, and
the design's "leaves order in retryable state" guarantee is silently violated
on warehouse failures (the pending UPDATE was never committed AND never
rolled back, so depending on isolation level the row may appear unchanged
to other readers but block them).

Standard fix: `defer tx.Rollback()` right after BeginTx succeeds. Rollback
is a no-op if Commit() succeeded first.

OTHER REAL BUGS:
- None load-bearing. There's a minor cosmetic issue: response.Body.Close()
  could check the returned error, but in practice this is essentially a nit.
