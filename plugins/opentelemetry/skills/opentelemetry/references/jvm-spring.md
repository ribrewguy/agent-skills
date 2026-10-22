# Spring Boot: Actuator, Micrometer, and the OTel bridge

Wiring for Spring Boot MVC and WebFlux apps, in Kotlin. The rules (what gets a span, which metrics, the error and async rules, the export contract) live in [SKILL.md](../SKILL.md#span-tiers); this file says how to deliver them on Spring. Examples use the project's invented service: `OrderService`, `OrderRepository`, `PricingClient`, `AuditJob`, and the `orders` and `pricing` routes, in package `fixture`.

## General approach

A Spring app takes the ecosystem path ([Metrics](../SKILL.md#metrics)): Actuator with Micrometer `Observation` as the single instrumentation API, Micrometer Tracing with the OTel bridge turning observations into OTel spans, Micrometer's OTLP registry exporting metrics, and the OTel Logback appender exporting logs through the same `OpenTelemetry` bean Spring Boot builds. Spring instruments Tier 1 itself: inbound HTTP (`http.server.requests`), `RestClient` and `WebClient` built from the auto-configured builders, `@Scheduled`, and Spring AMQP once observation is switched on. Tier 2 is one aspect, `ServiceObservationAspect`, that wraps every public method of every `@Service` and `@Repository` bean in an `Observation`. Configuration is `application.yaml` only: the `OTEL_*` variables are mapped onto `management.*` properties with `${}` placeholders, so no code ever names an endpoint or a sampler.

Spring Boot 4 reorganised the OpenTelemetry properties and starters. This file gives both lines: Boot 4.x, and Boot 3.4 to 3.5 (3.4 is the first with OTLP log export). Earlier Boot 3 lines lack log export; upgrade rather than hand-build it.

## Dependencies

Name artifacts; the build pins versions (the Spring Boot BOM manages all of these except the OTel instrumentation artifacts, which the `io.opentelemetry.instrumentation:opentelemetry-instrumentation-bom` manages).

| Purpose | Boot 4.x | Boot 3.4 to 3.5 |
|---|---|---|
| Actuator (observation, JVM runtime metrics) | `org.springframework.boot:spring-boot-starter-actuator` | same |
| Tracing bridge, OTLP span and log exporter, OTLP metrics registry | `org.springframework.boot:spring-boot-starter-opentelemetry` | `io.micrometer:micrometer-tracing-bridge-otel`, `io.opentelemetry:opentelemetry-exporter-otlp`, `io.micrometer:micrometer-registry-otlp` |
| Tier 2 aspect | `org.springframework.boot:spring-boot-starter-aspectj` (renamed in Boot 4) | `org.springframework.boot:spring-boot-starter-aop` |
| Pipeline log appender | `io.opentelemetry.instrumentation:opentelemetry-logback-appender-1.0` | same |
| Context across threads, Reactor, coroutines | `io.micrometer:context-propagation` | same |
| Coroutine bridges | `io.opentelemetry:opentelemetry-extension-kotlin`, `org.jetbrains.kotlinx:kotlinx-coroutines-slf4j`, `org.jetbrains.kotlinx:kotlinx-coroutines-reactor` | same |
| Messaging (when used) | `org.springframework.boot:spring-boot-starter-amqp` | same |
| Tests | `io.opentelemetry:opentelemetry-sdk-testing`, `org.testcontainers:testcontainers`, `org.testcontainers:junit-jupiter`, `org.awaitility:awaitility-kotlin` | same |

Kotlin classes are final; the `kotlin-spring` compiler plugin opens `@Service`, `@Repository`, and `@Component` classes so the aspect's proxy can subclass them.

**The alternative path is `io.opentelemetry.instrumentation:opentelemetry-spring-boot-starter`.** It brings OTel's own instrumentation with semantic-convention names (`http.server.request.duration`, `http.route`) and reads every `OTEL_*` variable natively. The trade-off: it instruments the same edges Micrometer Tracing does, so running both produces duplicate server and client spans, and Tier 2 then belongs on the OTel API, not `Observation`. Pick one: this file's Micrometer path (the default here), or the OTel starter with `micrometer-tracing-bridge-otel` and Boot's tracing auto-configuration removed. Never both.

## Configuration

Spring's Micrometer path reads `management.*` properties, not most `OTEL_*` variables, and its sampling default is 0.1. The mapping below lives in `application.yaml`, never in code:

| Variable | Boot 4.x property | Boot 3.4 to 3.5 property |
|---|---|---|
| `OTEL_SERVICE_NAME` | `spring.application.name` (Boot also merges the variable into the `Resource`) | same |
| `OTEL_EXPORTER_OTLP_ENDPOINT` + `/v1/traces` | `management.opentelemetry.tracing.export.otlp.endpoint` | `management.otlp.tracing.endpoint` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` + `/v1/metrics` | `management.otlp.metrics.export.url` | same |
| `OTEL_EXPORTER_OTLP_ENDPOINT` + `/v1/logs` | `management.opentelemetry.logging.export.otlp.endpoint` | `management.otlp.logging.endpoint` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `management.opentelemetry.tracing.export.otlp.transport`, `management.opentelemetry.logging.export.otlp.transport` (`http` or `grpc`) | `management.otlp.tracing.transport`, `management.otlp.logging.transport` |
| `OTEL_EXPORTER_OTLP_HEADERS` (backend auth) | `management.opentelemetry.tracing.export.otlp.headers.*`, `management.opentelemetry.logging.export.otlp.headers.*`, `management.otlp.metrics.export.headers.*` | `management.otlp.tracing.headers.*`, `management.otlp.logging.headers.*`, `management.otlp.metrics.export.headers.*` |
| `OTEL_METRIC_EXPORT_INTERVAL` (milliseconds) | `management.otlp.metrics.export.step` (a duration: `60s` is the OTel default) | same |
| `OTEL_TRACES_SAMPLER` | `management.opentelemetry.tracing.sampler` | none; Boot 3 always uses parent-based ratio sampling |
| `OTEL_TRACES_SAMPLER_ARG` | `management.tracing.sampling.probability`, default `1.0` here | same |
| `OTEL_RESOURCE_ATTRIBUTES` | merged into the `Resource` and the OTLP registry; `management.opentelemetry.resource-attributes.*` overrides | same on 3.5 (verify on 3.4, see [Known complexities](#known-complexities)) |
| (none) | `management.otlp.metrics.export.base-time-unit: seconds`, so `app.service.duration` is in `s` | same |

Boot 4 also maps `OTEL_*` variables onto these properties by itself (`management.opentelemetry.map-environment-variables`, default `true`). The explicit placeholders below make the mapping visible, work identically on Boot 3, and also resolve from test property sources, which is what lets the integration test configure the app through `OTEL_EXPORTER_OTLP_ENDPOINT`. Each endpoint honours the signal-specific variable first, then the general one plus the signal path, then the standard local default.

`OTEL_EXPORTER_OTLP_HEADERS` is a comma-separated `key=value` list and a placeholder cannot split it into a map property. Give each header its own placeholder (`"[authorization]": ${OTLP_AUTHORIZATION:}` under each `headers` key, the value from a secret) in the profile that talks to an authenticated backend, or leave auth to a collector sidecar. Boot 4's own environment mapping may handle the variable directly; check the bound value under `/actuator/configprops` before relying on it. Never put the header value in the file.

**Boot 4.x `application.yaml`:**

```yaml
spring:
  application:
    name: ${OTEL_SERVICE_NAME:orders}
  reactor:
    context-propagation: auto            # same as Hooks.enableAutomaticContextPropagation()
management:
  tracing:
    sampling:
      probability: ${OTEL_TRACES_SAMPLER_ARG:1.0}
    propagation:
      type: w3c                          # W3C tracecontext; W3C baggage rides along while baggage is enabled (the default)
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318}/v1/traces}
          transport: http
    logging:
      export:
        otlp:
          endpoint: ${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318}/v1/logs}
          transport: http
  otlp:
    metrics:
      export:
        url: ${OTEL_EXPORTER_OTLP_METRICS_ENDPOINT:${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318}/v1/metrics}
        base-time-unit: seconds
  metrics:
    distribution:
      percentiles-histogram:
        "[app.service.duration]": true   # export histogram buckets, not only count and sum
```

**Boot 3.4 to 3.5 `application.yaml`:** the same `spring` block and `management.tracing`, `management.otlp.metrics`, and `management.metrics` blocks, with the trace and log exporters under `management.otlp`:

```yaml
management:
  otlp:
    tracing:
      endpoint: ${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318}/v1/traces}
      transport: http
    logging:
      endpoint: ${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318}/v1/logs}
      transport: http
    metrics:
      export:
        url: ${OTEL_EXPORTER_OTLP_METRICS_ENDPOINT:${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318}/v1/metrics}
        base-time-unit: seconds
```

**gRPC**, when the project chooses it: `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` cannot be passed through a placeholder, because Spring's values are `http` and `grpc` and gRPC endpoints take no path suffix. Put the gRPC values in a profile (`application-otlp-grpc.yaml`) activated by deployment: `transport: grpc` and the endpoints as `${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4317}` without `/v1/...`. Micrometer's OTLP registry speaks HTTP only (as of this writing), so the metrics URL keeps the collector's HTTP port.

What the configuration already gives without code: W3C `tracecontext` and `baggage` propagation; batch span and log processors with bounded queues; JVM memory, GC, and thread metrics from Actuator; export failures logged by the OTel exporter's throttled logger instead of thrown; and a graceful flush when the context closes, bounded by the SDK's shutdown timeout and `spring.lifecycle.timeout-per-shutdown-phase`. The app starts and serves with no collector reachable.

`management.observations.key-values` is not a resource-attribute mechanism: it adds a low-cardinality tag to every observation, so every span and every metric. Use it only for a tag you want on each data point.

## Tier 2 aspect

`ServiceObservationAspect` records each public `@Service` or `@Repository` call through one `Observation` named `app.service.duration` with contextual name `ClassName.method`. The tracing handler turns it into the span `OrderService.getOrder`; `DefaultMeterObservationHandler` turns it into the timer `app.service.duration` (histogram, `s`). The aspect adds `code.function.name` (fully qualified: `fixture.OrderService.getOrder`) and `outcome` as low-cardinality key-values, so both appear on the span and the timer, and increments the counter `app.service.calls` (unit `{call}`) with the same two attributes. No `code.namespace`.

```kotlin
package fixture.telemetry

import io.micrometer.core.instrument.Counter
import io.micrometer.core.instrument.MeterRegistry
import io.micrometer.observation.Observation
import io.micrometer.observation.ObservationRegistry
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor
import io.opentelemetry.api.trace.Span
import io.opentelemetry.api.trace.StatusCode
import org.aspectj.lang.ProceedingJoinPoint
import org.aspectj.lang.annotation.Around
import org.aspectj.lang.annotation.Aspect
import org.aspectj.lang.reflect.MethodSignature
import org.reactivestreams.Publisher
import org.springframework.aop.support.AopUtils
import org.springframework.core.KotlinDetector
import org.springframework.stereotype.Component
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono
import reactor.core.publisher.SignalType
import reactor.util.context.ContextView
import java.util.Collections
import java.util.WeakHashMap
import java.util.concurrent.atomic.AtomicBoolean

@Aspect
@Component
class ServiceObservationAspect(
    private val observations: ObservationRegistry,
    private val meters: MeterRegistry,
) {
    // Exceptions already recorded as an event by the span where they originated (identity semantics).
    private val recorded: MutableSet<Throwable> =
        Collections.synchronizedSet(Collections.newSetFromMap(WeakHashMap()))

    @Around(
        "(@within(org.springframework.stereotype.Service) || @within(org.springframework.stereotype.Repository))" +
            " && execution(public * *(..))",
    )
    fun observe(pjp: ProceedingJoinPoint): Any? {
        val type = AopUtils.getTargetClass(pjp.target)
        val method = (pjp.signature as MethodSignature).method
        val function = "${type.name}.${method.name}"
        val name = "${type.simpleName}.${method.name}"
        // A suspend fun reaches the aspect as a Mono (Spring AOP adapts coroutines through Reactor).
        return when {
            KotlinDetector.isSuspendingFunction(method) || Mono::class.java.isAssignableFrom(method.returnType) ->
                Mono.deferContextual { ctx -> observeReactive(pjp, ctx, name, function) { Mono.from(it) } }
            Flux::class.java.isAssignableFrom(method.returnType) ->
                Flux.deferContextual { ctx -> observeReactive(pjp, ctx, name, function) { Flux.from(it) } }
            else -> observeBlocking(pjp, name, function)
        }
    }

    private fun start(name: String, function: String, parent: Observation?): Observation =
        Observation.createNotStarted(DURATION, observations)
            .contextualName(name)
            .lowCardinalityKeyValue(CODE_FUNCTION, function)
            .parentObservation(parent ?: observations.currentObservation)
            .start()

    private fun observeBlocking(pjp: ProceedingJoinPoint, name: String, function: String): Any? {
        val observation = start(name, function, parent = null)
        val result = try {
            observation.openScope().use { pjp.proceed() }
        } catch (e: Throwable) {
            fail(observation, e)
            complete(observation, function, failed = true)
            throw e
        }
        complete(observation, function, failed = false)
        return result
    }

    // Starts at subscription, not assembly. Subscribes the source inside the observation's scope, so a
    // coroutine body (started synchronously on Dispatchers.Unconfined) sees this span as current on
    // every Spring line, not only where PropagationContextElement exists.
    private fun <P : Publisher<Any?>> observeReactive(
        pjp: ProceedingJoinPoint, ctx: ContextView, name: String, function: String, wrap: (Publisher<Any?>) -> P,
    ): P {
        val observation = start(name, function, ctx.getOrDefault<Observation>(ObservationThreadLocalAccessor.KEY, null))
        val done = AtomicBoolean(false)
        @Suppress("UNCHECKED_CAST")
        val source: Publisher<Any?> = try {
            observation.openScope().use { pjp.proceed() as Publisher<Any?> }
        } catch (e: Throwable) {
            Mono.error(e)
        }
        val scoped = Publisher<Any?> { subscriber -> observation.openScope().use { source.subscribe(subscriber) } }
        val observed: Publisher<Any?> = Flux.from(scoped)
            .doOnError { fail(observation, it) }
            .doFinally { if (done.compareAndSet(false, true)) complete(observation, function, failed = it == SignalType.ON_ERROR) }
            .contextWrite { it.put(ObservationThreadLocalAccessor.KEY, observation) }
        return wrap(observed)
    }

    private fun fail(observation: Observation, error: Throwable) {
        if (recorded.add(error)) {
            observation.error(error) // originating span: exception event plus ERROR
        } else {
            // the failure propagated out of a child that already recorded it: ERROR status only
            observation.openScope().use { Span.current().setStatus(StatusCode.ERROR) }
        }
    }

    private fun complete(observation: Observation, function: String, failed: Boolean) {
        val outcome = if (failed) "error" else "success"
        observation.lowCardinalityKeyValue(OUTCOME, outcome)
        Counter.builder(CALLS)
            .baseUnit("{call}")
            .description("Calls to public service and repository methods")
            .tag(CODE_FUNCTION, function)
            .tag(OUTCOME, outcome)
            .register(meters)
            .increment()
        observation.stop()
    }

    private companion object {
        const val DURATION = "app.service.duration"
        const val CALLS = "app.service.calls"
        const val CODE_FUNCTION = "code.function.name"
        const val OUTCOME = "outcome"
    }
}
```

Notes:

- `observation.error(e)` makes the bridge record the `exception` event and set `ERROR`. The `recorded` set is what keeps an ancestor Tier 2 span (`OrderService.getOrder` when `OrderRepository.findById` threw) from recording the same exception again; it sets `ERROR` through the OTel API while the observation's scope makes its span current. Ancestors that catch the exception never see it and stay `UNSET`.
- `DefaultMeterObservationHandler` also tags the timer with `error` (the exception's simple class name or `none`) and registers a long-task timer `app.service.duration.active`. Both are Micrometer's defaults; dashboards read `outcome`. On an ancestor that only set status, the timer's `error` tag stays `none`.
- The reactive path relies on Spring AOP handing the aspect a `Mono` for a `suspend fun` (it needs `kotlinx-coroutines-reactor` on the classpath). The observation starts when the `Mono` is subscribed, not when it is assembled, and the source is subscribed inside the observation's scope. Spring runs the coroutine on `Dispatchers.Unconfined`, so its body starts synchronously inside that scope, and the service's `Context.current()` captures the service span on Boot 3 and Boot 4 alike ([Spring MVC](#spring-mvc)). On Boot 4 (Spring Framework 7), `PropagationContextElement` additionally restores the observation on every resumption. `done` guards against a second `stop()` when both an error and a cancel arrive. The fixture test `coroutine hop keeps the parent span` is the proof on both lines.
- The aspect does not cover `AuditJob` (a `@Component`), controllers, or Spring Data repository interfaces, which carry no `@Repository` annotation; add `|| this(org.springframework.data.repository.Repository)` to the pointcut for those.

## Spring MVC

Inbound requests get a SERVER span from `ServerHttpObservationFilter`, auto-configured. Outbound calls get a CLIENT span and a `traceparent` header **only when the client is built from the auto-configured builder**:

```kotlin
@Component
class PricingClient(builder: RestClient.Builder, private val env: Environment) {
    private val client = builder.build() // the injected builder carries the observation registry

    // The port is read per call: singletons are built before the embedded server picks its port,
    // so a constructor-time local.server.port would fall back to a default under RANDOM_PORT.
    fun quote(id: String): Price =
        client.get().uri("http://localhost:{port}/pricing/{id}", env.getProperty("local.server.port"), id)
            .retrieve().body<Price>()!!
}
```

`RestClient.create()` or `RestTemplate()` built by hand has no observation registry: no client span, no propagation, and the far side starts a new trace (Critical).

**Coroutines.** A `suspend` service method that hops dispatchers loses thread-locals (the OTel `Context`, Micrometer's current observation, the MDC) unless the coroutine context carries them. Carry the OTel context with `opentelemetry-extension-kotlin` and the MDC with `MDCContext`:

```kotlin
@Service
class OrderService(private val orders: OrderRepository, private val pricing: PricingClient, private val audit: AuditJob) {
    private val log = LoggerFactory.getLogger(OrderService::class.java)

    suspend fun getOrder(id: String): Order? =
        withContext(Dispatchers.IO + Context.current().asContextElement() + MDCContext()) {
            val order = orders.findById(id) ?: return@withContext null   // span OrderRepository.findById, child of OrderService.getOrder
            val total = pricing.quote(id).price
            log.atInfo().addKeyValue("order.id", id).log("order fetched")
            audit.record(id)
            order.copy(total = total)
        }
}
```

`Context.current()` is evaluated when the coroutine body starts, which the aspect arranges to happen inside the `OrderService.getOrder` observation's scope, so it captures that span and the repository span on the IO thread parents correctly. On Boot 3 these explicit elements are required. On Boot 4 (Spring Framework 7) with `spring.reactor.context-propagation: auto`, Spring's own `PropagationContextElement` also restores the observation (and with it the span and MDC) on every resumption; the explicit elements are then redundant but harmless. Any `launch` or `async` in a scope without these elements (an application `CoroutineScope`, `GlobalScope`) starts with no trace context: High.

`ServiceObservationAspect` sees `getOrder` as a `Mono`; the `Mono` branch keeps the span open until the coroutine completes, not until it first suspends.

## Spring WebFlux

WebFlux keeps the current observation on the Reactor `Context`, not on a thread. Three things make spans and logs follow it:

1. **Automatic context propagation**, at startup: `Hooks.enableAutomaticContextPropagation()` in `main`, or `spring.reactor.context-propagation: auto` (already in the configuration above). Reactor then restores registered thread-locals around every operator.
2. **The observation accessor**, `ObservationThreadLocalAccessor`, which `micrometer-observation` registers with `context-propagation` through the service loader. Restoring the observation opens its scope, which makes the OTel span current and writes `traceId` and `spanId` into the MDC (Micrometer Tracing's event listener). Nothing to register by hand for tracing.
3. **Clients from the builder**: `WebClient.Builder` injected, never `WebClient.create()`.

Request-scoped MDC keys such as `request.id` still need their own accessors; that wiring is in the [`application-logging`](../../../../application-logging/skills/application-logging/SKILL.md) skill's JVM wiring. Tracing adds nothing to it.

```kotlin
@Service
class OrderService(private val orders: OrderRepository, private val pricing: PricingClient, private val audit: AuditJob) {
    private val log = LoggerFactory.getLogger(OrderService::class.java)

    fun getOrder(id: String): Mono<Order> =
        Mono.fromCallable { orders.findById(id) }                    // OrderRepository.findById, parent restored from the Reactor Context
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap { order -> pricing.quote(id).map { order.copy(total = it.price) } }
            .doOnNext {
                log.atInfo().addKeyValue("order.id", id).log("order fetched")
                audit.record(id).subscribe()                         // fire and forget; see Async and scheduled
            }
}
```

The aspect's `Mono` branch writes the `OrderService.getOrder` observation into the Reactor `Context` (`contextWrite`), so every operator upstream of it, including the callable on `boundedElastic`, runs with that span current. A `suspend` handler on WebFlux follows the MVC coroutine rule.

## Async and scheduled

**Context across `@Async` and executors.** Register a `TaskDecorator` that captures a `ContextSnapshot` on submit and restores it on the worker thread; Spring's `ContextPropagatingTaskDecorator` is exactly that:

```kotlin
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfig {
    @Bean
    fun contextPropagatingTaskDecorator(): TaskDecorator = ContextPropagatingTaskDecorator()
}
```

Boot 3 applies a `TaskDecorator` bean to the auto-configured executor. Boot 4 documents `spring.task.execution.propagate-context: true` for the auto-configured executor and the bean for an executor you build yourself; set both. Any executor you construct by hand needs `setTaskDecorator(...)`; a raw `Executors` pool or `CompletableFuture.supplyAsync` without it drops the trace.

**`@Async` job triggered from a request: new root, span link to the caller.** The decorator makes the request's span current on the worker thread, which would make the job a child. Start a root deliberately, linking the inherited span:

```kotlin
@Component
class AuditJob(private val tracer: Tracer) {   // io.micrometer.tracing.Tracer
    private val log = LoggerFactory.getLogger(AuditJob::class.java)

    @Async
    fun record(id: String) {
        val trigger = tracer.currentSpan()?.context()           // carried here by the TaskDecorator
        val span = tracer.spanBuilder()
            .name("AuditJob.record")
            .setNoParent()                                      // own trace
            .apply { if (trigger != null) addLink(Link(trigger)) }
            .start()
        try {
            tracer.withSpan(span).use {                         // also switches the MDC to the job's trace
                log.atInfo().addKeyValue("order.id", id).log("audit recorded")
            }
        } catch (e: Exception) {
            span.error(e)
            throw e
        } finally {
            span.end()
        }
    }
}
```

The decorator carries what `context-propagation` accessors hold, chiefly Micrometer's current observation. On Boot 3, code inside `withContext(Dispatchers.IO + Context.current().asContextElement())` has the OTel context but not the observation thread-local (only Spring Framework 7's `PropagationContextElement` restores it), so the decorator snapshots no observation and the job sees no trigger. There, enqueue the job before the dispatcher hop, or upgrade to Boot 4.

The link points at the span that was current when the job was enqueued: `OrderService.getOrder`, which lives in the request's trace. It is not the SERVER span itself; assertions compare the link's trace ID with the request's.

On WebFlux, return `Mono<Void>` and capture `trigger` when `record` is called (assembly runs on the caller's restored context), then build the root span inside `Mono.fromRunnable { ... }`. Capturing at assembly avoids depending on whether a fire-and-forget `subscribe()` carries the caller's context.

**`@Scheduled`: root span, no parent, no link.** Spring instruments scheduled methods as an observation with no parent, so nothing to add: the job starts its own trace. Do not invent a link; nothing triggered it.

## RabbitMQ with Spring AMQP

Spring AMQP creates producer and consumer observations once enabled; the producer injects `traceparent` into message headers and the listener container extracts it before opening the consumer span, so the consumer span is a child in the same trace.

```yaml
spring:
  rabbitmq:
    template:
      observation-enabled: true
    listener:
      simple:
        observation-enabled: true
      direct:
        observation-enabled: true     # when the app uses direct listener containers
```

Or in code, for a template or container you build: `rabbitTemplate.setObservationEnabled(true)` and `container.setObservationEnabled(true)`. Build the `RabbitTemplate` from Boot's `RabbitTemplateConfigurer` or inject the auto-configured one, so it carries the `ObservationRegistry`.

The consumer span is a child of the producer by default; add the link the skill requires ([Background and messaging](../SKILL.md#background-and-messaging)) from the headers:

```kotlin
@Component
class AuditListener(openTelemetry: OpenTelemetry) {
    private val propagator = openTelemetry.propagators.textMapPropagator

    @RabbitListener(queues = ["orders.audit"])
    fun onAudit(message: Message) {
        val producer = propagator.extract(Context.root(), message.messageProperties.headers, HeaderGetter)
        Span.current().addLink(Span.fromContext(producer).spanContext)   // Span.addLink after start: needs an OTel API recent enough to have it
        // ... handle the message under the consumer span
    }

    private object HeaderGetter : TextMapGetter<Map<String, Any?>> {
        override fun keys(carrier: Map<String, Any?>) = carrier.keys
        override fun get(carrier: Map<String, Any?>?, key: String) = carrier?.get(key)?.toString()
    }
}
```

Messaging attributes on these spans are Spring AMQP's own key names, not all of the semantic-convention ones; confirm `messaging.system` and `messaging.destination.name` are present or add them with a custom `RabbitTemplateObservationConvention` and `RabbitListenerObservationConvention`.

## Lambda-style handler

A Spring Cloud Function or any handler the platform freezes after return must not leave telemetry in a buffer ([Serverless](../SKILL.md#serverless)). Boot owns the span and log processors (batch), so flush the providers per invocation; and because Micrometer's OTLP registry has no public per-invocation flush, bridge Micrometer into an OTel `SdkMeterProvider` (`io.opentelemetry.instrumentation:opentelemetry-micrometer-1.5`) and flush that. Profile `serverless`, with `management.otlp.metrics.export.enabled: false` in `application-serverless.yaml`:

```kotlin
@Configuration(proxyBeanMethods = false)
@Profile("serverless")
class ServerlessTelemetryConfig {
    @Bean // Boot registers an SdkMeterProvider bean into its OpenTelemetry bean
    fun sdkMeterProvider(resource: Resource, @Value("\${management.otlp.metrics.export.url}") url: String): SdkMeterProvider =
        SdkMeterProvider.builder()
            .setResource(resource)
            .registerMetricReader(PeriodicMetricReader.create(OtlpHttpMetricExporter.builder().setEndpoint(url).build()))
            .build()

    @Bean // Tier 2 and business meters now land in the SdkMeterProvider
    fun meterRegistry(openTelemetry: OpenTelemetry): MeterRegistry =
        OpenTelemetryMeterRegistry.builder(openTelemetry).build()
}

@Component
class GetOrderFunction(
    private val orders: OrderService,
    private val traces: SdkTracerProvider,
    private val logs: SdkLoggerProvider,
    private val metrics: SdkMeterProvider,
) : (String) -> Order? {
    override fun invoke(id: String): Order? = try {
        runBlocking { orders.getOrder(id) }
    } finally {
        CompletableResultCode.ofAll(listOf(traces.forceFlush(), logs.forceFlush(), metrics.forceFlush()))
            .join(5, TimeUnit.SECONDS)                                   // bounded: never hang the invocation
    }
}
```

The endpoint comes from the same property the long-lived app uses, so it is still configuration. `forceFlush` on the `SdkMeterProvider` is required on every invocation ([Serverless](../SKILL.md#serverless)); there is no simple metric reader. Where you own the SDK outright (no Boot auto-configuration), use `SimpleSpanProcessor` and `SimpleLogRecordProcessor` instead of flushing traces and logs, and still flush the meter provider.

## Logs

The pipeline appender is `io.opentelemetry.instrumentation.logback.appender.v1_0.OpenTelemetryAppender`, declared in `logback-spring.xml` as the [`application-logging`](../../../../application-logging/skills/application-logging/SKILL.md) skill's configuration does (`captureKeyValuePairAttributes` on). It must be installed into the `OpenTelemetry` bean Boot built, the one the tracing bridge and the log exporter use, or records leave without the resource or not at all. Spring Boot does not install it ([Spring Boot: Logging with OpenTelemetry](https://docs.spring.io/spring-boot/reference/actuator/loggers.html)); one bean does:

```kotlin
@Component
class OpenTelemetryAppenderInitializer(private val openTelemetry: OpenTelemetry) : InitializingBean {
    override fun afterPropertiesSet() = OpenTelemetryAppender.install(openTelemetry)
}
```

Records logged before this bean runs (early startup) are not exported; that is expected.

**Correlation.** The appender reads the trace and span from the current OTel `Context`, which the bridge keeps in step with the current observation, so each record's `trace_id` and `span_id` are right without any MDC. The console is different: Micrometer Tracing writes the MDC keys `traceId` and `spanId`, not `trace_id` and `span_id`. The console pattern and JSON encoder owned by `application-logging` read the Micrometer keys and present them under the standard names: `%X{traceId}` where that pattern reads `%X{trace_id}`, and in the JSON encoder `<mdcKeyFieldName>traceId=trace_id</mdcKeyFieldName>` and `<mdcKeyFieldName>spanId=span_id</mdcKeyFieldName>` inside `<mdc>`. Never copy the IDs into the MDC by hand. With `captureMdcAttributes` set to `*`, the OTel records also carry `traceId` and `spanId` as attributes; harmless, or list the request keys explicitly to drop them.

## Test templates

The test templates are in a separate file, `references/jvm-spring-tests.md`, listed in the skill's [See also](../SKILL.md#see-also): an in-memory `@TestConfiguration`, one component test per assertion in [Verification](../SKILL.md#verification) for MVC and WebFlux, and the Testcontainers collector test. Run both layers before reporting done.

## Known complexities

- **Boot 3 versus Boot 4 property names.** Boot 4 moved trace and log export under `management.opentelemetry.*` and the AOP starter to `spring-boot-starter-aspectj`; the metrics URL kept its name. Copying a Boot 3 key into a Boot 4 app is silently ignored: the exporter then posts to its default endpoint. Check the startup log or the `/actuator/configprops` endpoint for the bound value.
- **`OTEL_RESOURCE_ATTRIBUTES` on Boot 3.4.** The Boot 3.5 documentation states the variable is merged into the `Resource`; whether 3.4 does is unverified here. On 3.4, if the collector output lacks `service.version` or `deployment.environment.name`, upgrade, or set each under `management.opentelemetry.resource-attributes` from deployment variables (map keys with dots need brackets: `"[service.version]"`). A custom `Resource` bean turns the merge off.
- **Tier 1 names are Micrometer's.** The server span is named like `http get /orders/{id}` and carries `uri` (the route template), `method`, `status`, `outcome`, not `http.route`; the metric is `http.server.requests`. Accepted ([Metrics](../SKILL.md#metrics)); tests and probes match the route on `http.route` or `uri`. Spring Framework 7 offers OpenTelemetry-named observation conventions for HTTP; adopting them is a project choice.
- **Sampling defaults to 0.1** without the `management.tracing.sampling.probability` mapping. A test that sees one request in ten is this.
- **Handled 404s.** Return `null` or an empty `Optional` from the service and map it to `404` in the controller. Throwing `ResponseStatusException(NOT_FOUND)` from a service propagates out of the Tier 2 span and marks it `ERROR`.
- **Self-invocation.** A call from one method of `OrderService` to another on `this` bypasses the proxy and gets no span. Accept it (it is the same unit of work) or move the callee to its own bean.
- **Exceptions thrown as singletons.** The aspect's `recorded` set is identity-based; a reused exception instance gets its event only the first time. Do not reuse exception instances.
- **Server span and the exception.** Spring's server observation records the exception that escapes the handler, so on `GET /orders/boom` both the service span and the server span carry an `exception` event. The error rule accepts this auto-instrumented default.
- **Not compiled in this reference.** The following are from documentation and memory, to be confirmed by the fixture build: the WebFlux `Mono.fromCallable` plus `subscribeOn(Schedulers.boundedElastic())` hop keeping the service span current through automatic propagation; the aspect's subscribe-inside-scope behaviour on Boot 3; Micrometer `Span.Builder.setNoParent()` and `addLink(Link)`; Spring AOP handing the aspect a `Mono` for a `suspend fun`; the contrib collector image's default config path; `OpenTelemetryMeterRegistry` exporting timers in seconds; HTTP-only Micrometer OTLP registry.
