---
title: Composition over absorption
parent: Concepts
nav_order: 4
---

# Composition over absorption

Skills in this collection stay strictly in their lane and name neighbor skills for adjacent concerns. You get a small library of sharp tools that compose cleanly, instead of one mega-skill that "knows everything about your engineering process."

## The principle

When a task touches two domains, say a PR review of a REST endpoint, two skills load:

- `structured-code-review` provides the *output format*: the `Findings:` preamble, severity tags, the per-finding `Source of truth:` pattern.
- `rest-api-design` provides the *what to flag*: `GET`-mutates-state, missing idempotency, snake_case on the wire, sub-resource verbs for state transitions.

Together they produce a structured review that catches REST violations. Neither skill needs to know the other exists, except for a "composes-with" cross-reference at the bottom of each.

## The anti-pattern: absorption

The temptation is to make one skill that does it all. "While we're reviewing REST, why not also flag password hashing issues, SQL injection, missing auth, broken file layout..." Soon the skill is 2,000 lines and knows about everything but does none of it well, and updating any single concern means revising the mega-skill.

Two specific failure modes:

- **Scope creep blunts the skill.** A skill that covers everything reads as guidance about nothing in particular. Sharper skills produce sharper outputs.
- **Inconsistent updates.** When the cryptography landscape changes, every skill that mentions hashing has to update. With composition, only the cryptography skill changes; the REST review skill keeps deferring to it.

## How skills express their lane

Each skill's body has explicit out-of-scope language. From `rest-api-design`:

> **Out of scope**. Name the adjacent skill and defer; don't absorb its job:
>
> | Concern | Belongs to |
> |---|---|
> | Password hashing choices, KDF algorithms, credential storage | cryptography / security skill |
> | OAuth flows, session lifecycle, MFA implementation, CSRF token mechanics | auth skill |
> | SQL injection, prepared statements, ORM patterns, DB schema choices | data-access / security skill |
> | File and module layout, handler organization inside the repo | architecture skill |
> | ... | ... |

When the skill encounters one of these in its review/design output, the reviewer flags it in one line and defers. It doesn't recenter the review around it:

> *"Note: `hash(body.password)` is called synchronously in the handler. That's a concurrency concern for the crypto/perf skills to review, not a REST-conventions issue."*

## When skills do compose

Two skills compose when:

- One handles *how to present* (output format, severity tagging, structured preamble) and the other handles *what to identify* (domain rules, anti-patterns, conventions).
- One handles a *workflow* (multi-agent git topology, branch protection, promotion gates) and another handles a *single concern within that workflow* (commit message format, code review format, closeout summary format).
- One is a *foundation* (e.g., `structured-code-review`'s severity ladder) and another *builds on it* (e.g., a domain review skill that adds `Critical` to the ladder).

Composition is documented in the skill body's **Composes with** section with concrete cross-references to other skills in the collection.

## When skills don't compose

Two skills *don't* compose, and shouldn't be loaded together, when:

- They both shape the same dimension and disagree. Two skills that both mandate an output format would conflict.
- One depends on tooling the other doesn't recognize. (Resolve by making one of them the "abstraction" and the other an "adapter". See [Dependency tiers](dependency-tiers).)
- One's vocabulary contradicts the other's. (E.g., one calls a thing "Bead," the other calls it "Issue." Resolve by picking one canonical vocabulary in the collection.)

## Why this scales

Adding a new domain skill (say, `frontend-component-review`) to the collection takes:

1. Write the SKILL.md focused on frontend component conventions
2. Add a "Composes with: structured-code-review" line so reviews use the shared format
3. Add a "Composes with: rest-api-design" line if the components consume REST APIs
4. Done

The new skill is immediately useful in combination with everything else. Without composition, the same skill would either duplicate format/severity machinery (drift risk) or absorb pieces of other skills' jobs (scope creep).

## See also

- [`structured-code-review`](../skills/structured-code-review): the canonical "format" skill that other review skills compose with.
- [Dependency tiers](dependency-tiers): how skills declare what they depend on, including their "composes with" cross-references.
