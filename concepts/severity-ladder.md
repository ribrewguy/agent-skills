---
title: Severity ladder
parent: Concepts
nav_order: 3
---

# Severity ladder

The skills in this collection share one severity vocabulary across audits, code reviews, and design feedback. Picking shared words means the user sees the same triage signal whether the output came from `rest-api-design`, `structured-code-review`, or any future review/audit skill.

## The ladder

| Severity | Criterion |
|---|---|
| **Critical** | *(optional, domain-dependent)* Production-blocker. Security/data-integrity issue, breaks existing consumers in a way that can't be reverted without a deploy. Domain skills MAY add this tier when warranted (e.g., `rest-api-design` flags `GET` endpoints that mutate state as Critical). The default is the three-tier scale below. |
| **High** | Correctness or contract violation. Will cause wrong behavior, break consumers, fail security/compliance, or fail the source-of-truth check materially. The author cannot ship until this is addressed. |
| **Medium** | Design or convention deviation. Doesn't break the build but creates debt — inconsistency, missing convention, or scope drift from the design. The author should fix before merge unless they have a specific reason to defer. |
| **Low** | Polish. Naming nit, minor clarity issue, "nice to have" addition. Optional. |

`structured-code-review` defines the three-tier ladder as canonical. Domain skills that genuinely have production-blocker class issues add `Critical` and document it in their own bodies.

## Why a shared ladder matters

When a PR review surfaces 12 findings, the author needs to triage in seconds. If finding A says "Severity: P1," finding B says "Critical," and finding C says "Major," the author has to mentally translate each one to the same scale before they can compare them. A shared ladder turns 12 unranked items into a sorted list, scanned down the left margin.

The same author working across multiple repos — each with its own ad-hoc severity vocabulary — is doing this translation constantly. Codifying one vocabulary across a skill collection means the translation cost goes to zero.

## Format conventions

In skill outputs:

- Severity tags are wrapped in backticks: `` `High` ``, `` `Medium` ``, `` `Low` ``, `` `Critical` ``
- Findings are sorted highest severity first, then grouped by file or topic within each severity
- The final recommendation (block / approve-with-changes / approve) follows from the highest severity in the list

## Format example

```
- `Critical` [api/routes/users.ts:14]
  Problem: GET endpoint deletes a user.
  Why it matters: Caches, prefetchers, link unfurlers, security scanners
    all follow GET URLs. Any of them hitting this endpoint will delete
    a user — and CSRF protection is weaker on GET in most frameworks.
  Source of truth: REST conventions (GET must be safe and idempotent).
  Proposed fix: DELETE /api/users/:id

- `High` [api/routes/users.ts:8]
  Problem: List endpoint returns a bare array.
  Why it matters: Bare arrays can't grow into paginated lists without
    breaking every existing consumer. The shape becomes a de facto
    contract the moment the response ships.
  Source of truth: Repo convention (every list endpoint paginates).
  Proposed fix: Wrap in `{ data: [...], pagination: {...} }`.
```

## When NOT to add Critical

Don't add `Critical` for emphasis on a normal `High` finding. Critical means "production-blocker" specifically — security, data integrity, irrecoverable consumer break. If everything Important is Critical, nothing is.

Domain skills that consider adding Critical:
- ✅ `rest-api-design` — `GET` mutating state, `SELECT *` shipping `password_hash` to the wire, money-moving POST without idempotency
- ✅ A future security skill — known CVE, secrets in source, missing authorization on a destructive route
- ❌ A skill about naming conventions — "very inconsistent naming" is still High at most

## See also

- [`structured-code-review`](../skills/structured-code-review) — defines the three-tier scale as canonical.
- [`rest-api-design`](../skills/rest-api-design) — adds `Critical` for REST production-blockers.
