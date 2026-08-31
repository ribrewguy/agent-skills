I'm pausing the localStorage implementation on tf-33. This is a real spec conflict between two layers of the source of truth, and I won't resolve it silently by editing "whichever doc is wrong" — I'll lay it out, recommend a resolution, and make the edit once you confirm.

## The conflict, quoted

- **tf-33 acceptance criteria:** store the refresh token in **localStorage** so the session survives a tab close.
- **docs/architecture/security.md, "Token storage":** refresh tokens **must live in httpOnly cookies** and **must never be readable from JavaScript**.

These cannot both be satisfied. A token in localStorage is, by definition, readable from JavaScript.

## Why I'm not treating this as a coin flip

Architecture docs are guardrails that sit above task specs. When a task contradicts the architecture, the default presumption is that the *task* is wrong — architecture doesn't get edited to match a ticket.

And in this case the guardrail is load-bearing, not stylistic. A refresh token in localStorage is exfiltratable by any script that executes on the page, so a single XSS bug escalates into durable account takeover. The httpOnly rule exists precisely to break that chain, and it matches current OWASP guidance. "The task spec is probably stale" is plausible; "the security architecture is stale" is not something I should conclude on my own — relaxing that rule would need an explicit, recorded decision from whoever owns the security architecture, not a drive-by edit to unblock today's landing.

## Recommended resolution

1. **security.md stays as-is.** I won't touch it.
2. **Update tf-33's acceptance criteria** to align with the architecture:
   - Refresh token delivered as an `httpOnly`, `Secure`, `SameSite` cookie set by the auth server; never exposed to JS.
   - Session survives tab close via cookie persistence (`Max-Age`/`Expires`) — this still satisfies the original *intent* of the criterion.
   - Access token held in memory only; on a fresh tab, the client calls the refresh endpoint with `credentials: 'include'` to re-establish the session.
3. **Rework the in-flight client code** to that model.

Confirm and I'll make the task-spec edit — I'm asking first because acceptance criteria are a record of intent, and I don't rewrite them unilaterally even when the fix looks obvious. If you actually *do* want localStorage here, that's an architecture exception: it needs an explicit sign-off from the security-doc owner recorded in security.md, and I'd want that stated in so many words before proceeding.

## Honest impact on "land it today"

The cookie approach changes scope: the client no longer stores the refresh token at all, so part of tf-33 moves server-side.

- If the auth server **already sets** the refresh cookie on login/refresh, the client change is small (drop the localStorage code, add `credentials: 'include'`, handle the silent-refresh-on-load path) — still very landable today.
- If it **doesn't**, there's backend work (Set-Cookie on login/refresh, CORS `Access-Control-Allow-Credentials`, CSRF posture for the refresh endpoint) that tf-33 as written didn't include. In that case I'd flag it immediately and we can decide whether to split the server piece into its own task rather than force a same-day merge of unplanned auth-server changes.

First thing I'll do once you confirm the direction is check which of those two worlds we're in and report back. Urgency is real, but shipping a known violation of the security architecture to make a date isn't a trade I'll make silently — and the compliant path may well still make today.
