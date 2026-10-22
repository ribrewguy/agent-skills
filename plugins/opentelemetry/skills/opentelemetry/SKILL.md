---
name: opentelemetry
description: "Use when a project must support OpenTelemetry, or when adding, reviewing, or debugging traces, metrics, or log correlation in any server code, including requests like 'must support otel', 'add tracing', 'instrument this service', or 'why is this trace broken'. Covers OTLP export to a collector configured only by standard OTEL_* environment variables, W3C propagation across every process boundary, the three span tiers (auto-instrumented edges, class-level service and repository spans, rare explicit spans), the default service metrics, the pipeline log appender with trace_id and span_id correlation, background jobs as linked root spans, serverless flush, and verification against an in-memory exporter and a real collector. Symptoms: a trace that stops at a service boundary, a log without a trace ID, a metric with an ID attribute, a vendor SDK import. Not for collector or backend configuration, dashboards, alerting, or browser RUM."
---

# OpenTelemetry

## Overview

An application that "supports OTel" emits three signals (traces, metrics, logs) over OTLP to a collector, keeps one trace across every process boundary a request crosses, and proves both with tests before anyone calls it done. This skill is the rulebook for that result: what gets a span, what gets measured, how context moves, how telemetry leaves the process, and how to verify it. The app knows only OTLP and a collector endpoint; everything past the collector (fan-out, backends, dashboards, alerting) is deployment-dependent and out of scope.

This skill owns what is traced, what is measured, how context moves, how telemetry leaves the process, and the pipeline log appender. The [`application-logging`](../../../application-logging/skills/application-logging/SKILL.md) skill owns what is logged, at which level, in which shape, the console appender, and the denylist. **When both are loaded on a logging question, `application-logging` governs the content of a record and `opentelemetry` governs its transport and correlation fields.**

The body is stack-neutral. Wiring lives in the references: [references/jvm-spring.md](references/jvm-spring.md) (Spring Boot MVC and WebFlux on the Micrometer path), [references/jvm-other.md](references/jvm-other.md) (Ktor, JAX-RS, plain JVM on the OTel SDK), [references/node.md](references/node.md) (Nuxt/Nitro, plain Node, Express-style), [references/semantic-conventions.md](references/semantic-conventions.md) (the stable attribute names), and [references/verification.md](references/verification.md) (the three test layers). Read the stack reference before writing wiring code; do not guess artifact or package names.

## When to use

- A project, new or existing, "must support OpenTelemetry" or "needs tracing".
- Adding a service, repository, outbound client, queue producer or consumer, or background job to an instrumented app.
- Reviewing a PR that touches telemetry setup, propagation, spans, metrics, or log correlation.
- Debugging "why is this trace broken" or "why can't I find this request's logs".
- Symptoms:
  - A trace stops at a service boundary: the far side of an HTTP call or a queue starts a new trace.
  - A log record emitted during a request has no `trace_id`.
  - A metric attribute holds an order ID, user ID, email, or free text.
  - Spans on getters, mappers, validators, controllers, or one per loop item.
  - Telemetry with no `service.name`, or `unknown_service`.
  - A vendor SDK import (Datadog, Sentry tracing, a Grafana-specific agent) in application code.
  - A hard-coded collector endpoint or sampler in code.

## Export contract

The application exports traces, metrics, and logs over **OTLP to a collector**. Configuration is by the standard environment variables only:

| Variable | Purpose |
|---|---|
| `OTEL_SERVICE_NAME` | `service.name`; required. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector endpoint. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` by default; `grpc` when the project chooses it. |
| `OTEL_RESOURCE_ATTRIBUTES` | `service.version`, `service.namespace`, `deployment.environment.name`, others. |
| `OTEL_TRACES_SAMPLER` | Sampler choice. |
| `OTEL_TRACES_SAMPLER_ARG` | Sampler argument. |
| `OTEL_LOG_LEVEL` | SDK's own diagnostic level. |

**No endpoint or sampler is hard-coded in application code.** On Spring these variables reach the Micrometer path through `management.*` property mapping in configuration; see [Metrics](#metrics). Code that builds an exporter with a URL literal, or a sampler with a ratio literal, is wrong even if the value matches today's deployment.

**Required resource attributes:**

| Attribute | When |
|---|---|
| `service.name` | Always. Missing `service.name` is a verification failure. |
| `service.version` | Always. |
| `service.namespace` | When the app belongs to a system of services. |
| `deployment.environment.name` | Always. |

**Protocol default: OTLP over HTTP/protobuf.** It needs fewer native dependencies and passes through ordinary HTTP proxies. gRPC is permitted when the project chooses it.

**Propagators: W3C `tracecontext` and `baggage`, both always on.** B3 only if an upstream system requires it, and then in addition, never instead.

**Never crash, never block.** The SDK must never crash or block the app when no collector is reachable. Long-lived processes use batch processors with bounded queues; export failures are logged once at `WARN` and then suppressed; a shutdown hook flushes gracefully with a bounded timeout.

**Serverless is the exception to batching:** nothing may be buffered. See [Serverless](#serverless).

**No vendor SDKs or direct-to-backend exporters.** The app speaks OTLP; the collector decides where data goes.

## Span tiers

| Tier | What | Mechanism | Rule |
|---|---|---|---|
| 1 | Inbound server, outbound HTTP client, database, messaging, cache | Auto-instrumentation | Confirm present; never hand-write. Context propagation across every one is a hard rule. |
| 2 | Public methods on services and repositories | Class-level annotation or aspect (JVM); `withSpan` wrapper (Node) | Always. Applied at the class so new methods are covered without remembering. |
| 3 | Anything else | Explicit span | Only if it would earn a bar on a flame graph: does IO, can plausibly exceed a few milliseconds, or is a decision point worth debugging later (cache miss, branch taken). Otherwise an attribute or span event on the parent. |

**Tier 2 on the JVM is a custom aspect, not `@WithSpan` alone.** `@WithSpan` is method-target only and records no metrics, so it cannot deliver class-level coverage plus the default instruments. On Spring the aspect records each call through a Micrometer `Observation` named `app.service.duration`, which yields the span and the duration histogram, and increments an explicit Counter `app.service.calls`. Elsewhere it uses the OTel tracer and meter directly. On Node, a `withSpan` wrapper applied to the service and repository objects does the same.

**Don'ts.** No spans on:

- controllers or route handlers (the server span covers them);
- mappers, validators, getters, utilities;
- items inside a loop over a collection, unless the body does IO. Use one span with an `item.count` attribute instead.

**Naming.** Low-cardinality. Tier 2 spans are `ClassName.method` (`OrderService.getOrder`, `OrderRepository.findById`) with a fully qualified `code.function.name` attribute per semantic conventions (JVM `fixture.OrderService.getOrder`, Node `OrderService.getOrder`). `code.namespace` is deprecated; do not emit it. IDs and other high-cardinality values go in attributes (`order.id`), never in the name. `OrderService.getOrder 42` breaks every aggregation the backend does.

**Error rule.** The span whose operation failed **records the exception event and sets status `ERROR`**. Ancestors the failure propagates out of set status `ERROR` only, without recording the exception again. Ancestors that catch and handle the failure stay `UNSET`. An auto-instrumented server span that records the exception by default is accepted as the ecosystem norm; do not fight it. A handled 404 is not an error on the server span: `GET /orders/404` ends with no span in `ERROR`; `GET /orders/boom`, where `OrderService.getOrder` throws and the 500 propagates, marks the service span (exception event plus `ERROR`) and the server span (`ERROR`).

**Async rule.** A job that runs later gets **its own root span with a span link to the triggering trace**, not a parent relationship. `AuditJob.record` enqueued during `GET /orders/42` starts a new trace and links back to the request's span. A parent relationship would stretch the request trace over the job's lifetime and misattribute its duration.

## Metrics

**Default set, from the Tier 2 wrapper, no per-method code.** Every public service and repository method emits:

| Name | Instrument | Unit | Attributes |
|---|---|---|---|
| `app.service.calls` | Counter | `{call}` | `code.function.name`, `outcome` |
| `app.service.duration` | Histogram | `s` | `code.function.name`, `outcome` |

`outcome` is `success` or `error`, nothing else. Together they give rate, errors, and duration per service method. Auto-instrumentation supplies the HTTP and database layers. **Runtime metrics are turned on**: JVM memory and GC, Node event loop and heap.

**Business metrics** exist when a question someone will ask of the running system demands one, not speculatively.

**Instrument choice:**

| Instrument | Use for | Example |
|---|---|---|
| Counter | Events that only go up | `order.placed` (`{order}`) |
| UpDownCounter | Additive levels that rise and fall; an observable UpDownCounter when the level is owned elsewhere and read at collection time | `order.in_flight` (`{order}`); `audit.queue.depth` (`{message}`) read from the broker |
| Histogram | Durations and sizes | `pricing.quote.duration` (`s`) |
| Observable gauge | A non-additive current value (ratio, temperature) sampled at collection time | `pricing.cache.hit_ratio` (`1`) |

**Naming rules:**

- Dotted lowercase, singular namespace, domain first: `order.placed`, not `orders.placed` or `placed_orders`.
- A plural final noun only when the instrument counts those things and the unit is `{thing}`: `app.service.calls` with unit `{call}`.
- Never a `_total` suffix or any other suffix the backend adds: `order.placed`, not `order_placed_total`.
- Units in UCUM (`s`, `By`, `{order}`); durations in seconds, never milliseconds in the name.
- Attributes are low-cardinality. **Never an ID, email, or free text.** `order.id` belongs on a span, not on a metric.

**Spring uses the ecosystem path.** A Spring app uses Actuator with Micrometer for metrics exported over OTLP, Micrometer Tracing with the OTel bridge for traces, and the OTel Logback appender for logs. Tier 1 metric names are therefore Micrometer's (`http.server.requests`, `jvm.memory.used`) on Spring and semantic-convention names on Node. That difference is accepted: a Spring developer expects Micrometer names, and the collector can rename if a deployment needs uniformity. **Tier 2 and business metrics use OTel naming on every stack**, registered through Micrometer on Spring and through the OTel API elsewhere. Spring's Micrometer OTLP path reads `management.otlp.*` and `management.tracing.sampling.probability` (default 0.1), not most `OTEL_*` variables, so the Spring reference maps the `OTEL_*` variables onto the `management.*` properties in configuration, never in code, with sampling 1.0 unless the variable says otherwise. Micrometer's OTLP registry also defaults to milliseconds; set `management.otlp.metrics.export.base-time-unit=seconds` so `app.service.duration` is really in `s` ([references/jvm-spring.md](references/jvm-spring.md) has the mapping). Non-Spring JVM frameworks (Ktor, JAX-RS, plain JVM) use the OTel SDK and its instrumentation directly. Node uses the OTel JS SDK.

## Logs

Logs reach the pipeline through **two appenders fed by the same log call** (the model is defined in [`application-logging`](../../../application-logging/skills/application-logging/SKILL.md)):

- **Console appender, for humans.** One readable line on stdout, or one JSON line with `LOG_FORMAT=json`. Owned by `application-logging`.
- **OTel appender, for the pipeline.** Owned here. JVM: the OTel Logback appender. Node: pino with the OTel pino instrumentation. Each log call becomes an OTel log record over OTLP; structured key-value arguments become record attributes.

**Correlation fields are `trace_id` and `span_id` on every stack.** The instrumentation attaches them from the active span; nobody copies them by hand. A record emitted while a span is active without both fields is a High finding.

On Spring the OTel Logback appender must be installed into the same `OpenTelemetry` instance the Micrometer bridge uses, or log records export without resource attributes or not at all. On reactive and coroutine code the MDC needs an explicit bridge (see [Known dropped balls](#known-dropped-balls)).

## Background and messaging

- **Background jobs:** own root span, span link to the triggering span. The link context is captured at enqueue time and carried with the job.
- **Messaging:** producer and consumer spans follow the messaging semantic conventions. The producer injects context into message headers; the consumer **extracts context from the headers before opening the consumer span**; the consumer span is a child of the extracted context (same trace) and also carries a link to it.
- **Tested mechanisms:** the stack references carry tested recipes for Spring `@Async` and `@Scheduled`, Spring AMQP with RabbitMQ (producer and consumer spans with links, context in message headers), Nitro scheduled tasks, and RabbitMQ from Node via the `amqplib` instrumentation. Other brokers and job runners get the generic rule above.

## Serverless

Serverless and edge deployments are in scope. The process can end at any moment after the handler returns, so **nothing may be buffered**:

- use the simple span and log processors, which export immediately; or
- call `forceFlush` on the tracer and logger providers before the handler returns;

whichever the runtime supports. **Metrics always need `forceFlush` on the MeterProvider before the handler returns**, whichever option is chosen: there is no simple metric reader, so a periodic reader holds the last invocation's points. Where the framework or platform offers a streaming export path, use it instead. Batch processors with a background flush lose the last invocation's telemetry when the platform freezes the process. Nitro serverless and edge presets lack some auto-instrumentations and replace the preload hook with explicit initialisation at module load; [references/node.md](references/node.md) carries that path, and [references/jvm-other.md](references/jvm-other.md) carries the Lambda-style JVM handler.

## Known dropped balls

The places context is lost most often. Each one breaks a trace silently.

- **Kotlin coroutines** need the `opentelemetry-extension-kotlin` context bridge; every `async`/`launch` must carry the context element.
- **WebFlux and any Reactor code** carry context on the Reactor context: they need the Reactor instrumentation, automatic context propagation enabled, and an explicit bridge for MDC, since MDC is thread-local.
- **JVM thread pools and `CompletableFuture`** need the context-wrapping executor.
- **Node code that breaks async context** (callbacks through event emitters, manual promise chains across workers) must bind context explicitly.
- **RabbitMQ consumers** must extract context from headers before opening the consumer span, or the trace breaks at the broker.

## Verification

Three layers. The first two run before reporting done; templates are in [references/verification.md](references/verification.md), with the collector config at [assets/collector-test.yaml](assets/collector-test.yaml) and the compose file at [assets/docker-compose.otel.yaml](assets/docker-compose.otel.yaml).

1. **Component tests, in-process.** An in-memory span exporter (JVM: `InMemorySpanExporter` from `opentelemetry-sdk-testing` and its JUnit 5 extension; Node: `@opentelemetry/sdk-trace-base`), plus an in-memory log record exporter and metric reader.
2. **Integration test, real collector.** Testcontainers starts the official collector image with a config that receives OTLP and writes to a file exporter. The app is configured only through `OTEL_*` variables pointed at the container. The test reads the file and asserts that spans, log records, and metrics all arrived, and that log records carry the trace ID of a span in the same file. One per project.
3. **Local compose file, for humans.** One `grafana/otel-lgtm` service plus the collector config, host ports read from environment variables with the standard defaults. A convenience, not a gate.

**Checklist**

Component tests:
- [ ] A server span exists for a request; Tier 2 service and repository spans are its descendants in the expected order (`OrderRepository.findById` under `OrderService.getOrder`).
- [ ] An outbound call during the request produces a client span, and the receiving side (an in-process stub server) reports a server span with the same trace ID.
- [ ] A coroutine or async hop inside the service keeps the parent span.
- [ ] A log emitted inside the request carries `trace_id` and `span_id` equal to the active span.
- [ ] `app.service.calls` and `app.service.duration` were recorded with `code.function.name` and `outcome`; no `code.namespace`.
- [ ] No span has `ERROR` status on the happy path. On the failure path the failing operation's span carries the exception event and `ERROR`; ancestors the failure propagated out of carry `ERROR` (an auto-instrumented server span may also record the exception); ancestors that handled it stay `UNSET`.
- [ ] A background job triggered during the request starts its own trace and carries a span link to the triggering span.

Integration test:
- [ ] Spans, log records, and metrics all arrived at a real collector configured only through `OTEL_*` variables.
- [ ] Log records in the collector output carry the trace ID of a span in the same output.

Configuration and wiring:
- [ ] Resource attributes present: `service.name`, `service.version`, `deployment.environment.name`, and `service.namespace` when part of a system.
- [ ] Propagators configured: W3C `tracecontext` and `baggage`.
- [ ] No endpoint or sampler in code; no vendor SDK imports.
- [ ] SDK shutdown hook registered, with a bounded flush timeout (or per-invocation flush on serverless).
- [ ] App starts and serves requests with no collector reachable.
- [ ] Runtime metrics on.
- [ ] Console appender readable; pipeline appender on.
- [ ] Denylist grep clean (the grep and the denylist are in `application-logging`).

## Red flags

- An exporter built with a URL literal, or a sampler with a hard-coded ratio.
- A vendor tracing SDK or agent alongside or instead of OTLP.
- B3 configured instead of W3C `tracecontext`.
- Hand-written spans for inbound HTTP, outbound HTTP, database, or messaging calls that auto-instrumentation covers.
- A service or repository class whose public methods produce no span.
- `@WithSpan` on individual methods as the Tier 2 mechanism.
- A span opened in a controller, route handler, mapper, validator, getter, or per loop item.
- An ID, timestamp, or user value in a span name.
- `ERROR` on an ancestor that caught and handled the failure, or on a handled 404.
- `code.namespace` emitted, or `code.function.name` not fully qualified.
- A background job that becomes a child of the request span, or has no link to it.
- `GlobalScope.launch`, a raw `Executors` pool, or `CompletableFuture.supplyAsync` without context wrapping in instrumented code.
- A message consumer that opens its span before extracting header context.
- A metric attribute holding an ID, email, URL with path parameters, or free text.
- A counter named `*_total` or a duration metric in milliseconds.
- `trace_id` copied into MDC or a child logger by hand.
- A batch processor with no forced flush in a serverless handler.
- No shutdown hook, or an unbounded flush on shutdown.
- "Done" with no test that asserts a span, a log correlation, or a metric.

## Common rationalizations

| Rationalization | Reality |
|---|---|
| "The agent will auto-instrument everything." | Auto-instrumentation gives Tier 1 only: the edges of the process. Your services and repositories are invisible, and coroutines, Reactor, executors, and queues still drop context unless wired. |
| "We'll add tracing when we need it." | You need it during the incident, and the incident is not the time to discover the trace stops at `PricingClient`. Wiring is a few files today. |
| "Batch export is fine on Lambda." | The platform freezes the process after the handler returns; the batch never ships. Simple span and log processors or `forceFlush` per invocation, plus `forceFlush` on the MeterProvider every time. |
| "A span per item makes the trace complete." | It makes the trace unreadable and expensive. One span with `item.count`; per-item spans only when each item does IO. |
| "The log line has the order ID, that's enough correlation." | The order ID finds this order's lines, not the request's other lines, the downstream service's lines, or the span that was slow. `trace_id` does all of that. |
| "Micrometer names are wrong, use semconv." | On Spring the ecosystem norm wins for Tier 1: developers and dashboards expect `http.server.requests`. The collector can rename. Tier 2 and business metrics use OTel names everywhere. |
| "`NOT_FOUND` should be an error span." | A 404 is a correct answer to a question about something that is not there. Marking it `ERROR` turns every missing order into an error-rate spike. |
| "One `@WithSpan` on the controller covers it." | The server span already covers the controller. `@WithSpan` is method-only, records no metrics, and misses every new method; Tier 2 is a class-level aspect on services and repositories. |
| "We hard-code the endpoint, it never changes." | It changes per environment, per test, and per laptop. `OTEL_EXPORTER_OTLP_ENDPOINT` is the one place everyone looks. |
| "The ancestor spans should be red too, the request failed." | The exception event belongs to the operation that failed; ancestors get `ERROR` only when the failure propagates out of them, and stay `UNSET` when they handled it. Otherwise every error points at the root and the culprit is hidden. |

## How to present findings

When this skill drives an audit, review, or design answer, three guardrails apply:

1. **Don't cite this skill in the output.** Argue from consequences in your own voice: "the consumer opens its span before extracting headers, so every message starts a new trace" beats "the skill requires extraction first".
2. **Stay in lane: traces, metrics, propagation, export, the pipeline appender, verification.** Record content, levels, and the denylist belong to `application-logging`; collector and backend configuration, dashboards, alerting, and RUM are out of scope. Name an out-of-lane issue in one sentence and defer.
3. **Tag every finding with severity** so the reader can triage down the left margin.

For the canonical findings format (preamble, severity-tagged findings with file:line citations, source of truth per finding, a formal answer even with no findings), compose with [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md). That skill governs how to present; this one governs what to flag.

Severity ladder, shared with `application-logging`:

| Severity | Criterion | Telemetry examples |
|---|---|---|
| **Critical** | Secrets or PII in logs; context lost across a process boundary. | Outbound call without propagation; consumer that does not extract headers; a token in a span or log attribute. |
| **High** | Tier 1 or Tier 2 span missing; log without trace context; metric with an ID attribute. | Repository with no spans; a record under an active span without `trace_id`; `order.id` on `app.service.calls`; coroutine hop that loses the parent. |
| **Medium** | Naming or unit convention miss; exception logged at multiple layers; missing resource attribute. | `order_placed_total`; duration in ms; ID in a span name; no `service.version`; `ERROR` on a handled 404. |
| **Low** | Level nit; message wording. | A Tier 3 span that should be an attribute; a span event that could name its entity more clearly. |

## Invocation examples

- "This Spring Boot app must support OTel. Wire it and prove it."
- "Add tracing to the orders service; the pricing call should show up in the same trace."
- "Review this PR for telemetry: propagation, span coverage, log correlation. Tag findings with severity."
- "Why is this trace broken after the RabbitMQ hop?"
- "Design the metrics for order placement; should `order.id` be an attribute?"

## How to extend for a project

Projects typically need a thin companion skill that locks in what this one leaves open:

- `service.namespace` and the `service.name` scheme for the system.
- The sampler and ratio per environment (set in deployment, documented in the companion).
- The business metrics catalog: names, instruments, units, allowed attribute values.
- Project-specific Tier 3 spans worth keeping (the cache, the pricing decision).
- Any upstream that requires B3 in addition to W3C.
- Where the Tier 2 aspect or `withSpan` wrapper lives, and which packages it covers.

Name it something like `<project>-telemetry` and have it reference this skill as its foundation.

## See also

- [`application-logging`](../../../application-logging/skills/application-logging/SKILL.md): record content, levels, the console appender, and the denylist.
- [references/semantic-conventions.md](references/semantic-conventions.md): HTTP, DB, messaging, code, error, resource, and log attribute names.
- [references/jvm-spring.md](references/jvm-spring.md): Spring Boot MVC and WebFlux on Actuator, Micrometer, and the OTel bridge; Tier 2 aspect; `@Async`, `@Scheduled`, Spring AMQP.
- [references/jvm-spring-tests.md](references/jvm-spring-tests.md): Spring component tests on in-memory exporters and the Testcontainers collector test.
- [references/jvm-other.md](references/jvm-other.md): Ktor, JAX-RS, plain JVM on the OTel SDK; the Java agent; Lambda-style handlers.
- [references/node.md](references/node.md): Nuxt/Nitro long-lived and serverless, plain Node, Express-style; `withSpan`; `amqplib`; pino.
- [references/verification.md](references/verification.md): component, integration, and local compose layers.
- [assets/collector-test.yaml](assets/collector-test.yaml) and [assets/docker-compose.otel.yaml](assets/docker-compose.otel.yaml).
- [`java-practices`](../../../java-practices/skills/java-practices/SKILL.md) and [`kotlin-practices`](../../../kotlin-practices/skills/kotlin-practices/SKILL.md): JVM code conventions the wiring follows.
- `nuxt`: Nuxt and Nitro conventions for the server side.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md): the findings format reviews compose with.
