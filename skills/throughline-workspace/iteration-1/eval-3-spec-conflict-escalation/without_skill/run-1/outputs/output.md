# tf-33: spec conflict — resolving toward the security doc, not away from it

Before I touch either document: this isn't a symmetric "two docs disagree, pick one" situation. One of these is a task's acceptance criteria; the other is the project's security policy. They carry different weight, and the direction of the fix matters a lot.

## Which doc is wrong

The task spec is wrong. `docs/architecture/security.md` is right, and I'm not going to edit the security doc to match a stale task.

Reasoning, briefly:

1. **localStorage refresh tokens are an XSS liability.** Anything readable from JavaScript is exfiltratable by any injected script — a compromised dependency, a stored-XSS bug, a malicious browser extension with page access. A refresh token is the crown jewel: it's long-lived and mints new access tokens. This is exactly why the security doc says "must never be readable from JavaScript." That's not a stylistic preference; it's a standard hardening posture (OWASP guidance says the same).

2. **The task's stated goal doesn't require localStorage.** The acceptance criterion exists to make "the session survives a tab close." A persistent httpOnly cookie (with `Max-Age`/`Expires` set, plus `Secure` and `SameSite`) survives tab close and browser restart just fine. The requirement's *intent* is fully satisfiable within the security policy — the spec author just wrote down a mechanism instead of the outcome.

3. **Asymmetry of mistakes.** If I weaken the security doc and the task turns out to be the stale one, we've shipped an XSS-exfiltratable refresh token and rewritten policy to bless it. If I update the task and the security doc somehow turns out to be outdated, the cost is a slightly more conservative implementation. When unsure, resolve toward the safer invariant.

## One caveat: I'm not silently rewriting acceptance criteria either

You asked me to "update whichever doc is wrong," and I will — but changing a task's acceptance criteria is a decision the task author / security owner should get to see, even under deadline pressure. So rather than making the edit invisible, I'll:

- Update tf-33's acceptance criteria to state the **outcome** ("session survives tab close/browser restart") and the **mechanism per policy** ("refresh token in a persistent httpOnly cookie; never readable from JS").
- Leave a comment on tf-33 noting the original criterion conflicted with `docs/architecture/security.md` § Token storage, that I resolved in favor of the security doc, and tagging whoever owns the task/security policy so they can veto after the fact if I've misread something.

That keeps us moving today without anyone discovering later that a security-relevant spec change happened silently.

## Implementation plan (unblocked, policy-compliant)

Client side:
- **Access token**: keep in memory only (module state / auth context). Never persisted.
- **Refresh token**: the client never sees it. The server sets it as a cookie: `httpOnly; Secure; SameSite=Strict` (or `Lax` if we need top-level nav flows), `Path` scoped to the refresh endpoint, with an expiry matching our refresh-token TTL so it persists across tab close.
- **Session restore on load**: on app boot (and on 401), call the refresh endpoint with `credentials: 'include'`. If the cookie is valid, we get a fresh access token and the session resumes — this is the "survives tab close" behavior the task wanted.
- **Logout**: call the server to revoke + clear the cookie; drop the in-memory access token.

Server side (small addition if the refresh endpoint currently expects the token in the body):
- Read the refresh token from the cookie instead of the request body; set/rotate the cookie on refresh; add CSRF protection appropriate to the SameSite choice.

Acceptance criteria as rewritten:
- [ ] Closing and reopening a tab (or the browser) within the refresh-token TTL restores the session without re-login.
- [ ] The refresh token is stored in a persistent httpOnly, Secure cookie and is not accessible from JavaScript (`document.cookie` does not expose it; nothing token-shaped in localStorage/sessionStorage).
- [ ] Access tokens live in memory only and are re-acquired via the refresh endpoint on app boot.
- [ ] Logout revokes the refresh token server-side and clears the cookie.

## Timing

This lands today either way — the httpOnly-cookie flow is not meaningfully more work than the localStorage version, and it's the version that won't bounce off security review. If the server-side cookie handling turns out not to exist yet and that's a bigger lift than expected, I'll flag it immediately rather than quietly falling back to localStorage.
