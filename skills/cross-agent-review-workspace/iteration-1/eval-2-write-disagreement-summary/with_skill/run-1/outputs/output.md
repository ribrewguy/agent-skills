## Cross-Agent Review Disagreement

Topic: For database reads that are NOT explicitly tagged with a freshness requirement, should the default route be the read replica or the primary?

Implementing agent's position:
  Route all writes and any read flagged `requires_fresh: true` to the primary; route all other reads (the un-tagged majority) to the read replica. The replica was added precisely to relieve primary load, and replica lag is typically <100ms in this setup, which is below the tolerance of the vast majority of reads. Production systems including Stripe use this pattern.
  Tradeoff they accepted: a small surface of bugs where a caller fails to set `requires_fresh: true` on a read that actually needs fresh data, in exchange for the load-relief benefit of the replica being realized across the un-tagged majority.

Reviewing agent's position:
  Route all reads to the primary by default; let callers OPT IN to the replica with an explicit `prefer_replica: true`. Only writes and explicit replica-opts go off the default. The reasoning is that many handlers are AI-generated and are not reliable about correctly tagging freshness, so a replica-by-default policy will produce silent stale-data bugs (e.g., a customer modifies an order then reads its status from the replica before the write has propagated).
  Tradeoff they propose: forfeiting most of the replica's load-relief value (since most reads will keep hitting the primary), in exchange for eliminating a class of silent data-inconsistency bugs that are hard to catch in testing.

What both agree on:
  Replica lag exists and is roughly <100ms in this setup. The decision is not about the magnitude of replica lag — it is purely about which side the default should land on for reads that are not explicitly tagged.

What's at stake in the choice:
  Silent data-inconsistency bugs (read-your-own-writes failures presenting as "intermittent" customer-visible problems) vs. realized primary-load relief from the replica investment. A choice that gets this wrong either underuses the infrastructure that was built to relieve primary load, or ships a class of bugs that look like flakes in production and are hard to reproduce.

Recommended escalation:
  Surface this to the engineering owner of the orders / payments data path (the team that owns both primary load capacity and the customer-visible consistency contract). Specific question to ask: "Given that many read handlers are AI-generated and unlikely to reliably tag freshness needs, do we accept replica-by-default with a class of silent stale-read bugs as an ongoing operational risk, or do we accept primary-by-default and the corresponding underuse of the read replica? If replica-by-default, what monitoring will surface stale-read bugs before customers do?"
