Review Scope: `POST /auth/login` implementation in `api/routes/auth.py`  
Process Used: Cold second-pass review against supplied acceptance criteria only  
Execution Context: Static review; no commands, files, or tests executed  
Integration Target: FastAPI auth route  
Governing Documents: Login endpoint design / acceptance criteria in package  
Reviewer: Cross-vendor reviewer  
Severity Scale: Critical, High, Medium, Low as defined in review request  
Date: 2026-04-27

**Critical Findings**

None.

**High Findings**

**H-1: Unknown email returns 404 and explicit message, leaking account existence**  
Citation: `api/routes/auth.py:12-13`  
Problem: The implementation returns `404` with `detail='No user with that email'` when the email is not found.  
Why it matters: This directly violates the requirement that the endpoint must not leak whether an email is registered. Clients can enumerate valid accounts by comparing status codes and messages.  
Source of truth: Acceptance criteria: “On invalid credentials, returns 401 with the standard error envelope” and “must NOT leak whether an email is registered.”  
Proposed fix: Return the same `401` standard error envelope for both unknown email and wrong password, for example `{ code, message, requestId }` with a generic message such as “Invalid email or password.”

**H-2: Wrong password response shape and message differ from required standard envelope**  
Citation: `api/routes/auth.py:14-15`  
Problem: Wrong password raises `HTTPException(status_code=401, detail='Incorrect password')` instead of the required `{ code, message, requestId }` envelope. The message also distinguishes the failure reason.  
Why it matters: This violates the API contract and creates a response-shape/message leak between credential failure modes. Clients and tests expecting the standard envelope will fail.  
Source of truth: Acceptance criteria: “On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`” and “Treat ‘no such user’ and ‘wrong password’ identically.”  
Proposed fix: Route all authentication failures through the same error helper/middleware that emits the standard envelope with identical status, code, and message.

**H-3: Timing side channel leaks whether an email exists**  
Citation: `api/routes/auth.py:11-15`  
Problem: For unknown emails, the function returns before calling `verify_password`; for known emails, it performs password hash verification.  
Why it matters: Password hash verification is intentionally expensive. The response-time difference can reveal registered emails even if response bodies are normalized.  
Source of truth: Acceptance criteria: “The endpoint must NOT leak whether an email is registered.”  
Proposed fix: Always perform a password verification step using a constant dummy password hash when the user is missing, then return the same generic `401` response.

**Medium Findings**

**M-1: No visible rate-limiting integration on the login route**  
Citation: `api/routes/auth.py:9-10`  
Problem: The route has no dependency, decorator, or call that indicates login attempts participate in rate limiting.  
Why it matters: The acceptance criteria explicitly require a rate-limiting interaction test. Without integration at the endpoint boundary, credential stuffing protection may be bypassed or untested.  
Source of truth: Acceptance criteria: “6 unit tests cover … rate-limiting interaction.”  
Proposed fix: Add the project’s standard rate-limit dependency/decorator for auth attempts, keyed appropriately by IP and/or email, and include the required unit test.

**M-2: Malformed body and missing-field failures likely use FastAPI’s default validation shape, not the standard error contract**  
Citation: `api/routes/auth.py:10`  
Problem: The endpoint relies on `LoginBody` request parsing, but no local or referenced handler ensures malformed JSON or missing fields are returned in the API’s standard error envelope.  
Why it matters: The acceptance criteria require tests for malformed body and missing field. If the project expects the standard envelope for API errors, FastAPI’s default `422` validation response will not match.  
Source of truth: Acceptance criteria: “Accepts JSON body `{ email, password }`” and tests must cover “malformed body, missing field.”  
Proposed fix: Ensure request validation errors are mapped through the project’s standard error envelope, or add route-level validation/error handling consistent with the rest of the API.

**Low Findings**

None.
