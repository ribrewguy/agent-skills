Findings:

Reviewer: Codex (cross-vendor second pass)
Implementer: Claude
Source of truth: Acceptance criteria provided in the handoff package
Files reviewed: api/middleware/auth.ts (full final-state contents)
Gates re-run: not applicable here (no test suite supplied with the handoff); findings derived from first-principles inspection of the code against the spec
Mode: targeted (timing attacks, session token validation gaps, error envelope correctness, design conformance) plus open-ended
Severity scale: Critical / High / Medium / Low
Disposition: Ship is BLOCKED on Findings 1, 2, and 3.

---

### Finding 1 — Critical: Authentication compares user-supplied token to the signing key directly

File: api/middleware/auth.ts (the `if (token === expected)` branch)
Source of truth: design says "the session token verification must be timing-safe" and implies cryptographic verification of the token. The variable `SESSION_SIGNING_KEY` names a *signing key*, not a session value.

The middleware treats authentication as `req.cookies.session === process.env.SESSION_SIGNING_KEY`. This is wrong at the design level, not just at the timing level:

- A signing key is a long-lived secret used to *sign or HMAC* session payloads. It is not a value any client should ever transmit. Comparing a user-supplied cookie to the signing key means the only way to authenticate is for the attacker to learn or guess the signing key — and if they ever do, they have not just a session, they have the ability to forge any session.
- There is no per-user binding. Every successful "auth" returns the *same* path (whichever user `decode(SESSION_SIGNING_KEY).userId` happens to resolve to, or undefined behavior if it doesn't decode), regardless of who the actual user is.
- The expected design is to verify the token cryptographically — e.g., HMAC-verify a signed payload, or validate a JWT signature, then extract the user id from the verified payload.

This is not a hardening issue. The middleware does not perform authentication as specified. Block ship.

### Finding 2 — Critical: `token === expected` is not constant-time, violating the explicit timing-safe requirement

File: api/middleware/auth.ts (`if (token === expected)`)
Source of truth: design says "the session token verification must be timing-safe (use a constant-time comparison)."

Even if Finding 1 is resolved (i.e., the comparison is later restored to a legitimate cryptographic verification), the use of JavaScript's `===` operator on strings short-circuits on the first differing byte. This leaks token bytes via timing across many requests. The design explicitly calls for constant-time comparison; this code does not provide one. Use `crypto.timingSafeEqual` over equal-length Buffers, or rely on a vetted verifier (HMAC verify, JWT verify) that is constant-time internally.

### Finding 3 — High: `decode(token)` is invoked on a value that is, by construction, the signing key

File: api/middleware/auth.ts (`req.user = await db.users.findOne({ id: decode(token).userId })`)
Source of truth: first-principles correctness.

The line `decode(token).userId` is reached only when `token === expected`, where `expected = process.env.SESSION_SIGNING_KEY`. So `decode` is being called on the signing key string, not on a session token. The behavior is undefined in practice — depending on `decode`'s implementation it will throw, return `undefined`, or return whatever happens to fall out of decoding a non-token value. Then `db.users.findOne({ id: undefined })` may match an arbitrary row depending on the DB layer's null/undefined handling, returning a *random user* on the rare path where this branch is taken.

This compounds Finding 1 into a potentially exploitable user-impersonation primitive.

### Finding 4 — High: The "malformed" validation path required by the design is not implemented

File: api/middleware/auth.ts (entire function)
Source of truth: design says "if the cookie is missing, malformed, or expired, the middleware should return 401 with our standard error envelope (`{ code: \"SessionExpired\", ... }`)."

The code handles only two cases: `!token` (missing) and `token === expected` (the broken pseudo-success path). There is no shape/structure validation of the token (length, encoding, signature presence). Any malformed string that is not equal to the signing key falls through to the final `return res.status(401).json({ code: 'SessionExpired', message: 'Invalid session', ... })` — which happens to return 401, but only by accident; there is no actual malformed-detection logic.

### Finding 5 — High: Expiration validation required by the design is not implemented

File: api/middleware/auth.ts (entire function)
Source of truth: design says expired cookies should return 401.

There is no expiration check anywhere in the middleware. If a real cryptographic verification is added later (per Finding 1), it must additionally verify a `exp`/issued-at claim and reject expired tokens. As written, an attacker who once had a valid session would retain indefinite access, because the only "verification" is equality with a long-lived signing key.

### Finding 6 — Medium: Error envelope reuses `code: "SessionExpired"` for cases that are not expiration

File: api/middleware/auth.ts (both 401 returns)
Source of truth: design specifies the envelope for missing/malformed/expired collectively but uses the literal code `SessionExpired`. Reasonable to interpret strictly (always `SessionExpired` for any auth failure here) or loosely (distinct codes per failure class).

The current code uses `code: 'SessionExpired'` for both the missing-cookie path and the failed-comparison path. If the API contract is that `SessionExpired` is the umbrella code for any session-layer rejection, this conforms. If the contract distinguishes "missing" from "invalid" from "expired", the code is wrong and clients cannot tell why they got a 401. Flag for the API owner to confirm. Either way, "missing cookie" returning `SessionExpired` is misleading wording for clients.

### Finding 7 — Medium: `req.user` is populated from a DB row but no null check is performed

File: api/middleware/auth.ts (`req.user = await db.users.findOne({ id: decode(token).userId })`)
Source of truth: design says "after successful verification, attach the user object to `req.user`."

`db.users.findOne` may return null if the user has been deleted/disabled since the token was issued. The current code attaches `null` to `req.user` and proceeds via `next()`, leaving downstream handlers to discover the absence. Either reject with 401 here (preferable; the session is no longer authentic if the user is gone) or document that downstream handlers must defend against `req.user === null`.

### Finding 8 — Low: `decode(token)` is called without a try/catch

File: api/middleware/auth.ts (same line as Finding 3)
Source of truth: defensive coding.

`decode` may throw on malformed input. An uncaught throw inside an async middleware bubbles to the framework's error handler and likely returns 500, leaking implementation details and breaking the design's "return 401" contract. Wrap in try/catch (or use a verifier whose contract is "return null on failure rather than throw").

---

### Recommended next steps

- Findings 1 and 2 must be resolved together: replace direct comparison with a real cryptographic verifier (HMAC verify of a signed payload, or JWT verify), and ensure the verifier is constant-time. The signing key must never be compared to a user-supplied value.
- Re-handoff once verification is reworked. A second targeted pass should look at: (a) the new verifier's exception handling, (b) clock-skew tolerance on `exp` validation, (c) whether the cookie is HttpOnly/Secure/SameSite-set at issuance time (out of scope for this file but adjacent).
- This change is not safe to ship in its current form.
