# JVM logging: Logback, MDC, Spring Boot, Kotlin

Code logs through SLF4J and nothing else; Logback renders every call through two appenders at once. The `CONSOLE` appender writes one readable line to stdout, and its `JSON` twin replaces it when `LOG_FORMAT=json`. The `OTEL` appender hands the same event to the OpenTelemetry SDK as a log record. Fields travel as SLF4J key-value pairs and never get interpolated into the message. Request-scoped values (`request.id`, `user.id`) sit in the MDC, so every record in the request inherits them. `trace_id` and `span_id` arrive in the MDC from the OTel instrumentation that the `opentelemetry` skill configures; this file reads them and never writes them. The rules themselves (levels, field names, the denylist, logging an exception once) live in [SKILL.md](../SKILL.md#field-rules). This file is wiring only.

```kotlin
private val log = LoggerFactory.getLogger(OrderService::class.java)

log.atInfo().setMessage("order fetched").addKeyValue("order.id", id).log()
log.atWarn().setMessage("pricing unavailable, using cached price")
    .addKeyValue("order.id", id).addKeyValue("error.type", e.javaClass.simpleName)
    .setCause(e).log()
```

## Logback configuration

The file goes in `src/main/resources`. Spring Boot projects name it `logback-spring.xml`; see [Spring Boot profile switch](#spring-boot-profile-switch). Artifacts: `ch.qos.logback:logback-classic`, `net.logstash.logback:logstash-logback-encoder` (JSON variant), `io.opentelemetry.instrumentation:opentelemetry-logback-appender-1.0` (OTel appender).

```xml
<configuration>
  <!-- Spring Boot only: lets application-{profile}.yml supply a default; the LOG_FORMAT env var still wins. -->
  <springProperty scope="context" name="LOG_FORMAT" source="log.format" defaultValue="text"/>

  <property name="SERVICE_NAME" value="${OTEL_SERVICE_NAME:-unknown_service:java}"/>

  <!-- Human console: timestamp, level, logger, message, short trace ID, key-value fields. -->
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX, UTC} %-5level %logger{0} [%.-8X{trace_id}] %msg %kvp{NONE}%replace( request.id=%X{request.id}){' request.id=$', ''}%replace( user.id=%X{user.id}){' user.id=$', ''}%n</pattern>
    </encoder>
  </appender>

  <!-- One-line JSON on stdout, the shape SKILL.md defines. Selected by LOG_FORMAT=json. -->
  <appender name="JSON" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
      <providers>
        <timestamp><fieldName>timestamp</fieldName><timeZone>UTC</timeZone></timestamp>
        <logLevel><fieldName>severity_text</fieldName></logLevel>
        <message><fieldName>body</fieldName></message>
        <pattern><pattern>{"service.name":"${SERVICE_NAME}"}</pattern></pattern>
        <loggerName><fieldName>logger</fieldName><shortenedLoggerNameLength>0</shortenedLoggerNameLength></loggerName>
        <mdc/>            <!-- trace_id, span_id, request.id, user.id as top-level keys -->
        <keyValuePairs/>  <!-- addKeyValue(...) fields as top-level keys -->
        <throwableClassName><fieldName>exception.type</fieldName></throwableClassName>
        <throwableMessage><fieldName>exception.message</fieldName></throwableMessage>
        <stackTrace><fieldName>exception.stacktrace</fieldName></stackTrace>
      </providers>
    </encoder>
  </appender>

  <!-- Pipeline: every event becomes an OTel log record. Installed and exported as configured by the opentelemetry skill. -->
  <appender name="OTEL" class="io.opentelemetry.instrumentation.logback.appender.v1_0.OpenTelemetryAppender">
    <captureKeyValuePairAttributes>true</captureKeyValuePairAttributes>
    <captureMdcAttributes>*</captureMdcAttributes>
  </appender>

  <!-- LOG_FORMAT selects the console appender by name; anything unrecognized falls back to CONSOLE. -->
  <property name="CONSOLE_FOR_text" value="CONSOLE"/>
  <property name="CONSOLE_FOR_json" value="JSON"/>

  <root level="INFO">
    <appender-ref ref="${CONSOLE_FOR_${LOG_FORMAT:-text}:-CONSOLE}"/>
    <appender-ref ref="OTEL"/>
  </root>
</configuration>
```

A request to `GET /orders/42` produces, on the console:

```text
2026-10-22T14:03:11.482Z INFO  OrderService [4bf92f35] order fetched order.id=42 request.id=9d1c0e2a user.id=u-7f3a
```

and with `LOG_FORMAT=json`, one line:

```json
{"timestamp":"2026-10-22T14:03:11.482Z","severity_text":"INFO","body":"order fetched","service.name":"orders","logger":"OrderService","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","request.id":"9d1c0e2a","user.id":"u-7f3a","order.id":"42"}
```

What the pieces do:

- `%.-8X{trace_id}` keeps the first 8 characters of the MDC `trace_id`. The `-` truncates from the end; without it Logback keeps the last 8. When no span is active, the brackets are empty.
- `%kvp{NONE}` prints the call's key-value pairs as unquoted `key=value`.
- `%replace(...)` prints a request-context key only when the MDC has it, so a log line written outside a request doesn't end in an empty `user.id=`.
- Stack traces: the console pattern lets Logback append them after the line. The JSON encoder puts the whole trace in `exception.stacktrace` as one escaped string, so the record stays one line. The OTel appender records the exception as attributes on the log record.
- With `captureMdcAttributes` set to `*`, `request.id` and `user.id` become record attributes on the pipeline path as well, so [Never log](../SKILL.md#never-log) covers MDC keys too.

## MDC request context

Thread-per-request stacks (Spring MVC, servlet containers) set the context in a servlet filter and clear it in `finally`, as [SKILL.md](../SKILL.md#request-scoped-context) requires. Register the filter after Spring Security's chain so the principal is already resolved. A `@Component` filter's default order is lowest precedence, which already places it there.

```kotlin
@Component
class RequestContextFilter : OncePerRequestFilter() {
    override fun doFilterInternal(request: HttpServletRequest, response: HttpServletResponse, chain: FilterChain) {
        val requestId = request.getHeader("X-Request-Id")?.takeIf(SAFE_ID::matches) ?: UUID.randomUUID().toString()
        MDC.put("request.id", requestId)
        // The opaque ID, never a username that might be an email.
        currentUserId()?.let { MDC.put("user.id", it) }
        try {
            chain.doFilter(request, response)
        } finally {
            MDC.remove("request.id")
            MDC.remove("user.id")
        }
    }

    private companion object {
        val SAFE_ID = Regex("[A-Za-z0-9-]{1,64}")  // an inbound header is untrusted; no newlines into the console
    }
}
```

`currentUserId()` stands in for however the application maps the authenticated principal to its opaque user ID.

### WebFlux: Reactor Context, not MDC plus `finally`

The servlet pattern fails on WebFlux: the `finally` runs when the `Mono` is assembled, before the request executes, and the work then hops threads, so the MDC is empty or stale wherever the log call actually runs. Instead, the `WebFilter` writes the values into the Reactor Context, and context propagation copies them into the MDC around each operator that runs user code, including the log call.

```kotlin
@Component
class RequestContextWebFilter : WebFilter {
    override fun filter(exchange: ServerWebExchange, chain: WebFilterChain): Mono<Void> {
        val requestId = exchange.request.headers.getFirst("X-Request-Id")?.takeIf(SAFE_ID::matches)
            ?: UUID.randomUUID().toString()
        return exchange.getPrincipal<Principal>()
            .map { userIdOf(it) }            // opaque ID, never an email
            .map { Optional.of(it) }
            .defaultIfEmpty(Optional.empty())
            .flatMap { userId ->
                chain.filter(exchange).contextWrite { ctx ->
                    val withRequest = ctx.put("request.id", requestId)
                    userId.map { withRequest.put("user.id", it) }.orElse(withRequest)
                }
            }
    }

    private companion object {
        val SAFE_ID = Regex("[A-Za-z0-9-]{1,64}")
    }
}
```

At startup, turn on automatic propagation and register one `ThreadLocalAccessor` per key. The accessor registry is `ContextRegistry` from `io.micrometer:context-propagation`; it tells Reactor how to move a Context entry into the MDC and how to clear it afterward.

```kotlin
fun main(args: Array<String>) {
    Hooks.enableAutomaticContextPropagation()
    listOf("request.id", "user.id").forEach { key ->
        ContextRegistry.getInstance().registerThreadLocalAccessor<String>(
            key,
            { MDC.get(key) },          // read the current value
            { MDC.put(key, it) },      // copy the Context value into the MDC
            { MDC.remove(key) },       // clear it when the Context has no such key
        )
    }
    runApplication<OrdersApplication>(*args)
}
```

In Spring Boot, the property `spring.reactor.context-propagation=auto` is equivalent to the `Hooks` call. The accessor registration is still required either way. Trace and span IDs reach the MDC on WebFlux through the same mechanism; their wiring belongs to the `opentelemetry` skill.

### Ktor and JAX-RS

Both use the Logback configuration above unchanged. Outside Spring the file is `logback.xml`, minus the `springProperty` line. Only the place that sets the context changes:

- **Ktor:** install `CallId` (`retrieveFromHeader(HttpHeaders.XRequestId)`, `generate { UUID.randomUUID().toString() }`) and `CallLogging` with `callIdMdc("request.id")` and `mdc("user.id") { call -> call.principal<UserIdPrincipal>()?.name }`. `CallLogging` sets and restores those MDC keys around each call's coroutines. Set its own access-log `level` to `DEBUG` so it stays within the one-`INFO`-per-request budget.
- **JAX-RS on a servlet container:** use a plain servlet `Filter` with the same put/`finally`/remove shape as the Spring filter above. A `ContainerRequestFilter` and `ContainerResponseFilter` pair has no `finally`, and the response filter is skipped on some failure paths, so a pooled thread can keep the last request's MDC. If filters are the only option, also remove the keys at the start of the request filter. Quarkus uses its own log manager instead of Logback; there the same fields and shape apply, but the configuration is Quarkus's.

## Spring Boot profile switch

Spring Boot loads `logback-spring.xml` (not `logback.xml`) after the `Environment` is ready, which is what makes `<springProperty>` work. The switch resolves in this order:

1. The `LOG_FORMAT` environment variable. Relaxed binding maps it to `log.format`, and the environment outranks profile files.
2. `log.format` in the active profile's file, for example `application-prod.yml`:

   ```yaml
   log:
     format: json
   ```

3. The `defaultValue="text"` on the `springProperty`, which selects the human `CONSOLE` appender for local runs.

Deployments set `LOG_FORMAT=json` explicitly when the platform scrapes stdout. The profile default is a convenience and doesn't replace the deployment setting. Spring Boot's built-in `logging.structured.format.console` (ECS, GELF, Logstash) is the [override path](#known-complexities) for platform-specific shapes. It is not the default, because its field names differ from the shape in SKILL.md.

## Kotlin and coroutines

The MDC is thread-local, and a coroutine resumes on whatever thread its dispatcher picks, so MDC values set before a suspension point are gone after it. `MDCContext` from `org.jetbrains.kotlinx:kotlinx-coroutines-slf4j` captures the MDC when it is created and reinstalls it on every resumption.

```kotlin
// Spring MVC suspend handler: the filter's MDC is captured here and survives every suspension.
suspend fun getOrder(id: String): Order = withContext(MDCContext()) {
    val order = orderRepository.findById(id) ?: throw OrderNotFound(id)
    val total = pricingClient.quote(id)            // suspends, may resume on another thread
    log.atInfo().setMessage("order fetched").addKeyValue("order.id", id).log()  // request.id, user.id still present
    order.copy(total = total)
}

// Background work gets its own context, with the triggering order as a field.
auditScope.launch(MDCContext(mapOf("order.id" to id))) { auditJob.record(id) }
```

Rules:

- `MDC.put` inside a coroutine doesn't survive the next suspension. To add a key mid-coroutine, wrap the rest in `withContext(MDCContext(MDC.getCopyOfContextMap() + ("key" to value)))`.
- Every `launch`, `async`, or `withContext` that switches dispatchers needs `MDCContext()` in its context, or it starts with whatever MDC the worker thread last held.
- On WebFlux with coroutines, the Reactor Context bridge above already populates the MDC. Add `MDCContext()` only where code leaves the reactive chain.

## Known complexities

- **Trace IDs in the MDC.** The pattern reads `trace_id` and `span_id`. The OTel Java agent and the `opentelemetry-logback-mdc-1.0` instrumentation write those names, while Micrometer Tracing writes `traceId` and `spanId` by default. Which mechanism writes the keys, and how they are aligned, is configured by the `opentelemetry` skill. Never fix it by copying IDs into the MDC by hand.
- **The OTel appender needs an installed SDK.** The appender sends nothing until an `OpenTelemetry` instance is installed into it. The Spring Boot starter and the Java agent do that automatically; otherwise it is configured by the `opentelemetry` skill. Records emitted before installation are dropped unless the appender is told to buffer them.
- **Nested variable lookup for the switch.** `${CONSOLE_FOR_${LOG_FORMAT:-text}:-CONSOLE}` uses Logback's nested substitution, so the switch needs no Janino `<if>` block. A misspelled value (`LOG_FORMAT=JSON`) falls back to `CONSOLE` instead of failing. Check that `json` is lowercase in deployment manifests.
- **Key-value pairs need the SLF4J fluent API.** `addKeyValue` and `%kvp` are only in the fluent-API generation of SLF4J and Logback. A codebase on the older API has no key-value pairs at all; upgrade rather than reaching for `StructuredArguments` or string interpolation.
- **`captureMdcAttributes` exports everything in the MDC.** `*` is right when the MDC holds only request context. A library that puts its own keys in the MDC sends them to the backend too; list the keys explicitly if that happens.
- **Platform-specific JSON (ECS, GCP).** This is an override, never the default. Replace the `JSON` appender's encoder with `net.logstash.logback.encoder.LogstashEncoder` plus the platform's field mapping, or use Spring Boot's `logging.structured.format.console=ecs`. Keep `trace_id`, `span_id`, and the denylist intact under the new names.
- **Thread pools and `@Async`.** An executor thread doesn't inherit the submitting thread's MDC. Use a `TaskDecorator` that copies `MDC.getCopyOfContextMap()` into the task and clears it in `finally`, or the Micrometer context-propagation executor wrapper.
