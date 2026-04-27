Review Scope: `POST /auth/login` implementation in `api/routes/auth.py`  
Process Used: Closed-context structured code review from provided package only  
Execution Context: No commands run, no files read  
Integration Target: Login endpoint acceptance criteria  
Governing Documents: Provided design / acceptance criteria  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low  
Date: 2026-04-26

**Critical Findings**

None.

**High Findings**

**api/routes/auth.py:12**

Problem statement: Unknown email returns `404` with `detail='No user with that email'`, while wrong password returns `401` with `detail='Incorrect password'`.

Why it matters: This directly violates the requirement that the endpoint must not leak whether an email is registered. Clients can distinguish registered from unregistered emails by status code and message.

Source-of-truth reference: Acceptance criteria: “The endpoint must NOT leak whether an email is registered. Treat ‘no such user’ and ‘wrong password’ identically from the client's perspective.”

Proposed fix: Return the same `401` response for both unknown email and wrong password, using the standard error envelope. For example, route both cases through a shared `invalid_credentials()` helper.

---

**api/routes/auth.py:13**

Problem statement: Invalid credentials are raised as `HTTPException(..., detail='...')`, not the required standard error envelope `{ code, message, requestId }`.

Why it matters: The acceptance criteria explicitly require invalid credentials to return `401` with the standard envelope. FastAPI’s default `HTTPException` shape is typically `{"detail": ...}`, so this response contract is likely wrong.

Source-of-truth reference: Acceptance criteria: “On invalid credentials, returns 401 with the standard error envelope `{ code: string, message: string, requestId: string }`.”

Proposed fix: Use the project’s standard error mechanism or exception type that serializes to `{ code, message, requestId }`. The message should be generic, such as “Invalid email or password.”

**Medium Findings**

**api/routes/auth.py:12**

Problem statement: The password verification path is skipped entirely when no user is found.

Why it matters: Even after normalizing the visible response, this can create a timing difference between unknown email and wrong password. The acceptance criteria prohibit leaking registration status from the client’s perspective; timing can be observable enough to matter for auth endpoints.

Source-of-truth reference: Acceptance criteria: “Treat ‘no such user’ and ‘wrong password’ identically from the client's perspective.”

Proposed fix: For unknown users, run `verify_password` against a fixed dummy password hash before returning the same invalid-credentials response.

**Low Findings**

None.
