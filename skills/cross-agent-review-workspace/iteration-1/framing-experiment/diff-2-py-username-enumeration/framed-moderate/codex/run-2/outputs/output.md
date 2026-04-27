Review Scope: `api/routes/auth.py` new `POST /auth/login` endpoint  
Process Used: Static review of the supplied package only; no tools or filesystem access used  
Execution Context: Closed-context evaluation  
Integration Target: FastAPI auth route  
Governing Documents: Login endpoint design / acceptance criteria in package  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-27

## Critical Findings

None.

## High Findings

### `api/routes/auth.py:12-15` - Login leaks whether the email exists

Problem statement: The unknown-email path returns `404` with `detail='No user with that email'`, while the wrong-password path returns `401` with `detail='Incorrect password'`.

Why it matters: This directly violates the requirement that the endpoint must not leak whether an email is registered. Clients can distinguish registered and unregistered emails by both status code and message, enabling user enumeration.

Source-of-truth reference: Acceptance criteria: “The endpoint must NOT leak whether an email is registered. Treat ‘no such user’ and ‘wrong password’ identically from the client's perspective.”

Proposed fix: Return the same `401` response for both branches, using a generic authentication failure code/message, for example `INVALID_CREDENTIALS`.

### `api/routes/auth.py:13-15` - Invalid credential responses do not use the standard error envelope

Problem statement: The endpoint raises `HTTPException` with string `detail` values. FastAPI will normally serialize these as `{"detail": "..."}`, not as `{ code, message, requestId }`.

Why it matters: The acceptance criteria require invalid credentials to return the standard error envelope. Clients expecting the shared API error shape will receive a different schema.

Source-of-truth reference: Acceptance criteria: “On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`.”

Proposed fix: Use the project’s standard error helper/middleware contract for auth failures, or raise an exception type that is converted into the standard envelope. Ensure both unknown email and wrong password produce the same `401` envelope.

## Medium Findings

None.

## Low Findings

None.
