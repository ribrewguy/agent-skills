# Spring Boot: test templates

Component and integration test templates for the Spring wiring in the skill's Spring reference (`references/jvm-spring.md`). They implement the first two layers of [Verification](../SKILL.md#verification) against the invented `orders` app: `GET /orders/{id}` through `OrderService.getOrder`, `OrderRepository.findById`, and `PricingClient.quote` (an HTTP call to the same app's `/pricing/{id}`), logging `order fetched` with `order.id`, and enqueuing `AuditJob.record`. `GET /orders/404` is a handled not-found; `GET /orders/boom` throws in `OrderService.getOrder`.

## General approach

Component tests run the whole app in-process (`@SpringBootTest` on a random port) with the OTLP exporters switched off and in-memory capture switched on: `InMemorySpanExporter` and `InMemoryLogRecordExporter` from `io.opentelemetry:opentelemetry-sdk-testing`, each behind a simple processor so nothing waits for a batch. Spring Boot adds every `SpanProcessor` and `LogRecordProcessor` bean to the SDK providers it builds, so the test sees exactly what production would export. The receiving side of the outbound call is the app's own `/pricing` route, which serves as the in-process stub server.

Metrics on this path go through Micrometer, not an OTel `SdkMeterProvider`, so an `InMemoryMetricReader` would see nothing; the component tests assert on the `MeterRegistry` bean, which holds exactly the meters the OTLP registry exports. `InMemoryMetricReader` applies only to the serverless profile, where Micrometer is bridged into an `SdkMeterProvider`. The integration test then proves the real export: metrics, spans, and logs at a real collector.

Spring Boot switches tracing off in tests unless asked. Boot 3: `@AutoConfigureObservability`. Boot 4: `@AutoConfigureTracing` and `@AutoConfigureMetrics` (Boot 4 split the annotation; confirm the names against the Boot version the project pins).

The same test class serves `mvc` and `webflux`; only `coroutine hop keeps the parent span` changes its comment (the hop is `withContext(Dispatchers.IO)` in MVC and `subscribeOn(Schedulers.boundedElastic())` in WebFlux).

## In-memory configuration

```kotlin
package fixture

import io.opentelemetry.sdk.logs.LogRecordProcessor
import io.opentelemetry.sdk.logs.export.SimpleLogRecordProcessor
import io.opentelemetry.sdk.testing.exporter.InMemoryLogRecordExporter
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter
import io.opentelemetry.sdk.trace.SpanProcessor
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor
import org.springframework.boot.test.context.TestConfiguration
import org.springframework.context.annotation.Bean

@TestConfiguration(proxyBeanMethods = false)
class InMemoryTelemetryConfig {
    // Exporters are not beans: as SpanExporter beans Boot would also feed them through its batch processor.
    @Bean fun inMemorySpans(): SpanProcessor = SimpleSpanProcessor.create(SPANS)
    @Bean fun inMemoryLogs(): LogRecordProcessor = SimpleLogRecordProcessor.create(LOGS)

    companion object {
        val SPANS: InMemorySpanExporter = InMemorySpanExporter.create()
        val LOGS: InMemoryLogRecordExporter = InMemoryLogRecordExporter.create()
    }
}
```

Test properties that switch the OTLP exporters off (keep the line for the Boot line in use):

```properties
# Boot 4.x
management.tracing.export.otlp.enabled=false
management.logging.export.otlp.enabled=false
management.otlp.metrics.export.enabled=false
# Boot 3.4 to 3.5
management.otlp.tracing.export.enabled=false
management.otlp.logging.export.enabled=false
management.otlp.metrics.export.enabled=false
```

## Component tests

```kotlin
package fixture

import fixture.InMemoryTelemetryConfig.Companion.LOGS
import fixture.InMemoryTelemetryConfig.Companion.SPANS
import io.micrometer.core.instrument.MeterRegistry
import io.opentelemetry.api.trace.SpanKind
import io.opentelemetry.api.trace.StatusCode
import io.opentelemetry.sdk.trace.data.SpanData
import org.assertj.core.api.Assertions.assertThat
import org.awaitility.kotlin.await
import org.awaitility.kotlin.untilAsserted
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.context.annotation.Import
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

@SpringBootTest(
    webEnvironment = RANDOM_PORT,
    properties = [
        "management.tracing.export.otlp.enabled=false",      // Boot 4; Boot 3: management.otlp.tracing.export.enabled
        "management.logging.export.otlp.enabled=false",      // Boot 4; Boot 3: management.otlp.logging.export.enabled
        "management.otlp.metrics.export.enabled=false",
    ],
)
@AutoConfigureObservability // Boot 4: @AutoConfigureTracing @AutoConfigureMetrics
@Import(InMemoryTelemetryConfig::class)
class TelemetryComponentTest(@Autowired private val meters: MeterRegistry) {
    @LocalServerPort private var port = 0
    private val http = HttpClient.newHttpClient()

    @BeforeEach fun reset() { SPANS.reset(); LOGS.reset() }

    private fun get(path: String): Int =
        http.send(HttpRequest.newBuilder(URI("http://localhost:$port$path")).build(), HttpResponse.BodyHandlers.discarding()).statusCode()

    private fun spans(): List<SpanData> = SPANS.finishedSpanItems
    private fun SpanData.route(): String =
        attributes.asMap().entries.firstOrNull { it.key.key == "http.route" || it.key.key == "uri" }?.value?.toString().orEmpty()
    private fun server(route: String) = spans().single { it.kind == SpanKind.SERVER && it.route().startsWith(route) }
    private fun named(name: String) = spans().single { it.name == name }
    private fun SpanData.isDescendantOf(ancestor: SpanData): Boolean {
        val byId = spans().associateBy { it.spanId }
        var parent = byId[parentSpanId]
        while (parent != null) { if (parent.spanId == ancestor.spanId) return true; parent = byId[parent.parentSpanId] }
        return false
    }
    /** Waits until the request's server span and the background job's span have both ended. */
    private fun awaitOrder42() = await.atMost(Duration.ofSeconds(10)).untilAsserted {
        assertThat(spans().map { it.name }).contains("OrderService.getOrder", "AuditJob.record")
        server("/orders/"); server("/pricing/")
    }

    @Test
    fun `server span has service and repository spans as descendants in order`() {
        assertThat(get("/orders/42")).isEqualTo(200); awaitOrder42()
        val request = server("/orders/")
        val service = named("OrderService.getOrder")
        val repository = named("OrderRepository.findById")
        assertThat(service.isDescendantOf(request)).isTrue()
        assertThat(repository.isDescendantOf(service)).isTrue()
        assertThat(service.attributes.asMap().mapKeys { it.key.key })
            .containsEntry("code.function.name", "fixture.OrderService.getOrder")
            .doesNotContainKey("code.namespace")
    }

    @Test
    fun `outbound call produces a client span and the stub server span shares its trace`() {
        assertThat(get("/orders/42")).isEqualTo(200); awaitOrder42()
        val request = server("/orders/")
        val client = spans().single { it.kind == SpanKind.CLIENT && it.traceId == request.traceId }
        val pricing = server("/pricing/")
        assertThat(client.isDescendantOf(request)).isTrue()
        assertThat(pricing.traceId).isEqualTo(request.traceId)
        assertThat(pricing.parentSpanId).isEqualTo(client.spanId)    // traceparent crossed the wire
    }

    @Test
    fun `coroutine hop keeps the parent span`() {
        // MVC: findById runs inside withContext(Dispatchers.IO); WebFlux: on Schedulers.boundedElastic()
        assertThat(get("/orders/42")).isEqualTo(200); awaitOrder42()
        assertThat(named("OrderRepository.findById").parentSpanId).isEqualTo(named("OrderService.getOrder").spanId)
    }

    @Test
    fun `log inside the request carries trace_id and span_id of the active span`() {
        assertThat(get("/orders/42")).isEqualTo(200); awaitOrder42()
        val service = named("OrderService.getOrder")
        val record = LOGS.finishedLogRecordItems.single { it.bodyValue?.asString() == "order fetched" }
        assertThat(record.spanContext.traceId).isEqualTo(service.traceId)
        assertThat(record.spanContext.spanId).isEqualTo(service.spanId)
        assertThat(record.attributes.asMap().mapKeys { it.key.key }).containsEntry("order.id", "42")
    }

    @Test
    fun `default service metrics recorded with code function name and outcome`() {
        assertThat(get("/orders/42")).isEqualTo(200); awaitOrder42()
        val function = "fixture.OrderService.getOrder"
        val calls = meters.get("app.service.calls").tag("code.function.name", function).tag("outcome", "success").counter()
        assertThat(calls.count()).isGreaterThanOrEqualTo(1.0)
        assertThat(calls.id.baseUnit).isEqualTo("{call}")
        val duration = meters.get("app.service.duration").tag("code.function.name", function).tag("outcome", "success").timer()
        assertThat(duration.count()).isGreaterThanOrEqualTo(1L)
        assertThat(meters.find("app.service.calls").tagKeys("code.namespace").meters()).isEmpty()
        assertThat(meters.find("app.service.duration").tagKeys("code.namespace").meters()).isEmpty()
    }

    @Test
    fun `no span has error status on the happy path`() {
        assertThat(get("/orders/42")).isEqualTo(200); awaitOrder42()
        assertThat(spans().filter { it.status.statusCode == StatusCode.ERROR }).isEmpty()
    }

    @Test
    fun `handled not found has no error span`() {
        assertThat(get("/orders/404")).isEqualTo(404)
        await.atMost(Duration.ofSeconds(10)).untilAsserted { server("/orders/") }
        assertThat(spans().filter { it.status.statusCode == StatusCode.ERROR }).isEmpty()
    }

    @Test
    fun `failure marks the originating span and the ancestors it propagated out of`() {
        assertThat(get("/orders/boom")).isEqualTo(500)
        await.atMost(Duration.ofSeconds(10)).untilAsserted { server("/orders/") }
        val service = named("OrderService.getOrder")
        assertThat(service.status.statusCode).isEqualTo(StatusCode.ERROR)
        assertThat(service.events.filter { it.name == "exception" }).hasSize(1)   // recorded once, where it originated
        assertThat(server("/orders/").status.statusCode).isEqualTo(StatusCode.ERROR)
        // no other Tier 2 span records the same exception (the server span may: accepted default)
        assertThat(spans().filter { it.kind == SpanKind.INTERNAL && it !== service && it.events.any { e -> e.name == "exception" } }).isEmpty()
        assertThat(meters.get("app.service.calls").tag("outcome", "error").counter().count()).isGreaterThanOrEqualTo(1.0)
    }

    @Test
    fun `background job starts its own trace with a link to the triggering span`() {
        assertThat(get("/orders/42")).isEqualTo(200); awaitOrder42()
        val request = server("/orders/")
        val job = named("AuditJob.record")
        assertThat(job.parentSpanContext.isValid).isFalse()                          // root span
        assertThat(job.traceId).isNotEqualTo(request.traceId)                       // own trace
        assertThat(job.links.map { it.spanContext.traceId }).contains(request.traceId) // link back to the request
    }
}
```

## Integration test with a real collector

One per project. Testcontainers starts the official contrib collector with the skill's `assets/collector-test.yaml` (OTLP receivers on 4317 and 4318, file exporter to `/out/telemetry.jsonl`); copy that file to `src/test/resources/collector-test.yaml`. The app is configured only through `OTEL_*` names: `@DynamicPropertySource` supplies `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_SERVICE_NAME` as properties, and the `${}` placeholders in `application.yaml` resolve them exactly as they would resolve the environment variables. Pin the image tag in the project; it is unpinned here because skills name artifacts, not versions.

```kotlin
package fixture

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.assertj.core.api.Assertions.assertThat
import org.awaitility.kotlin.await
import org.awaitility.kotlin.untilAsserted
import org.junit.jupiter.api.Test
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.testcontainers.containers.GenericContainer
import org.testcontainers.containers.wait.strategy.Wait
import org.testcontainers.images.builder.Transferable
import org.testcontainers.junit.jupiter.Container
import org.testcontainers.junit.jupiter.Testcontainers
import org.testcontainers.utility.MountableFile
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

@SpringBootTest(webEnvironment = RANDOM_PORT, properties = ["management.otlp.metrics.export.step=1s"])
@AutoConfigureObservability // Boot 4: @AutoConfigureTracing @AutoConfigureMetrics
@Testcontainers
class CollectorIntegrationTest {
    @LocalServerPort private var port = 0
    private val mapper = ObjectMapper()

    companion object {
        @Container @JvmStatic
        val collector: GenericContainer<*> = GenericContainer("otel/opentelemetry-collector-contrib")
            .withCopyFileToContainer(MountableFile.forClasspathResource("collector-test.yaml"), "/etc/otelcol-contrib/config.yaml")
            .withCopyToContainer(Transferable.of("", 0b110_110_110), "/out/telemetry.jsonl") // writable by the image's non-root user
            .withExposedPorts(4318)
            .waitingFor(Wait.forListeningPort())

        @DynamicPropertySource @JvmStatic
        fun otel(registry: DynamicPropertyRegistry) {
            registry.add("OTEL_EXPORTER_OTLP_ENDPOINT") { "http://${collector.host}:${collector.getMappedPort(4318)}" }
            registry.add("OTEL_SERVICE_NAME") { "orders" }
        }
    }

    private fun telemetry(): List<JsonNode> =
        collector.copyFileFromContainer("/out/telemetry.jsonl") { it.bufferedReader().readLines() }
            .filter(String::isNotBlank).map(mapper::readTree)

    private fun List<JsonNode>.all(path: String): List<JsonNode> = flatMap { it.findValues(path) }.flatMap { it.toList() }
    private fun JsonNode.serviceName() = path("resource").path("attributes")
        .first { it.path("key").asText() == "service.name" }.path("value").path("stringValue").asText()

    @Test
    fun `spans logs and metrics reach a real collector with correlated trace ids`() {
        val status = HttpClient.newHttpClient().send(
            HttpRequest.newBuilder(URI("http://localhost:$port/orders/42")).build(), HttpResponse.BodyHandlers.discarding(),
        ).statusCode()
        assertThat(status).isEqualTo(200)

        await.atMost(Duration.ofSeconds(60)).pollInterval(Duration.ofSeconds(1)).untilAsserted {
            val lines = telemetry()
            val spans = lines.all("resourceSpans").flatMap { it.findValues("spans") }.flatMap { it.toList() }
            val logs = lines.all("resourceLogs").flatMap { it.findValues("logRecords") }.flatMap { it.toList() }
            val metrics = lines.all("resourceMetrics").flatMap { it.findValues("metrics") }.flatMap { it.toList() }

            assertThat(spans.map { it.path("name").asText() }).contains("OrderService.getOrder", "OrderRepository.findById")
            assertThat(metrics.map { it.path("name").asText() }).contains("app.service.calls", "app.service.duration")
            assertThat(metrics.first { it.path("name").asText() == "app.service.duration" }.path("unit").asText()).isEqualTo("s")

            val traceIds = spans.map { it.path("traceId").asText() }.toSet()
            val fetched = logs.first { it.path("body").path("stringValue").asText() == "order fetched" }
            assertThat(traceIds).contains(fetched.path("traceId").asText())              // log correlated to a span in the same output

            assertThat(lines.all("resourceSpans").map { it.serviceName() }).containsOnly("orders")
            assertThat(lines.all("resourceLogs").map { it.serviceName() }).containsOnly("orders")
            assertThat(lines.all("resourceMetrics").map { it.serviceName() }).containsOnly("orders")
        }
    }
}
```

## Known complexities

- **Batch delays in the integration test.** Traces leave on the batch processor's schedule (5 s by default), logs every second, metrics on `management.otlp.metrics.export.step` (set to `1s` above; the default is one minute). The await covers all three; do not shorten it below the trace batch delay.
- **The collector's file.** The contrib image runs as a non-root user and `/out` does not exist in it; the template pre-creates a world-writable `telemetry.jsonl` so the file exporter can append, and reads it back with `copyFileFromContainer`. A bind mount works too, but a `tmpfs` mount does not: `docker cp` cannot read it. The default config path `/etc/otelcol-contrib/config.yaml` is the contrib image's; confirm it against the pinned tag.
- **Server span matching.** Micrometer's server span carries `uri`, not `http.route`; the helper accepts either so the same test survives a switch to OTel-named conventions.
- **Background job timing.** `AuditJob.record` runs after the response; every test that asserts on `GET /orders/42` waits for its span before reading, so spans from one test never leak into the next after `reset()`.
- **Resource attributes in the integration test.** `@DynamicPropertySource` supplies properties, not environment variables, so `OTEL_RESOURCE_ATTRIBUTES` set that way is not merged into the `Resource`. The test asserts `service.name` only; `service.version` and `deployment.environment.name` are checked by the compose layer or a run with the real variables set.
