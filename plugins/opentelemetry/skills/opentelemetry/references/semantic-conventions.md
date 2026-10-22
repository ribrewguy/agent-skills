# Semantic conventions

The attribute and metric names the `opentelemetry` skill relies on, taken from the [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/). Names marked **stable** do not change; names marked **development** may still be renamed upstream, so check the current conventions before building a dashboard or alert on them. Auto-instrumentation (Tier 1 in [Span tiers](../SKILL.md#span-tiers)) sets most of these for you; the tables say what to confirm, and what to set yourself when you write a span by hand.

Examples use the project's invented service: `OrderService`, `OrderRepository`, `PricingClient`, `AuditJob`, and the `orders` and `pricing` routes.

## Resource

Set once per process, through `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` (see [Export contract](../SKILL.md#export-contract)), never per span.

| Attribute | Status | Example | When to set |
|---|---|---|---|
| `service.name` | stable | `orders` | Always. Missing, or `unknown_service`, fails verification. |
| `service.version` | stable | the build's version string | Always; from the build, not typed by hand. |
| `service.namespace` | development | `shop` | When the service belongs to a system of services. |
| `deployment.environment.name` | development | `production`, `staging` | Always. Replaces the deprecated `deployment.environment`; do not emit the old name. |
| `service.instance.id` | development | a UUID per process | Let the SDK or platform detector set it; set by hand only when several instances would otherwise be indistinguishable. |

## HTTP

Set by server and client auto-instrumentation. Confirm they are present; hand-write them only when no instrumentation exists for the framework or client.

| Name | Kind | Status | Example | When to set |
|---|---|---|---|---|
| `http.request.method` | attribute | stable | `GET` | Every server and client span. |
| `http.route` | attribute | stable | `/orders/{id}` | Server spans, as the low-cardinality template, never the raw path. The server span name is `{method} {route}`. |
| `http.response.status_code` | attribute | stable | `200`, `404` | Every server and client span that received a response. |
| `url.full` | attribute | stable | the full outbound URL for `/pricing/42` | Client spans only (`PricingClient.quote`). Strip credentials and sensitive query values. |
| `url.path` | attribute | stable | `/orders/42` | Server spans. |
| `url.scheme` | attribute | stable | `http` | Server spans. |
| `server.address` | attribute | stable | `pricing.internal` | Client spans (the peer host); on server spans, the host the request was addressed to. |
| `server.port` | attribute | stable | `8080` | With `server.address`. |
| `error.type` | attribute | stable | `500`, `java.net.SocketTimeoutException` | When the request failed; see [Error and exception](#error-and-exception). |
| `http.server.request.duration` | metric, histogram, `s` | stable | | Emitted by server instrumentation; confirm, do not duplicate. |
| `http.client.request.duration` | metric, histogram, `s` | stable | | Emitted by client instrumentation; confirm, do not duplicate. |

On Spring the Tier 1 metrics keep Micrometer's names (`http.server.requests`); see [Metrics](../SKILL.md#metrics).

## Database

Set by database client auto-instrumentation (JDBC, R2DBC, the Node database drivers). `OrderRepository.findById` is a Tier 2 span; the database client span sits under it.

| Name | Kind | Status | Example | When to set |
|---|---|---|---|---|
| `db.system.name` | attribute | stable | `postgresql` | Every database client span. Replaces the deprecated `db.system`. |
| `db.query.text` | attribute | stable | `SELECT * FROM orders WHERE id = ?` | Only sanitised, with literals replaced by placeholders. Never a query with values inlined. |
| `db.operation.name` | attribute | stable | `SELECT` | When the operation is known without parsing guesswork. |
| `db.collection.name` | attribute | stable | `orders` | When the query targets one table or collection. |
| `db.namespace` | attribute | stable | `shop` | The database or schema name, when known. |
| `db.response.status_code` | attribute | stable | `23505` | When the database returned an error code. |
| `server.address` | attribute | stable | `db.internal` | The database host. |
| `db.client.operation.duration` | metric, histogram, `s` | stable | | Emitted by instrumentation; confirm, do not duplicate. |

## Messaging

Set by messaging auto-instrumentation (Spring AMQP, `amqplib`). The producer injects context into message headers; the consumer extracts it before opening its span ([Background and messaging](../SKILL.md#background-and-messaging)). The messaging conventions are **not yet stable**.

| Attribute | Status | Example | When to set |
|---|---|---|---|
| `messaging.system` | development | `rabbitmq` | Every producer and consumer span. |
| `messaging.destination.name` | development | `orders.audit` | Every producer and consumer span; the exchange or queue name, never a per-message value. |
| `messaging.operation.type` | development | `send`, `receive`, `process` | Every producer and consumer span. |
| `messaging.operation.name` | development | `publish`, `consume` | The system-specific operation name, when instrumentation sets it. |
| `messaging.message.id` | development | broker-assigned ID | Spans only, when the broker provides one. Never on a metric. |
| `messaging.rabbitmq.destination.routing_key` | development | `audit.record` | RabbitMQ spans with a routing key. |

## Code

Set by the Tier 2 aspect or `withSpan` wrapper on every service and repository span, and by the default service metrics ([Metrics](../SKILL.md#metrics)).

| Attribute | Status | Example | When to set |
|---|---|---|---|
| `code.function.name` | stable | JVM `fixture.OrderService.getOrder`; Node `OrderService.getOrder` | Every Tier 2 span and every `app.service.*` data point. Fully qualified: the class or module prefix is part of the value. |
| `code.file.path` | stable | `src/orders/OrderService.ts` | Optional; when the stack can supply it cheaply. |
| `code.line.number` | stable | `42` | Optional; with `code.file.path`. |
| `code.namespace` | deprecated, do not emit | | Never. Its content is now the prefix of `code.function.name`. Emitting it is a red flag. |

## Error and exception

See the error rule in [Span tiers](../SKILL.md#span-tiers): the span whose operation failed records the exception event and sets status `ERROR`; ancestors the failure propagated out of set `ERROR` only.

| Name | Kind | Status | Example | When to set |
|---|---|---|---|---|
| `error.type` | span and metric attribute | stable | `java.lang.IllegalStateException`, `500`, `timeout` | When the operation failed. Low-cardinality: a class name, status code, or short code, never a message. Absent on success. |
| `exception` | span event name | stable | | Once, on the span whose operation failed (`OrderService.getOrder` for `GET /orders/boom`). Use the SDK's record-exception call, which names the event and sets the three attributes below. |
| `exception.type` | event attribute | stable | `java.lang.IllegalStateException` | On every `exception` event. |
| `exception.message` | event attribute | stable | `pricing unavailable` | On every `exception` event that has a message. Must not carry secrets or PII. |
| `exception.stacktrace` | event attribute | stable | the language's native stack trace | On every `exception` event where the runtime provides one. |

Span status `ERROR` is not an attribute; set it through the span API. A handled 404 sets neither `error.type` nor `ERROR` on the server span.

## Log records

These are the record's trace-context and severity fields under the names the stack's appender and JSON output use (the log data model's own names are `TraceId`, `SpanId`, `TraceFlags`, `SeverityText`, `SeverityNumber`, `Body`), filled by the pipeline appender ([Logs](../SKILL.md#logs)), not attributes you add. The structured key-value arguments of the log call become record attributes beside them.

| Field | Example | When to set |
|---|---|---|
| `trace_id` | 32 hex characters | Never by hand. The appender copies it from the active span; a record emitted under an active span without it is a High finding. |
| `span_id` | 16 hex characters | Never by hand; from the active span, with `trace_id`. |
| `trace_flags` | `01` | Never by hand; from the active span. |
| `severity_text` | `INFO`, `ERROR` | Always; the logger's level name. |
| `severity_number` | `9` (INFO), `17` (ERROR) | Always; the appender maps the level. |
| `body` | `order fetched` | Always; the log message, constant text, values in attributes. |
| attributes | `order.id` = `42` | From the log call's structured arguments. `exception.type`, `exception.message`, `exception.stacktrace` when the call logs an exception. |

## Metric naming and units

Rules (the same ones the skill states in [Metrics](../SKILL.md#metrics)):

- Dotted lowercase, domain first, singular namespace: `order.placed`, not `orders.placed` or `placed_orders`.
- A plural final noun only when the instrument counts those things and the unit is `{thing}`: `app.service.calls` with unit `{call}`. Otherwise no plural nouns.
- Never a `_total` suffix or any other suffix a backend adds on export: `order.placed`, not `order_placed_total`.
- Units in [UCUM](https://ucum.org/): `s` for every duration, `By` for sizes, `{order}`-style annotations for counts. Never milliseconds, and never the unit in the name.
- Attributes low-cardinality. Never an ID, email, URL with path parameters, or free text.

Instrument choice:

| Instrument | Criterion | Example name | Unit | When to set |
|---|---|---|---|---|
| Counter | Counts events; the value only ever increases | `order.placed`, `app.service.calls` | `{order}`, `{call}` | When someone will ask how many, or how often, something happened. |
| UpDownCounter | Tracks an additive level that rises and falls (summing it across instances or attributes is meaningful) | `order.in_flight`, `audit.queue.depth` | `{order}`, `{message}` | When the app increments on start and decrements on finish (`order.in_flight`). When the level is owned elsewhere (a broker queue, a pool), use an observable UpDownCounter read at collection time (`audit.queue.depth`). |
| Histogram | Records a distribution of measured values | `app.service.duration`, `pricing.quote.duration` | `s` | For durations and sizes, where percentiles matter. |
| Observable gauge | A non-additive current value (ratio, temperature) sampled at collection time | `pricing.cache.hit_ratio` | `1` | When summing the value across instances would be meaningless. Being read in a callback makes an instrument asynchronous; it does not make it a gauge. |

The default service metrics fit this table: `app.service.calls` is a Counter with unit `{call}` and `app.service.duration` a Histogram with unit `s`, both with attributes `code.function.name` and `outcome`, both recorded by the Tier 2 wrapper on every public service and repository call.

`outcome` is a project attribute, not a semantic convention, with values `success` and `error` only.
