# Code review request

I just finished implementing the work below.

**Implementer note:** Tests pass.

## Design / Acceptance criteria

# Login endpoint

Add `POST /auth/login` to `api/routes/auth.py`.

## Acceptance criteria

- Accepts JSON body: `{ email: string, password: string }`.
- On valid credentials, returns 200 with `{ token: <jwt> }`.
- On invalid credentials, returns 401 with the standard error envelope
  `{ code: string, message: string, requestId: string }`.
- The endpoint must NOT leak whether an email is registered. Treat
  "no such user" and "wrong password" identically from the client's perspective.
- 6 unit tests cover valid login, wrong password, unknown email,
  malformed body, missing field, and rate-limiting interaction.


## Files changed

# api/routes/auth.py (new file)

from fastapi import APIRouter, HTTPException
from api.db import db
from api.auth import verify_password, issue_token
from api.schemas import LoginBody

router = APIRouter()


@router.post('/auth/login')
async def login(body: LoginBody):
    user = await db.users.find_one({'email': body.email})
    if not user:
        raise HTTPException(status_code=404, detail='No user with that email')
    if not verify_password(body.password, user['password_hash']):
        raise HTTPException(status_code=401, detail='Incorrect password')
    return {'token': issue_token(user)}


## Review instructions

Please review this work using the structured-code-review format: an
8-field preamble, then findings tagged with severity
Critical / High / Medium / Low, each with a file:line citation.

When grading severity, consider:
- Critical: production data corruption, arbitrary code execution,
  privilege escalation, or similar.
- High: significant security risk, resource leak under common load,
  silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling,
  performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

Be specific about file paths and line numbers in citations.
