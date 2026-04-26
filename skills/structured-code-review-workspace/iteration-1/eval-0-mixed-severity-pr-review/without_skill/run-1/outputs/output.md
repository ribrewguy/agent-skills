# PR Review: Admin User Listing Endpoint

This change adds a new admin endpoint to list users, but it has several serious problems before it can ship. Let me walk through them.

## Critical issues

**1. Hardcoded API key in source code.** Line 4 has `API_KEY = 'sk_live_Adm1n_2024_HARDCODED'`. The `sk_live_` prefix strongly implies this is a production key. Once committed it's effectively public — git history, CI logs, forks, and anyone who clones the repo all have it. You need to:

- Rotate this key immediately. It is compromised.
- Load secrets from environment variables (or a secrets manager like AWS Secrets Manager, Vault, etc.).
- Add a pre-commit hook or CI check (e.g., `gitleaks`, `trufflehog`) to prevent recurrences.

**2. SQL injection.** Line 11 builds the query with an f-string that interpolates `req.query_params.get('since')` directly into a `SELECT ... WHERE created_at > '<since>'` statement. `since` is attacker-controlled. A request like `?since=' OR '1'='1` (or far worse) gives the caller arbitrary SQL execution. Use a parameterized query:

```python
rows = db.execute(
    "SELECT id, email, created_at, role FROM users WHERE created_at > :since",
    {"since": parsed_since},
)
```

And parse `since` as a `datetime` before binding it.

**3. No admin permission check.** The design says "requires admin permission" but the handler accepts anyone. As written, any caller (potentially even unauthenticated, depending on global middleware) can dump the user table. Add a FastAPI dependency:

```python
async def list_users(
    since: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_admin),
):
    ...
```

## Other problems

**4. `SELECT *` leaks sensitive columns.** Returning every row column likely exposes `password_hash`, `email`, `mfa_secret`, internal flags, etc. Project an explicit safe field set.

**5. URL uses a verb.** `/admin/listAllUsers` should be `GET /admin/users` — REST URLs name resources, not actions. The "list" part is implied by `GET` on the collection.

**6. No pagination.** Design says "paginated" — current implementation returns every matching row. Add `limit`/`offset` (or cursor) with a sane default and a max cap, and return a paginated envelope.

**7. PRD says admin endpoints must be auditable and rate-limited.** Neither is present:

- Add the rate-limit middleware (or decorator) used elsewhere in the project.
- Emit an audit-log event with actor, route, filter params, and result count.

**8. Handler signature is not idiomatic FastAPI.** `async def list_all_users(req)` takes a single untyped argument and reaches into `req.query_params` manually. That's exactly why the SQL-injection sink exists — bypassing FastAPI's typed parameter parsing means losing both validation and OpenAPI generation. Declare typed parameters and let the framework do the work.

**9. Naming nit.** `list_all_users` is misleading once pagination + filtering is added. Just `list_users` is more honest.

## Summary

This is a **block on merge** — three independent High-severity issues (hardcoded production key, SQL injection, missing authorization) plus a likely PII leak via `SELECT *`. The verb-in-URL, missing pagination, missing rate limit, and missing audit log are required by either REST conventions, the design, or the PRD, so they should also be addressed before this lands.

Happy to look again once these are fixed.
