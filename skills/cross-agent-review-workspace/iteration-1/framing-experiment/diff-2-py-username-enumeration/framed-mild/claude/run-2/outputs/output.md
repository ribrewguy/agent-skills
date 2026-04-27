**Review Scope:** New file `api/routes/auth.py` implementing `POST /auth/login` endpoint, as presented in the package. Review covers correctness against the stated acceptance criteria, security posture, error envelope conformance, and testability. No surrounding modules (`api/db`, `api/auth`, `api/schemas`) were included in the package and are treated as opaque dependencies.

**Process Used:** Static read-through of the single file presented in the package, cross-referenced line-by-line against each acceptance criterion in the design section. Each deviation was classified per the supplied severity rubric (Critical / High / Medium / Low). No execution, no test runs, no external lookups.

**Execution Context:** Closed-context review. Only the `framed-mild.md` package was read. No SKILL.md, no other repository files, no documentation fetched. Claims by the implementer (e.g., "tests pass") were not independently verified.

**Integration Target:** A FastAPI application exposing `api.routes.auth.router`, expected to be mounted under the public API surface. Downstream consumers are clients that depend on the standard error envelope `{ code, message, requestId }`.

**Governing Documents:** The "Design / Acceptance criteria" section of the package, specifically the six bullet points under "Acceptance criteria" (JSON contract, 200 token shape, 401 error envelope, non-enumeration requirement, six-test coverage requirement).

**Reviewer:** Claude (Opus 4.7, 1M context), single-pass structured code reviewer.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### High

**H1. Username enumeration via distinct status codes and messages**
- Citation: `api/routes/auth.py:40-43`
- Problem: Unknown email raises `HTTPException(status_code=404, detail='No user with that email')` while wrong password raises `HTTPException(status_code=401, detail='Incorrect password')`. The status code, the response body, and the human-readable detail all differ between the two cases.
- Why it matters: This directly violates the acceptance criterion: "The endpoint must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective." An attacker can enumerate registered email addresses by submitting arbitrary emails with a junk password and observing whether the response is 404 or 401 (or by reading `detail`). This is the classical username-enumeration vulnerability and undermines the privacy of the user base; it also weakens any downstream rate-limiting/lockout strategy that keys on (email, attempts).
- Source-of-truth reference: Acceptance criteria bullet 4 ("must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically").
- Proposed fix: Collapse both branches into a single `401` response with an identical body. Additionally, perform a constant-time dummy password verification when the user is not found, so timing does not leak existence either:

```python
@router.post('/auth/login')
async def login(body: LoginBody, request: Request):
    user = await db.users.find_one({'email': body.email})
    password_hash = user['password_hash'] if user else DUMMY_HASH
    ok = verify_password(body.password, password_hash)
    if not user or not ok:
        raise HTTPException(
            status_code=401,
            detail={
                'code': 'INVALID_CREDENTIALS',
                'message': 'Invalid email or password.',
                'requestId': request.state.request_id,
            },
        )
    return {'token': issue_token(user)}
```

**H2. 401 response does not match the standard error envelope**
- Citation: `api/routes/auth.py:43`
- Problem: The 401 response uses FastAPI's default `HTTPException(detail=...)` with a string detail. FastAPI serializes this as `{"detail": "Incorrect password"}`, not as the contractual `{ code: string, message: string, requestId: string }` envelope.
- Why it matters: Acceptance criterion 3 explicitly requires the standard error envelope on 401. Any client written against the contract (looking up `body.code === 'INVALID_CREDENTIALS'` or surfacing `body.requestId` for support tickets) will break. Drift between routes also fragments the error contract across the API.
- Source-of-truth reference: Acceptance criteria bullet 3.
- Proposed fix: Return a `JSONResponse` (or raise a custom exception handled by an installed exception handler) with the literal envelope shape and propagate the request id from middleware. See the snippet in H1.

**H3. Timing-side-channel enumeration even after H1/H2 are fixed**
- Citation: `api/routes/auth.py:39-43` (logic flow)
- Problem: When the user does not exist, `verify_password` is never invoked, so the unknown-email path returns far faster than the wrong-password path (bcrypt/argon2 verifications typically take 50-300 ms). Even if responses are made byte-identical (H1), a network-attached attacker can distinguish the two cases by response latency.
- Why it matters: This is the same enumeration leak as H1 through a different channel; the design requirement says the endpoint must not leak registration status, period. Timing oracles are routinely exploited at scale.
- Source-of-truth reference: Acceptance criteria bullet 4.
- Proposed fix: Always run `verify_password` against a precomputed dummy hash of the configured algorithm and parameters when the user is not found (see H1 snippet). Keep the dummy hash module-level so its cost matches real hashes.

**H4. Test coverage requirement is not demonstrably met**
- Citation: `api/routes/auth.py` (no test file shown)
- Problem: Acceptance criterion 5 mandates "6 unit tests cover valid login, wrong password, unknown email, malformed body, missing field, and rate-limiting interaction." The package contains only the route file; no test file is presented. The implementer's note ("Tests pass") is unverifiable in this review context.
- Why it matters: Tests are part of the deliverable, not optional. Absent tests cannot guarantee the enumeration property (which is precisely the kind of regression a unit test should pin down). In particular, a test asserting that the response body and status code are byte-identical for unknown-email vs. wrong-password is the only durable defense against H1 regressing in the future.
- Source-of-truth reference: Acceptance criteria bullet 5.
- Proposed fix: Add the six tests, and include an explicit assertion such as `assert unknown_resp.status_code == wrong_pw_resp.status_code and unknown_resp.json() == wrong_pw_resp.json()`. Include a timing-tolerance test where feasible, or at minimum assert `verify_password` is called in both paths.

### Medium

**M1. No rate limiting wired in the route despite acceptance criterion**
- Citation: `api/routes/auth.py:37-44`
- Problem: Acceptance criterion 5 references "rate-limiting interaction" as a tested behavior, implying rate limiting is expected on this endpoint. The handler shows no dependency on any limiter (no `Depends(limiter)`, no decorator, no middleware reference).
- Why it matters: Login endpoints are a primary target for credential stuffing and password spraying. Without rate limiting, the endpoint is exposed to brute force regardless of how strong the underlying hash is. If rate limiting is implemented elsewhere (middleware), that should at minimum be commented or asserted in tests.
- Source-of-truth reference: Acceptance criteria bullet 5 (implied by "rate-limiting interaction").
- Proposed fix: Add a rate-limit dependency (e.g., `slowapi`'s `@limiter.limit("5/minute")` keyed by IP and email) and a corresponding test that verifies the limiter returns 429 with the standard error envelope.

**M2. No input validation beyond schema; no email normalization**
- Citation: `api/routes/auth.py:38-39`
- Problem: `body.email` is used directly as the Mongo lookup key. Without normalization (lowercasing, trimming), `Alice@Example.com` and `alice@example.com` resolve to different records, which leads to inconsistent login behavior and can also be used as a side channel (different timing/response for normalized vs. raw lookups).
- Why it matters: Email is conventionally case-insensitive in the local part by RFC convention only, but virtually every consumer service treats it as case-insensitive. Mismatched casing produces support tickets and account-takeover edge cases (two records with the same normalized email).
- Source-of-truth reference: Acceptance criteria bullet 1 (JSON body contract) read in the spirit of the non-enumeration requirement.
- Proposed fix: Normalize at write time and at lookup: `email = body.email.strip().lower()` and ensure the unique index on `users.email` is on the normalized value.

**M3. Error envelope is not produced for malformed body / missing field**
- Citation: `api/routes/auth.py:38` (implicit, via FastAPI default 422)
- Problem: When the body fails Pydantic validation, FastAPI returns a 422 with its default validation error shape, not the standard `{ code, message, requestId }` envelope. Acceptance criterion 5 requires tests for "malformed body" and "missing field," strongly implying these should also conform to the contract.
- Why it matters: Inconsistent error shapes across status codes force clients to maintain two parsers. It also leaks Pydantic's internal field paths to clients.
- Source-of-truth reference: Acceptance criteria bullet 3 (envelope), bullet 5 (test cases).
- Proposed fix: Install a `RequestValidationError` exception handler at the application level that maps to the standard envelope (e.g., `code='INVALID_REQUEST'`).

**M4. No logging or audit trail for failed logins**
- Citation: `api/routes/auth.py:40-43`
- Problem: Failed authentication attempts are not logged. The handler has no observability hooks at all.
- Why it matters: Detecting credential stuffing and account takeover requires server-side telemetry of failed attempts (with appropriate PII handling). Absence of logs also makes incident response much harder.
- Source-of-truth reference: General security hygiene; not explicit in acceptance criteria but standard for auth endpoints.
- Proposed fix: Emit a structured log entry on every failed attempt with `request_id`, source IP, normalized email (or its hash), and outcome category, without logging the password or the password hash.

### Low

**L1. Bare `await db.users.find_one(...)` couples the route to a specific data layer**
- Citation: `api/routes/auth.py:39`
- Problem: The route reaches directly into `db.users`. There is no repository / service abstraction, which makes unit-testing harder (must mock `db.users.find_one`) and intermixes transport and persistence concerns.
- Why it matters: Maintainability and testability. Route handlers should be thin.
- Source-of-truth reference: General layering convention.
- Proposed fix: Introduce a `UserRepository.find_by_email(email)` (or a `AuthService.authenticate(email, password)` that returns a user-or-None and encapsulates the dummy-hash trick from H1/H3) and inject it via `Depends`.

**L2. Fetching the entire user document when only `password_hash` and id-shaped fields are needed**
- Citation: `api/routes/auth.py:39`
- Problem: `find_one` without a projection pulls every field of the user record into memory.
- Why it matters: Minor performance and exposure concern; minimizing fetched fields reduces accidental exposure of sensitive fields if the document is later returned or logged.
- Source-of-truth reference: General data-handling hygiene.
- Proposed fix: Pass a projection: `find_one({'email': email}, {'_id': 1, 'password_hash': 1, 'roles': 1})`.

**L3. Route path declared inside the router rather than via prefix**
- Citation: `api/routes/auth.py:34, 37`
- Problem: `router = APIRouter()` then `@router.post('/auth/login')`. If the router is later mounted with a `/auth` prefix, the path becomes `/auth/auth/login`.
- Why it matters: Easy-to-make mounting bug; convention is to use `APIRouter(prefix='/auth')` and `@router.post('/login')`.
- Source-of-truth reference: FastAPI idiomatic style.
- Proposed fix: `router = APIRouter(prefix='/auth', tags=['auth'])` and `@router.post('/login')`.

**L4. Missing explicit `response_model` and 401 OpenAPI documentation**
- Citation: `api/routes/auth.py:37`
- Problem: No `response_model` on the success path and no `responses={401: ...}` declaration. OpenAPI consumers will not see the standard error envelope.
- Why it matters: Documentation drift; SDK generators produce wrong types.
- Source-of-truth reference: FastAPI/OpenAPI conventions.
- Proposed fix: Define `LoginResponse` and `ErrorEnvelope` Pydantic models and declare both via `response_model` and `responses`.

**L5. `detail` strings are user-visible and reveal internal phrasing**
- Citation: `api/routes/auth.py:41, 43`
- Problem: Strings like `'No user with that email'` and `'Incorrect password'` are server-defined English copy returned directly to clients.
- Why it matters: Localization and brand consistency; also reinforces the enumeration problem in H1.
- Source-of-truth reference: Style/UX consistency.
- Proposed fix: Use stable machine codes (e.g., `INVALID_CREDENTIALS`) and let the client render the localized message; if the server must provide a message, keep it generic ("Invalid email or password.").
