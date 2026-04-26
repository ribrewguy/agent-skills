# Disagreement Summary: Default routing for non-tagged DB reads

## Context

Two agents reviewed the same DB query helper and reached different conclusions on a real design choice. This summary is for human escalation.

## The contested decision

**Should the default routing for reads that do NOT carry an explicit freshness tag be the read replica or the primary?**

## Implementing Agent's Position

**Default reads to the read replica; require `requires_fresh: true` to opt into primary.**

- Replica lag in this setup is typically <100ms.
- The vast majority of reads tolerate <100ms of lag.
- Routing un-tagged reads to the primary defeats the purpose of having a replica — primary load is the constraint the replica was provisioned to relieve.
- This is the pattern used by Stripe and other high-scale production systems.

## Reviewing Agent's Position

**Default reads to the primary; require `prefer_replica: true` to opt into the replica.**

- The replica-by-default pattern is correct only if every caller correctly tags reads with `requires_fresh`.
- In practice, many handlers in this codebase are AI-generated and do not reliably tag freshness needs.
- A future endpoint that reads order status without tagging `requires_fresh` and reads stale data immediately after a customer write will manifest as a customer-visible bug that looks like a flake.
- The cost of primary-by-default is some lost load-relief from the replica. The cost of the alternative is silent data inconsistency that is hard to catch in tests.
- Safer default is primary-by-default with explicit replica opt-in.

## Points of Agreement

- Replica lag exists and is approximately <100ms.
- The choice is not about replica lag magnitude; it is about default routing for reads that callers do not tag.
- Both writes always go to the primary.
- A `requires_fresh` / `prefer_replica` tagging mechanism is desired.

## What Is at Stake

- **Silent stale-read bugs** vs. **primary-load pressure**.
- One default produces bugs that are hard to reproduce and surface only as user-visible inconsistency. The other underutilizes the read replica and may produce primary-load problems in the future as traffic grows.

## Recommended Escalation

Escalate to the engineering owner / tech lead responsible for the data layer (the person accountable for both primary capacity and customer-facing consistency).

Specific question to ask:

> Given that a meaningful share of read handlers are AI-generated and unlikely to reliably tag freshness, do we accept replica-by-default and the silent-stale-read failure mode (with whatever monitoring is needed to surface it), or do we accept primary-by-default and forfeit some of the replica's load-relief value? If replica-by-default, what is our plan for catching the un-tagged-but-needs-fresh case before it reaches customers?
