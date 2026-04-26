Findings:
Review Scope: Task task-101
Process Context: Full process
Execution Context: Unable to determine
Integration Target: Unable to determine
Design Reference: Admin user listing endpoint, paginated, requires admin permission, filters by creation date.
Architecture Reference: None applicable
Feature Specification Reference: None applicable
PRD Reference: docs/prds/02-admin-tooling.md §3 ("Admin endpoints must be auditable and rate-limited")

- `High` [api/routes/admin.py:4]
  Problem: A live-looking API key (`sk_live_Adm1n_2024_HARDCODED`) is hardcoded in source.
  Why it matters: Secrets in source leak through git history, CI logs, and forks. The `sk_live_` prefix suggests a production credential, so a single repo read grants production access. This is also unauditable — there's no way to rotate or scope it.
  Source of truth: PRD `docs/prds/02-admin-tooling.md` §3 (admin endpoints must be auditable) and standard secret-handling practice.
  Proposed fix: Remove the literal from the file. Load it from a secrets manager (env var injected from Vault/SSM/etc.) at startup, and rotate the exposed key immediately since it is now compromised by virtue of having been committed.

- `High` [api/routes/admin.py:11]
  Problem: The `since` query parameter is interpolated into the SQL via an f-string, producing a textbook SQL injection sink.
  Why it matters: An attacker controlling `?since=` can read, modify, or destroy arbitrary tables. This is a correctness and security contract violation; any admin route compounds the blast radius.
  Source of truth: General correctness/security baseline and PRD §3 (auditable admin endpoints — an exploited endpoint is not auditable).
  Proposed fix: Use parameterized queries (e.g., `db.execute("SELECT ... WHERE created_at > :since", {"since": parsed_since})`) and parse `since` as a typed `datetime` before binding.

- `High` [api/routes/admin.py:9-12]
  Problem: The handler has no admin permission check; any authenticated (or unauthenticated) caller can list users.
  Why it matters: The design explicitly requires admin permission. Shipping without it is a privilege-escalation path on a route that returns the full users table.
  Source of truth: Task task-101 design ("requires admin permission").
  Proposed fix: Add a dependency that verifies the caller's admin role (e.g., `Depends(require_admin)`) and reject non-admins with `403`.

- `High` [api/routes/admin.py:12]
  Problem: `SELECT *` returns the full row, almost certainly including columns like `password_hash`, `email`, `mfa_secret`, etc.
  Why it matters: Admin listing is supposed to surface a defined projection of user data; returning every column risks leaking credentials and PII to anything that can reach the endpoint, and freezes the DB schema as the public response shape (Hyrum's Law).
  Source of truth: Design ("user listing endpoint" implies a defined user view, not the raw row) and general data-exposure baseline.
  Proposed fix: Select an explicit column list (`id, email, created_at, role`) and return a typed `User` model with only safe fields.

- `Medium` [api/routes/admin.py:9]
  Problem: URL uses a verb (`/admin/listAllUsers`) instead of a resource.
  Why it matters: REST resources should be nouns; verbs in URLs make the surface inconsistent and harder for clients to discover. The convention everywhere else in this codebase will be resource-oriented.
  Source of truth: Standard REST conventions; design wording ("Admin user listing endpoint" describes the resource, not an action).
  Proposed fix: Rename to `GET /admin/users` and update any callers.

- `Medium` [api/routes/admin.py:9-12]
  Problem: No pagination is implemented; the handler returns every matching row in one response.
  Why it matters: Design explicitly requires the listing to be paginated. Unbounded responses scale O(users) and will time out / OOM as the table grows.
  Source of truth: Task task-101 design ("paginated").
  Proposed fix: Add `limit` and `offset` (or cursor) query parameters with sensible defaults and a max cap, and return a paginated envelope (`{ data, page, limit, total }` per repo convention).

- `Medium` [api/routes/admin.py:9-12]
  Problem: No rate-limiting or audit-log hook on a destructive-data-class admin endpoint.
  Why it matters: PRD §3 mandates that admin endpoints are auditable and rate-limited. A bulk listing endpoint without either is a compliance gap.
  Source of truth: PRD `docs/prds/02-admin-tooling.md` §3.
  Proposed fix: Wrap with the existing rate-limit middleware (or add `@rate_limit(...)`) and emit an audit-log event including `actor_id`, `route`, `since` filter, and result count.

- `Medium` [api/routes/admin.py:10]
  Problem: Handler signature `async def list_all_users(req)` is not idiomatic FastAPI; `req` is untyped and bypasses FastAPI's request validation.
  Why it matters: FastAPI's value comes from typed parameters that drive validation, schema generation, and OpenAPI. Reaching into `req.query_params` manually loses all of that and is the proximate cause of the SQL-injection sink.
  Source of truth: Repo conventions for FastAPI handlers; design intent for filtering by creation date implies a typed `since: datetime` parameter.
  Proposed fix: Declare `since: datetime | None = None`, `limit: int = 50`, `offset: int = 0`, `current_user: User = Depends(require_admin)` and let FastAPI parse and validate.

- `Low` [api/routes/admin.py:9]
  Problem: Handler name `list_all_users` includes "all", which contradicts the paginated, filtered semantics.
  Why it matters: Naming nit, but "all" misleads readers and review tooling.
  Source of truth: Naming consistency.
  Proposed fix: Rename to `list_users`.

Residual Risks / Gaps:
- Could not verify whether the existing FastAPI app already has admin auth middleware (`require_admin`) or rate-limit middleware available; the proposed fixes assume one exists.
- No test file appears in the diff; behavior under empty `since`, malformed `since`, and non-admin caller is unverified.
- `Execution Context` and `Integration Target` weren't stated in the prompt; if multi-agent or non-`main` integration applies, these fields should be filled in before merge.
