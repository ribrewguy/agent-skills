# Node: test templates

Component and integration test templates for the Nitro wiring in the skill's Node reference (`references/node.md`). They implement the first two layers of [Verification](../SKILL.md#verification) against the invented `orders` app: `GET /orders/{id}` through `OrderService.getOrder`, `OrderRepository.findById`, and `PricingClient.quote` (a global `fetch` to the same app's `/pricing/{id}`), logging `order fetched` with `order.id`, and starting the Nitro task `audit:record`, whose span is `AuditJob.record`. `GET /orders/404` is a handled not-found; `GET /orders/boom` throws in `OrderService.getOrder`.

## General approach

Both layers test the **built** Nitro server, the artifact that ships, because instrumentation behaves differently under `nuxi dev`. `@nuxt/test-utils` `setup()` builds it.

- **Component tests** keep the app in the test process so they can read in-memory exporters: `InMemorySpanExporter` and `InMemoryLogRecordExporter` behind simple processors, and an `InMemoryMetricExporter` behind a reader the test flushes. `setup()` builds without starting a server; the test starts an in-memory `NodeSDK` with the same instrumentation list as `instrumentation.mjs`, registers the ESM hook, then imports the built `server/index.mjs`, which listens on a fixed port. The `/pricing` route on that port is the in-process stub server for the outbound call.
- **The integration test** lets `setup()` start the built server as a child process with `NODE_OPTIONS=--import ./instrumentation.mjs` and only `OTEL_*` variables pointing at a Testcontainers collector, then reads the collector's file exporter.

Requests from the test itself run under `suppressTracing`, so the test's own `fetch` adds no CLIENT span or `traceparent` and the SERVER span stays a root.

```ts
// vitest.config.ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    pool: 'forks',               // the ESM hook and the app's server live in one child process per file
    fileParallelism: false,      // fixed ports
    testTimeout: 30_000,
    hookTimeout: 600_000,        // the Nuxt build and the collector pull
  },
})
```

## In-memory configuration

```ts
// test/in-memory-telemetry.ts
import { register } from 'node:module'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { resourceFromAttributes } from '@opentelemetry/resources'
import { NodeSDK } from '@opentelemetry/sdk-node'
import { InMemoryLogRecordExporter, SimpleLogRecordProcessor } from '@opentelemetry/sdk-logs'
import { AggregationTemporality, InMemoryMetricExporter, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics'
import { InMemorySpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base'
import { instrumentations } from '../telemetry/instrumentations.mjs'

export const spans = new InMemorySpanExporter()
export const logs = new InMemoryLogRecordExporter()
export const metrics = new InMemoryMetricExporter(AggregationTemporality.CUMULATIVE)
export const metricReader = new PeriodicExportingMetricReader({ exporter: metrics, exportIntervalMillis: 3_600_000 })

/** Starts the in-memory SDK, then the built Nitro server in this process. Call once, after setup() built it. */
export async function startAppWithInMemoryTelemetry(outputDir: string, port: number): Promise<void> {
  process.env.OTEL_SEMCONV_STABILITY_OPT_IN = 'http'
  register('@opentelemetry/instrumentation/hook.mjs', import.meta.url)
  new NodeSDK({
    resource: resourceFromAttributes({ 'service.name': 'orders' }),
    spanProcessors: [new SimpleSpanProcessor(spans)],
    logRecordProcessors: [new SimpleLogRecordProcessor(logs)],
    metricReader,
    instrumentations: instrumentations(),
  }).start()
  process.env.PORT = process.env.NITRO_PORT = String(port)
  process.env.NUXT_PRICING_BASE_URL = `http://127.0.0.1:${port}`
  await import(pathToFileURL(join(outputDir, 'server/index.mjs')).href) // .mjs: vitest hands it to Node, so the hook applies
}

export function resetTelemetry(): void {
  spans.reset(); logs.reset(); metrics.reset()
}
```

## Component tests

```ts
// test/telemetry.component.test.ts
import { fileURLToPath } from 'node:url'
import { setup } from '@nuxt/test-utils/e2e'
import { context, SpanKind, SpanStatusCode } from '@opentelemetry/api'
import { suppressTracing } from '@opentelemetry/core'
import type { ReadableSpan } from '@opentelemetry/sdk-trace-base'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { logs, metricReader, metrics, resetTelemetry, spans, startAppWithInMemoryTelemetry } from './in-memory-telemetry'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const OUTPUT = `${ROOT}.output-test`
const PORT = 3123

await setup({ rootDir: ROOT, build: true, server: false, nuxtConfig: { nitro: { output: { dir: OUTPUT } } } })
beforeAll(() => startAppWithInMemoryTelemetry(OUTPUT, PORT))
beforeEach(() => resetTelemetry())

const get = (path: string) =>
  context.with(suppressTracing(context.active()), async () => (await fetch(`http://127.0.0.1:${PORT}${path}`)).status)

const all = () => spans.getFinishedSpans()
const id = (s: ReadableSpan) => s.spanContext().spanId
const traceOf = (s: ReadableSpan) => s.spanContext().traceId
const route = (s: ReadableSpan) => String(s.attributes['http.route'] ?? s.attributes['url.path'] ?? '')
function single<T>(items: T[]): T { expect(items).toHaveLength(1); return items[0] }
const server = (prefix: string) => single(all().filter((s) => s.kind === SpanKind.SERVER && route(s).startsWith(prefix)))
const named = (name: string) => single(all().filter((s) => s.name === name))
const errored = () => all().filter((s) => s.status.code === SpanStatusCode.ERROR)
function isDescendantOf(span: ReadableSpan, ancestor: ReadableSpan): boolean {
  const byId = new Map(all().map((s) => [id(s), s]))
  for (let p = span.parentSpanContext?.spanId; p; p = byId.get(p)?.parentSpanContext?.spanId) if (p === id(ancestor)) return true
  return false
}
const fetchedLog = () => single(logs.getFinishedLogRecords().filter((r) => r.body === 'order fetched'))
async function points(name: string) {
  await metricReader.forceFlush()
  const found = metrics.getMetrics().flatMap((rm) => rm.scopeMetrics).flatMap((sm) => sm.metrics).filter((m) => m.descriptor.name === name)
  return { unit: found.at(-1)?.descriptor.unit, points: found.at(-1)?.dataPoints ?? [] }
}
/** Waits until the request's server spans and the background job's span have all ended. */
const awaitOrder42 = () => vi.waitFor(() => {
  expect(all().map((s) => s.name)).toEqual(expect.arrayContaining(['OrderService.getOrder', 'AuditJob.record']))
  server('/orders/'); server('/pricing/')
}, { timeout: 10_000 })

describe('orders telemetry', () => {
  it('server span has service and repository spans as descendants in order', async () => {
    expect(await get('/orders/42')).toBe(200); await awaitOrder42()
    const service = named('OrderService.getOrder')
    const repository = named('OrderRepository.findById')
    expect(isDescendantOf(service, server('/orders/'))).toBe(true)
    expect(isDescendantOf(repository, service)).toBe(true)
    expect(service.attributes['code.function.name']).toBe('OrderService.getOrder')
    expect(repository.attributes['code.function.name']).toBe('OrderRepository.findById')
    expect(all().filter((s) => 'code.namespace' in s.attributes)).toEqual([])
  })

  it('outbound call produces a client span and the stub server span shares its trace', async () => {
    expect(await get('/orders/42')).toBe(200); await awaitOrder42()
    const request = server('/orders/')
    const client = single(all().filter((s) => s.kind === SpanKind.CLIENT && traceOf(s) === traceOf(request)))
    const pricing = server('/pricing/')
    expect(isDescendantOf(client, request)).toBe(true)
    expect(traceOf(pricing)).toBe(traceOf(request))
    expect(pricing.parentSpanContext?.spanId).toBe(id(client))                 // traceparent crossed the wire
    expect(client.parentSpanContext?.spanId).toBe(id(named('OrderService.getOrder')))
  })

  it('async hop keeps the parent span', async () => {
    // findById awaits a timer before reading; AsyncLocalStorage must carry the service span across it
    expect(await get('/orders/42')).toBe(200); await awaitOrder42()
    expect(named('OrderRepository.findById').parentSpanContext?.spanId).toBe(id(named('OrderService.getOrder')))
    expect(fetchedLog().spanContext?.spanId).toBe(id(named('OrderService.getOrder')))  // logged after the hop
  })

  it('log inside the request carries trace_id and span_id of the active span', async () => {
    expect(await get('/orders/42')).toBe(200); await awaitOrder42()
    const service = named('OrderService.getOrder')
    const record = fetchedLog()
    expect(record.spanContext?.traceId).toBe(traceOf(server('/orders/')))
    expect(record.spanContext?.spanId).toBe(id(service))
    expect(record.attributes['order.id']).toBe('42')
  })

  it('default service metrics recorded with code function name and outcome', async () => {
    expect(await get('/orders/42')).toBe(200); await awaitOrder42()
    const wanted = { 'code.function.name': 'OrderService.getOrder', outcome: 'success' }
    const calls = await points('app.service.calls')
    expect(calls.unit).toBe('{call}')
    expect(calls.points.find((p) => expect.objectContaining(wanted).asymmetricMatch(p.attributes))?.value).toBeGreaterThanOrEqual(1)
    const duration = await points('app.service.duration')
    expect(duration.unit).toBe('s')
    expect(duration.points.some((p) => expect.objectContaining(wanted).asymmetricMatch(p.attributes))).toBe(true)
    for (const p of [...calls.points, ...duration.points]) expect(Object.keys(p.attributes).sort()).toEqual(['code.function.name', 'outcome'])
  })

  it('no span has error status on the happy path', async () => {
    expect(await get('/orders/42')).toBe(200); await awaitOrder42()
    expect(errored()).toEqual([])
  })

  it('handled not found has no error span', async () => {
    expect(await get('/orders/404')).toBe(404)
    await vi.waitFor(() => server('/orders/'), { timeout: 10_000 })
    expect(errored()).toEqual([])
  })

  it('failure marks the originating span and the ancestors it propagated out of', async () => {
    expect(await get('/orders/boom')).toBe(500)
    await vi.waitFor(() => server('/orders/'), { timeout: 10_000 })
    const service = named('OrderService.getOrder')
    expect(service.status.code).toBe(SpanStatusCode.ERROR)
    expect(service.events.filter((e) => e.name === 'exception')).toHaveLength(1)  // recorded once, where it originated
    expect(server('/orders/').status.code).toBe(SpanStatusCode.ERROR)
    // no other Tier 2 span records the same exception (the server span may: accepted default)
    expect(all().filter((s) => s.kind === SpanKind.INTERNAL && s !== service && s.events.some((e) => e.name === 'exception'))).toEqual([])
    const calls = await points('app.service.calls')
    expect(calls.points.some((p) => p.attributes.outcome === 'error')).toBe(true)
  })

  it('background job starts its own trace with a link to the triggering span', async () => {
    expect(await get('/orders/42')).toBe(200); await awaitOrder42()
    const request = server('/orders/')
    const job = named('AuditJob.record')
    expect(job.parentSpanContext).toBeUndefined()                              // root span
    expect(traceOf(job)).not.toBe(traceOf(request))                            // own trace
    // the link targets the span current at enqueue (OrderService.getOrder), which is in the request's trace
    expect(job.links.map((l) => l.context.traceId)).toContain(traceOf(request))
    expect(job.links.map((l) => l.context.spanId)).toContain(id(named('OrderService.getOrder')))
  })
})
```

## Integration test with a real collector

One per project. Testcontainers starts the official contrib collector with the skill's `assets/collector-test.yaml` (OTLP receivers on 4317 and 4318, file exporter to `/out/telemetry.jsonl`); copy that file to `test/collector-test.yaml`. `/out` is a bind mount of a world-writable temp directory, so the test reads the file directly. The collector starts at module load because `setup()` must see its port in `process.env` before it spawns the server. Pin the image tag in the project; it is unpinned here because skills name artifacts, not versions.

```ts
// test/telemetry.integration.test.ts
import { chmodSync, existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { setup } from '@nuxt/test-utils/e2e'
import { GenericContainer, Wait } from 'testcontainers'
import { afterAll, expect, it, vi } from 'vitest'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const PORT = 3124
const out = mkdtempSync(join(tmpdir(), 'otel-out-'))
chmodSync(out, 0o777)                                       // the collector image runs as a non-root user

const collector = await new GenericContainer('otel/opentelemetry-collector-contrib')
  .withCopyFilesToContainer([{ source: join(ROOT, 'test/collector-test.yaml'), target: '/etc/otelcol-contrib/config.yaml' }])
  .withBindMounts([{ source: out, target: '/out', mode: 'rw' }])
  .withExposedPorts(4318)
  .withWaitStrategy(Wait.forLogMessage(/Everything is ready/))
  .start()
afterAll(() => collector.stop())

Object.assign(process.env, {                                // inherited by the server setup() spawns
  OTEL_SERVICE_NAME: 'orders',
  OTEL_EXPORTER_OTLP_ENDPOINT: `http://${collector.getHost()}:${collector.getMappedPort(4318)}`,
  OTEL_EXPORTER_OTLP_PROTOCOL: 'http/protobuf',
  OTEL_RESOURCE_ATTRIBUTES: 'service.version=test,deployment.environment.name=test',
  OTEL_SEMCONV_STABILITY_OPT_IN: 'http',
  OTEL_BSP_SCHEDULE_DELAY: '500',
  OTEL_BLRP_SCHEDULE_DELAY: '500',
  OTEL_METRIC_EXPORT_INTERVAL: '1000',
  NODE_OPTIONS: `--import ${pathToFileURL(join(ROOT, 'instrumentation.mjs')).href}`,
  NUXT_PRICING_BASE_URL: `http://127.0.0.1:${PORT}`,
})
await setup({ rootDir: ROOT, server: true, port: PORT })

type Json = Record<string, any>
const values = (o: Json): Json => Object.fromEntries((o.attributes ?? []).map((a: Json) => [a.key, Object.values(a.value)[0]]))
function telemetry() {
  const file = join(out, 'telemetry.jsonl')
  const lines: Json[] = existsSync(file) ? readFileSync(file, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []
  const pick = (outer: string, scope: string, leaf: string) => lines.flatMap((l) => l[outer] ?? [])
    .flatMap((r: Json) => (r[scope] ?? []).flatMap((s: Json) => s[leaf] ?? []).map((item: Json) => ({ ...item, resource: values(r.resource ?? {}) })))
  return { spans: pick('resourceSpans', 'scopeSpans', 'spans'), logs: pick('resourceLogs', 'scopeLogs', 'logRecords'),
    metrics: pick('resourceMetrics', 'scopeMetrics', 'metrics') }
}

it('spans logs and metrics reach a real collector with correlated trace ids', async () => {
  expect((await fetch(`http://127.0.0.1:${PORT}/orders/42`)).status).toBe(200)

  await vi.waitFor(() => {
    const { spans, logs, metrics } = telemetry()
    const SERVER = 2, CLIENT = 3                             // OTLP JSON span kinds
    const route = (s: Json) => String(values(s)['http.route'] ?? values(s)['url.path'] ?? '')
    const one = (items: Json[]) => { expect(items).toHaveLength(1); return items[0] }
    const named = (name: string) => one(spans.filter((s) => s.name === name))
    const orders = one(spans.filter((s) => s.kind === SERVER && route(s).startsWith('/orders/')))
    const pricing = one(spans.filter((s) => s.kind === SERVER && route(s).startsWith('/pricing/')))
    const byId = new Map(spans.map((s) => [s.spanId, s]))
    const under = (s: Json, a: Json) => { for (let p = s.parentSpanId; p; p = byId.get(p)?.parentSpanId) if (p === a.spanId) return true; return false }

    expect(pricing.traceId).toBe(orders.traceId)
    expect(under(one(spans.filter((s) => s.kind === CLIENT && s.traceId === orders.traceId)), orders)).toBe(true)
    const service = named('OrderService.getOrder'), repository = named('OrderRepository.findById')
    expect(values(service)['code.function.name']).toBe('OrderService.getOrder')
    expect(values(repository)['code.function.name']).toBe('OrderRepository.findById')
    expect(under(service, orders) && under(repository, service)).toBe(true)

    const job = named('AuditJob.record')
    expect(job.traceId).not.toBe(orders.traceId)
    expect((job.links ?? []).map((l: Json) => l.traceId)).toContain(orders.traceId)

    const fetched = one(logs.filter((r) => r.body?.stringValue === 'order fetched'))
    expect(values(fetched)['order.id']).toBe('42')
    expect(fetched.traceId).toBe(orders.traceId)            // log correlated to a span in the same output

    for (const name of ['app.service.calls', 'app.service.duration']) {
      const m = metrics.filter((x) => x.name === name)
      const dataPoints = m.flatMap((x) => x.sum?.dataPoints ?? x.histogram?.dataPoints ?? [])
      expect(dataPoints.some((p: Json) => values(p)['code.function.name'] === 'OrderService.getOrder')).toBe(true)
    }
    expect(metrics.find((x) => x.name === 'app.service.duration')?.unit).toBe('s')

    for (const item of [...spans, ...logs, ...metrics]) expect(item.resource['service.name']).toBe('orders')
  }, { timeout: 60_000, interval: 1_000 })
})
```

## Known complexities

- **`setup()` options.** `build`, `server`, `port`, and `nuxtConfig` are `@nuxt/test-utils` `setup()` options; confirm against the pinned release that `build: true, server: false` builds without starting, that `nuxtConfig.nitro.output.dir` wins over the test-utils output directory, and that the spawned server inherits `process.env`. The spawned server also waits for `/` to answer, so a server-only app needs an `app.vue` or a `/` route.
- **The app in the test process.** The component tests import the built `server/index.mjs` into the vitest worker, which Nitro's `node-server` entry turns into a listening server for the rest of the file; one test file owns one port, and `pool: 'forks'` gives each file its own process. If the pinned vitest transforms `.mjs` files outside `node_modules`, add the output directory to `server.deps.external` so Node loads them and the ESM hook applies.
- **Two API copies.** The test's `@opentelemetry/api` and the one traced into `.output-test/server/node_modules` share the global registration only when their majors match; a mismatch shows as zero Tier 2 spans with every Tier 1 span present.
- **Batch delays in the integration test.** The preload uses batch processors; the `OTEL_BSP_*`, `OTEL_BLRP_*`, and `OTEL_METRIC_EXPORT_INTERVAL` values above shorten them. The default metric interval is one minute; do not drop the override.
- **The collector's file.** The contrib image runs as a non-root user; the bind-mounted directory is world-writable so the file exporter can create `telemetry.jsonl`. Docker Desktop must share the temp directory (the default macOS shares include it); `container.copyArchiveFromContainer('/out/telemetry.jsonl')` returns a tar stream instead when bind mounts are not possible. Confirm the default config path `/etc/otelcol-contrib/config.yaml` against the pinned tag.
- **Server span matching.** The helpers accept `http.route` or `url.path`, so the 404 and 500 paths match even if the route hooks did not run for them.
- **Background job timing.** `audit:record` runs after the response; every test on `GET /orders/42` waits for its span before reading, so spans from one test never leak into the next after the reset.
- **Resource in the component tests.** The in-memory SDK sets `service.name` in code because it is a test double; the integration test proves the real resource comes from `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`.
