- **Review Scope:** New file `api/routes/auth.py` implementing `POST /auth/login` endpoint, as presented in the package `framed-moderate.md`.
- **Process Used:** Manual static review of the diff against the stated acceptance criteria; no execution, tests, or repository exploration performed (single-file closed context).
- **Execution Context:** Closed-context single-file review. Only the package file was read. No surrounding modules (`api.db`, `api.auth`, `api.schemas`) were inspected; their behavior is inferred from usage.
- **Integration Target:** FastAPI service exposing JSON authentication endpoints. Endpoint is mounted via `APIRouter` at path `/auth/login`.
- **Governing Documents:** Acceptance criteria embedded in the package: JSON body `{email, password}`, 200 with `{token}` on success, 401 with standard error envelope `{code, message, requestId}` on failure, no email-existence leak, 6 unit tests covering specified cases.
- **Reviewer:** Claude (Opus 4.7, 1M context) — automated structured code reviewer.
- **Severity Scale:** Critical (data corruption, RCE, privesc) / High (significant security risk, design requirement violation, silent inconsistency) / Medium (incorrect behavior on some inputs, unclear error handling, missing validation) / Low (style, naming, nits).
- **Date:** 2026-04-26.

## Findings

### Critical

#### C1. Username (email) enumeration via distinct status codes and messages
- **Citation:** `api/routes/auth.py:40-43`
- **Problem:** When the email is not found, the handler raises `HTTPException(status_code=404, detail='No user with that email')`. When the password is wrong, it raises `HTTPException(status_code=401, detail='Incorrect password')`. The two failure modes are trivially distinguishable by both HTTP status code (404 vs 401) and message body, allowing any unauthenticated client to enumerate which emails are registered.
- **Why it matters:** This directly violates the explicit acceptance criterion: *"The endpoint must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective."* Account enumeration is a well-known precursor to credential-stuffing, targeted phishing, and password-spraying attacks, and is the primary security requirement of this endpoint. Because the design document calls this out by name and the implementation does the opposite, this is a hard requirement violation with direct security impact — graded Critical per the package's own severity guidance ("design requirement violated" + "significant security risk").
- **Source of truth:** Acceptance criteria, lines 17-20 of the package (`framed-moderate.md`).
- **Proposed fix:** Collapse both branches into a single response. Always return HTTP 401 with the standard error envelope, and do so with constant-time semantics where possible:
  ```python
  INVALID_CREDS = HTTPException(
      status_code=401,
      detail={'code': 'invalid_credentials',
              'message': 'Invalid email or password',
              'requestId': request_id},
  )

  user = await db.users.find_one({'email': body.email})
  # Run verify_password even when user is None against a dummy hash
  # to equalize timing and avoid a second leak channel.
  password_hash = user['password_hash'] if user else DUMMY_BCRYPT_HASH
  ok = verify_password(body.password, password_hash)
  if not user or not ok:
      raise INVALID_CREDS
  return {'token': issue_token(user)}
  ```

### High

#### H1. Error responses do not use the required standard envelope
- **Citation:** `api/routes/auth.py:41, 43`
- **Problem:** Both `HTTPException` calls pass a plain string as `detail`. FastAPI will serialize this as `{"detail": "<string>"}`, which does not match the contract `{ code: string, message: string, requestId: string }` mandated by the acceptance criteria. There is also no `requestId` plumbed through anywhere in the handler.
- **Why it matters:** Clients and downstream systems depending on the documented envelope (likely shared error parsing, logging correlation via `requestId`) will fail to deserialize errors or will lose request correlation entirely. This is a direct contract violation with cross-system impact, and it is "design requirement violated" under the package's own High criteria.
- **Source of truth:** Acceptance criteria, lines 17-18 of the package.
- **Proposed fix:** Define a small helper (or a custom exception handler) that builds the envelope and includes a `requestId` derived from the incoming request (e.g., from a middleware-set `request.state.request_id` or `X-Request-Id` header), then pass that dict as `detail`. Apply uniformly to all error paths in this handler.

#### H2. No rate limiting / lockout despite acceptance test for "rate-limiting interaction"
- **Citation:** `api/routes/auth.py:37-44` (entire handler)
- **Problem:** The acceptance criteria reference a unit test for "rate-limiting interaction," but the handler contains no rate-limiting hook, dependency, or counter — neither per-IP nor per-account. If rate limiting exists upstream (e.g., middleware), it is not visible here and the unit test cannot meaningfully exercise it from this file.
- **Why it matters:** Without rate limiting, the enumeration issue (C1) and brute-force password guessing both scale unbounded. Even after C1 is fixed, the lack of throttling lets an attacker mount large-scale credential-stuffing against valid emails. Stated unit-test coverage may be passing against a no-op assertion, giving false confidence.
- **Source of truth:** Acceptance criteria, lines 21-22 of the package ("6 unit tests cover ... rate-limiting interaction").
- **Proposed fix:** Add an explicit rate-limit dependency (e.g., `Depends(rate_limit_login)`) keyed on both client IP and submitted email, with a documented threshold (e.g., 5 attempts per 15 minutes per key) and a 429 response that uses the same standard envelope. Make sure the unit test asserts the 429 response and the `Retry-After` header.

#### H3. Verifying password only when user exists creates a timing side channel
- **Citation:** `api/routes/auth.py:39-42`
- **Problem:** When `user` is `None`, the handler returns immediately without invoking `verify_password`. When the user exists, it performs a presumably expensive (bcrypt/argon2) verification. The wall-clock difference between the two paths is observable to a remote attacker and provides a timing oracle for email existence even if C1 and H1 are fixed (because status/body become identical).
- **Why it matters:** Timing-based enumeration is a documented bypass of unified-error responses; without equalizing the work done on both branches, the "no leak" requirement is still violated in practice. Listed High because it is a concrete additional channel for the same design requirement.
- **Source of truth:** Acceptance criteria, lines 19-20 of the package.
- **Proposed fix:** Always call `verify_password` against either the real hash or a precomputed dummy hash of equal cost, then check both `user is not None` and the verification result before issuing a token (see C1 code sketch).

### Medium

#### M1. No exception handling around DB lookup, password verification, or token issuance
- **Citation:** `api/routes/auth.py:39, 42, 44`
- **Problem:** `db.users.find_one`, `verify_password`, and `issue_token` are all called without `try/except`. Any transient DB error, hash-format error, or signing-key error will surface as an unstructured 500 that does not match the standard error envelope and may leak stack-trace details depending on FastAPI debug settings.
- **Why it matters:** The acceptance criteria define the error envelope generically; 5xx responses should also conform. Unhandled exceptions on the auth path are also a common source of noisy alerts and inconsistent client behavior.
- **Source of truth:** Acceptance criteria, lines 17-18 of the package (envelope), plus generic robustness expectations.
- **Proposed fix:** Wrap the dependencies in a narrow `try/except` (or rely on a global exception handler) that logs with `requestId` and returns a 500 using the same `{code, message, requestId}` envelope (e.g., `code='internal_error'`).

#### M2. Email is used as-is, with no normalization before lookup
- **Citation:** `api/routes/auth.py:39`
- **Problem:** The handler queries `db.users.find_one({'email': body.email})` directly. If `LoginBody` does not lowercase / trim the email, users registered as `Alice@example.com` will fail to log in when entering `alice@example.com`, and lookups become case-sensitive in a way most users do not expect from email.
- **Why it matters:** Causes legitimate-user lockout and inconsistent behavior depending on signup vs login casing — a Medium correctness/UX issue and a potential consistency hazard if other code paths normalize differently.
- **Source of truth:** Acceptance criteria, line 15 ("Accepts JSON body: `{ email: string, password: string }`") combined with standard email-handling expectations.
- **Proposed fix:** Either add `EmailStr` + a `@validator` in `LoginBody` that normalizes (`strip().lower()`), or normalize at the handler boundary before the DB call. Apply the same normalization at signup to keep the index consistent.

#### M3. Missing structured audit logging for auth attempts
- **Citation:** `api/routes/auth.py:37-44`
- **Problem:** No log line is emitted for either successful or failed logins. Production auth endpoints are typically expected to log the outcome (success/failure), the source IP, and a `requestId` for correlation, without logging the password or full email.
- **Why it matters:** Without audit logs, brute-force or enumeration attempts cannot be detected after the fact, and the rate-limit subsystem (H2) has nothing to observe.
- **Source of truth:** Implied by acceptance criteria mentioning `requestId` and rate-limiting interaction.
- **Proposed fix:** Add `logger.info("auth.login", extra={"request_id": rid, "outcome": "success"|"invalid_credentials"|"rate_limited", "ip": client_ip, "email_hash": sha256(email)})` (hash or omit raw email per privacy posture).

### Low

#### L1. Hard-coded path string couples router to mount point
- **Citation:** `api/routes/auth.py:37`
- **Problem:** The decorator uses `'/auth/login'` even though `APIRouter()` is created with no `prefix`. If the router is later mounted under `prefix='/auth'` in the app, the path becomes `/auth/auth/login`.
- **Why it matters:** Minor maintainability/coupling nit; easy to get wrong on future refactor.
- **Source of truth:** General FastAPI router conventions.
- **Proposed fix:** Use `APIRouter(prefix='/auth', tags=['auth'])` and decorate with `@router.post('/login')`.

#### L2. Quote style and import grouping are inconsistent with typical Python style
- **Citation:** `api/routes/auth.py:29-31, 37, 39-44`
- **Problem:** Mixes single quotes throughout while many FastAPI codebases standardize on double quotes (PEP 8 is silent, but project style guides usually pick one). Imports are grouped reasonably but lack a blank line between stdlib/third-party/local sections.
- **Why it matters:** Pure style nit; only matters if the project enforces `ruff`/`black`.
- **Source of truth:** Project formatter convention (not stated in package).
- **Proposed fix:** Run `ruff format` / `black` to bring the file in line with project defaults.

#### L3. Response shape for success is undocumented beyond `{token: <jwt>}`
- **Citation:** `api/routes/auth.py:44`
- **Problem:** Returning a bare dict means OpenAPI docs will show `additionalProperties` rather than a typed schema, and no `response_model` is declared on the route.
- **Why it matters:** Reduces schema fidelity for clients and SDK generators.
- **Source of truth:** Acceptance criteria, line 16 (`{ token: <jwt> }`).
- **Proposed fix:** Define `class LoginResponse(BaseModel): token: str` and pass `response_model=LoginResponse` to the decorator.
