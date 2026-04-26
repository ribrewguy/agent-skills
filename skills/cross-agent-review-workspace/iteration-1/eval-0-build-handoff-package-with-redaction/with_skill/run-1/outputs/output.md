# Handoff package for Codex review

Paste the block below into a `codex exec` invocation (or equivalent). It is the complete package; no other context is required.

---

```
You are acting as a second-pass cross-vendor reviewer. Your job is to find what is wrong with the work below. Do not validate that the work is good — assume something was missed. Apply structured-code-review's format (severity-tagged findings, file:line citations, source-of-truth references).

=== TASK / DESIGN (source of truth) ===

Task: task-100 — Add idempotent retry on transient processor failures.

Acceptance criteria:
- When the payment processor returns a 5xx response, retry the request.
- When the payment processor times out, retry the request.
- Retry up to 3 times total, with exponential backoff: 250 ms, 500 ms, 1000 ms.
- Persist the Idempotency-Key with the request so retries do not double-charge.
- If all retries exhaust, return the original 5xx to the caller.

=== FILES TO REVIEW (final state) ===

- api/services/payments.ts — adds a `retryWithBackoff` helper and integrates it into the processor call path.
- api/services/payments.test.ts — unit tests covering the retry paths, including retry exhaustion.
- api/db/idempotency_keys.ts — new persistence module for Idempotency-Key storage.

(Attach the final file contents inline when dispatching. No commit messages, no PR description, no review notes from the implementer.)

=== ARCHITECTURAL CONTEXT (minimal) ===

- The orders service calls the payment processor via the function in api/services/payments.ts.
- Idempotency keys are now written to the DB through api/db/idempotency_keys.ts before the first attempt; the same key is reused for retries.
- The processor is a third-party HTTP API; treat its 5xx and timeout behavior as the canonical transient-failure surface.

=== WHAT TO LOOK FOR (targeted, on top of an open-ended pass) ===

Domain risk classes that a second model family is well-placed to surface:

1. Idempotency correctness across failure modes
   - What happens if the DB write of the Idempotency-Key succeeds but the first processor attempt never goes out (process crash between persist and call)?
   - What happens if the processor receives the request, the response is lost in transit, and we retry with the same key — does the processor's idempotency contract actually protect us, or are we relying on it without verifying behavior?
   - Is the Idempotency-Key generated with sufficient entropy and uniqueness per logical payment intent (not per attempt)?

2. Retry classification
   - Are 5xx and timeouts the only retried conditions? Are 4xx (especially 408, 425, 429, 409) handled correctly — i.e., NOT retried unless explicitly safe?
   - Are network-level errors (DNS failure, connection reset, TLS handshake failure) classified the same as timeouts? They should be — verify.
   - Is a 5xx that arrives AFTER a timeout (i.e., the request actually succeeded server-side) being double-counted as a retryable failure?

3. Backoff and retry-storm risk
   - Is the backoff schedule strictly 250/500/1000 ms as specified, or is jitter added? If no jitter, a downstream outage will produce synchronized retry storms across callers.
   - Is the total budget (≈1.75 s of waits plus 4 calls) compatible with upstream request timeouts? A retry that exceeds the upstream's deadline silently wastes money without ever being seen.
   - Is the retry count off-by-one anywhere — "3 retries" vs. "3 total attempts" is a common mis-spec.

4. Concurrency and persistence ordering
   - The Idempotency-Key is persisted before the first attempt; is the persistence in the same transaction as the order state, or could a successful charge end up orphaned from its order row on a crash?
   - If two concurrent requests for the same logical payment race, do both end up with the same key (correct) or different keys (double-charge risk)?
   - Are DB writes for the key idempotent themselves (UPSERT vs. INSERT), or can a retry of the persistence itself error out?

5. Failure-surface fidelity to the spec
   - Spec says: "Return the original 5xx if all retries exhaust." Does the code preserve the ORIGINAL 5xx response body and headers, or does it synthesize a new response that loses processor diagnostic info?
   - On exhaustion, is the Idempotency-Key cleaned up, marked-failed, or left as-is? The spec is silent — flag any choice the implementer made and whether it is justifiable.

6. Test coverage gaps
   - Re-run the test suite yourself; do not trust any prior report.
   - Look specifically for: tests that exercise the timeout path (not just 5xx), tests that verify the Idempotency-Key is reused across retries (not regenerated), tests that verify behavior when the DB write fails before the first attempt.

=== INSTRUCTIONS ===

Produce a structured-code-review-format report. Severity-tag each finding (Critical / High / Medium / Low). Cite file:line. For each finding, name the source of truth (acceptance criterion, domain rule, or first-principles argument). Do not produce a "looks good overall" summary — produce a list of concerns.

Re-run lint, typecheck, and the test suite yourself as part of the review. Do not assume any prior gate passed.
```

---

That is the package as dispatched. The implementer's self-assessment, gate results, and reasoning trace are deliberately omitted from the block above so the review is independent.
