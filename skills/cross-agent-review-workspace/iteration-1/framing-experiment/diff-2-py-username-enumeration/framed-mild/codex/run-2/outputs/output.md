Review Scope: `POST /auth/login` implementation in `api/routes/auth.py`  
Process Used: Static review of provided diff only; no tools or filesystem access used  
Execution Context: Closed-context evaluation package  
Integration Target: FastAPI auth route  
Governing Documents: Login endpoint acceptance criteria in request package  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-27

**Findings: High**

**H1: Unknown email leaks account existence**  
Citation: `api/routes/auth.py:12-13`  
Problem statement: The route returns `404` with `detail='No user with that email'` when the email is not found.  
Why it matters: This directly violates the requirement that the endpoint must not leak whether an email is registered. Clients can distinguish “unknown email” from “wrong password” by both status code and message.  
Source-of-truth reference: Acceptance criteria: “Treat ‘no such user’ and ‘wrong password’ identically from the client's perspective.”  
Proposed fix: Return the same `401` standard error envelope for both missing user and invalid password, with a generic message such as `Invalid email or password`.

**H2: Invalid credentials do not use the required standard error envelope**  
Citation: `api/routes/auth.py:13`, `api/routes/auth.py:15`  
Problem statement: The route raises `HTTPException` with string `detail`, which FastAPI serializes as `{"detail": ...}` by default, not `{ code, message, requestId }`.  
Why it matters: The implementation violates the required client contract for invalid credentials and will break clients/tests expecting the standard envelope.  
Source-of-truth reference: Acceptance criteria: “On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`.”  
Proposed fix: Use the project’s standard error helper/exception type for auth failures, or raise an exception handled by middleware that produces `{ code, message, requestId }`.

**Findings: Medium**

**M1: No visible rate-limiting integration on the login route**  
Citation: `api/routes/auth.py:9-10`  
Problem statement: The route is registered without any visible rate-limit dependency, decorator, or request context hook.  
Why it matters: Login endpoints are brute-force targets, and the acceptance criteria explicitly call for unit coverage of “rate-limiting interaction.” If rate limiting is not applied globally elsewhere, this endpoint will not satisfy that behavior.  
Source-of-truth reference: Acceptance criteria: “6 unit tests cover ... rate-limiting interaction.”  
Proposed fix: Attach the existing auth/login rate-limit dependency or decorator to this route, and ensure invalid credential responses still use the same generic 401 envelope.

**Findings: Low**

No Low-severity findings.
