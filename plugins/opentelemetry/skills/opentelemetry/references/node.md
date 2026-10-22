# Node: Nuxt/Nitro, plain Node, Express-style

Wiring for Node servers on the OTel JS SDK: Nuxt 4 / Nitro 2 on the long-lived `node-server` preset, the same app on serverless and edge presets, and plain Node or Express. The rules (what gets a span, which metrics, the error and async rules, the export contract) live in [SKILL.md](../SKILL.md#span-tiers); this file says how to deliver them on Node. It is the Node counterpart of `jvm-spring.md` and `jvm-other.md`: same span names, same metrics, same error rule. Examples use the project's invented service: `OrderService`, `OrderRepository`, `PricingClient`, `AuditJob`, and the `orders` and `pricing` routes. Code is TypeScript or ESM for a Nuxt 4 / Nitro 2 project.

## General approach

Node uses the OTel JS SDK and its instrumentation packages directly ([Metrics](../SKILL.md#metrics)). Four pieces:

1. **A preload file, `instrumentation.mjs`,** loaded with `node --import` before the app. It starts `NodeSDK`: OTLP exporters behind batch processors, resource from `OTEL_*`, W3C propagators, a bounded shutdown on `SIGTERM`. No endpoint or sampler in code.
2. **Tier 1 from `@opentelemetry/auto-instrumentations-node`**, registered by the same file: `node:http` for the SERVER span, `undici` for global `fetch` CLIENT spans, database drivers, `amqplib`, `pino`, and the runtime metrics (event loop, heap).
3. **Tier 2 from one wrapper,** `withSpan` in `server/utils/telemetry.ts`, applied to the service and repository objects by `traced`. It opens the `ClassName.method` span and records `app.service.calls` and `app.service.duration`.
4. **Logs through pino** with `@opentelemetry/instrumentation-pino`, which writes `trace_id` and `span_id` into every record and sends each record to the OTel logs pipeline.

**Why a preload and not a Nitro plugin.** Instrumentation patches a module when it is imported. A Nitro plugin runs after the Nitro runtime has imported the HTTP server and the modules the plugins and utils pull in (database client, pino), so a plugin cannot patch them: the SERVER span, the DB spans, and log correlation silently go missing. `--import` runs before the first application import. A Nitro plugin initialises the SDK only on presets with no process entry to preload into (serverless and edge, below).

Context moves through `AsyncLocalStorage`: `await`, timers, and promise chains keep the active span. Callbacks registered on an emitter outside the request and work handed to `worker_threads` do not ([Known dropped balls](../SKILL.md#known-dropped-balls)); bind them with `context.bind(context.active(), fn)` or pass a carrier.

## Dependencies

Name packages; the project's lockfile pins versions. Keep `@opentelemetry/*` packages on one release line: the SDK packages version together, and a mixed tree registers a second, incompatible API copy.

| Purpose | Package |
|---|---|
| API (application code imports only these); SDK and preload (with the ESM hook) | `@opentelemetry/api`, `@opentelemetry/api-logs`; `@opentelemetry/sdk-node`, `@opentelemetry/instrumentation` |
| Tier 1 bundle (http, undici, pg, amqplib, pino, runtime metrics, express) | `@opentelemetry/auto-instrumentations-node` |
| Instrumentations configured by name or picked individually | `@opentelemetry/instrumentation-pino`, `@opentelemetry/instrumentation-amqplib` |
| OTLP over HTTP/protobuf (long-lived default) | `@opentelemetry/exporter-trace-otlp-proto`, `@opentelemetry/exporter-metrics-otlp-proto`, `@opentelemetry/exporter-logs-otlp-proto` |
| OTLP over HTTP/JSON (serverless and edge: smaller, `fetch` transport) | `@opentelemetry/exporter-trace-otlp-http`, `@opentelemetry/exporter-metrics-otlp-http`, `@opentelemetry/exporter-logs-otlp-http` |
| Processors, readers, providers, in-memory exporters | `@opentelemetry/sdk-trace-base`, `@opentelemetry/sdk-metrics`, `@opentelemetry/sdk-logs` |
| Resource, propagators, error handler | `@opentelemetry/resources`, `@opentelemetry/core`, `@opentelemetry/semantic-conventions` |
| Edge context manager | `@opentelemetry/context-async-hooks` |
| Tests | `vitest`, `@nuxt/test-utils`, `testcontainers` |

The `-otlp-http` exporters speak HTTP/JSON, not HTTP/protobuf; the `-otlp-proto` ones speak the skill's default ([Export contract](../SKILL.md#export-contract)). `OTEL_EXPORTER_OTLP_PROTOCOL` documents the choice but does not switch an exporter class built in code; `grpc` means swapping in the `-otlp-grpc` packages.

## Long-lived server (Nitro node-server)

The preload, with the Tier 1 list in its own module so the tests reuse it:

```js
// telemetry/instrumentations.mjs
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node'

export function instrumentations() {
  return getNodeAutoInstrumentations({
    '@opentelemetry/instrumentation-fs': { enabled: false },              // one span per file read: noise
    '@opentelemetry/instrumentation-runtime-node': { enabled: true },     // event loop and heap
    '@opentelemetry/instrumentation-http': { ignoreIncomingRequestHook: (req) => req.url === '/health' },
    '@opentelemetry/instrumentation-pino': {
      logKeys: { traceId: 'trace_id', spanId: 'span_id', traceFlags: 'trace_flags' }, // the defaults, pinned
    },
  })
}

// instrumentation.mjs: node --import ./instrumentation.mjs .output/server/index.mjs
import { randomUUID } from 'node:crypto'
import { register } from 'node:module'
import { diag, DiagConsoleLogger, DiagLogLevel } from '@opentelemetry/api'
import { CompositePropagator, setGlobalErrorHandler, W3CBaggagePropagator, W3CTraceContextPropagator } from '@opentelemetry/core'
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-proto'
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-proto'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto'
import { envDetector, hostDetector, processDetector, resourceFromAttributes } from '@opentelemetry/resources'
import { NodeSDK } from '@opentelemetry/sdk-node'
import { BatchLogRecordProcessor } from '@opentelemetry/sdk-logs'
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics'
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base'
import { instrumentations } from './telemetry/instrumentations.mjs'

// Nitro's output is ESM: route every later import through the instrumentation hook so it can be patched.
register('@opentelemetry/instrumentation/hook.mjs', import.meta.url)

// SDK diagnostics at WARN unless OTEL_LOG_LEVEL says otherwise (NodeSDK applies that variable itself).
if (!process.env.OTEL_LOG_LEVEL) diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.WARN)
let exportWarned = false
setGlobalErrorHandler((error) => { // export failures: one WARN, then quiet; never thrown into the app
  if (exportWarned) return
  exportWarned = true
  diag.warn(`telemetry export failing, further failures suppressed: ${error?.message ?? error}`)
})

const sdk = new NodeSDK({
  // service.name, service.version, deployment.environment.name: OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES.
  resource: resourceFromAttributes({ 'service.instance.id': randomUUID() }),
  resourceDetectors: [envDetector, processDetector, hostDetector],  // merged over the resource above
  textMapPropagator: new CompositePropagator({
    propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
  }),
  spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter())],       // endpoint and queue limits: OTEL_*
  logRecordProcessors: [new BatchLogRecordProcessor(new OTLPLogExporter())],
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter(),
    exportIntervalMillis: Number(process.env.OTEL_METRIC_EXPORT_INTERVAL ?? 60_000),
  }),
  instrumentations: instrumentations(),
})
sdk.start()

process.once('SIGTERM', () => {
  const timeout = new Promise((resolve) => setTimeout(resolve, 5_000).unref())
  Promise.race([sdk.shutdown(), timeout]).catch(() => {}).finally(() => process.exit(0)) // bounded flush
})
```

Exporters, processors, and readers read the endpoint, headers, timeouts, and queue sizes from `OTEL_EXPORTER_OTLP_*`, `OTEL_BSP_*`, and `OTEL_BLRP_*`; the sampler comes from `OTEL_TRACES_SAMPLER`. Unreachable collectors cost a WARN line, not a crash: exports fail into the error handler above. Newer `sdk-node` releases take `metricReaders` (an array) and deprecate `metricReader`; use whichever the pinned release types.

**Start script and config.** The preload is part of the start command everywhere the built server runs; the `start` script is `node --import ./instrumentation.mjs .output/server/index.mjs`.

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  nitro: { preset: 'node-server', experimental: { tasks: true } },
  runtimeConfig: { pricingBaseUrl: 'http://127.0.0.1:3000', amqpUrl: '' }, // NUXT_PRICING_BASE_URL, NUXT_AMQP_URL at runtime
})
```

Container images that run `node .output/server/index.mjs` directly set `NODE_OPTIONS="--import /app/instrumentation.mjs"` instead. Deploy `instrumentation.mjs`, `telemetry/`, and the OTel packages next to `.output`: Nitro traces only what the app imports into `.output/server/node_modules`, and the app never imports the SDK.

**`http.route` on the SERVER span.** Nitro and h3 never tell the http instrumentation which route matched, so the SERVER span has `url.path` (`/orders/42`) but no `http.route`. Set it from the matched template in a plugin, through the RPC metadata the http instrumentation stores in the request context:

```ts
// server/plugins/http-route.ts
import { context } from '@opentelemetry/api'
import { getRPCMetadata, RPCType } from '@opentelemetry/core'
import type { H3Event } from 'h3'

function setRoute(event: H3Event) {
  const route = event.context.matchedRoute?.path            // the template, /orders/:id; never the raw path
  const rpc = getRPCMetadata(context.active())              // the inbound request's SERVER span
  if (!route || rpc?.type !== RPCType.HTTP) return
  rpc.route = route
  rpc.span.setAttribute('http.route', route)
  rpc.span.updateName(`${event.method} ${route}`)
}

export default defineNitroPlugin((nitroApp) => {
  nitroApp.hooks.hook('beforeResponse', (event) => setRoute(event))
  nitroApp.hooks.hook('error', (_error, { event }) => { if (event) setRoute(event) })
})
```

Probes and the test templates match the SERVER span on `http.route` and fall back to `url.path` when the route is absent, so a response path that skips both hooks still matches. Set `OTEL_SEMCONV_STABILITY_OPT_IN=http` in every environment: the http instrumentation emits the old attribute names (`http.target`, `http.method`) unless asked for the stable ones (`url.path`, `http.request.method`).

## Tier 2 wrapper

`withSpan` does for Node what the aspect does on the JVM:

- span named `ClassName.method` (`OrderService.getOrder`), attribute `code.function.name` with the same value, which is fully qualified for Node; no `code.namespace`;
- `app.service.calls`, a Counter with unit `{call}`, and `app.service.duration`, a Histogram with unit `s` and explicit bucket boundaries advice in seconds, both with attributes `code.function.name` and `outcome` only;
- the error rule: the span the error originates in records the `exception` event and sets `ERROR`; every wrapper the same error propagates out of sets `ERROR` only. A `WeakSet` of recorded errors gives identity semantics.

```ts
// server/utils/telemetry.ts
import { context, metrics, propagation, ROOT_CONTEXT, SpanStatusCode, trace } from '@opentelemetry/api'
import type { Counter, Histogram, MeterProvider, Span } from '@opentelemetry/api'

const SCOPE = 'fixture.telemetry'
const BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10]
const recorded = new WeakSet<object>() // errors already recorded by the span they originated in

// The metrics API has no proxy provider: instruments made before the SDK registers stay no-ops.
// Re-resolve whenever the global provider changes (the preload, or a test's in-memory SDK).
let instruments: { provider: MeterProvider; calls: Counter; duration: Histogram } | undefined
function meters() {
  const provider = metrics.getMeterProvider()
  if (instruments?.provider !== provider) {
    const meter = provider.getMeter(SCOPE)
    instruments = { provider,
      calls: meter.createCounter('app.service.calls', { unit: '{call}', description: 'Service and repository calls' }),
      duration: meter.createHistogram('app.service.duration', {
        unit: 's', description: 'Service and repository call duration', advice: { explicitBucketBoundaries: BUCKETS },
      }),
    }
  }
  return instruments
}

/** Runs fn under a child span of the active context; name is ClassName.method. */
export function withSpan<T>(name: string, fn: (span: Span) => Promise<T>): Promise<T> {
  const started = performance.now()
  return trace.getTracer(SCOPE).startActiveSpan(name, { attributes: { 'code.function.name': name } }, async (span) => {
    let outcome: 'success' | 'error' = 'success'
    try {
      return await fn(span)
    } catch (error) {
      outcome = 'error'
      const isObject = typeof error === 'object' && error !== null
      if (!isObject || !recorded.has(error)) {
        span.recordException(error instanceof Error ? error : String(error)) // originating span: the event, once
        if (isObject) recorded.add(error)
      }
      span.setStatus({ code: SpanStatusCode.ERROR })                          // originating span and every ancestor
      throw error
    } finally {
      const attributes = { 'code.function.name': name, outcome }
      const { calls, duration } = meters()
      calls.add(1, attributes)
      duration.record((performance.now() - started) / 1000, attributes)
      span.end()
    }
  })
}

/** Class-level Tier 2: every public (non-underscore) method runs inside withSpan. A sync method would now return a Promise: keep them async. */
export function traced<T extends object>(className: string, target: T): T {
  return new Proxy(target, {
    get(obj, prop, receiver) {
      const value = Reflect.get(obj, prop, receiver)
      if (typeof value !== 'function' || typeof prop !== 'string' || prop.startsWith('_') || prop === 'constructor') return value
      return (...args: unknown[]) => withSpan(`${className}.${prop}`, async () => value.apply(receiver, args))
    },
  })
}

/** Captures the current span as a W3C carrier: the link target for a job started later. */
export function captureTrigger(): Record<string, string> {
  const carrier: Record<string, string> = {}
  propagation.inject(context.active(), carrier)
  return carrier
}

/** A background job's span: a new root, linked to the trigger, never its child. */
export function withLinkedRootSpan<T>(name: string, trigger: Record<string, string>, fn: () => Promise<T>): Promise<T> {
  const link = trace.getSpanContext(propagation.extract(ROOT_CONTEXT, trigger))
  const options = { root: true, links: link ? [{ context: link }] : [], attributes: { 'code.function.name': name } }
  const span = trace.getTracer(SCOPE).startSpan(name, options, ROOT_CONTEXT)
  return context.with(trace.setSpan(ROOT_CONTEXT, span), async () => {
    try {
      return await fn()
    } catch (error) {
      span.recordException(error instanceof Error ? error : String(error))
      span.setStatus({ code: SpanStatusCode.ERROR })
      throw error
    } finally {
      span.end()
    }
  })
}
```

The services, with the outbound hop on global `fetch` to an absolute URL so undici produces the CLIENT span and the `traceparent` header:

```ts
// server/utils/orders.ts
import { setTimeout as sleep } from 'node:timers/promises'
import type { Logger } from 'pino'

export interface Order { id: string; total: number }
const ORDERS = new Map<string, { id: string }>([['42', { id: '42' }]])

export const orderRepository = traced('OrderRepository', {
  async findById(id: string) {
    await sleep(1)                                         // an async hop; the span stays current across it
    return ORDERS.get(id)
  },
})

export const pricingClient = {                             // Tier 1 covers it: the undici CLIENT span
  async quote(id: string): Promise<{ id: string; price: number }> {
    const base = useRuntimeConfig().pricingBaseUrl         // http://127.0.0.1:<port>; never Nitro's relative $fetch
    const response = await fetch(new URL(`/pricing/${encodeURIComponent(id)}`, base))
    if (!response.ok) throw new Error(`pricing returned ${response.status}`)
    return response.json()
  },
}

export const orderService = traced('OrderService', {
  async getOrder(id: string, log: Logger): Promise<Order | undefined> {
    if (id === 'boom') throw new Error('order lookup failed')
    const order = await orderRepository.findById(id)
    if (!order) return undefined                           // the handler maps this to 404: handled, not an error
    const { price } = await pricingClient.quote(id)
    log.info({ 'order.id': id }, 'order fetched')
    void runTask('audit:record', { payload: { id, trigger: captureTrigger() } })
      .catch((err) => log.warn({ err, 'order.id': id }, 'audit not recorded'))
    return { id, total: price }
  },
})

// server/routes/orders/[id].get.ts
export default defineEventHandler(async (event) => {
  const order = await orderService.getOrder(getRouterParam(event, 'id')!, event.context.logger)
  if (!order) throw createError({ statusCode: 404, statusMessage: 'order not found' })
  return order
})
```

`/pricing/[id].get.ts` returns `{ id, price }` and `/health.get.ts` returns `{ status: 'ok' }`; neither gets a Tier 2 span. Never throw `createError({ statusCode: 404 })` from inside a service: it propagates out of the Tier 2 span and marks it `ERROR`.

## Serverless and edge

Serverless and edge presets (`aws-lambda`, `netlify`, `vercel`, `vercel-edge`, `cloudflare-module`) have no start command to preload into, and the platform can freeze the process the moment the response is out ([Serverless](../SKILL.md#serverless)). So the SDK is initialised at module load in a Nitro plugin; spans and logs use the simple processors, which export as each span or record ends; and every response waits on a bounded `forceFlush` of all three providers. **The `MeterProvider` must be flushed on every invocation**: there is no simple metric reader, and a periodic reader would hold the points until a timer the platform never lets fire.

**What does not load.** On edge runtimes no auto-instrumentation loads: each patches a Node module at import time, and an edge bundle has neither the modules nor the import hooks. Missing there: `instrumentation-http` (no `node:http` server; the platform owns the socket, so the SERVER span below is created by the plugin), `instrumentation-undici` (edge `fetch` is not undici), `instrumentation-pino` (pino's Node build and its streams), `instrumentation-amqplib` and the database drivers such as `instrumentation-pg` (no raw TCP), and `instrumentation-runtime-node` (no event loop or heap APIs). On serverless Node presets the modules exist, but a plugin runs after the runtime imported them; where the platform accepts `NODE_OPTIONS` (AWS Lambda does), add `--import ./instrumentation.mjs` with the simple processors and keep the flush below.

```ts
// server/plugins/00.telemetry.ts: serverless and edge presets only; node-server uses instrumentation.mjs
import { context, metrics, propagation, ROOT_CONTEXT, SpanKind, SpanStatusCode, trace } from '@opentelemetry/api'
import { logs } from '@opentelemetry/api-logs'
import { AsyncLocalStorageContextManager } from '@opentelemetry/context-async-hooks'
import { CompositePropagator, W3CBaggagePropagator, W3CTraceContextPropagator } from '@opentelemetry/core'
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http'
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { resourceFromAttributes } from '@opentelemetry/resources'
import { LoggerProvider, SimpleLogRecordProcessor } from '@opentelemetry/sdk-logs'
import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics'
import { BasicTracerProvider, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base'

const env = process.env // edge exporter builds may not read env themselves: pass what OTEL_* says
const url = (signal: string) => env.OTEL_EXPORTER_OTLP_ENDPOINT ? { url: `${env.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/${signal}` } : {}
const pairs = (env.OTEL_RESOURCE_ATTRIBUTES ?? '').split(',').filter(Boolean)
  .map((pair) => [pair.slice(0, pair.indexOf('=')), pair.slice(pair.indexOf('=') + 1)].map((part) => decodeURIComponent(part.trim())))
const resource = resourceFromAttributes({ 'service.name': env.OTEL_SERVICE_NAME, ...Object.fromEntries(pairs) })

context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable())
propagation.setGlobalPropagator(new CompositePropagator({ propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()] }))
const tracerProvider = new BasicTracerProvider({ resource, spanProcessors: [new SimpleSpanProcessor(new OTLPTraceExporter(url('traces')))] })
const loggerProvider = new LoggerProvider({ resource, processors: [new SimpleLogRecordProcessor(new OTLPLogExporter(url('logs')))] })
const meterProvider = new MeterProvider({
  resource,
  readers: [new PeriodicExportingMetricReader({ exporter: new OTLPMetricExporter(url('metrics')), exportIntervalMillis: 3_600_000 })], // the flush exports
})
trace.setGlobalTracerProvider(tracerProvider)
logs.setGlobalLoggerProvider(loggerProvider)
metrics.setGlobalMeterProvider(meterProvider)

function flush(): Promise<unknown> { // bounded: a dead collector never holds the invocation
  const all = Promise.allSettled([tracerProvider.forceFlush(), loggerProvider.forceFlush(), meterProvider.forceFlush()])
  return Promise.race([all, new Promise((resolve) => setTimeout(resolve, 2_000))])
}

export default defineNitroPlugin((nitroApp) => {
  const handle = nitroApp.h3App.handler
  nitroApp.h3App.handler = (event) => {
    const parent = propagation.extract(ROOT_CONTEXT, getRequestHeaders(event))
    const span = trace.getTracer('fixture.telemetry').startSpan(event.method, {
      kind: SpanKind.SERVER, attributes: { 'http.request.method': event.method, 'url.path': event.path.split('?')[0] },
    }, parent)
    return context.with(trace.setSpan(parent, span), async () => {
      let status: number | undefined
      try {
        return await handle(event)
      } catch (error) {
        status = (error as { statusCode?: number }).statusCode ?? 500
        throw error
      } finally {
        status ??= getResponseStatus(event)
        const route = event.context.matchedRoute?.path
        if (route) { span.setAttribute('http.route', route); span.updateName(`${event.method} ${route}`) }
        span.setAttribute('http.response.status_code', status)
        if (status >= 500) span.setStatus({ code: SpanStatusCode.ERROR })   // a handled 404 stays UNSET
        span.end()
        const waitUntil = event.context.waitUntil as ((p: Promise<unknown>) => void) | undefined
        if (waitUntil) waitUntil(flush()); else await flush()                // edge: after the response; Lambda: before
      }
    })
  }
})
```

The `AsyncLocalStorageContextManager` needs `node:async_hooks`: Cloudflare provides it under the `nodejs_compat` flag, Vercel Edge as a global. Without it, `withSpan` cannot find a parent and every Tier 2 span becomes a root.

**Outbound `fetch` on edge.** With no undici instrumentation, wrap `fetch` once and call the wrapper from `PricingClient`. `@opentelemetry/instrumentation-fetch` targets browsers (it relies on resource timing); it is not confirmed on edge runtimes.

```ts
// server/utils/traced-fetch.ts: edge presets only
import { context, propagation, SpanKind, SpanStatusCode, trace } from '@opentelemetry/api'

export function tracedFetch(input: string | URL, init: RequestInit = {}): Promise<Response> {
  const url = new URL(input)
  const method = (init.method ?? 'GET').toUpperCase()
  return trace.getTracer('fixture.telemetry').startActiveSpan(method, {
    kind: SpanKind.CLIENT,
    attributes: { 'http.request.method': method, 'server.address': url.hostname, 'url.full': `${url.origin}${url.pathname}` },
  }, async (span) => {
    const headers = new Headers(init.headers)
    propagation.inject(context.active(), headers, { set: (carrier, key, value) => carrier.set(key, value) })
    try {
      const response = await fetch(url, { ...init, headers })
      span.setAttribute('http.response.status_code', response.status)
      if (response.status >= 400) span.setStatus({ code: SpanStatusCode.ERROR })   // client spans: 4xx counts
      return response
    } catch (error) {
      span.recordException(error as Error); span.setStatus({ code: SpanStatusCode.ERROR }); throw error
    } finally { span.end() }
  })
}
```

**Logs on edge.** pino and its instrumentation do not run there; emit through the logs API so records still carry the active trace: `logs.getLogger('fixture').emit({ severityText: 'INFO', body: 'order fetched', attributes: { 'order.id': id }, context: context.active() })`, behind one small `log` helper so call sites keep the fields-first shape. A background job started from an edge request must finish under `waitUntil` before the flush, or its span is lost.

## Nitro tasks and RabbitMQ

**Nitro tasks** need `nitro.experimental.tasks: true` (the config above). `AuditJob.record` is the task `audit:record`, started from `OrderService.getOrder` with `runTask` and not awaited ([Nitro tasks](https://nitro.build/guide/tasks)). `runTask` runs in the same process and inherits the request's async context, so a span started the ordinary way would become a child of the request and stretch its trace. `withLinkedRootSpan` starts it from `ROOT_CONTEXT` with `root: true` and a link to the carrier captured at enqueue; the carrier holds the span current at that moment, `OrderService.getOrder`, which is in the request's trace ([Background and messaging](../SKILL.md#background-and-messaging)).

```ts
// server/tasks/audit/record.ts
import { logger } from '../../utils/logger'

export default defineTask({
  meta: { name: 'audit:record', description: 'Record an audit entry for a fetched order' },
  run({ payload }) {
    const { id, trigger } = payload as { id: string; trigger: Record<string, string> }
    return withLinkedRootSpan('AuditJob.record', trigger, async () => {
      logger.child({ logger: 'AuditJob' }).info({ 'order.id': id }, 'audit recorded')  // trace_id is the job's own
      return { result: 'recorded' }
    })
  },
})
```

The carrier is a plain `traceparent` record, so the same payload survives a hop through a real queue. A task started by `scheduledTasks` (cron) has no trigger: pass `{}` and it gets a root span with no link.

**RabbitMQ with `amqplib`.** `@opentelemetry/instrumentation-amqplib` (in the bundle) creates a PRODUCER span on `publish` and `sendToQueue` and injects `traceparent` into the message headers; on `consume` it extracts the headers and runs the callback under a CONSUMER span that is a child of the producer, the same trace. Add the link the skill requires from the same headers. The consumer span ends when the message is acked or nacked, so always settle it.

```ts
// server/utils/audit-queue.ts
import amqp from 'amqplib'

export const AUDIT_QUEUE = 'orders.audit'
let channel: Promise<amqp.Channel> | undefined

export function auditChannel(): Promise<amqp.Channel> {
  channel ??= amqp.connect(useRuntimeConfig().amqpUrl).then(async (connection) => {
    const ch = await connection.createChannel()
    await ch.assertQueue(AUDIT_QUEUE, { durable: true })
    return ch
  })
  return channel
}

export async function publishAudit(id: string): Promise<void> {     // PRODUCER span and headers: the instrumentation
  const ch = await auditChannel()
  ch.sendToQueue(AUDIT_QUEUE, Buffer.from(JSON.stringify({ id })), { persistent: true, contentType: 'application/json' })
}

// server/plugins/audit-consumer.ts
import { propagation, ROOT_CONTEXT, trace } from '@opentelemetry/api'
import { logger } from '../utils/logger'

export default defineNitroPlugin(() => {
  const log = logger.child({ logger: 'AuditConsumer' })
  auditChannel().then((ch) => ch.consume(AUDIT_QUEUE, (msg) => {
    if (!msg) return
    // The CONSUMER span is current here: the instrumentation extracted the headers before opening it.
    const producer = trace.getSpanContext(propagation.extract(ROOT_CONTEXT, msg.properties.headers ?? {}))
    if (producer) trace.getActiveSpan()?.addLink({ context: producer })   // Span.addLink: a recent @opentelemetry/api
    try {
      const { id } = JSON.parse(msg.content.toString()) as { id: string }
      log.info({ 'order.id': id }, 'audit recorded')
      ch.ack(msg)                                                         // ends the CONSUMER span
    } catch (err) {
      log.error({ err }, 'audit message rejected')
      ch.nack(msg, false, false)
    }
  })).catch((err) => log.warn({ err }, 'audit consumer not started'))
})
```

Do not turn on the instrumentation's option that makes consumer spans new traces with links only (its README names it): the skill wants the child and the link. The plugin does not need the preload ordering for `amqplib` itself (`instrumentation.mjs` patched it already); it only starts consuming.

## Logs

pino is configured by the [`application-logging`](../../../../application-logging/skills/application-logging/SKILL.md) skill: root logger, `LOG_FORMAT`, redaction, the `err` serializer, and the child logger on `event.context.logger`. Tracing adds only `@opentelemetry/instrumentation-pino`, configured in `telemetry/instrumentations.mjs` and registered by the preload, which does two things to every record ([Logs](../SKILL.md#logs)):

- **Correlation.** It writes `trace_id`, `span_id`, and `trace_flags` from the active span into the record, so the stdout line carries them in both formats. `logKeys` pins those names. Its `logHook(span, record)` option adds further span-derived fields to the stdout record; never use it, or a pino `mixin`, to copy the IDs by hand.
- **The logs bridge.** It sends each record to the global `LoggerProvider` that `NodeSDK` registered from `logRecordProcessors`. The OTel record's body is the message, its attributes are the record's fields (`order.id`), and its trace context comes from the injected IDs. Both are on by default; `disableLogCorrelation` and `disableLogSending` must stay `false`.

The instrumentation patches pino when pino is imported; that is why it lives in the preload. Records from consola (`console.*` in Nitro) never reach it. The custom `messageKey: 'body'`, timestamp, and level formatters from the logging setup change the record it parses; the component test's correlation assertion is the check after changing any of them.

## Plain Node and Express

The same `instrumentation.mjs`, `telemetry/instrumentations.mjs`, and `withSpan` module work without Nitro: `node --import ./instrumentation.mjs server.mjs`. Differences:

- **Express** is instrumented by `@opentelemetry/instrumentation-express` in the bundle, which sets `http.route` on the SERVER span itself; no route plugin. It also creates a span per middleware and route handler, which the tier rules forbid; turn them off with `'@opentelemetry/instrumentation-express': { ignoreLayersType: ['middleware', 'request_handler', 'router'] }`. Express 5 needs a recent instrumentation release.
- **Plain `node:http`** has no router: set the route the way the Nitro plugin does, with `getRPCMetadata(context.active())` inside the handler once the route is known.
- **Request context**: a first middleware creates the request's pino child logger (`req.log = logger.child({ 'request.id': id })`) as the logging skill's Nitro middleware does.
- **Errors**: one error-handling middleware logs the exception once and maps it; a not-found returns `404` without throwing through a Tier 2 span.
- **Background jobs**: `captureTrigger()` at enqueue and `withLinkedRootSpan` in the worker, whatever runs the job.

## Test templates

The test templates are in a separate file, `references/node-tests.md`, listed in the skill's [See also](../SKILL.md#see-also): vitest component tests on `InMemorySpanExporter`, `InMemoryLogRecordExporter`, and `InMemoryMetricExporter` against the built Nitro app, one per assertion in [Verification](../SKILL.md#verification), and the Testcontainers collector test. Run both layers before reporting done.

## Known complexities

- **Nitro's `$fetch` with a relative URL makes no network hop.** `$fetch('/pricing/42')` inside the server calls the route in-process: no socket, no undici, so no CLIENT span, no `traceparent`, and no second SERVER span. The trace looks complete and hides the hop. Outbound calls, including the fixture's self-call, use global `fetch` with an absolute URL (`http://127.0.0.1:<port>/pricing/42`); `@opentelemetry/instrumentation-undici` supplies the CLIENT span.
- **No `http.route` by default.** Nitro does not report the matched route to the http instrumentation, so the SERVER span is named `GET` and lacks `http.route` until the route plugin sets it; probes fall back to `url.path`. The template is Nitro's syntax (`/orders/:id`).
- **Stable HTTP attribute names are opt-in.** Without `OTEL_SEMCONV_STABILITY_OPT_IN=http` the http and undici instrumentations emit `http.target` and `http.method`; dashboards and probes keyed on `url.path` and `http.request.method` see nothing.
- **Inlined dependencies cannot be patched.** Nitro's `node-server` build keeps dependencies external in `.output/server/node_modules`, which the ESM hook can patch. A dependency inlined into a chunk (by `externals.inline`, or a bundler setting) has no module boundary to hook: its spans disappear with no error. Keep pino, database drivers, and `amqplib` external.
- **One API copy, one major.** The preload's `@opentelemetry/api` and the copy Nitro traces into `.output/server/node_modules` share globals only when their majors match; otherwise the app's `withSpan` talks to a no-op API.
- **`runTask` is single-flight.** Nitro runs one instance of a task name at a time; a call while one is running receives the running call's result, so its payload is dropped. Fine for the fixture; for a job per request at volume, publish to RabbitMQ.
- **Shutdown race.** Nitro's `node-server` installs its own `SIGTERM` graceful shutdown (tuned by its `NITRO_SHUTDOWN_*` variables) and may exit before the preload's `sdk.shutdown()` resolves. Confirm on the fixture that the last batch reaches the collector after `SIGTERM`; if it does not, let Nitro close the server without forcing the exit and leave the exit to the preload.
- **Server span and the exception.** h3 catches the service's error and answers `500`; the http instrumentation sets `ERROR` from the status but sees no exception, so on `GET /orders/boom` only `OrderService.getOrder` carries the `exception` event. The error rule is met as written.
- **Non-`Error` throws.** A thrown string or number cannot enter the `WeakSet`, so each wrapper it passes through records it again. Throw `Error` objects; reused error instances get their event only the first time.
- **`nuxi dev`.** Nuxt's dev server runs Nitro in a worker; `NODE_OPTIONS=--import` preloads may not reach it. Verify telemetry on the built server (`npm run build && npm start`), which is what the tests run.
- **Not run in this reference.** From documentation, SDK sources read earlier, and memory, to be confirmed by the fixture build: `setGlobalErrorHandler` being the only path export failures take (some exporter versions may also log through `diag`); `getRPCMetadata` and `rpc.span` being set by the http instrumentation for Nitro's requests, and context still active in Nitro's `beforeResponse` and `error` hooks; `NodeSDK` merging `resource` with `resourceDetectors` output; `metricReader` versus `metricReaders` by release; h3 v1 reading `app.handler` per request so the serverless wrapper takes effect, `event.context.waitUntil` on edge presets, and `process.env` being populated at module load on Cloudflare; the edge build of the `-otlp-http` exporters using `fetch`; `Span.addLink`; the amqplib instrumentation's consumer span being a child of the producer by default; `ignoreLayersType` values for Express.
