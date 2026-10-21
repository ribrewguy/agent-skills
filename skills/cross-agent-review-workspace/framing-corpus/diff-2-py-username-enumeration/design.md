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
