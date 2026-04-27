**Review Scope:** New file `api/routes/auth.py` implementing `POST /auth/login` endpoint, against the supplied design / acceptance criteria.

**Process Used:** Manual cold read of the diff embedded in the package; static reasoning against the acceptance criteria. No code was executed, no tests were run, no linters or SAST tools were invoked. Quality claims in the package are not assumed; all conformance assertions are re-derived from the snippet itself.

**Execution Context:** Closed-context single-pass review. Only the supplied package was read; no surrounding repository (e.g., `api/db`, `api/auth`, `api/schemas`, error-envelope middleware, rate limiter, test suite) was inspected. Findings about referenced modules are necessarily based on the call sites visible in the diff.

**Integration Target:** FastAPI application, routes mounted via `APIRouter`, persistence via an async `db.users` collection (Mongo-style `find_one`), password verification + JWT issuance via `api.auth`, request validation via a Pydantic `LoginBody` schema in `api.schemas`.

**Governing Documents:** The "Design / Acceptance criteria" section of the supplied package (lines 23-38), specifically the requirements that responses be 200/401, that the error envelope be `{ code, message, requestId }`, that registered-vs-unregistered email MUST NOT be distinguishable, and that 6 specific unit tests exist.

**Reviewer:** Cross-vendor second-pass reviewer (Claude, Opus 4.7, 1M context), acting cold.

**Severity Scale:**
- Critical: production data corruption, RCE, privilege escalation, or equivalent.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior on some inputs, unclear error handling, performance degradation, missing validation implied by the design.
- Low: style, naming, minor refactors, nits.

**Date:** 2026-04-26

## Findings

### Critical

**1. Username (email) enumeration via distinct status code on unknown user — acceptance criterion directly violated.**
- Citation: `api/routes/auth.py:56-57`
  ```
  if not user:
      raise HTTPException(status_code=404, detail='No user with that email')
  ```
- Problem: When the email is not present in `db.users`, the endpoint returns HTTP **404** with the literal string `"No user with that email"`. When the email exists but the password is wrong, it returns HTTP **401** with `"Incorrect password"` (line 59). A client (or attacker script) can therefore trivially distinguish "registered email" from "unregistered email" by reading either the status code or the `detail` string.
- Why it matters: This is the exact failure mode the acceptance criteria call out as forbidden ("The endpoint must NOT leak whether an email is registered. Treat 'no such user' and 'wrong password' identically from the client's perspective."). It enables credential-stuffing target lists, account-existence checks for harassment / doxxing, and password-reset oracle attacks. Severity is Critical because the design's headline security requirement is broken on the primary code path.
- Source-of-truth reference: Acceptance criteria, package lines 35-36 ("On invalid credentials, returns 401…"; "must NOT leak whether an email is registered").
- Proposed fix: Collapse both branches into a single 401 response that uses the standard error envelope, with one shared message such as `"Invalid email or password"`. Example:
  ```python
  INVALID = HTTPException(
      status_code=401,
      detail={"code": "AUTH_INVALID_CREDENTIALS",
              "message": "Invalid email or password",
              "requestId": request_id},
  )
  user = await db.users.find_one({'email': body.email})
  if not user or not verify_password(body.password, user['password_hash']):
      raise INVALID
  ```
  Additionally, run `verify_password` against a fixed dummy hash when `user is None` (see Finding 2) so timing does not re-introduce the oracle.

### High

**2. Timing side-channel re-introduces the same enumeration oracle the spec forbids.**
- Citation: `api/routes/auth.py:55-59` (control flow as a whole).
- Problem: Even after Finding 1 is fixed at the response layer, the unknown-user branch returns *immediately* after the DB lookup, while the known-user branch additionally runs `verify_password` (typically a deliberately slow KDF such as bcrypt/argon2 on the order of 50-300ms). The wall-clock difference is large, stable, and remotely measurable. An attacker can enumerate accounts via response latency alone.
- Why it matters: The acceptance criterion says "Treat 'no such user' and 'wrong password' identically from the client's perspective." A measurable timing delta is observable from the client and therefore violates the requirement. This is a well-known and routinely exploited pattern against login endpoints.
- Source-of-truth reference: Acceptance criteria, package line 36.
- Proposed fix: Always perform a password verification, even when the user record is missing, against a precomputed dummy hash of the same algorithm/cost as production hashes. Example:
  ```python
  DUMMY_HASH = settings.AUTH_DUMMY_HASH  # precomputed bcrypt/argon2 hash
  ok = verify_password(body.password,
                       user['password_hash'] if user else DUMMY_HASH)
  if not user or not ok:
      raise INVALID
  ```
  Optionally enforce a minimum response time floor as defense in depth.

**3. Error response shape does not match the standard error envelope.**
- Citation: `api/routes/auth.py:57, 59`
- Problem: `HTTPException(status_code=..., detail=<str>)` causes FastAPI to emit `{"detail": "<str>"}`. The acceptance criteria mandate the envelope `{ code: string, message: string, requestId: string }`. The implementation supplies neither `code` nor `requestId`, and the field name is `detail`, not `message`. Clients written against the spec will fail to parse error responses and will not have a `requestId` to correlate with logs.
- Why it matters: This is a contract violation visible to every consumer. It also breaks observability (no `requestId` to thread through logs / support tickets) and silently disagrees with whatever shape the rest of the API uses.
- Source-of-truth reference: Acceptance criteria, package lines 33-34.
- Proposed fix: Either (a) raise via a project-standard exception class that an exception handler converts into the envelope, or (b) return a `JSONResponse` with the envelope explicitly, populating `requestId` from the inbound request context (e.g., a middleware that puts a UUID on `request.state.request_id`). Ensure the success path is also documented as `{ token: <jwt> }` per spec — that part is correct.

**4. Acceptance criterion for tests is unmet — the diff ships zero tests.**
- Citation: Package "Files changed" section (lines 41-60); only `api/routes/auth.py` is included.
- Problem: The spec requires 6 unit tests covering: valid login, wrong password, unknown email, malformed body, missing field, and rate-limiting interaction. None are present in the changeset.
- Why it matters: Without these tests, regressions on the security-critical behavior (especially the equal-treatment requirement and the envelope shape) cannot be enforced in CI. The "rate-limiting interaction" test is particularly important because no rate limiting is visible in the implementation either (see Finding 5).
- Source-of-truth reference: Acceptance criteria, package lines 37-38.
- Proposed fix: Add the six tests. The "unknown email" and "wrong password" tests should assert *byte-for-byte identical* response bodies (modulo `requestId`) and status codes; ideally also assert response timing is within a bounded delta. The malformed-body and missing-field tests should assert 422 (FastAPI's default for Pydantic validation) — or whatever the project's error envelope mandates — and that they do NOT collide with the 401 path.

**5. Rate-limiting interaction is referenced by the spec but absent from the route.**
- Citation: `api/routes/auth.py:53-60` (entire handler).
- Problem: The acceptance list explicitly enumerates "rate-limiting interaction" as a covered behavior, implying the endpoint participates in a rate limiter. The handler has no dependency, decorator, or middleware hook signaling participation. If rate limiting is intended to be applied via global middleware that's fine, but there is no evidence here — and without rate limiting the endpoint is a free credential-stuffing target.
- Why it matters: Login endpoints without rate limiting are a standard attack surface for password spraying and stuffing, regardless of password hashing strength. Spec mentions it; implementation does not demonstrate it.
- Source-of-truth reference: Acceptance criteria, package line 38 ("rate-limiting interaction").
- Proposed fix: Add an explicit dependency or decorator (e.g., `slowapi` `@limiter.limit("5/minute")` keyed on client IP and on email, or a project-internal limiter), and document/test the behavior. The rate-limit response must also use the standard error envelope.

### Medium

**6. `body.email` is used as a raw query value with no normalization.**
- Citation: `api/routes/auth.py:55`
- Problem: `db.users.find_one({'email': body.email})` performs an exact-match lookup against whatever the client sent. Without lowercasing / trimming, the same human user can be either found or not found depending on capitalization or trailing whitespace, depending on how rows were inserted. This produces inconsistent login outcomes and, combined with Findings 1-2, exposes information about which case-variant exists in the DB.
- Why it matters: Email is canonically case-insensitive on the local-part for user-facing identity in essentially every consumer system; storing/looking up unnormalized strings is a long-tail correctness bug and an enumeration oracle by another name.
- Source-of-truth reference: General correctness; spec implies "valid login" must succeed deterministically (line 37).
- Proposed fix: Normalize at the Pydantic layer (`EmailStr` plus `@field_validator` lowering and stripping) and ensure the same normalization is applied at user-creation time.

**7. Untrusted dictionary access on `user['password_hash']` — KeyError leaks 500s.**
- Citation: `api/routes/auth.py:58`
- Problem: If a `users` document is missing the `password_hash` field (legacy row, social-login row, partially migrated record), this raises `KeyError`, which FastAPI converts to a 500. A 500 on a specific email is itself an enumeration signal (it tells the attacker "this email exists in a degraded state"), and it crashes legitimate logins.
- Why it matters: Silent data inconsistency between users with/without password hashes becomes a user-visible 500 and a side-channel.
- Source-of-truth reference: Acceptance line 36 (uniform behavior), and general robustness.
- Proposed fix: Use `user.get('password_hash')` and treat a missing/None hash as "invalid credentials" via the same 401 path used in Finding 1. Log internally for ops follow-up.

**8. No password length / shape guardrail on input.**
- Citation: `api/routes/auth.py:54` (relies entirely on `LoginBody` whose definition is not shown).
- Problem: Without a max length on `password`, a client can submit a multi-megabyte string, which a CPU-bound KDF such as bcrypt/argon2 will then chew through. Repeated requests are an easy DoS, and bcrypt specifically has a hard 72-byte truncation that some KDFs handle differently — silently truncating long passwords can cause subtle login behavior differences.
- Why it matters: Resource exhaustion under common load; possible silent correctness divergence.
- Source-of-truth reference: Implied by spec (acceptance line 38: "malformed body, missing field"). The schema must enforce sane bounds.
- Proposed fix: In `LoginBody`, set `password: constr(min_length=1, max_length=1024)` (or the project's standard) and `email: EmailStr`. Reject oversize before reaching `verify_password`.

**9. JWT issuance is uncontextualized — no audience, no scope, no remote-IP / UA binding shown.**
- Citation: `api/routes/auth.py:60` — `issue_token(user)` is called with the entire user document.
- Problem: Passing the full user record into `issue_token` is a footgun: implementations of `issue_token` that serialize "interesting" user fields into JWT claims will inadvertently leak `password_hash`, internal flags, MFA secrets, etc. Without seeing `issue_token` we cannot rule this out, and the call site does not constrain it.
- Why it matters: Information disclosure via JWT payload is a recurring real-world vulnerability. The acceptance spec only requires `{ token: <jwt> }`; it does not authorize leaking arbitrary user fields into the token.
- Source-of-truth reference: General secure-design principle; spec line 33 specifies the success body but says nothing that licenses leaking user state.
- Proposed fix: Pass only the explicit claims needed (e.g., `issue_token(user_id=user['_id'], roles=user.get('roles', []))`) and review `api/auth.issue_token` to ensure it whitelists claims rather than blindly serializing the input.

**10. No structured logging / audit trail for failed logins.**
- Citation: `api/routes/auth.py:53-60` (handler body).
- Problem: There is no logging on success or failure. Login is the canonical event you must audit (for SOC2/SOX/etc., for abuse detection, and to power the rate limiter from Finding 5). An attacker spraying passwords leaves no in-app trace.
- Why it matters: Operability and detectability. Absence of audit trail also undermines the rate-limiting test the spec asks for.
- Source-of-truth reference: Implied by acceptance line 38 ("rate-limiting interaction"), which presupposes observable login attempts.
- Proposed fix: Emit a structured log on each attempt with `requestId`, source IP, normalized email, outcome, and elapsed time — but never log the password or the password hash.

### Low

**11. Route prefix is hard-coded inside the handler path.**
- Citation: `api/routes/auth.py:53` — `@router.post('/auth/login')`
- Problem: Convention in FastAPI codebases is to construct the router with `APIRouter(prefix='/auth', tags=['auth'])` and register `@router.post('/login')`. Hard-coding `/auth/login` here makes it easy for the prefix to be re-applied at mount time, producing `/auth/auth/login`. Without the wider repo this is a "smells off" not a confirmed bug.
- Why it matters: Minor maintainability / collision risk.
- Source-of-truth reference: FastAPI idiom; spec only specifies the resulting path (line 27).
- Proposed fix: `router = APIRouter(prefix='/auth', tags=['auth'])` and `@router.post('/login')`.

**12. Handler is `async` but does no concurrency-relevant awaits beyond the DB call.**
- Citation: `api/routes/auth.py:54-60`
- Problem: `verify_password` and `issue_token` are called synchronously inside an async handler. If either is CPU-bound (bcrypt/argon2 typically is), they block the event loop and degrade throughput across all concurrent requests, not just login.
- Why it matters: Performance under load; not a correctness bug.
- Source-of-truth reference: General async/CPU-bound guidance; not in spec.
- Proposed fix: Run `verify_password` via `await asyncio.get_running_loop().run_in_executor(None, verify_password, ...)` or via a dedicated thread pool, and consider the same for `issue_token` if it does heavy crypto.

**13. Detail strings are ad-hoc and not localized / not codified.**
- Citation: `api/routes/auth.py:57, 59`
- Problem: Free-form English strings as `detail` are a maintenance nuisance and are likely to drift from the documented `code` set. Once the envelope from Finding 3 is in place, the `code` field is the contract; the `message` is a hint.
- Why it matters: Cosmetic / maintainability.
- Source-of-truth reference: Spec mandates a `code` field (line 34) which functions as the stable identifier.
- Proposed fix: Define an enum of error codes (`AUTH_INVALID_CREDENTIALS`, `AUTH_RATE_LIMITED`, …) and centralize message text.
