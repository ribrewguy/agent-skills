# Spring Kotlin fixture (no telemetry by design)

A small Kotlin Spring Boot app used to evaluate the `opentelemetry` skill. It has two Maven modules that implement the same HTTP contract:

- `mvc`: Spring Web MVC. `OrderService.getOrder` is a `suspend` function (`withContext(Dispatchers.IO)`), `PricingClient` uses `RestClient`, and `AuditJob.record` is `@Async`.
- `webflux`: Spring WebFlux. `OrderService.getOrder` returns `Mono<OrderView>`, `PricingClient` uses `WebClient`, and `AuditJob.record` subscribes on `Schedulers.boundedElastic()`.

There is no telemetry: no OpenTelemetry, Micrometer, Actuator, or tracing, and no logging configuration beyond Spring Boot defaults. An agent adds all of it. Run `./mvnw -q verify` to confirm the contract still holds (10 tests).

## Contract

| Route | Behaviour |
|---|---|
| `GET /orders/{id}` | `OrderService.getOrder(id)` calls `OrderRepository.findById(id)` (in-memory map, ids 1 to 100), then `PricingClient.quote(id)` (HTTP GET to this app's `/pricing/{id}`), logs INFO `order fetched` with field `order.id`, enqueues `AuditJob.record(id)`, and returns `200` JSON `{ "id", "total" }`. |
| `GET /orders/404` | Repository returns nothing; handled `404`. |
| `GET /orders/boom` | Service throws; `500`. |
| `GET /pricing/{id}` | `200` JSON `{ "id", "price" }`. |
| `GET /health` | `200`. |

The port comes from `PORT` (default 8080).
