# Cross-Agent Review Recommendations

Cross-agent review pays back when a second model is statistically likely to find issues a single agent or deterministic gate misses. It does not pay back on mechanical changes whose risk surface is fully covered by tests, types, or visual inspection.

## Change 1 — Typo fix `'pubish'` → `'publish'`

**Recommendation: Do NOT apply cross-agent review.**

Why: One-character change in a string literal. Risk surface is "is the new spelling correct" — a glance answers that. A second AI pass would have nothing meaningful to add. The deterministic gate here is reading the diff; that's enough.

## Change 2 — axios 1.7.0 → 1.7.1 lockfile bump

**Recommendation: Do NOT apply cross-agent review.**

Why: Patch release of a mature dependency, no app code changes, lockfile-only diff. The signal that matters here comes from the upstream changelog, the security advisory feeds, and CI. A second LLM reading the lockfile would either parrot the changelog or fabricate concerns.

## Change 3 — POST /api/transfers (money transfer endpoint)

**Recommendation: APPLY cross-agent review.**

Why: This is the textbook case. The change is:
- **Money-touching** — bugs cost real dollars and are often invisible until after they fire.
- **Side-effecting** — emails sent, audit rows written. Ordering and crash-safety matter.
- **New endpoint surface** — authorization, idempotency, and validation all need to be right.

8 unit tests + 1 staging integration test is solid coverage but does not catch design-level issues such as authorization gaps, retry-induced double-execution, or race conditions in the side-effect ordering. Different model families miss different things in money-paths; the cross-agent overhead is well worth it. Ask the second agent specifically about idempotency, authorization checks, and side-effect ordering under crash/retry.

## Change 4 — Email batching refactor (one-call-per-recipient → batch)

**Recommendation: APPLY cross-agent review.**

Why: This is a behavior-preservation refactor of integration code, and "behavior should be identical" is exactly the claim that quietly turns out wrong in 1 of 20 cases. Specific risks:

- Per-recipient personalization may not survive batching the way the implementer assumed.
- The batch endpoint may have different semantics for partial failure (some recipients delivered, others not) — silent drops are easy to miss.
- Bounce / unsubscribe handling commonly differs between single-send and batch APIs.
- 12 unit tests give confidence but do not exercise real upstream partial-failure modes.

Ask the second agent specifically about partial-failure handling, per-recipient personalization correctness, and parity with the prior bounce/unsubscribe behavior.

## Honest tradeoff

If we ran cross-agent review on every change, the cost would dwarf the catch-rate benefit and the team would route around it. If we ran it on no change, we'd ship the bugs the deterministic gates can't catch — exactly the high-impact ones (money, security, integration). Reserving it for changes 3 and 4 here matches the policy.
