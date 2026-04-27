**Review Scope:** New `POST /auth/login` endpoint added in `api/routes/auth.py` (8 lines of route handler logic, plus imports). Reviewed against the design/acceptance criteria provided in the package.

**Process Used:** Manual line-by-line static review of the diff against the stated acceptance criteria. No execution, no test run, no dependency inspection (other files were not provided and per scope are out of bounds).

**Execution Context:** Single-file diff review in a closed context; only the package contents were available. No repository checkout, no ability to inspect `api.db`, `api.auth`, `api.schemas`, or the test suite.

**Integration Target:** A FastAPI-based HTTP API. The endpoint is registered on an `APIRouter` and consumes a `LoginBody` Pydantic schema, a Mongo-style `db.users` collection, and helper functions `verify_password` / `issue_token`.

**Governing Documents:** The "Design / Acceptance criteria" section of the package, in particular: (a) JSON body shape `{email, password}`; (b) 200 with `{token}` on success; (c) 401 with the standard error envelope `{code, message, requestId}` on invalid credentials; (d) MUST NOT leak whether an email is registered — "no such user" and "wrong password" must be indistinguishable from the client side.

**Reviewer:** Claude (Opus 4.7, 1M context), acting as cross-agent code reviewer.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

_None._

### High

**1. Username (email) enumeration via differing status codes — `api/routes/auth.py:40-43`**

- Problem: When the user lookup fails, the handler raises `HTTPException(status_code=404, detail='No user with that email')`. When the password check fails, it raises `HTTPException(status_code=401, detail='Incorrect password')`. The two failure modes are trivially distinguishable by an unauthenticated caller (different status codes and different `detail` strings).
- Why it matters: The acceptance criteria explicitly state: "The endpoint must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective." This is a direct violation of a stated security requirement and is the canonical username-enumeration vulnerability — an attacker can probe the `/auth/login` endpoint with arbitrary emails to harvest a list of valid accounts, then focus credential-stuffing or phishing on the confirmed set. This is also the de-facto industry guidance (OWASP ASVS V3.2.3 / Authentication Cheat Sheet: "Responses to invalid login attempts must be generic… do not disclose whether the username is valid").
- Source-of-truth reference: Package "Acceptance criteria" bullet 4 ("The endpoint must NOT leak whether an email is registered…").
- Proposed fix: Collapse both failure paths into a single response. Always return HTTP 401 with the standard error envelope and a generic message, regardless of whether the user was found or the password was wrong. Additionally, when the user is missing, still perform a dummy `verify_password` call against a fixed bogus hash so that response timing does not leak existence either. Example:
  ```python
  GENERIC_INVALID = HTTPException(
      status_code=401,
      detail={'code': 'invalid_credentials',
              'message': 'Invalid email or password',
              'requestId': request_id},
  )
  user = await db.users.find_one({'email': body.email})
  password_hash = user['password_hash'] if user else DUMMY_HASH
  ok = verify_password(body.password, password_hash)
  if not user or not ok:
      raise GENERIC_INVALID
  return {'token': issue_token(user)}
  ```

**2. Error response does not match the standard error envelope — `api/routes/auth.py:41,43`**

- Problem: Both `HTTPException` calls pass `detail='<string>'`. FastAPI will serialize this as `{"detail": "No user with that email"}` (or similar). The acceptance criteria require the error envelope `{ code: string, message: string, requestId: string }`.
- Why it matters: Clients written against the documented error envelope will fail to parse the 401/404 responses, breaking error handling across the product. This is a stated design-requirement violation.
- Source-of-truth reference: Package "Acceptance criteria" bullet 3 ("On invalid credentials, returns 401 with the standard error envelope `{ code, message, requestId }`").
- Proposed fix: Either return a `JSONResponse` with the envelope shape directly, or pass a dict to `HTTPException(detail=...)` matching the envelope, or (preferred) use the project's existing error-envelope helper / exception handler so `requestId` is populated consistently. The 404 path should be removed entirely (see finding 1) so only the 401 envelope path remains.

### Medium

**3. Wrong status code on unknown email (404 vs. 401) — `api/routes/auth.py:41`**

- Problem: Independently of the enumeration concern, returning `404` for "no such user" is wrong for an authentication endpoint. Auth failures should be `401 Unauthorized`. The acceptance criteria specify 401 for invalid-credentials cases.
- Why it matters: Even setting aside enumeration, a 404 on `/auth/login` will be misinterpreted by clients, intermediaries, and monitoring — a 404 typically indicates the route itself does not exist, not a credentials problem. It also confounds rate-limit / fail2ban-style middleware that keys off 401s.
- Source-of-truth reference: Package "Acceptance criteria" bullet 3 ("On invalid credentials, returns 401…").
- Proposed fix: Subsumed by finding 1 — collapse to a single 401 path.

**4. No explicit handling of malformed body / missing fields beyond Pydantic defaults — `api/routes/auth.py:38`**

- Problem: The handler relies entirely on `LoginBody` for validation. The acceptance criteria call out that there are unit tests for "malformed body" and "missing field", which strongly implies the endpoint should produce the standard error envelope for those cases too. FastAPI's default 422 response shape (`{"detail": [...]}`) does not match the `{code, message, requestId}` envelope.
- Why it matters: If the project has a global exception handler that rewrites validation errors into the envelope, this is fine; if not, the malformed-body and missing-field tests will pass against the current default shape but real clients will still see a non-standard error body. Worth verifying.
- Source-of-truth reference: Package "Acceptance criteria" bullet 5 (test list includes "malformed body, missing field"); bullet 3 (envelope shape).
- Proposed fix: Confirm that a `RequestValidationError` exception handler is registered globally and emits the standard envelope. If not, register one, or convert validation errors locally in this route.

**5. Rate-limiting interaction is implicit, not visible in the handler — `api/routes/auth.py:37-44`**

- Problem: One of the six tests covers "rate-limiting interaction", but the handler contains no rate-limit guard, dependency, or decorator. Presumably this is enforced by middleware, but there is no visible marker (e.g., a `Depends(rate_limit_login)`) tying this endpoint to the policy.
- Why it matters: Auth endpoints are the primary target of credential-stuffing and password-spray attacks; rate limiting is load-bearing security. If it is only applied at a global middleware level, it is easy to silently lose for this route during a future refactor (e.g., moving to a different router prefix or adding an exemption). An explicit, route-level dependency makes the contract auditable.
- Source-of-truth reference: Package "Acceptance criteria" bullet 5 ("rate-limiting interaction"); implicit defense-in-depth norms for auth endpoints.
- Proposed fix: Add an explicit `Depends(...)` for the login rate limiter on the route, even if the underlying enforcement remains in middleware. Document in a comment what policy applies (e.g., "5 attempts per IP per minute, then 429").

**6. Successful-login response does not echo `requestId` and lacks token metadata — `api/routes/auth.py:44`**

- Problem: The success response is `{'token': issue_token(user)}`. The criteria only require `{token}` on success, so this is technically compliant, but for operability it is worth considering returning at least `{token, token_type: 'bearer', expires_in: <seconds>}` so clients do not have to decode the JWT to learn its lifetime.
- Why it matters: Minor; affects client ergonomics and debuggability rather than correctness.
- Source-of-truth reference: General API hygiene; not strictly required by the package.
- Proposed fix: Add `token_type` and `expires_in` to the success response if `issue_token` exposes the TTL, and consider including `requestId` for log correlation across success and failure paths.

### Low

**7. `detail` strings reveal internal phrasing — `api/routes/auth.py:41,43`**

- Problem: Strings like `'No user with that email'` and `'Incorrect password'` are user-facing once finding 1 is fixed they will go away, but if any of them survive (e.g., copy-pasted into the new envelope), they should be neutralized to a single `'Invalid email or password'`.
- Why it matters: Style / consistency of user-facing copy.
- Source-of-truth reference: Package criteria bullet 4 (no leakage).
- Proposed fix: Use a single constant `INVALID_CREDENTIALS_MESSAGE = 'Invalid email or password'`.

**8. Direct dictionary access on user document — `api/routes/auth.py:42,44`**

- Problem: `user['password_hash']` and `issue_token(user)` assume the document always contains `password_hash` and whatever fields `issue_token` expects. A user record missing `password_hash` (e.g., social-only signup, partially migrated row) will raise `KeyError` and surface as a 500.
- Why it matters: Robustness; could turn a benign data-quality issue into a 500 spike.
- Source-of-truth reference: General defensive coding.
- Proposed fix: `user.get('password_hash')` with an explicit "no password set, treat as invalid credentials" branch (which then folds into the generic 401 from finding 1).

**9. No structured logging of auth attempts — `api/routes/auth.py:37-44`**

- Problem: There is no logging of login attempts (success or failure). For an auth endpoint, structured logs (with `requestId`, source IP, outcome, but never the password) are essentially mandatory for incident response.
- Why it matters: Operability and security forensics.
- Source-of-truth reference: General security/operability norms; not explicit in the package.
- Proposed fix: Emit a structured log line on each outcome (`auth.login.success` / `auth.login.failure`) with `requestId`, hashed-or-truncated email, and reason category (but not which of "no user" vs "bad password" — that distinction must remain server-side only, and ideally only in logs the customer cannot see).

**10. `async` handler performs no `await` on `verify_password` — `api/routes/auth.py:42`**

- Problem: `verify_password` is called synchronously inside an `async def`. Password hashing/verification (bcrypt, argon2) is CPU-bound and blocks the event loop; under load this serializes login throughput across the worker.
- Why it matters: Performance under realistic load; not a correctness bug.
- Source-of-truth reference: General FastAPI/asyncio guidance.
- Proposed fix: Either run `verify_password` via `await asyncio.get_running_loop().run_in_executor(None, verify_password, ...)` or, if the helper already off-loads internally, document that. Same consideration applies to `issue_token` if it does heavy crypto.
