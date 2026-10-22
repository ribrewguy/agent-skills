# Non-Spring JVM: the OTel SDK directly

Wiring for JVM apps that are not Spring Boot: Ktor, JAX-RS (Jersey, RESTEasy), and plain JVM services, in Kotlin with Java where the API is Java-first. The rules (what gets a span, which metrics, the error and async rules, the export contract) live in [SKILL.md](../SKILL.md#span-tiers); this file says how to deliver them with the OTel SDK and its instrumentation libraries. It is the direct-SDK counterpart of `jvm-spring.md`: same span names, same metrics, same error rule. Examples use the project's invented service: `OrderService`, `OrderRepository`, `PricingClient`, `AuditJob`, and the `orders` and `pricing` routes, in package `fixture`.

## General approach

A non-Spring JVM app uses the OTel API and SDK as its only instrumentation API ([Metrics](../SKILL.md#metrics)). Four pieces:

1. **SDK autoconfigure** builds the `OpenTelemetrySdk` from the `OTEL_*` variables: exporters, processors, resource, propagators, sampler. No endpoint or sampler in code.
2. **Tier 1 from instrumentation libraries**, one per framework and client (Ktor server and client plugins, the JDK `HttpClient` wrapper, JDBC), each handed the same `OpenTelemetry` instance. Or from the **Java agent**, which instruments all of Tier 1 with no code and replaces pieces 1 and 2.
3. **Tier 2 from one wrapper**, `withServiceSpan` (Kotlin) or `ServiceSpans.run` (Java), around every public service and repository method. It opens the `ClassName.method` span and records `app.service.calls` and `app.service.duration` with the OTel meter.
4. **Logs** through `opentelemetry-logback-appender-1.0` installed into the same SDK, and `opentelemetry-logback-mdc-1.0` putting `trace_id` and `span_id` into each console event's MDC.

Context does not cross threads by itself on this path: executors need `Context.taskWrapping`, coroutines need `asContextElement()`. The agent does both automatically; the library path does neither.

**Dependencies.** Name artifacts; the build pins versions through `io.opentelemetry:opentelemetry-bom` and `io.opentelemetry.instrumentation:opentelemetry-instrumentation-bom-alpha` (the instrumentation libraries are mostly alpha).

| Purpose | Artifact |
|---|---|
| API (all application code compiles against this) | `io.opentelemetry:opentelemetry-api` |
| SDK, built from `OTEL_*` | `io.opentelemetry:opentelemetry-sdk`, `io.opentelemetry:opentelemetry-sdk-extension-autoconfigure` |
| OTLP exporters (traces, metrics, logs) | `io.opentelemetry:opentelemetry-exporter-otlp` |
| JVM runtime metrics | `io.opentelemetry.instrumentation:opentelemetry-runtime-telemetry-java17` (`-java8` on older JVMs) |
| Pipeline log appender; MDC trace keys for the console | `io.opentelemetry.instrumentation:opentelemetry-logback-appender-1.0`, `io.opentelemetry.instrumentation:opentelemetry-logback-mdc-1.0` |
| Ktor server and client (Ktor 3; `-2.0` for Ktor 2) | `io.opentelemetry.instrumentation:opentelemetry-ktor-3.0` |
| JDK `HttpClient` (JAX-RS apps calling out) | `io.opentelemetry.instrumentation:opentelemetry-java-http-client` |
| JDBC | `io.opentelemetry.instrumentation:opentelemetry-jdbc` |
| Coroutine context element | `io.opentelemetry:opentelemetry-extension-kotlin`, `org.jetbrains.kotlinx:kotlinx-coroutines-slf4j` |
| Tests | `io.opentelemetry:opentelemetry-sdk-testing`, `org.testcontainers:testcontainers`, `org.testcontainers:junit-jupiter` |

## SDK autoconfigure

`AutoConfiguredOpenTelemetrySdk` reads the `OTEL_*` variables natively ([Export contract](../SKILL.md#export-contract)); nothing is mapped by hand as on Spring. Build it once in `main`, before anything else creates a tracer or logs:

```kotlin
package fixture.telemetry

import io.opentelemetry.instrumentation.logback.appender.v1_0.OpenTelemetryAppender
import io.opentelemetry.instrumentation.runtimemetrics.java17.RuntimeMetrics
import io.opentelemetry.sdk.OpenTelemetrySdk
import io.opentelemetry.sdk.autoconfigure.AutoConfiguredOpenTelemetrySdk

object Telemetry {
    fun init(): OpenTelemetrySdk {
        val sdk = AutoConfiguredOpenTelemetrySdk.builder()
            .setResultAsGlobal()            // GlobalOpenTelemetry for libraries that look it up
            .build()
            .openTelemetrySdk
        OpenTelemetryAppender.install(sdk)  // pipeline log appender: same SDK, same resource
        RuntimeMetrics.create(sdk)          // JVM memory, GC, threads, CPU; closed with the SDK at exit
        ServiceSpans.install(sdk)           // Tier 2 wrapper's tracer and meters
        return sdk
    }
}
```

**What autoconfigure sets up**, all from `OTEL_*`:

- `Resource` from `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`, plus SDK and telemetry attributes. Host, process, and container detectors only when `io.opentelemetry.instrumentation:opentelemetry-resources` is on the classpath (picked up through the service loader).
- OTLP exporters for traces, metrics, and logs (`OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`, all `otlp` by default), endpoint, headers, and protocol from `OTEL_EXPORTER_OTLP_*`. Set `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` explicitly in deployment: the SDK's default protocol has differed between releases and the agent's.
- A batch span processor and a batch log record processor with bounded queues (`OTEL_BSP_*`, `OTEL_BLRP_*`), and a periodic metric reader (`OTEL_METRIC_EXPORT_INTERVAL`, 60 s default).
- Propagators from `OTEL_PROPAGATORS`, default `tracecontext,baggage`: the W3C pair the skill requires. Leave the variable unset, or add `b3` after them, never instead.
- Sampler from `OTEL_TRACES_SAMPLER` and `OTEL_TRACES_SAMPLER_ARG`, default `parentbased_always_on`.
- A JVM shutdown hook that flushes and shuts the SDK down; export failures are logged by the exporter's throttled logger, never thrown. The app starts with no collector reachable.

**What it does not set up:**

- **Any instrumentation.** Autoconfigure builds the pipeline only; no inbound or outbound span exists until a framework's instrumentation library is installed with this SDK (sections below) or the [Java agent](#java-agent) runs.
- Runtime metrics (`RuntimeMetrics.create` above), the log appender install, the Tier 2 wrapper, and context propagation across executors and coroutines. Each is one line or one section here.

### Logs

`logback.xml` declares two appenders fed by the same call ([Logs](../SKILL.md#logs)). `CONSOLE` is the console appender from the [`application-logging`](../../../../application-logging/skills/application-logging/SKILL.md) skill, pattern and JSON switch included, declared above these in the same file; the MDC appender wraps it so its pattern's `%X{trace_id}` and `%X{span_id}` resolve:

```xml
<appender name="CONSOLE_TRACED" class="io.opentelemetry.instrumentation.logback.mdc.v1_0.OpenTelemetryAppender">
  <appender-ref ref="CONSOLE"/>
</appender>
<appender name="OTEL" class="io.opentelemetry.instrumentation.logback.appender.v1_0.OpenTelemetryAppender">
  <captureKeyValuePairAttributes>true</captureKeyValuePairAttributes>
  <captureMdcAttributes>*</captureMdcAttributes>
</appender>
<root level="INFO">
  <appender-ref ref="CONSOLE_TRACED"/> <!-- not CONSOLE as well: every line would print twice -->
  <appender-ref ref="OTEL"/>
</root>
```

The pipeline appender reads the trace and span from `Context.current()` when the record is emitted, so OTLP records carry `trace_id` and `span_id` without any MDC. The MDC appender adds `trace_id`, `span_id`, and `trace_flags` to each event's MDC as it passes to `CONSOLE`, also from `Context.current()`; it does not write the thread's MDC. The keys are already the standard names, so the `application-logging` pattern needs no remapping (unlike Spring's `traceId`). Never put the IDs into the MDC by hand. Records logged before `OpenTelemetryAppender.install` runs are not exported.

### Lambda-style handler

A handler the platform freezes after it returns must leave nothing in a buffer ([Serverless](../SKILL.md#serverless)). Keep autoconfigure for configuration, swap the batch processors for simple ones through the processor customizers, and flush all three providers before returning: the simple processors start each export at span end, the OTLP exporter sends asynchronously, and `forceFlush` waits for those requests; `forceFlush` on the `SdkMeterProvider` is the only way metrics leave, since there is no simple metric reader. `RequestHandler` is from `com.amazonaws:aws-lambda-java-core`.

```kotlin
package fixture

import com.amazonaws.services.lambda.runtime.RequestHandler
import fixture.telemetry.ServiceSpans
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.opentelemetry.instrumentation.ktor.v3_0.KtorClientTelemetry
import io.opentelemetry.instrumentation.logback.appender.v1_0.OpenTelemetryAppender
import io.opentelemetry.sdk.autoconfigure.AutoConfiguredOpenTelemetrySdk
import io.opentelemetry.sdk.common.CompletableResultCode
import io.opentelemetry.sdk.logs.export.BatchLogRecordProcessor
import io.opentelemetry.sdk.logs.export.SimpleLogRecordProcessor
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor
import kotlinx.coroutines.runBlocking
import java.util.concurrent.TimeUnit

class GetOrderHandler : RequestHandler<Map<String, String>, Order?> {
    override fun handleRequest(input: Map<String, String>, ctx: com.amazonaws.services.lambda.runtime.Context): Order? =
        try {
            runBlocking { orders.getOrder(input.getValue("id")) }
        } finally {
            CompletableResultCode.ofAll(
                listOf(sdk.sdkTracerProvider.forceFlush(), sdk.sdkLoggerProvider.forceFlush(), sdk.sdkMeterProvider.forceFlush()),
            ).join(5, TimeUnit.SECONDS)                                   // bounded: never hang the invocation
        }

    private companion object {
        val sdk = AutoConfiguredOpenTelemetrySdk.builder()
            .addSpanProcessorCustomizer { p, _ -> if (p is BatchSpanProcessor) SimpleSpanProcessor.create(p.spanExporter) else p }
            .addLogRecordProcessorCustomizer { p, _ ->
                if (p is BatchLogRecordProcessor) SimpleLogRecordProcessor.create(p.logRecordExporter) else p
            }
            .setResultAsGlobal()
            .build()
            .openTelemetrySdk
            .also { OpenTelemetryAppender.install(it); ServiceSpans.install(it) }
        val http = HttpClient(CIO) { install(KtorClientTelemetry) { setOpenTelemetry(sdk) } }
        val orders = OrderService(OrderRepository(), PricingClient(http, System.getenv("PRICING_URL")), AuditJob.inline(sdk))
    }
}
```

The replaced batch processors are dropped without shutdown (shutting them down would close the exporter the simple processor now uses); each leaves one idle daemon thread per cold start. A SERVER-style span per invocation comes from `io.opentelemetry.instrumentation:opentelemetry-aws-lambda-core-1.0` (its `TracingRequestHandler` base class); its constructor and flush behaviour vary by release, so check its README and keep the meter flush either way. The Java agent and the OTel Lambda layer add seconds of cold start; prefer this path on Lambda.

## Tier 2 wrapper

There is no container to hang an aspect on, so Tier 2 is one wrapper applied by hand to the body of every public service and repository method. It does what `ServiceObservationAspect` does in `jvm-spring.md`, with the OTel API:

- span named `ClassName.method` (`OrderService.getOrder`), attribute `code.function.name` fully qualified (`fixture.OrderService.getOrder`); no `code.namespace`;
- `app.service.calls`, a Counter with unit `{call}`, and `app.service.duration`, a Histogram with unit `s`, both with attributes `code.function.name` and `outcome` only;
- the error rule: the span the exception originates in records the `exception` event and sets `ERROR`; a wrapper the same exception propagates out of sets `ERROR` only.

The caller passes the fully qualified function name; the span name is derived from it. The histogram carries **explicit bucket boundaries advice** in seconds, because the SDK's default boundaries are tuned for milliseconds and would put almost every call in the first bucket. A `View` the app registers for the instrument overrides the advice.

```java
package fixture.telemetry;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.function.Supplier;

public final class ServiceSpans {
    public static final AttributeKey<String> CODE_FUNCTION = AttributeKey.stringKey("code.function.name");
    public static final AttributeKey<String> OUTCOME = AttributeKey.stringKey("outcome");
    private static final List<Double> BUCKETS =
        List.of(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0);
    // Exceptions already recorded as an event by the span they originated in (identity semantics).
    private static final Set<Throwable> RECORDED =
        Collections.synchronizedSet(Collections.newSetFromMap(new WeakHashMap<>()));
    private static volatile Instruments instruments = Instruments.of(OpenTelemetry.noop());

    private ServiceSpans() {}

    /** Once at startup with the built SDK; tests call it again with their in-memory SDK. */
    public static void install(OpenTelemetry openTelemetry) {
        instruments = Instruments.of(openTelemetry);
    }

    /** Runs body under the span for function, e.g. "fixture.OrderRepository.findById". */
    public static <T> T run(String function, Supplier<T> body) {
        long started = System.nanoTime();
        Span span = start(function);
        Throwable error = null;
        try (Scope ignored = span.makeCurrent()) {
            return body.get();
        } catch (Throwable e) {
            error = e;
            throw e;
        } finally {
            end(function, span, started, error);
        }
    }

    /** Starts the span as a child of Context.current(); the caller makes it current. */
    public static Span start(String function) {
        return instruments.tracer().spanBuilder(spanName(function)).setAttribute(CODE_FUNCTION, function).startSpan();
    }

    /** Applies the error rule, records both metrics, ends the span. */
    public static void end(String function, Span span, long startedNanos, Throwable error) {
        if (error != null) {
            if (RECORDED.add(error)) {
                span.recordException(error);   // originating span: the exception event, once
            }
            span.setStatus(StatusCode.ERROR);   // originating span and every ancestor it propagates out of
        }
        Attributes attributes = Attributes.of(CODE_FUNCTION, function, OUTCOME, error == null ? "success" : "error");
        Instruments in = instruments;
        in.calls().add(1, attributes);
        in.duration().record((System.nanoTime() - startedNanos) / 1e9, attributes);
        span.end();
    }

    // fixture.OrderService.getOrder -> OrderService.getOrder
    static String spanName(String function) {
        int method = function.lastIndexOf('.');
        return function.substring(function.lastIndexOf('.', method - 1) + 1);
    }

    private record Instruments(Tracer tracer, LongCounter calls, DoubleHistogram duration) {
        static Instruments of(OpenTelemetry otel) {
            Meter meter = otel.getMeter("fixture.telemetry");
            return new Instruments(
                otel.getTracer("fixture.telemetry"),
                meter.counterBuilder("app.service.calls").setUnit("{call}")
                    .setDescription("Service and repository calls").build(),
                meter.histogramBuilder("app.service.duration").setUnit("s")
                    .setDescription("Service and repository call duration")
                    .setExplicitBucketBoundariesAdvice(BUCKETS).build());
        }
    }
}
```

The Kotlin entry points delegate to it. `withServiceSpan` is for blocking bodies; a `suspend` body takes `withServiceSpanSuspending`, which makes the span current through the coroutine context instead of a thread-local scope (see [Kotlin coroutines](#kotlin-coroutines)). Calling a suspend function inside `withServiceSpan` does not compile, which is the point: the blocking form would leak its scope across a suspension.

```kotlin
package fixture.telemetry

import io.opentelemetry.context.Context
import io.opentelemetry.extension.kotlin.asContextElement
import kotlinx.coroutines.withContext
import java.util.function.Supplier

fun <T> withServiceSpan(name: String, block: () -> T): T = ServiceSpans.run(name, Supplier { block() })

suspend fun <T> withServiceSpanSuspending(name: String, block: suspend () -> T): T {
    val started = System.nanoTime()
    val span = ServiceSpans.start(name)
    var error: Throwable? = null
    try {
        return withContext(Context.current().with(span).asContextElement()) { block() }
    } catch (e: Throwable) {
        error = e
        throw e
    } finally {
        ServiceSpans.end(name, span, started, error)
    }
}
```

Applied to the fixture. Every public method's body is one wrapper call; a reviewer checks that no public method of a service or repository class lacks one:

```kotlin
class OrderRepository {
    private val rows = java.util.concurrent.ConcurrentHashMap(mapOf("42" to Order("42", 0.0)))

    fun findById(id: String): Order? = withServiceSpan("fixture.OrderRepository.findById") { rows[id] }
}

class OrderService(private val orders: OrderRepository, private val pricing: PricingClient, private val audit: AuditJob) {
    private val log = org.slf4j.LoggerFactory.getLogger(OrderService::class.java)

    suspend fun getOrder(id: String): Order? = withServiceSpanSuspending("fixture.OrderService.getOrder") {
        if (id == "boom") error("pricing unavailable")                      // exception event plus ERROR here
        val order = orders.findById(id) ?: return@withServiceSpanSuspending null // handled 404: no ERROR
        val total = pricing.quote(id).price                                 // client span, child of this span
        log.atInfo().addKeyValue("order.id", id).log("order fetched")       // trace_id and span_id of this span
        audit.record(id)                                                    // linked root span, below
        order.copy(total = total)
    }
}
```

Java: `return ServiceSpans.run("fixture.OrderRepository.findById", () -> Optional.ofNullable(rows.get(id)));`.

A handled 404 is the service returning `null` (or an empty `Optional`), mapped to `404` at the route. Throwing a not-found exception out of the service marks its span `ERROR`. Because the wrapper is explicit, a call from one method of a class to another on `this` gets its own span, unlike the Spring proxy. Where a DI container offers method interception (Guice's `bindInterceptor`), an interceptor calling `ServiceSpans.start` and `end` gives class-level coverage instead; `suspend` methods still need the coroutine form.

## Ktor

`opentelemetry-ktor-3.0` provides two plugins. `KtorServerTelemetry` creates the SERVER span with `http.route` from the routing tree and extracts `traceparent`; `KtorClientTelemetry` creates the CLIENT span and injects `traceparent` on every request from that `HttpClient`. Both take the SDK instance; neither reads a global.

```kotlin
package fixture

import fixture.telemetry.Telemetry
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.Application
import io.ktor.server.application.install
import io.ktor.server.engine.embeddedServer
import io.ktor.server.netty.Netty
import io.ktor.server.response.respond
import io.ktor.server.routing.get
import io.ktor.server.routing.routing
import io.opentelemetry.api.OpenTelemetry
import io.opentelemetry.instrumentation.ktor.v3_0.KtorClientTelemetry
import io.opentelemetry.instrumentation.ktor.v3_0.KtorServerTelemetry

fun main() {
    val otel = Telemetry.init()
    embeddedServer(Netty, port = System.getenv("PORT")?.toInt() ?: 8080) { module(otel) }.start(wait = true)
}

fun Application.module(otel: OpenTelemetry) {
    install(KtorServerTelemetry) { setOpenTelemetry(otel) }
    val http = HttpClient(CIO) { install(KtorClientTelemetry) { setOpenTelemetry(otel) } }
    val orders = OrderService(OrderRepository(), PricingClient(http, System.getenv("PRICING_URL")), AuditJob.pooled(otel))
    // ContentNegotiation with a JSON serializer is installed as usual for call.respond(order).
    routing {
        get("/orders/{id}") {
            val order = orders.getOrder(call.parameters["id"]!!)
            if (order == null) call.respond(HttpStatusCode.NotFound) else call.respond(order)
        }
    }
}
```

Plugin and package names changed across releases (`KtorServerTracing` and `KtorClientTracing` earlier, a `server` and `client` subpackage in some versions); match the imports to the instrumentation BOM in use. The server plugin runs the rest of the pipeline under the request's OTel context as a coroutine context element, so a route handler and the `suspend` calls it makes see the SERVER span as current across dispatcher switches. An exception that escapes the route becomes a `500`, and the plugin records it on the SERVER span as well; the error rule accepts that default. `HttpStatusCode.NotFound` leaves every span `UNSET`.

## JAX-RS

Jersey and RESTEasy have no maintained standalone instrumentation library in OpenTelemetry's instrumentation repository as of this writing; the JAX-RS, Jersey, RESTEasy, and servlet-container instrumentations ship inside the Java agent. Options, in order:

1. **The Java agent** (next section). It names the SERVER span from the resource's `@Path` template, so `http.route` is `/orders/{id}`, and instruments the JAX-RS client, the JDK `HttpClient`, and JDBC in the same move. The default for JAX-RS.
2. **The container's own library instrumentation**, where your embedded server has one in the instrumentation repository's supported-libraries list. Check that list for your server before writing anything; it changes between releases.
3. **No server instrumentation available and the agent ruled out:** a `ContainerRequestFilter` and `ContainerResponseFilter` pair built on the `Instrumenter` API from `io.opentelemetry.instrumentation:opentelemetry-instrumentation-api`, with an `HttpServerAttributesGetter` over `ContainerRequestContext`. This is hand-written Tier 1, so treat it as a last resort and test it against the HTTP semantic conventions; no template is given here.

On options 2 and 3, outbound calls take a library instrumentation of the client underneath: `JavaHttpClientTelemetry.builder(otel).build().newHttpClient(client)` for the JDK `HttpClient`, the OkHttp or Apache HttpClient libraries for those. Tier 2, logs, executors, and the error rule are the same as everywhere on this page: `ServiceSpans.run` in the service, a handled 404 returned as `Response.status(404)` from a `null` result, never a `NotFoundException` thrown out of the service.

## Java agent

`io.opentelemetry.javaagent:opentelemetry-javaagent` is zero-code Tier 1: inbound HTTP for every major server and framework, outbound HTTP clients, JDBC and R2DBC, messaging, Logback (it installs its own appender and injects `trace_id` and `span_id` into the MDC), runtime metrics, and context propagation across executors, `CompletableFuture`, and Kotlin coroutines. It reads every `OTEL_*` variable natively.

```shell
export JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar"
export OTEL_SERVICE_NAME=orders
export OTEL_RESOURCE_ATTRIBUTES="service.version=${BUILD_VERSION},deployment.environment.name=staging"
export OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
java -jar orders.jar
```

With the agent, the application depends on `opentelemetry-api` only, plus `opentelemetry-extension-kotlin` if it uses the coroutine element. It does not build an SDK: drop `Telemetry.init`, the autoconfigure and exporter artifacts, the library instrumentations, and both Logback appender artifacts, or spans and log records are produced twice. Tier 2 still uses the wrapper, bound to the agent's SDK through the global: `ServiceSpans.install(GlobalOpenTelemetry.get())`. The agent's `@WithSpan` and `otel.instrumentation.methods.include` make spans but no metrics, so they are not Tier 2.

Trade-offs:

- **Not testable in-process.** The component tests run in a JVM without the agent, so they cannot assert the agent's Tier 1 spans against an in-memory exporter. They test Tier 2, logs, and context with the SDK testing artifacts; Tier 1 is proved only by the integration test, which starts the app's JVM with the agent against the Testcontainers collector.
- **A startup flag.** Every environment that runs the app (container image, local run configuration, test fork) must carry `-javaagent`; forget it in one and that environment silently has no Tier 1. The agent also adds startup time, which matters for serverless cold starts.
- **Version coupling.** The agent bundles its own SDK and instrumentation, each instrumentation tested against a range of library versions. Upgrading a framework past the agent's range can silently drop its spans; the application's `opentelemetry-api` must not be newer than the API the agent bridges, or calls to the newer methods are no-ops. Upgrade the agent with the framework.

## Executors and CompletableFuture

The OTel `Context` is a thread-local. A task handed to another thread starts with an empty context unless something carries it. On the library path, wrap every executor the app creates:

```kotlin
val executor: ExecutorService = Context.taskWrapping(Executors.newFixedThreadPool(4))
```

`Context.taskWrapping` captures `Context.current()` at submit time and makes it current while the task runs (overloads exist for `Executor` and `ScheduledExecutorService`). For a single task, `Context.current().wrap(runnable)` or `wrapSupplier(supplier)` does the same.

`CompletableFuture.supplyAsync(supplier)` without an executor runs on `ForkJoinPool.commonPool()`, which nothing wraps: the work runs with no span current and its spans start new traces. Pass the wrapped executor to every async stage, including later ones:

```kotlin
CompletableFuture.supplyAsync({ orders.findById(id) }, executor)
    .thenApplyAsync({ order -> order?.copy(total = pricing.quoteBlocking(id).price) }, executor)
```

A non-async stage (`thenApply`) runs on whichever thread completes the previous stage, under that thread's context; keep span-producing work in the `*Async` overloads with the wrapped executor. The agent instruments executors, `ForkJoinPool`, and `CompletableFuture` itself, so none of this is needed under it; it is harmless if left in.

### Background job: a linked root span

`AuditJob.record`, enqueued during `GET /orders/42`, must start its own trace with a span link to the request's span ([Span tiers](../SKILL.md#span-tiers)). The wrapped executor (or the agent) makes the request's span current on the worker thread, which would make the job a child. Capture the trigger at enqueue time and start a root deliberately with `setNoParent()` and `addLink(...)`:

```kotlin
package fixture

import fixture.telemetry.ServiceSpans
import io.opentelemetry.api.OpenTelemetry
import io.opentelemetry.api.trace.Span
import io.opentelemetry.api.trace.StatusCode
import io.opentelemetry.context.Context
import java.util.concurrent.Executor
import java.util.concurrent.Executors

class AuditJob(otel: OpenTelemetry, private val executor: Executor) {
    private val tracer = otel.getTracer("fixture.telemetry")
    private val log = org.slf4j.LoggerFactory.getLogger(AuditJob::class.java)

    fun record(id: String) {
        val trigger = Span.current().spanContext                    // captured at enqueue
        executor.execute {
            val span = tracer.spanBuilder("AuditJob.record")
                .setNoParent()                                      // own trace, despite the inherited context
                .apply { if (trigger.isValid) addLink(trigger) }
                .setAttribute(ServiceSpans.CODE_FUNCTION, "fixture.AuditJob.record")
                .startSpan()
            try {
                span.makeCurrent().use { log.atInfo().addKeyValue("order.id", id).log("audit recorded") }
            } catch (e: Exception) {
                span.recordException(e)
                span.setStatus(StatusCode.ERROR)
                throw e
            } finally {
                span.end()
            }
        }
    }

    companion object {
        fun pooled(otel: OpenTelemetry) = AuditJob(otel, Context.taskWrapping(Executors.newFixedThreadPool(2)))
        fun inline(otel: OpenTelemetry) = AuditJob(otel, Executor { it.run() }) // serverless: finish before the flush
    }
}
```

The link points at the span current at enqueue, `OrderService.getOrder`, which lives in the request's trace; assertions compare the link's trace ID with the request's. A scheduled job nothing triggered gets a root span and no link.

## Kotlin coroutines

A coroutine can resume on any thread, so the thread-local `Context` is wrong after a suspension unless the coroutine context restores it. `opentelemetry-extension-kotlin` provides the element: `Context.asContextElement()` (and `Span.asContextElement()`), which sets the OTel context on the thread every time the coroutine resumes and restores the previous one when it suspends.

- **A `suspend` body that switches dispatcher must carry the element.** `withContext(Dispatchers.IO)` inherits elements from its parent, so inside a Ktor handler (the server plugin installs one) or inside `withServiceSpanSuspending` the context follows the switch. A coroutine started from a scope without the element (`GlobalScope`, an application `CoroutineScope`, `runBlocking` in a worker) starts with whatever the thread happened to hold: pass it explicitly, `scope.launch(Context.current().asContextElement()) { ... }`. A coroutine hop that loses the parent is a High finding.
- **Never `span.makeCurrent()` across a suspension point.** The scope is thread-local: after the coroutine resumes elsewhere it closes on the wrong thread, and the span stays current on the original thread for unrelated coroutines. Make a span current in a coroutine only through `withContext(Context.current().with(span).asContextElement())`, as `withServiceSpanSuspending` does.
- **Reading the context** inside a coroutine: `Context.current()` is correct while the element is present; `coroutineContext.getOpenTelemetryContext()` reads it from the coroutine context directly.

**Ordering with `MDCContext`.** Request-scoped MDC keys (`request.id`) cross dispatchers through `kotlinx-coroutines-slf4j`'s `MDCContext`, which replaces the whole thread MDC map on every resumption with the map it captured when it was created. Write the OTel element after it:

```kotlin
withContext(Dispatchers.IO + MDCContext() + Context.current().asContextElement()) { /* ... */ }
```

The reason: on this path `opentelemetry-logback-mdc-1.0` adds `trace_id` and `span_id` to each console event from `Context.current()` at the moment the event is appended; it never writes them into the thread's MDC. So the trace keys are correct whenever the OTel element is present, whatever its position, and `MDCContext` neither captures nor clobbers them. The order matters for any mechanism that does write trace keys into the thread MDC when a context becomes current (a hand-rolled scope listener, a `ContextStorage` wrapper, Spring's observation in `jvm-spring.md`): the elements are applied in order, so an `MDCContext` placed after it would overwrite those keys with its stale snapshot on every resumption. OTel element last is correct under both mechanisms. Create `MDCContext()` before any span is current if anything does write trace keys into the MDC, so its snapshot holds request keys only.

## Known complexities

- **`ThreadLocal` loss across `CompletableFuture.supplyAsync`.** Without an executor argument the task runs on `ForkJoinPool.commonPool()` with an empty `Context`: no parent span, a new trace for every span inside, logs without `trace_id`. The same holds for `parallelStream()`, `Thread { }`, and any `Executors.new*` pool not passed through `Context.taskWrapping`. The agent fixes all of these; the library path fixes none.
- **Agent plus SDK in one JVM.** Calling `AutoConfiguredOpenTelemetrySdk...setResultAsGlobal()` under the agent fails because the global is already set; installing library instrumentation or the Logback appenders under the agent duplicates spans and records. Pick one path per deployment.
- **Global state in tests.** `GlobalOpenTelemetry` can be set once per JVM. Tests build an SDK over `InMemorySpanExporter`, `InMemoryMetricReader`, and `InMemoryLogRecordExporter`, pass it to `ServiceSpans.install` and to the plugins, and call `OpenTelemetryAppender.install` with it; call `GlobalOpenTelemetry.resetForTest()` between tests that set the global.
- **Histogram buckets.** Without the advice in `ServiceSpans`, `app.service.duration` in seconds lands almost entirely in the first default bucket. A `View` configured for the instrument overrides advice; if the project adds one, give it the same boundaries.
- **`outcome` on cancellation.** A cancelled coroutine throws `CancellationException` through `withServiceSpanSuspending`, which records it as `outcome=error` with an exception event. If cancellation is routine (client disconnects, timeouts by design), rethrow `CancellationException` without passing it to `end` as an error.
- **Reused exception instances.** The error rule's recorded set is identity-based; a singleton exception gets its event only the first time. Do not reuse exception instances.
- **Server span and the exception.** Ktor's and the agent's server instrumentation record an exception that escapes to a `500`, so on `GET /orders/boom` both the service span and the SERVER span carry an `exception` event. The error rule accepts this auto-instrumented default.
- **Not compiled in this reference.** From documentation, cached SDK sources, and memory, to be confirmed by a fixture build: `AutoConfiguredOpenTelemetrySdkBuilder.setResultAsGlobal()`; the Ktor plugin class names and package (`io.opentelemetry.instrumentation.ktor.v3_0`) and that the server plugin installs the context as a coroutine element; `RuntimeMetrics.create` in the `java17` module; `opentelemetry-logback-mdc-1.0` adding keys to the event's MDC at append time rather than the thread's MDC; `opentelemetry-aws-lambda-core-1.0`'s handler API; the absence of a standalone Jersey or RESTEasy library instrumentation. Confirmed against SDK sources: `addSpanProcessorCustomizer`, `addLogRecordProcessorCustomizer`, `BatchSpanProcessor.getSpanExporter()`, `BatchLogRecordProcessor.getLogRecordExporter()`, `setExplicitBucketBoundariesAdvice`, `SpanBuilder.setNoParent()` and `addLink`, `Context.taskWrapping` and `wrapSupplier`.
