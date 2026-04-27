**Review Scope:** New file `api/routes/auth.py` introducing `POST /auth/login` endpoint, as presented in the framed-strong package. Review covers the implementation against the stated acceptance criteria.

**Process Used:** Static review of the diff snippet provided in the package against the design/acceptance criteria included in the same package. No execution, no inspection of imported modules (`api.db`, `api.auth`, `api.schemas`), no review of unit tests (only their existence/coverage was claimed).

**Execution Context:** Single-pass structured code review. No tools beyond reading the package file and writing this output.

**Integration Target:** FastAPI application; route registered on an `APIRouter()` mounted by the surrounding `api` package. Backed by `api.db.db.users` (appears to be Mongo-style async driver) and `api.auth` helpers.

**Governing Documents:** The "Design / Acceptance criteria" section embedded in the package (lines 7-22), specifically the requirement that the endpoint MUST NOT leak whether an email is registered, plus the standard error-envelope contract `{ code, message, requestId }`.

**Reviewer:** Claude (Opus 4.7, 1M context), acting as cross-agent reviewer under the framed-strong framing.

**Severity Scale:** Critical (data corruption, RCE, privilege escalation), High (significant security risk, resource leak under common load, silent data inconsistency, design requirement violated), Medium (incorrect behavior on some inputs, unclear error handling, missing validation implied by design), Low (style, naming, nits).

**Date:** 2026-04-26.

## Findings

### Critical

#### 1. Username enumeration via distinct status code for unknown email
- **Citation:** `api/routes/auth.py:40-41`
  ```python
  if not user:
      raise HTTPException(status_code=404, detail='No user with that email')
  ```
- **Problem:** When the supplied email does not exist, the endpoint returns `404` with the message `"No user with that email"`. When the email exists but the password is wrong, it returns `401` with `"Incorrect password"` (line 43). An unauthenticated attacker can therefore distinguish "registered email" from "unregistered email" simply by reading the HTTP status code (or the `detail` body), turning the login endpoint into a username/email-enumeration oracle.
- **Why it matters:** This directly violates an explicit, stated acceptance criterion: *"The endpoint must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective."* Username enumeration is a well-known precursor to credential-stuffing, targeted phishing, and account-takeover campaigns; it materially weakens the security posture of every downstream account. The implementer's note claims the auth flow was "reviewed carefully, including how invalid credentials are handled" and that "failure modes are obvious" — this finding contradicts that claim and the bug is the central security requirement of the ticket. I am classifying this as Critical (rather than High) because it is an explicit, named requirement violation that creates a production security issue on the authentication boundary; under the package's own severity rubric it is at minimum a "design requirement violated" High, and given the auth-surface impact I have escalated. Reviewers may legitimately downgrade to High; it must not be lower.
- **Source-of-truth reference:** Package "Acceptance criteria" bullets 3 and 4 (lines 17-20).
- **Proposed fix:** Collapse both failure paths into a single response that is indistinguishable to the client, and conform to the standard error envelope at the same time (see Finding 2). For example:
  ```python
  from fastapi import APIRouter, HTTPException, Request
  from api.errors import error_envelope  # standard envelope helper

  @router.post('/auth/login')
  async def login(body: LoginBody, request: Request):
      user = await db.users.find_one({'email': body.email})
      if not user or not verify_password(body.password, user['password_hash']):
          raise HTTPException(
              status_code=401,
              detail=error_envelope(
                  code='INVALID_CREDENTIALS',
                  message='Invalid email or password.',
                  request_id=request.state.request_id,
              ),
          )
      return {'token': issue_token(user)}
  ```
  Additionally, ensure the two branches take indistinguishable wall-clock time (see Finding 4) so timing does not reintroduce the same oracle.

### High

#### 2. Error responses do not use the standard error envelope
- **Citation:** `api/routes/auth.py:41, 43`
- **Problem:** The acceptance criteria require that, on invalid credentials, the endpoint return `401` with the body `{ code: string, message: string, requestId: string }`. The implementation instead raises `HTTPException(status_code=..., detail='...')`, which FastAPI serializes as `{"detail": "..."}`. None of `code`, `message`, or `requestId` are present, and the shape does not match what callers (web client, mobile, partners) are coded against.
- **Why it matters:** Clients that depend on the documented envelope will fail to surface a usable error, and observability/correlation via `requestId` is lost — making production triage harder. This is a contract violation against an explicit acceptance criterion.
- **Source-of-truth reference:** Package "Acceptance criteria" bullet 3 (lines 17-18).
- **Proposed fix:** Build the error body using the project's envelope helper (or a `pydantic` model) and pass it as `detail`, populating `requestId` from the request-scoped correlation id (e.g. `request.state.request_id` set by middleware). See the snippet in Finding 1.

#### 3. No rate limiting on the login endpoint, despite tests claiming "rate-limiting interaction"
- **Citation:** `api/routes/auth.py:37-44` (entire handler — no decorator, dependency, or middleware reference)
- **Problem:** Acceptance criteria bullet 6 states one of the unit tests covers "rate-limiting interaction," implying rate limiting is part of the contract. The handler has no rate-limiting dependency, decorator, or call into a limiter. Either the test is asserting against behavior provided elsewhere (in which case the route still needs to be wired into it explicitly to be safe under refactors) or the requirement is silently unimplemented and the test is a stub.
- **Why it matters:** Without rate limiting, the same enumeration / brute-force attack from Finding 1 becomes industrial-scale: an attacker can issue tens of thousands of login attempts per minute against any account. Combined with Finding 1, this is a credential-stuffing accelerator.
- **Source-of-truth reference:** Package "Acceptance criteria" bullet 6 (lines 21-22) and implementer note ("All 6 unit tests pass") on line 5.
- **Proposed fix:** Attach the project's rate-limit dependency (e.g. `Depends(rate_limit('auth-login', per_ip=10, per_minute=1))` or equivalent SlowAPI / fastapi-limiter wiring) to the route, and ensure the unit test exercises it against this handler — not against the underlying limiter in isolation. If no project-wide limiter exists yet, this finding becomes a gating blocker.

#### 4. Timing side channel: bcrypt/argon2 path skipped when user is missing
- **Citation:** `api/routes/auth.py:39-43`
- **Problem:** Even after fixing Findings 1 and 2 to return identical status/body, the handler still takes a measurably different amount of time when `user` is `None` (no password hash verified) versus when `user` exists (a CPU-bound `verify_password` call runs). An attacker can time responses to enumerate accounts with high reliability — reproducing the very leak the design forbids.
- **Why it matters:** The acceptance criterion is "treat 'no such user' and 'wrong password' identically from the client's perspective." A timing oracle is observable to the client and therefore violates the criterion in spirit and in practice.
- **Source-of-truth reference:** Package "Acceptance criteria" bullet 4 (lines 19-20).
- **Proposed fix:** When the user is not found, still run `verify_password` against a fixed dummy hash of the same algorithm and cost as real hashes, then ignore the result. For example:
  ```python
  DUMMY_HASH = '$2b$12$' + 'a' * 53  # precomputed real hash of throwaway value
  ...
  user = await db.users.find_one({'email': body.email})
  password_hash = user['password_hash'] if user else DUMMY_HASH
  ok = verify_password(body.password, password_hash)
  if not user or not ok:
      raise HTTPException(...)  # see Finding 1
  ```
  This equalises the dominant cost (the KDF) across both branches.

### Medium

#### 5. Missing structured authentication-failure log / audit hook
- **Citation:** `api/routes/auth.py:40-43`
- **Problem:** Neither failure branch emits a log line or audit event. There is no record of failed login attempts, the email tried, or the source IP, which means the rate-limit and enumeration concerns above cannot be detected operationally.
- **Why it matters:** Even with rate limiting in place, an enterprise auth endpoint without per-attempt structured logs is effectively undebuggable in incident response and gives security monitoring nothing to alert on.
- **Source-of-truth reference:** Implied by acceptance criteria bullet 6 (rate-limiting interaction must be observable to be testable) and standard auth-endpoint hygiene.
- **Proposed fix:** Emit a structured log event (`event="auth.login.failed"`, `email_hash=...`, `reason="unknown_user"|"bad_password"`, `request_id=...`, `ip=...`). Hash or truncate the email if PII rules apply. Mirror with `event="auth.login.succeeded"` on the happy path.

#### 6. Email is matched case-sensitively / without normalization
- **Citation:** `api/routes/auth.py:39`
  ```python
  user = await db.users.find_one({'email': body.email})
  ```
- **Problem:** `body.email` is used verbatim as the lookup key. If the database stores emails lowercased (a common convention), users who type `Alice@Example.com` will be reported as "no such user" — re-triggering whichever failure path is configured. If the database stores them as-entered, two records can collide on the same logical address.
- **Why it matters:** Inconsistent normalization causes false negatives on login (user-visible bug), and silently weakens the enumeration mitigation by giving attackers another distinguishing signal (case-sensitive miss vs. password miss).
- **Source-of-truth reference:** Acceptance criteria bullet 1 (input contract) plus implicit design expectation that login matches account creation.
- **Proposed fix:** Normalize at the schema layer (`LoginBody.email: EmailStr` with a `@field_validator` that lowercases and strips), and ensure the same normalization is applied at signup. Consider matching on a `normalized_email` field rather than `email`.

#### 7. No defense against the `{}` / missing-field path beyond Pydantic's default 422
- **Citation:** `api/routes/auth.py:38` (signature `async def login(body: LoginBody)`)
- **Problem:** Acceptance criteria call out unit tests for "malformed body" and "missing field." FastAPI/Pydantic will return a default `422 Unprocessable Entity` with its own error shape, which again does not conform to the standard envelope `{ code, message, requestId }`.
- **Why it matters:** Same envelope-contract violation as Finding 2, but on a different code path. Clients written against the documented envelope will not be able to display these validation errors uniformly.
- **Source-of-truth reference:** Acceptance criteria bullets 3 and 6 (lines 17-22).
- **Proposed fix:** Register a `RequestValidationError` exception handler on the FastAPI app (or router) that re-shapes Pydantic errors into the standard envelope, with `code="VALIDATION_ERROR"` and `requestId` from the request scope.

### Low

#### 8. `find_one` projection pulls the entire user document, including `password_hash`, into application memory unconditionally
- **Citation:** `api/routes/auth.py:39`
- **Problem:** The query has no projection, so the whole user document — including the password hash and any other sensitive fields — is loaded even on the unknown-email path (where it is `None` anyway) and on the success path (where most fields are unused).
- **Why it matters:** Minor perf and minor blast-radius concern: anything that later logs the `user` dict (a common debugging mistake) would also log the hash. Tightening the projection now is a cheap defense-in-depth.
- **Source-of-truth reference:** General secure-by-default practice; not mandated by the acceptance criteria.
- **Proposed fix:** `await db.users.find_one({'email': normalized_email}, {'_id': 1, 'password_hash': 1, 'email': 1, 'roles': 1})` (adjust to whatever `issue_token(user)` actually needs).

#### 9. Route path is hardcoded inside the handler decorator instead of relying on the router prefix
- **Citation:** `api/routes/auth.py:37` `@router.post('/auth/login')`
- **Problem:** Hardcoding `/auth/login` on the handler, while the router will likely be mounted with a prefix elsewhere (e.g. `app.include_router(router, prefix='/auth')`), risks producing `/auth/auth/login` or, conversely, an unprefixed `/auth/login` that bypasses cross-cutting middleware applied at the prefix level.
- **Why it matters:** Cosmetic / structural; easy to fix and reduces a class of routing surprises.
- **Source-of-truth reference:** N/A — convention.
- **Proposed fix:** Construct the router with `APIRouter(prefix='/auth', tags=['auth'])` and use `@router.post('/login')` on the handler; mount with `app.include_router(router)` (no prefix at the include site).

#### 10. Implementer note overstates confidence
- **Citation:** Package lines 3-5 (implementer note).
- **Problem:** The note asserts "Reviewed the auth flow carefully, including how invalid credentials are handled" and "failure modes are obvious. Ready for production." The Critical and High findings above show the central security requirement of the ticket is unmet despite passing tests.
- **Why it matters:** Not a code defect, but a process signal: green tests are insufficient evidence that a security-sensitive acceptance criterion is satisfied; the test suite itself appears to be missing an assertion that the unknown-email and wrong-password responses are byte-identical (status, headers, body, timing). Worth flagging so the team strengthens the test, not just the code.
- **Source-of-truth reference:** Acceptance criteria bullets 4 and 6 (lines 19-22).
- **Proposed fix:** Add a unit test that performs both `unknown email` and `wrong password` requests and asserts equality of `response.status_code`, `response.json()`, and (loosely) response time. Make this test part of the acceptance gate before re-declaring the work production-ready.
