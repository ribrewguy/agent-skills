Review Scope: `POST /auth/login` implementation in `api/routes/auth.py`  
Process Used: Closed-context static review of provided package only  
Execution Context: No commands run; no files read outside package  
Integration Target: Login endpoint acceptance criteria  
Governing Documents: Provided design / acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as provided  
Date: 2026-04-27

**High Findings**

1. `api/routes/auth.py:12`-`13`  
Problem: Unknown emails return `404` with `detail='No user with that email'`, while wrong passwords return `401` with a different message.  
Why it matters: This directly leaks whether an email is registered, violating the requirement to treat “no such user” and “wrong password” identically from the client’s perspective.  
Source of truth: “The endpoint must NOT leak whether an email is registered.”  
Proposed fix: Return the same `401` response for both branches, with the same standard error envelope.

2. `api/routes/auth.py:13` and `api/routes/auth.py:15`  
Problem: Invalid credentials use FastAPI `HTTPException(..., detail='...')`, which produces FastAPI’s default error shape rather than `{ code, message, requestId }`.  
Why it matters: The acceptance criteria require the standard error envelope for invalid credentials. Clients depending on `code`, `message`, and `requestId` will receive the wrong contract.  
Source of truth: “On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`.”  
Proposed fix: Use the project’s standard error response helper/middleware path, or raise the project’s standardized auth error type, ensuring both unknown email and wrong password produce the same `401` envelope.

**Medium Findings**

1. `api/routes/auth.py:11`-`15`  
Problem: The unknown-user path exits before password verification, while existing-user wrong-password performs `verify_password`.  
Why it matters: Even if the visible status/message is normalized, response timing may still allow user enumeration if password verification is meaningfully slower than the missing-user branch.  
Source of truth: “The endpoint must NOT leak whether an email is registered.”  
Proposed fix: For missing users, perform a dummy password verification against a constant fake hash before returning the generic `401`.

**Low Findings**

No low-severity findings.

**Critical Findings**

No critical findings.
