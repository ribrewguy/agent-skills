# Code Review: requireAuth middleware

## Summary

This middleware has multiple serious problems that prevent it from functioning as a session-auth layer. The most important issue is that the implementation does not actually verify the session token — it compares the cookie value to a server-side signing key. This is both a fundamental design error and a security vulnerability.

## Findings

### 1. [Critical] Token comparison does not perform cryptographic verification

```ts
const expected = process.env.SESSION_SIGNING_KEY
if (token === expected) { ... }
```

This compares the raw cookie value to `SESSION_SIGNING_KEY`. A signing key is a server-side secret used to sign or HMAC tokens. It is never the token itself. As written:

- Authentication "succeeds" only if the user-supplied cookie equals the signing key — meaning the only way to log in is for the attacker to know the signing key.
- If they do, they impersonate everyone simultaneously — there is no per-user identity in the comparison at all.
- The intended pattern is: the cookie carries a signed/encrypted session payload (e.g. `userId.signature`), and the middleware verifies the signature using `SESSION_SIGNING_KEY`. Use HMAC verify, or a JWT/Paseto library.

This is not a hardening recommendation; the middleware does not do what the spec requires.

### 2. [Critical] Comparison is not timing-safe

The design explicitly requires "the session token verification must be timing-safe (use a constant-time comparison)." JavaScript's `===` short-circuits on the first byte that differs, leaking information about the secret across many requests.

Use `crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b))` (after length-checking) — or, better, use a library verifier whose contract is constant-time.

### 3. [High] `decode(token)` is called on the signing key

```ts
req.user = await db.users.findOne({ id: decode(token).userId })
```

This line only runs after `token === expected` passes, which means `token` is the signing key. So `decode(SESSION_SIGNING_KEY).userId` is being executed. Behavior depends on `decode`'s implementation:

- It may throw → uncaught, 500 to the client.
- It may return `undefined` or `{}` → `decode(...).userId` throws.
- It may produce a value → `db.users.findOne({ id: undefined })` may return an arbitrary row in some DB layers.

Combined with Finding 1, this creates a path where the "logged-in user" is essentially undefined.

### 4. [High] Missing expiration check

The design requires that expired tokens return 401. The middleware never checks expiration. Even after the comparison is fixed (per Finding 1), an `exp` claim must be validated and the request rejected if expired.

### 5. [High] Missing malformed-token detection

The design requires that malformed cookies return 401. The middleware does not validate the cookie's structure at all (length, encoding, presence of a signature segment). All non-equal strings fall through to the final `return res.status(401)` — which happens to return 401, but as a side effect, not a deliberate malformed check. After implementing real verification, the verifier should explicitly reject malformed inputs.

### 6. [Medium] Error envelope uses `SessionExpired` for non-expiration cases

Both 401 paths return `{ code: 'SessionExpired', ... }`, including the "no cookie supplied" case. If the API contract distinguishes between missing/invalid/expired session, this loses information and is misleading to clients. Confirm with the API owner whether `SessionExpired` is intentional umbrella vocabulary; if not, use distinct codes (`SessionMissing`, `SessionInvalid`, `SessionExpired`).

### 7. [Medium] No try/catch around `decode(token)`

If `decode` throws on a malformed input, the unhandled rejection becomes a 500 from Express's default error handler — violating the "return 401" contract.

### 8. [Medium] No null check on the user lookup

`db.users.findOne({ id: ... })` may return `null` if the user has been deleted since the token was issued. The current code assigns `null` to `req.user` and continues. Either reject with 401 (preferable) or document this contract for downstream handlers.

### 9. [Low] No defense against cookie injection / multiple `session` cookies

`req.cookies.session` is passed straight through. Depending on the cookie parser's behavior with multiple `session=` headers, this could be an array. Validate it is a string before use.

## Recommendation

Do not ship in this state. The verification logic must be replaced with a real signature verifier (HMAC or JWT), made constant-time, and extended with malformed/expired handling per the spec. Re-review after the rewrite.
