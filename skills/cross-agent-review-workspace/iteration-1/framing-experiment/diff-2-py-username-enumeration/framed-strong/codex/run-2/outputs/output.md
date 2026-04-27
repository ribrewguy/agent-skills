**Review Scope:** `POST /auth/login` implementation in `api/routes/auth.py`  
**Process Used:** Closed-context structured code review against supplied acceptance criteria  
**Execution Context:** No tools, no filesystem reads, no test execution  
**Integration Target:** New FastAPI auth route  
**Governing Documents:** Login endpoint acceptance criteria in review package  
**Reviewer:** Codex  
**Severity Scale:** Critical, High, Medium, Low as defined in request  
**Date:** 2026-04-26

## Critical Findings

None.

## High Findings

### `api/routes/auth.py:13` - Unknown email path leaks account existence

**Problem:** When no user is found, the endpoint returns `404` with `detail='No user with that email'`.

**Why it matters:** This directly violates the requirement that “no such user” and “wrong password” be treated identically from the client’s perspective. It enables account enumeration by distinguishing registered from unregistered emails.

**Source of truth:** Acceptance criteria: invalid credentials must return `401` with the standard error envelope and must not leak whether an email is registered.

**Proposed fix:** Return the exact same `401` response for both missing user and wrong password, for example a shared `invalid_credentials()` path producing `{ code, message, requestId }` with a generic message like `Invalid email or password`.

### `api/routes/auth.py:13` and `api/routes/auth.py:15` - Invalid credential responses do not use the standard error envelope

**Problem:** Both invalid credential branches raise `HTTPException` with string `detail`, which FastAPI normally serializes as `{"detail": ...}` rather than `{ code, message, requestId }`.

**Why it matters:** The endpoint does not satisfy the required error contract. Clients expecting the standard envelope will handle login failures inconsistently, and `requestId` will be missing from the response body.

**Source of truth:** Acceptance criteria: invalid credentials return `401` with `{ code: string, message: string, requestId: string }`.

**Proposed fix:** Use the project’s standard error response mechanism instead of raw string `HTTPException.detail`, or raise an exception type that existing middleware converts into the required envelope.

## Medium Findings

None.

## Low Findings

None.
