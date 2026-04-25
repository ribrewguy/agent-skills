---
title: rest-api-design
parent: Skills
nav_order: 1
---

# rest-api-design

For designing or reviewing HTTP REST APIs. Covers the usual suspects — URLs, methods, status codes, pagination, idempotency — plus a few opinionated takes that tend to surface in code review and that most REST guides skip or get wrong.

## What makes this skill distinct

- **State transitions are `PATCH`**, not a `/complete` or `/cancel` sub-resource verb. Side effects (emails, audit rows) belong to the state change in the service layer, not to a URL invention. Inventing verbs fragments the URL space and doesn't compose with generic update clients.
- **Error codes name the domain reason**, not the HTTP status. `TaskNotFound` or `CardDeclined`, not `NOT_FOUND` or `BAD_REQUEST`. The HTTP status classifies at the protocol layer; the code explains *why* within the domain. Echoing the status wastes the field.
- **Flat error envelopes.** If your type is `APIError`, wrapping its contents in `{ error: { ... } }` is a layer of indirection that HTTP status already provides. Drop the wrapper.
- **Typed contracts are language-agnostic.** Examples in TypeScript, Python, Go, and Rust — because "REST" isn't a TypeScript-ism.
- **Reviewer-grade output with severity tags.** When you ask it to audit a PR, every finding comes back tagged `Critical` / `High` / `Medium` / `Low` (the only domain skill in this collection that uses the `Critical` tier — see [Severity ladder](../concepts/severity-ladder)). The skill stays strictly in its lane — crypto, auth internals, file layout, etc. get flagged and handed off to neighbor skills rather than absorbed into one über-review.
- **Patch format selection.** Plain JSON partial / `application/merge-patch+json` (RFC 7396) / `application/json-patch+json` (RFC 6902). Three formats, three escalation steps; default to plain, escalate when you genuinely need null-means-delete or array-element ops.
- **Content-type negotiation done right.** Vendor media types, NDJSON for streaming, `application/x-ndjson` and SSE — all legitimate and called out as alternatives to the default JSON.

## What it covers

- Resource-oriented URL design (plural nouns, kebab-case, no verbs)
- HTTP method semantics, including PATCH for state transitions
- Status code discipline (`201 Created` + `Location` on POST, `204 No Content` on DELETE, etc.)
- Domain-expressive error code catalog (with explicit anti-pattern table for HTTP-status echoes)
- Flat error envelope (`{ code, message, details?, requestId }`) — explicitly NOT nested under `error:`
- Cursor / offset / page pagination strategies and the decision tree for which to pick
- Idempotency keys on side-effectful POSTs (payments, emails, externally-visible state)
- Content negotiation including streaming and vendor media types
- Three patch formats with escalation guidance
- Typed contract patterns (input/output separation, branded IDs, discriminated unions) in TypeScript, Python, Go, Rust
- Reviewer-grade output conventions (no skill self-citation, severity-tagged findings, strict lane-keeping)

## Quick install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install rest-api-design@ribrewguy-skills
```

For other tools, see [Install](../install).

## Composes with

- **[structured-code-review](structured-code-review)** — when reviewing a REST PR, this skill identifies the violations and `structured-code-review` formats them with a source-of-truth-aware preamble and severity tags.

## Tooling and dependencies

- **Required:** none — the skill is framework-agnostic
- **Strongly recommended:** TypeScript / Python / Go / Rust (or any typed language) for the typed-contract patterns; HTTP/JSON tooling for the wire-format examples
- **Optional:** none

The skill itself is language-agnostic; the examples use multiple languages so the patterns transfer.

## Source of truth

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/rest-api-design/skills/rest-api-design/SKILL.md)** — the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/rest-api-design/skills/rest-api-design/evals/evals.json)** — the four test cases used to verify the skill's behavior.

## Eval results

Iteration-2 benchmark (after rework based on user feedback): **100% pass rate with-skill vs. 82.5% with old version of the skill** across four test cases:

| Eval | What it probes |
|---|---|
| `design-task-api-from-scratch` | Whether the skill produces canonical envelopes, picks PATCH over sub-resource verbs, and uses domain-expressive error codes |
| `pr-audit-multiple-violations` | Whether the skill catches a realistic cluster of REST violations and tags severity, without drifting into adjacent concerns |
| `payments-post-idempotency-trap` | Whether the skill identifies missing `Idempotency-Key` on a money-moving POST |
| `bounded-notifications-not-a-list` | Whether the skill resists the urge to paginate a bounded-by-policy resource |

Eval transcripts and benchmark JSON live alongside the skill source.

## Invocation examples

- "Design the HTTP contract for a `<resource>` API — list with search/filter/sort, create, update, delete. Include typed request/response."
- "Review this PR against our REST conventions. List every violation with severity and propose the corrected alternative."
- "Is `POST /api/payments` ready to ship? Here's the draft."
- "Should this endpoint use PATCH or a sub-resource action?"
