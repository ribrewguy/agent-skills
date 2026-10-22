# Node logging: pino and Nitro

Server code logs through one pino logger and nothing else. `LOG_FORMAT` picks the stdout shape: `text` sends records through `pino-pretty` for humans in development, and `json` writes one-line JSON in the shape SKILL.md defines, which is the production setting. `@opentelemetry/instrumentation-pino` adds `trace_id` and `span_id` to every record and sends each record to the OTel logs pipeline. That makes it the OTel appender on Node. It is named here only; it is configured by the `opentelemetry` skill, and it must be registered before pino is first imported. Each request gets a child logger with its context bound, created in a Nitro middleware and carried on `event.context.logger`. Redaction and the error serializer are set once on the root logger, so every child inherits them. The rules themselves (levels, field names, the denylist, logging an exception once) live in [SKILL.md](../SKILL.md#field-rules). This file is wiring only.

```ts
log.info({ 'order.id': id }, 'order fetched')                   // fields first, stable message second
log.warn({ err, 'order.id': id }, 'pricing unavailable, using cached price')
```

## pino setup

Packages: `pino`, `pino-pretty` (a dev dependency, loaded only when `LOG_FORMAT=text`).

```ts
// server/utils/logger.ts
import pino, { type LoggerOptions } from 'pino'

const format = process.env.LOG_FORMAT ?? (process.env.NODE_ENV === 'production' ? 'json' : 'text')

// The denylist from SKILL.md as pino paths. A seatbelt, not the control: the field-name rule is the control.
const REDACT_PATHS = [
  'password', '*.password', 'token', '*.token', 'accessToken', 'refreshToken',
  'secret', '*.secret', 'apiKey', '*.apiKey', 'clientSecret',
  'authorization', '*.authorization', 'cookie', '*.cookie', 'sessionId', '*.sessionId',
  'cardNumber', '*.cardNumber', 'email', '*.email',
  'req.headers.authorization', 'req.headers.cookie', 'res.headers["set-cookie"]',
]

const common: LoggerOptions = {
  level: process.env.LOG_LEVEL ?? 'info',
  messageKey: 'body',
  base: { 'service.name': process.env.OTEL_SERVICE_NAME ?? 'unknown_service:node' },
  redact: { paths: REDACT_PATHS, censor: '[REDACTED]' },
  serializers: { err: pino.stdSerializers.err },   // type, message, stack (and cause) from any thrown value
}

const json: LoggerOptions = {
  ...common,
  timestamp: () => `,"timestamp":"${new Date().toISOString()}"`,
  formatters: {
    // Keep pino's numeric level alongside severity_text; the OTel pino instrumentation reads it.
    level: (label, number) => ({ severity_text: label.toUpperCase(), level: number }),
    // Flatten the error into the OTel exception fields so the record stays one flat line.
    // Handles both a raw Error and the serialized { type, message, stack }.
    log: (obj) => {
      const { err, ...rest } = obj as { err?: Error & { type?: string } }
      if (!err) return rest
      return {
        ...rest,
        'exception.type': err.type ?? err.constructor?.name ?? err.name,
        'exception.message': err.message,
        'exception.stacktrace': err.stack,
      }
    },
  },
}

async function createLogger() {
  if (format === 'json') return pino(json)
  // Dev only. pino-pretty runs as an in-process stream, not a transport, because the
  // messageFormat function that shortens trace_id cannot be passed into a transport worker.
  const { default: pretty } = await import('pino-pretty')
  return pino(common, pretty({
    messageKey: 'body',
    hideObject: true,   // fields are rendered as key=value by messageFormat below
    translateTime: "UTC:yyyy-mm-dd'T'HH:MM:ss.l'Z'",
    ignore: 'pid,hostname',
    messageFormat: (log, key) => {
      const { [key]: msg, level, time, logger: name, trace_id, span_id, trace_flags, 'service.name': svc, err, ...fields } = log
      const kv = Object.entries(fields).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
      const line = [`${name ?? ''} [${String(trace_id ?? '').slice(0, 8)}] ${msg}`, ...kv].join(' ')
      return err ? `${line}\n${(err as { stack?: string }).stack ?? ''}` : line   // stack trace after the line
    },
  }))
}

export const logger = await createLogger()
```

A request to `GET /orders/42` produces, with `LOG_FORMAT=text`:

```text
[2026-10-22T14:03:11.482Z] INFO: OrderService [4bf92f35] order fetched request.id=9d1c0e2a user.id=u-7f3a order.id=42
```

and with `LOG_FORMAT=json`, one line:

```json
{"severity_text":"INFO","level":30,"timestamp":"2026-10-22T14:03:11.482Z","service.name":"orders","request.id":"9d1c0e2a","user.id":"u-7f3a","logger":"OrderService","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","order.id":"42","body":"order fetched"}
```

Key order differs from the JVM output; consumers parse keys, not positions. In this shape, `level` is the one extra key, kept for the instrumentation.

## Child loggers per request

A Nitro middleware runs before every handler, creates the request's child logger, and attaches it to `event.context.logger`. Handlers and services log through that child and never through the module-level `logger`, so `request.id` and `user.id` reach every record without being passed by hand. Middleware runs in filename order, so the numeric prefix puts this one first.

```ts
// server/middleware/00.logger.ts
import { randomUUID } from 'node:crypto'
import type { Logger } from 'pino'
import { logger } from '../utils/logger'

const SAFE_ID = /^[A-Za-z0-9-]{1,64}$/   // an inbound header is untrusted

export default defineEventHandler((event) => {
  const inbound = getRequestHeader(event, 'x-request-id')
  const requestId = inbound && SAFE_ID.test(inbound) ? inbound : randomUUID()
  event.context.logger = logger.child({ 'request.id': requestId })
})

declare module 'h3' {
  interface H3EventContext { logger: Logger }
}
```

Once authentication has resolved the user, add the opaque ID in the auth middleware: `event.context.logger = event.context.logger.child({ 'user.id': user.id })`. Never bind the email.

```ts
// server/routes/orders/[id].get.ts
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')!
  const log = event.context.logger.child({ logger: 'OrderService' })
  const order = await orderService.getOrder(id, log)
  log.info({ 'order.id': id }, 'order fetched')
  await runTask('audit:record', { payload: { id } })
  return order
})
```

Services and clients that run outside a request (`PricingClient` setup, the `AuditJob` task) take a child of the root logger with their own bindings, for example `logger.child({ logger: 'AuditJob', 'order.id': payload.id })`. They get their own context, as SKILL.md's request-scoped rules require.

## Nitro integration

- **Import the logger in server code.** Nitro and Nuxt route `console.*` through consola, the framework's own logger. Its records reach neither pino, the redaction paths, nor the OTel instrumentation, and they carry no `trace_id`. Server code imports `logger` from `server/utils/logger.ts`, or takes `event.context.logger`.
- **Log the exception once, at the boundary.** Nitro's `error` hook is the handling boundary for unhandled request errors. Log there and nowhere upstream, and skip handled 4xx responses so a `GET /orders/404` stays out of `ERROR`:

  ```ts
  // server/plugins/error-logging.ts
  import { logger } from '../utils/logger'

  export default defineNitroPlugin((nitroApp) => {
    nitroApp.hooks.hook('error', (error, { event }) => {
      const status = (error as { statusCode?: number }).statusCode ?? 500
      if (status < 500) return
      // matchedRoute is the route template (/orders/:id), never the raw path with the ID
      ;(event?.context.logger ?? logger).error({ err: error, 'http.route': event?.context.matchedRoute?.path }, 'request failed')
    })
  })
  ```

  Nitro's default error handler also writes 5xx errors through consola, which would make this a second record of the same exception. Set `errorHandler` in the Nitro config to a handler that only builds the error response, so the hook's record is the only one.
- **Presets.** `node-server` runs the setup above unchanged. Edge presets have no worker threads and no `pino-pretty`. Run them with `LOG_FORMAT=json`, and remember that a serverless invocation must flush the OTel side per invocation, as configured by the `opentelemetry` skill.

## Known complexities

- **`console.log` goes to consola, not pino.** A `console.log` in a Nitro route looks like it works in development and loses level, fields, redaction, and correlation everywhere. Treat it as the red flag SKILL.md names.
- **Never use `pino-pretty` in production.** It formats on the event loop in the stream form above. It is a dev dependency, so a production install lacks it, and its output is exactly the multi-line, unparseable shape the pipeline cannot read. The default (`json` when `NODE_ENV=production`) prevents this. Deployments still set `LOG_FORMAT=json` explicitly.
- **Instrumentation load order.** `@opentelemetry/instrumentation-pino` patches pino at import time. If pino is imported before the instrumentation is registered, records have no `trace_id` and never reach the pipeline. Registration order is configured by the `opentelemetry` skill.
- **Custom keys versus the instrumentation.** `messageKey`, the custom `timestamp`, and `formatters` change the record the instrumentation parses when it builds the OTel log record. The numeric `level` is kept for that reason. Confirm severity, body, and timestamp on the pipeline side with the `opentelemetry` skill's correlation test after changing any of them.
- **`formatters.level` and multiple transports.** pino rejects `formatters.level` together with `transport.targets`. The JSON path writes straight to stdout with no transport, which avoids the conflict; keep it that way.
- **Redaction paths are exact.** `*.password` matches one level down, not deeper, and a path such as `user.email` means the nested `user` → `email`, not a literal dotted key. Test any path you add against a real record. Redaction catches mistakes; the review rule on field names in SKILL.md's [Never log](../SKILL.md#never-log) is what prevents them.
- **Top-level `await` in the logger module.** The dev-only dynamic import uses top-level `await`, which Nitro's ESM output supports. A CommonJS build would need the import moved into an async startup step.
- **Platform-specific JSON (ECS, GCP).** This is an override, never the default. Swap the `json` options for the platform's formatter, for example `@elastic/ecs-pino-format`, or a `formatters.level` that emits GCP's `severity`. Keep `trace_id`, `span_id`, and the redaction paths.
