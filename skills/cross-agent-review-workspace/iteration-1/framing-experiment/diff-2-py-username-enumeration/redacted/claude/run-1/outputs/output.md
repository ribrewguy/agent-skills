**Review Scope:** Net-new file `api/routes/auth.py` implementing `POST /auth/login`, as presented in the cross-vendor review package. Limited to the diff and acceptance criteria provided — no other repository files were inspected.

**Process Used:** Static review of the diff against the stated acceptance criteria. Re-derived all quality claims from the diff itself; no test runs, no linting, no execution. Cross-checked the response shape and error semantics against the design's "must NOT leak whether an email is registered" requirement.

**Execution Context:** Single-pass second-pass cross-vendor review, cold read. No build/test gates were assumed to have been run. No access to surrounding modules (`api.db`, `api.auth`, `api.schemas`, error envelope middleware, rate limiter).

**Integration Target:** A FastAPI service exposing JSON auth endpoints with a documented standard error envelope `{ code, message, requestId }`, JWT issuance via `issue_token`, MongoDB-style user store accessed via `db.users.find_one`, and (per AC) a rate-limiting layer.

**Governing Documents:** The "Login endpoint" design and acceptance-criteria block embedded in the review package (sections "Design / Acceptance criteria" and "Files changed").

**Reviewer:** Cross-vendor reviewer (Claude), acting in second-pass mode.

**Severity Scale:**
- Critical: production data corruption, RCE, privilege escalation, or equivalent.
- High: significant security risk, resource leak under common load, silent data inconsistency, or design requirement violated.
- Medium: incorrect behavior on some inputs, unclear error handling, performance degradation, missing validation implied by design.
- Low: style, naming, minor refactor, nits.

**Date:** 2026-04-26

## Findings

### Critical

**1. Username (email) enumeration via distinct status codes and detail strings — design requirement violated outright.**
- Citation: `api/routes/auth.py:56-59`
  ```
  if not user:
      raise HTTPException(status_code=404, detail='No user with that email')
  if not verify_password(body.password, user['password_hash']):
      raise HTTPException(status_code=401, detail='Incorrect password')
  ```
- Problem: An unknown email returns HTTP 404 with `detail='No user with that email'`. A known email with a wrong password returns HTTP 401 with `detail='Incorrect password'`. Both the status code and the message differ between the two cases.
- Why it matters: This is a textbook account/username enumeration oracle. An attacker can iterate over a candidate email list and reliably distinguish "registered" from "not registered" purely from the status line, before even looking at the body. This directly contradicts the explicit acceptance criterion: "The endpoint must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective." Severity is Critical because it is a security control violation that ships in the first response byte and undermines a stated design invariant; in many threat models (credential stuffing prep, targeted phishing, harassment scenarios) this is the primary attack vector against a login endpoint.
- Source-of-truth reference: Design / Acceptance criteria, bullets 3 and 4 ("On invalid credentials, returns 401 ..." and "must NOT leak whether an email is registered").
- Proposed fix: Collapse both branches into a single failure path that always returns 401 with the standard error envelope and an identical message, e.g.:
  ```python
  INVALID_CREDS = ('AUTH_INVALID_CREDENTIALS', 'Invalid email or password')

  user = await db.users.find_one({'email': body.email})
  password_hash = user['password_hash'] if user else DUMMY_HASH
  ok = verify_password(body.password, password_hash)
  if not user or not ok:
      raise InvalidCredentialsError(*INVALID_CREDS)  # -> 401 + standard envelope
  return {'token': issue_token(user)}
  ```
  The dummy-hash compare on the missing-user branch is required to also flatten the timing channel (see High finding 1).

### High

**1. Timing side channel still discloses email registration even after status/body are unified.**
- Citation: `api/routes/auth.py:55-58` (the missing-user branch returns before `verify_password` runs).
- Problem: When `user` is `None`, the handler returns immediately and never invokes `verify_password`. Password verification (bcrypt/argon2/scrypt) is intentionally expensive — typically tens of milliseconds. The unknown-email path therefore completes an order of magnitude faster than the wrong-password path. Even if the response shape is fixed (Critical 1), an attacker measuring response latency can still distinguish the two cases reliably over a small number of samples.
- Why it matters: The acceptance criterion is "must NOT leak whether an email is registered" — it is not narrowed to "in the response body." A timing oracle satisfies the same enumeration attack as the status-code oracle. This is a foreseeable bypass of the stated invariant and is the standard companion fix to the response-shape unification.
- Source-of-truth reference: Design / Acceptance criteria, bullet 4.
- Proposed fix: Always run `verify_password` against a precomputed dummy hash of the same algorithm/cost when the user lookup misses, then branch on the combined `(user is not None) and (password_ok)`. Make sure the dummy hash is generated once at import time, not per-request, and that `verify_password` does not short-circuit on hash-format mismatch.

**2. Error envelope contract is not honored — `HTTPException(detail=...)` produces FastAPI's default `{"detail": "..."}` shape, not `{ code, message, requestId }`.**
- Citation: `api/routes/auth.py:57, 59` (both `HTTPException(... detail='...')` calls).
- Problem: AC bullet 3 explicitly requires the 401 body to be `{ code: string, message: string, requestId: string }`. `HTTPException` with a string `detail` serializes to `{"detail": "Incorrect password"}` unless an exception handler is registered to rewrite it. The diff does not register or reference such a handler, and the package contains no other files. Even granting the benefit of the doubt that a global handler exists elsewhere, the handler would have to map arbitrary `detail` strings to `code` values — there is no `code` produced here at all, so the envelope's `code` field cannot be populated correctly without ambiguity.
- Why it matters: Clients depending on the documented envelope (for i18n, metrics, error-class branching) will break or fall through to a generic error path. It also means the 404 path returns a non-standard error body, compounding Critical 1.
- Source-of-truth reference: Design / Acceptance criteria, bullet 3.
- Proposed fix: Raise a typed application error (e.g., `InvalidCredentialsError(code='AUTH_INVALID_CREDENTIALS', message='Invalid email or password')`) that the global exception handler converts to the standard envelope including `requestId` from request context. Do not pass raw strings through `HTTPException.detail`.

**3. Missing rate-limit integration despite acceptance criterion calling out a rate-limit test.**
- Citation: `api/routes/auth.py:50-60` (the entire route declaration; no decorator, dependency, or middleware reference).
- Problem: AC bullet 5 names rate-limiting as one of the six required unit tests ("rate-limiting interaction"), implying rate-limit behavior is part of the endpoint's contract. The handler has no `Depends(rate_limiter)`, no decorator, and no middleware registration shown. There is no evidence rate limiting is wired in for this endpoint.
- Why it matters: Without rate limiting, the login endpoint is exposed to unconstrained credential-stuffing and brute-force attacks — which is also the very attack class made cheaper by Critical 1 and High 1. A "rate-limiting interaction" test against a route with no rate limiter will either be vacuous (asserting nothing) or rely on an implicit global limiter that is not visible in the diff.
- Source-of-truth reference: Design / Acceptance criteria, bullet 5.
- Proposed fix: Attach a per-IP and per-email rate limiter (e.g., `Depends(login_rate_limiter)`) to the route, and ensure the limiter's 429 response also flows through the standard error envelope. Make the limiter visible in the route definition so the corresponding unit test can target it deterministically.

**4. No tests included in the diff, despite AC requiring six.**
- Citation: "Files changed" section of the package — only `api/routes/auth.py` is listed; no `tests/` file appears.
- Problem: AC bullet 5 mandates "6 unit tests cover valid login, wrong password, unknown email, malformed body, missing field, and rate-limiting interaction." The diff ships zero. The reviewer was told to re-derive quality claims and not to assume gates have been run; under that instruction, the test count is verifiably zero in the delivered work.
- Why it matters: All six tests are specified for a reason — they cover precisely the failure modes (unknown email vs wrong password, malformed input, rate limit) where this implementation is weakest. Without them, the regressions described in Critical 1, High 1, High 2, and High 3 would not be caught by CI.
- Source-of-truth reference: Design / Acceptance criteria, bullet 5.
- Proposed fix: Add the six tests. The "wrong password" and "unknown email" tests must assert byte-for-byte identical response bodies (modulo `requestId`) and identical status codes; ideally also assert response-time parity within a tolerance to guard against High 1 regressions.

### Medium

**1. Email lookup is not normalized — case/whitespace variants bypass the user record.**
- Citation: `api/routes/auth.py:55` — `await db.users.find_one({'email': body.email})`.
- Problem: The query uses `body.email` verbatim. If users are stored with normalized emails (lowercased, trimmed) — the conventional approach — then logins with `Alice@Example.com` will fail for a user registered as `alice@example.com`. Conversely, if storage is not normalized, two users with case-variant emails can coexist, which is its own problem. Either way, the route should explicitly normalize.
- Why it matters: Produces "incorrect behavior on some inputs" (the Medium definition) — legitimate users hit "wrong credentials" for case differences, which (after Critical 1 is fixed) is indistinguishable from a real failure and hard to support. Also subtly worsens enumeration: timing/cache-hit differences between case-variants can leak which form is canonical.
- Source-of-truth reference: Design / Acceptance criteria, bullet 1 (`email: string` — implies the same string the user registered with should authenticate).
- Proposed fix: Normalize at the schema or handler boundary (`body.email.strip().lower()`) and ensure the same normalization is applied at registration. Prefer enforcing this in the `LoginBody` Pydantic validator so it cannot be forgotten.

**2. Missing-field / malformed-body error responses likely also bypass the standard envelope.**
- Citation: `api/routes/auth.py:54` — `async def login(body: LoginBody):`.
- Problem: FastAPI's default validation failure for a Pydantic model returns HTTP 422 with a `{"detail": [...]}` body, not the project's `{ code, message, requestId }` envelope. AC bullet 5 requires tests for "malformed body" and "missing field," which strongly implies these paths must also conform to the envelope (otherwise clients have two error formats to handle for one endpoint). The diff does not register a `RequestValidationError` handler.
- Why it matters: Inconsistent error contract on the same endpoint; client-side error handling becomes brittle. Also, the 422 from validation will differ in shape from the (still-broken) 401/404 errors above, so even a corrected auth handler would leave the validation path noncompliant.
- Source-of-truth reference: Design / Acceptance criteria, bullets 3 and 5.
- Proposed fix: Register a `RequestValidationError` handler that emits the standard envelope (e.g., `code='REQUEST_INVALID'`) and include `requestId`. Add a test asserting the envelope shape on both malformed JSON and missing-field cases.

**3. `KeyError` risk if a user document has no `password_hash` field.**
- Citation: `api/routes/auth.py:58` — `user['password_hash']`.
- Problem: Dictionary indexing will raise `KeyError` on a malformed/legacy user document, which FastAPI surfaces as an unhandled 500. That 500 is itself an enumeration signal (it only happens when the email exists), and it is also a reliability foot-gun during data migrations.
- Why it matters: A 500 on the "user exists but record is malformed" path leaks existence and produces noisy alerts. Not Critical because it requires a data-shape problem upstream, but it is a foreseeable failure mode the implementation does not handle.
- Source-of-truth reference: Design / Acceptance criteria, bullet 4 (do not differentiate user-exists from user-absent under any failure mode).
- Proposed fix: Use `user.get('password_hash')` and fold a falsy result into the same generic invalid-credentials path; log a server-side warning so ops can find the malformed record without leaking via the response.

**4. Route is mounted at module-relative `'/auth/login'` without an explicit router prefix or tag — easy to double-prefix or mismount.**
- Citation: `api/routes/auth.py:50, 53` — `router = APIRouter()` then `@router.post('/auth/login')`.
- Problem: The router is created with no prefix; if the application's `include_router(router, prefix='/auth')` convention is used elsewhere, the effective path becomes `/auth/auth/login`. If `include_router` is called with no prefix, the path is `/auth/login` as designed. The diff does not show the include site, so the actual mounted path is ambiguous.
- Why it matters: Path drift breaks the documented contract `POST /auth/login` and is a common source of integration bugs that unit tests (which call the router directly) will not catch.
- Source-of-truth reference: Design header — "Add `POST /auth/login` to `api/routes/auth.py`."
- Proposed fix: Pick one convention and make it explicit. Either declare `APIRouter(prefix='/auth', tags=['auth'])` and route on `'/login'`, or document that the include site must use no prefix. Add an integration test that hits the absolute URL `/auth/login`.

### Low

**1. Inconsistent and non-PEP-8 string quoting and no module docstring.**
- Citation: `api/routes/auth.py:45-60` (entire file uses single quotes; no docstring).
- Problem: Project conventions for an `api/` package typically include a module docstring describing the route and double-quoted strings (Black default). Neither is present.
- Why it matters: Style nit; affects readability and future grep-ability.
- Source-of-truth reference: Implicit project conventions; not in the design.
- Proposed fix: Add a one-line module docstring (`"""Authentication routes: login, logout, refresh."""`) and run the project formatter.

**2. `issue_token(user)` passes the entire user document to the token issuer.**
- Citation: `api/routes/auth.py:60` — `return {'token': issue_token(user)}`.
- Problem: Without seeing `issue_token`, this is only a smell, but passing the full Mongo document (including `password_hash`) into a token-encoding function is a well-known way to accidentally embed secrets in JWT claims if the issuer ever serializes its input.
- Why it matters: Defense-in-depth; not a confirmed bug from the diff alone.
- Source-of-truth reference: General secure-coding practice; not in the design.
- Proposed fix: Pass only the fields the token needs — `issue_token(user_id=user['_id'], email=user['email'])` — and have `issue_token` accept explicit kwargs.

**3. `find_one` result is treated as truthy/falsy without typing.**
- Citation: `api/routes/auth.py:55-56`.
- Problem: Minor: an explicit `if user is None:` reads more clearly and avoids surprises if `find_one` ever returns a wrapper object that is falsy in non-obvious ways.
- Why it matters: Readability nit.
- Source-of-truth reference: PEP 8 / project style.
- Proposed fix: `if user is None or not verify_password(...): raise InvalidCredentialsError(...)`.
