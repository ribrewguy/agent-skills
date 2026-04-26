```
feat(payments): add idempotent retry on transient processor failures

Wraps processor calls in a new retryWithBackoff helper that retries
5xx and timeout responses up to 3 times on a 250 / 500 / 1000 ms
schedule. The schedule is fixed (not exponential-with-jitter) because
the processor's published guidance prescribes those intervals and we
want to stay inside the documented behavior — diverging from it could
trip the processor's own duplicate-suppression heuristics.

4xx responses are surfaced immediately and never retried: a 4xx is the
processor telling us the request itself is wrong, so retrying it is
guaranteed waste at best and double-charge risk at worst.

Persists the Idempotency-Key in a new idempotency_keys module before
the first attempt, so retries survive in-process state loss between
attempts (process restart, container recycle, retry-after-reschedule).
Without persistence, a mid-retry restart would generate a fresh key
on the next attempt and the processor would treat it as a brand-new
charge instead of a retry of the same one — exactly the
double-charge bug this task exists to prevent.

Tests cover the four critical paths: retry-then-success, retry-then-
exhaustion (returning the original 5xx), 4xx-no-retry, and
key-survives-process-restart. 8 new tests, all passing alongside the
existing payments suite.

No externally visible behavior changes beyond what the spec already
documents — the retry semantics described in the spec are now actually
implemented.

Refs: task-100

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

A few notes on the surrounding ceremony, separate from the message itself:

- **No UAT gate prompt needed.** You've stated the change does not affect externally visible behavior beyond what the spec already documents, so there's nothing for the user to acceptance-test before commit.
- **Don't amend.** If a pre-commit hook fires and fails, the commit didn't happen — fix the issue, re-stage, create a new commit. Don't reach for `git commit --amend`.
- **Stage explicitly.** Add `api/services/payments.ts`, `api/db/idempotency_keys.ts`, and `api/services/payments.test.ts` by name rather than `git add -A`, to avoid sweeping in anything unintended.
- **Push when policy allows.** Once committed, if your branch policy and any required approvals allow it, perform the push — don't leave it as "ready to push when you are."
