---
title: opentelemetry
parent: Skills
nav_order: 14
---

# opentelemetry

For any server application that must support OpenTelemetry. Given a fresh project and the sentence "it must support OpenTelemetry", the skill wires traces, metrics, and log correlation the same way every time, and proves the wiring against a real collector before claiming done.

## What makes this skill distinct

- **OTLP to a collector, configured only by `OTEL_*` environment variables.** No endpoint or sampler in code, no vendor SDK. The collector and everything behind it are out of scope.
- **Three span tiers.** Auto-instrumented edges (inbound, outbound HTTP, database, messaging) are confirmed, never hand-written; every public method on services and repositories gets a class-level span named `ClassName.method`; anything else needs to earn a bar on a flame graph.
- **Context never drops at a boundary.** W3C `tracecontext` and `baggage` on, and the known dropped balls named: Kotlin coroutines, Reactor, thread pools, async hops, broker headers.
- **Background jobs are linked root spans**, not children.
- **One default metric set** (`app.service.calls`, `app.service.duration`) from the Tier 2 wrapper, with business metrics named by semantic conventions and no ID attributes.
- **Ecosystem norms win.** Spring apps use Actuator and Micrometer with the OTel bridge; other JVM frameworks use the SDK; Node uses the OTel JS SDK.
- **Serverless is first-class.** Nothing buffered: simple processors or a flush per invocation.
- **Verification is part of the skill.** Component tests on in-memory exporters, one integration test against a real collector, and a compose file for humans.

## What it covers

- Export contract, resource attributes, shutdown and no-collector behaviour
- Span tiers, naming, error handling, async and messaging rules
- Metrics instrument choice, naming, and units
- Per-stack references: Spring MVC and WebFlux, Ktor, JAX-RS and plain JVM, Nuxt/Nitro and plain Node
- A semantic-conventions reference of the stable attribute names the skill relies on
- A verification reference with a collector test config and a local compose file
- Reviewer-grade output with severity tags

## Install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install opentelemetry@ribrewguy-skills
```

For other tools, see [Install](../install).

## Composes with

- **[application-logging](application-logging)**: owns what is logged and at which level; this skill owns the pipeline appender and correlation fields.
- **[structured-code-review](structured-code-review)**: formats review findings.

## Source

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/opentelemetry/skills/opentelemetry/SKILL.md)**: the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/opentelemetry/skills/opentelemetry/evals/evals.json)**: the five test cases for the skill.
- **[Verifier on GitHub](https://github.com/ribrewguy/agent-skills/tree/main/tools/opentelemetry)**: drives a collector container against the fixture apps under `evals/opentelemetry-workspace/fixtures`.
