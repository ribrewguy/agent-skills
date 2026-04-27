Review Scope: `POST /auth/login` implementation in `api/routes/auth.py`  
Process Used: Static review of the provided diff only; no tools or filesystem access used  
Execution Context: Closed-context package review  
Integration Target: Login endpoint acceptance criteria  
Governing Documents: Provided design / acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as provided  
Date: 2026-04-27

## High Findings

### High: Unknown email leaks account registration state

Citation: `api/routes/auth.py:12-13`

Problem statement: When no user is found, the endpoint returns `404` with `detail='No user with that email'`.

Why it matters: The acceptance criteria explicitly require that “no such user” and “wrong password” be treated identically from the client’s perspective. Returning `404` and a specific message lets clients enumerate registered emails.

Source-of-truth reference: “The endpoint must NOT leak whether an email is registered. Treat ‘no such user’ and ‘wrong password’ identically from the client’s perspective.”

Proposed fix: Return the same `401` response for both unknown email and wrong password, using the standard error envelope:

```python
raise HTTPException(
    status_code=401,
    detail={"code": "invalid_credentials", "message": "Invalid email or password", "requestId": request_id},
)
```

Or use the project’s existing standard error helper if one exists.

### High: Invalid credential responses do not use the standard error envelope

Citation: `api/routes/auth.py:13` and `api/routes/auth.py:15`

Problem statement: Invalid credentials currently raise `HTTPException` with string details: `'No user with that email'` and `'Incorrect password'`.

Why it matters: The acceptance criteria require invalid credentials to return `{ code: string, message: string, requestId: string }`. FastAPI will serialize these as `{"detail": "..."}`, which does not match the required envelope and omits `requestId`.

Source-of-truth reference: “On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`.”

Proposed fix: Use the application’s standard error response mechanism for auth failures. If none exists in this file, inject or obtain the request ID and return a uniform `401` envelope for both failure branches.

## Medium Findings

### Medium: Malformed and missing-field validation likely does not use the standard envelope

Citation: `api/routes/auth.py:10`

Problem statement: The endpoint relies directly on `LoginBody` request parsing. FastAPI’s default validation errors usually return a `422` response with its own validation shape, not the standard `{ code, message, requestId }` envelope.

Why it matters: The acceptance criteria require tests for malformed body and missing field. If the API has a global validation-error handler this may be fine, but nothing in this implementation shows that malformed login requests conform to the service’s error format.

Source-of-truth reference: “6 unit tests cover valid login, wrong password, unknown email, malformed body, missing field, and rate-limiting interaction.”

Proposed fix: Confirm the app has a global validation exception handler that wraps malformed body and missing-field errors consistently. If not, add one or handle login validation errors through the existing standard envelope path.

## Low Findings

No Low findings.
