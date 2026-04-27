Review Scope: `POST /auth/login` implementation in `api/routes/auth.py` only  
Process Used: Closed-context second-pass review against supplied acceptance criteria  
Execution Context: No tools, no filesystem, no tests run; reviewed package contents only  
Integration Target: FastAPI auth route  
Governing Documents: Login endpoint design / acceptance criteria in package  
Reviewer: Codex cross-vendor reviewer  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-26

## High Findings

### High: Unknown email leaks account registration state

Citation: `api/routes/auth.py:12-13`

Problem statement: The implementation returns `404` with `detail='No user with that email'` when the email is not found.

Why it matters: This directly violates the requirement that the endpoint must not leak whether an email is registered. A client can enumerate registered accounts by comparing the unknown-email response to the wrong-password response.

Source-of-truth reference: Acceptance criteria: invalid credentials must return `401` with standard error envelope, and “no such user” and “wrong password” must be treated identically from the client’s perspective.

Proposed fix: Return the same `401` standard error envelope for both missing user and wrong password, with the same `code` and `message`.

### High: Wrong password and unknown email have different status codes and messages

Citation: `api/routes/auth.py:12-15`

Problem statement: Unknown email returns `404` / `"No user with that email"`, while wrong password returns `401` / `"Incorrect password"`.

Why it matters: Even if the explicit unknown-email message were removed, the different status codes and response bodies still create a response-shape leak. This fails the “identically from the client’s perspective” requirement.

Source-of-truth reference: Acceptance criteria: invalid credentials return `401` with `{ code, message, requestId }`; no such user and wrong password must be indistinguishable.

Proposed fix: Use one invalid-credentials path for both branches, for example raising a shared application error that serializes as `{ code: "INVALID_CREDENTIALS", message: "Invalid email or password", requestId }`.

### High: Invalid credential errors do not use the standard error envelope

Citation: `api/routes/auth.py:13` and `api/routes/auth.py:15`

Problem statement: The route raises FastAPI `HTTPException` with a string `detail`, which normally serializes as `{"detail": "..."}` rather than `{ code, message, requestId }`.

Why it matters: The API contract requires the standard error envelope. Clients relying on `code`, `message`, and `requestId` will not be able to handle these failures consistently.

Source-of-truth reference: Acceptance criteria: “On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`.”

Proposed fix: Use the project’s standard error helper/exception type, or add an exception handler path that emits the required envelope for invalid credentials.

## Medium Findings

### Medium: Missing-field and malformed-body behavior is left to FastAPI defaults

Citation: `api/routes/auth.py:10`

Problem statement: The route depends entirely on `LoginBody` request validation, with no visible handling to ensure malformed JSON or missing fields produce the API’s expected error shape.

Why it matters: The acceptance criteria explicitly require tests for malformed body and missing field. FastAPI defaults commonly return `422` validation payloads with a framework-specific shape, which may be inconsistent with the project’s standard error contract.

Source-of-truth reference: Acceptance criteria: endpoint accepts `{ email: string, password: string }`; required tests include malformed body and missing field.

Proposed fix: Ensure request validation failures are mapped through the project’s standard error envelope, either globally or for this router, and test both malformed JSON and missing `email` / `password`.

### Medium: No visible rate-limiting integration on the login route

Citation: `api/routes/auth.py:9-10`

Problem statement: The route has no rate-limit dependency, decorator, middleware hook, or explicit handling shown for login throttling.

Why it matters: Login is a brute-force-sensitive endpoint, and the acceptance criteria call out a rate-limiting interaction test. Without an integration point, valid and invalid login attempts may bypass throttling unless there is undisclosed global middleware.

Source-of-truth reference: Acceptance criteria: “6 unit tests cover ... rate-limiting interaction.”

Proposed fix: Attach the project’s rate-limiting mechanism to `POST /auth/login`, keyed appropriately by client identity and/or normalized email, and verify throttled responses use the expected error envelope.

## Low Findings

### Low: Email lookup does not visibly normalize email before query

Citation: `api/routes/auth.py:11`

Problem statement: The lookup uses `body.email` directly.

Why it matters: If registration stores normalized emails but login accepts arbitrary casing or surrounding whitespace, valid users may fail login. This is lower severity because normalization may be handled inside `LoginBody`, but that is not visible in this change.

Source-of-truth reference: Acceptance criteria: accepts `email: string` and authenticates valid credentials.

Proposed fix: Ensure `LoginBody` normalizes email consistently with registration, or normalize before querying.
