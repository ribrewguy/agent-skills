# MCP Sync Discipline

**Status:** Mandatory (governs all feature work)
**Scope:** Every pull request that adds, modifies, or removes a method on any `server/services/*.service.ts` module.
**Enforcement:** Automated CI check + governing policy below.

---

## The rule

The project MCP server must always expose every capability reachable from the web UI. Equivalently: **for every public method on a service module (`server/services/*.service.ts`), there is either a corresponding MCP tool binding OR a recorded exemption with a reason.** A pull request that violates this rule is rejected by CI.

The MCP server **MAY** expose capabilities that the UI does not expose — the rule is one-directional. But the UI MUST NOT have capabilities the MCP server lacks.

## Why

- **No drift between transports.** Two parallel surfaces (HTTP API + MCP) inevitably diverge unless drift is mechanically impossible. The sync-discipline test makes the divergence cost a failing build.
- **Single source of truth.** Business logic lives exactly once — in the service layer. The MCP server and the API are both transport adapters. Sync discipline protects that architectural decision from slow erosion.
- **AI-first coverage.** We have committed to MCP as a first-class interface. A user who asks an AI assistant to do something should never receive "I can't do that from here" when the UI allows it.

## How it's enforced

### 1. Service exports bind themselves to tools

Every service method authored for use from the web UI is registered in the MCP tool registry. The simplest pattern is a co-located binding file:

```
server/services/job-card.service.ts
server/services/job-card.service.mcp.ts    ← descriptors + bindings for the above
```

Alternatively, the tool descriptors themselves (in `server/mcp/tools/<name>.ts`) declare which service method they wrap via a typed import. The registry aggregates these.

### 2. Explicit exemptions

A service method that should **not** be reachable via MCP (e.g., a back-channel operation exposed only to an internal maintenance endpoint) is marked:

```ts
// server/services/job-card.service.mcp.ts
export const mcpExemptMethods = {
  internalReindex: 'internal maintenance only; never user-facing',
} as const
```

Every exemption carries a reason in free text. The sync test reads exemptions and accepts them as intentional.

### 3. CI test

`tests/unit/mcp/sync-discipline.test.ts` enumerates all public service methods reflectively, cross-checks them against registered MCP bindings + the exemption map, and fails the build if any method is neither bound nor exempt.

### 4. Generated catalog

At build time, `docs/architecture/mcp-tool-catalog.md` is regenerated from the tool registry. It lists every MCP tool, the service method it wraps, required permissions, and exempt methods with their reasons. Reviewers inspect catalog diffs in PRs the same way they inspect migration diffs — a clear indicator of the shape of the MCP surface.

## Authoring checklist for feature work

When a PR adds a new service method:

1. **Add the tool descriptor.** Create `server/mcp/tools/<name>.ts` with `defineMcpTool({...})`. Wire it to the service method. Include a succinct `description` — that description is the prompt the AI reads.
2. **Add RBAC requirement.** The tool runs the same `requirePermission` checks as the API. Add the permission in the descriptor if the toolkit supports it; otherwise invoke `requirePermission(useEvent(), '...')` at the top of the handler.
3. **Update the catalog doc** by running `pnpm mcp:catalog` (or the equivalent). Commit the regenerated doc.
4. **Run tests.** `pnpm test:unit` includes the sync-discipline test; it will fail if any method is unbound.

When a PR removes a service method, the corresponding tool descriptor is removed in the same commit.

When a PR marks a method as non-public (internal-only), it must be added to `mcpExemptMethods` with a one-line reason.

## Relationship to the feature-governance policy

This policy is a complement to `docs/policies/development/feature-governance.md`. Feature governance establishes the PRD-first discipline for new features; this policy establishes the MCP-parity discipline for implementation.

If a feature adds a new UI capability and skips the MCP tool binding, CI rejects the PR. The fix is to ship the MCP tool in the same PR.

## What this policy does not cover

- **MCP-only tools** (tools without a UI analog) are allowed and encouraged when they benefit AI usage (e.g., bulk read operations an AI client would use that a human UI would render differently). These do not require UI parity; only the reverse direction is enforced.
- **Transport / protocol version upgrades** to the MCP spec. Those are normal engineering work, not governed by this policy.
- **Deprecation of service methods.** Follow the normal deprecation path; the sync test will naturally drive the MCP tool removal at the same time.
