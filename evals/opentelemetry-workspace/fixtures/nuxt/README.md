# Nuxt fixture (no telemetry by design)

A small Nuxt 4 app (Nitro `node-server` preset, Nitro tasks enabled) used to evaluate the `opentelemetry` skill. It implements the same HTTP contract as the Spring Kotlin fixture. There is no telemetry: no OpenTelemetry and no logging library; server code uses `console`. An agent adds all of it. Run `npm install && npm test` to confirm the contract still holds (5 tests).

## Contract

| Route | Behaviour |
|---|---|
| `GET /orders/{id}` | `OrderService.getOrder(id)` calls `OrderRepository.findById(id)` (in-memory map, ids 1 to 100), then `PricingClient.quote(id)` (HTTP GET to this app's `/pricing/{id}`), logs INFO `order fetched` with field `order.id`, starts the `audit` Nitro task with `runTask` without awaiting it, and returns `200` JSON `{ "id", "total" }`. |
| `GET /orders/404` | Repository returns nothing; handled `404`. |
| `GET /orders/boom` | Service throws; `500`. |
| `GET /pricing/{id}` | `200` JSON `{ "id", "price" }`. |
| `GET /health` | `200`. |

Routes live under `server/routes` so the paths match the contract exactly. The port comes from `NITRO_PORT` or `PORT` (default 3000). The audit task appends the order id to the file named by `AUDIT_FILE` when set; the test uses that because the server runs in a child process.

Run the built server with `npm run build && node .output/server/index.mjs`.
