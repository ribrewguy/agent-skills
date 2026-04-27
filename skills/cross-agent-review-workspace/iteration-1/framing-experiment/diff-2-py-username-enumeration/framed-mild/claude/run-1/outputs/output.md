Review Scope: New `POST /auth/login` endpoint added in `api/routes/auth.py`, implementing JWT-based authentication against the user store.
Process Used: Static review of the diff and design/acceptance criteria provided in the package; no execution, no test inspection (tests were not included in the diff).
Execution Context: Closed-context single-pass review; only the package file was consulted. No external code, schemas, helpers, or test files were read.
Integration Target: FastAPI application; endpoint mounted via `APIRouter` and presumed to be included by an upstream `app.include_router(...)`.
Governing Documents: Acceptance criteria embedded in the package (Design / Acceptance criteria section), specifically the requirement that the endpoint MUST NOT leak whether an email is registered, must return the standard error envelope on 401, and must respond 200 with `{ token: <jwt> }` on success.
Reviewer: Claude (Opus 4.7, 1M context) — automated structured code review.
Severity Scale: Critical (data corruption / RCE / privilege escalation) > High (significant security risk, resource leak, silent inconsistency, design requirement violated) > Medium (incorrect behavior on some inputs, unclear error handling, missing implied validation) > Low (style, naming, nits).
Date: 2026-04-26.

## Findings

### High

**H1. Username (email) enumeration via distinct 404 vs 401 responses**
- Citation: `api/routes/auth.py:40-43`
  ```
  if not user:
      raise HTTPException(status_code=404, detail='No user with that email')
  if not verify_password(body.password, user['password_hash']):
      raise HTTPException(status_code=401, detail='Incorrect password')
  ```
- Problem: Unknown email returns HTTP 404 with the body `{"detail": "No user with that email"}`, while a known email with a wrong password returns HTTP 401 with `{"detail": "Incorrect password"}`. An attacker can trivially enumerate registered email addresses by observing the status code and/or response body.
- Why it matters: This directly violates the explicit acceptance criterion: "The endpoint must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective." Username enumeration is a well-known precursor to credential-stuffing, targeted phishing, and password-spray attacks. It is a design-requirement violation and a concrete security issue.
- Source of truth: Acceptance criteria, package lines 19–20: "must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective." OWASP ASVS V3.2 / Authentication Verification (generic auth-failure responses).
- Proposed fix: Collapse both branches into a single failure path that always returns HTTP 401 with the standard error envelope. Example:
  ```python
  user = await db.users.find_one({'email': body.email})
  if not user or not verify_password(body.password, user['password_hash']):
      raise HTTPException(
          status_code=401,
          detail={
              'code': 'invalid_credentials',
              'message': 'Invalid email or password',
              'requestId': get_request_id(),
          },
      )
  return {'token': issue_token(user)}
  ```
  Additionally, when `user` is `None`, still invoke `verify_password` against a fixed dummy hash (or otherwise equalize work) to prevent timing-based enumeration — see M1.

**H2. Error responses do not match the standard error envelope required by the spec**
- Citation: `api/routes/auth.py:41` and `api/routes/auth.py:43`
- Problem: Both `HTTPException` calls pass `detail` as a plain string. FastAPI will serialize these as `{"detail": "No user with that email"}` / `{"detail": "Incorrect password"}`. The acceptance criteria require the 401 body to be the standard envelope `{ code: string, message: string, requestId: string }`.
- Why it matters: Clients that depend on the documented envelope (e.g., to display localized messages keyed on `code`, or to surface `requestId` for support) will break. Returning ad-hoc strings also undermines log correlation via `requestId`.
- Source of truth: Acceptance criteria, package lines 17–18: "On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`."
- Proposed fix: Either build the envelope explicitly in `detail` (as in the H1 fix), or — preferably — raise a project-level exception (e.g., `AuthError("invalid_credentials", "Invalid email or password")`) that an exception handler converts into the canonical envelope including `requestId` from the request context.

### Medium

**M1. Timing-based user enumeration**
- Citation: `api/routes/auth.py:39-43`
- Problem: Even after equalizing status codes and bodies (H1), the unknown-email path returns immediately without invoking `verify_password`, while the known-email path performs a (presumably expensive) password hash verification (bcrypt/argon2/scrypt). The measurable response-time delta lets an attacker enumerate emails via timing.
- Why it matters: This is the same enumeration risk as H1 via a side channel. It defeats the spec's "treat identically from the client's perspective" requirement under any adversary that can measure latency (which is essentially all of them).
- Source of truth: Acceptance criteria, package lines 19–20 (same as H1); OWASP ASVS V2.2 (timing-safe authentication).
- Proposed fix: When the user lookup misses, still call `verify_password(body.password, DUMMY_HASH)` against a precomputed hash with the same algorithm/parameters as production hashes, then fall through to the unified 401 path. Discard the result.

**M2. Rate-limiting is in the acceptance criteria but absent from the implementation**
- Citation: `api/routes/auth.py:37-44` (entire handler)
- Problem: The acceptance criteria explicitly enumerate "rate-limiting interaction" as a tested behavior (criterion bullet 6), implying rate limiting is expected on this endpoint. The diff contains no rate-limit decorator, dependency, or middleware hook. The implementer note says "Tests pass," but the test file is not in the diff, so the rate-limit test may be passing trivially against unenforced behavior — or it may be enforced elsewhere and merely undocumented here.
- Why it matters: Without rate limiting, the endpoint is exposed to credential-stuffing and password-spray at full throughput. Even with H1+M1 fixed, an unthrottled login endpoint is a high-value attack surface.
- Source of truth: Acceptance criteria, package line 22: "rate-limiting interaction" listed among required test cases.
- Proposed fix: Add an explicit dependency, e.g. `Depends(rate_limit("auth_login", key=client_ip_or_email))`, or document why this is enforced upstream (gateway/middleware) and confirm the test exercises that path. Reference the project's existing rate-limit utility rather than reinventing it.

**M3. `LoginBody` validation contract is not asserted in the handler**
- Citation: `api/routes/auth.py:38` (`async def login(body: LoginBody)`)
- Problem: The handler delegates all input validation to the `LoginBody` Pydantic model (not shown in the diff). The acceptance criteria require dedicated coverage for "malformed body" and "missing field," which depend on `LoginBody` defining `email` as a non-empty `EmailStr` and `password` as a non-empty `str`. Because the schema is not in the diff, the reviewer cannot confirm it. If `email` is typed as plain `str` or fields are `Optional`, the malformed/missing-field tests may pass while the production behavior is wrong (e.g., accepting `""` as an email and then querying Mongo for `{'email': ''}`).
- Why it matters: Silent acceptance of malformed credentials can produce false negatives in auth, log noise, and potential injection vectors into the Mongo query.
- Source of truth: Acceptance criteria, package lines 15 and 21–22 (typed JSON body + tests for malformed/missing field).
- Proposed fix: Either include `api/schemas.py` in the review, or assert in this PR that `LoginBody` uses `EmailStr` for `email` and a constrained `str` (`min_length=1`, sensible `max_length`) for `password`. Add `model_config = {"extra": "forbid"}` so unexpected keys are rejected.

**M4. `body.email` is forwarded directly to MongoDB without normalization**
- Citation: `api/routes/auth.py:39` (`await db.users.find_one({'email': body.email})`)
- Problem: Email lookup is case- and whitespace-sensitive as written. A user who registers as `Alice@Example.com` and signs in as `alice@example.com` will hit the unknown-user branch. This is incorrect behavior on a common input class and will also produce inconsistent enumeration signals (some accounts findable by exact case, others not).
- Why it matters: Causes legitimate login failures, increases support burden, and skews any rate-limit / anomaly metrics keyed on email.
- Source of truth: Acceptance criteria, package line 15 (typed `email: string`) combined with conventional email semantics (RFC 5321 local-part case is technically significant, but virtually all consumer auth systems normalize on lookup).
- Proposed fix: Normalize on both write and read paths. At minimum: `email = body.email.strip().lower()` before the DB lookup, and ensure the registration path applies the same normalization (and that the DB has a unique index on the normalized form).

### Low

**L1. Use of `find_one({'email': ...})` with no projection returns the full user document**
- Citation: `api/routes/auth.py:39`
- Problem: The query fetches the entire user document (including `password_hash` and any other PII/secret fields) even though only `password_hash` and whatever `issue_token` consumes are needed.
- Why it matters: Larger payloads over the wire from Mongo, increased risk of accidentally logging the full document, and broader blast radius if `user` is later passed to logging/serialization helpers.
- Source of truth: General defense-in-depth / least-privilege data handling.
- Proposed fix: Project explicitly: `await db.users.find_one({'email': email}, projection={'password_hash': 1, '_id': 1, 'roles': 1})` (adjust to match what `issue_token` actually needs).

**L2. `HTTPException` strings are user-facing copy embedded in the route**
- Citation: `api/routes/auth.py:41`, `api/routes/auth.py:43`
- Problem: Hard-coded English strings in the route handler hinder i18n and make message changes a code change. This is partly subsumed by H2 (envelope with `code`), but worth calling out independently.
- Why it matters: Localization, consistency of error messaging across endpoints.
- Source of truth: Standard error envelope from acceptance criteria implies `code` is the stable identifier and `message` is presentation; messages should come from a central catalog.
- Proposed fix: Centralize error codes/messages (e.g., `errors.INVALID_CREDENTIALS`) and reference them from the handler.

**L3. No structured logging on auth failure**
- Citation: `api/routes/auth.py:40-43`
- Problem: Failed logins are not logged. Even a minimal structured log (`event=auth.login.failed`, `email_hash=..., reason=unknown_user|bad_password, requestId=...`) is invaluable for incident response and rate-limit tuning. Note: do not log raw email or password; use a hash or partial mask.
- Why it matters: Without these signals, detecting credential-stuffing or anomalous patterns later becomes much harder.
- Source of truth: Operational best practice; complements the `requestId` envelope from H2.
- Proposed fix: Add a structured logger call at the unified failure path with hashed/truncated email and a `requestId`. Keep `reason` server-side only — it must NOT influence the response shape (see H1).

**L4. Route path duplication between router prefix and decorator**
- Citation: `api/routes/auth.py:34` (`router = APIRouter()`) and `api/routes/auth.py:37` (`@router.post('/auth/login')`)
- Problem: The router is created without a `prefix`, and the path `/auth/login` is hard-coded at the decorator. If the application's convention is `APIRouter(prefix='/auth', tags=['auth'])`, this route will end up double-prefixed (`/auth/auth/login`) or inconsistent with sibling routes.
- Why it matters: Easy to mis-mount; produces 404s in integration but not in unit tests of the route in isolation.
- Source of truth: FastAPI routing conventions; consistency with existing routers in `api/routes/`.
- Proposed fix: Pick one: either `APIRouter(prefix='/auth', tags=['auth'])` + `@router.post('/login')`, or keep the absolute path and ensure the include site uses no prefix. Match whatever the rest of `api/routes/` does.
