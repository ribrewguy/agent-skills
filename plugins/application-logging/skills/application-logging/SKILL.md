---
name: application-logging
description: "Use whenever adding, changing, or reviewing logging in any server code, even when the request never says 'logging': wiring a new service, adding error handling, writing a filter or middleware, or reviewing a PR that touches log calls. Covers level meanings, structured fields passed as arguments instead of interpolated, the never-log denylist for credentials, tokens, session IDs and personal data, logging an exception once at the boundary that handles it, the two-appender model (human-readable console plus the OTel pipeline appender), and request-scoped context with trace correlation. Symptoms: values interpolated into messages, the same exception logged at every layer, println or console.log in server code, a token or password in a log line, multi-line records, levels used by mood instead of meaning. Not for log aggregation, collector or backend setup, dashboards, or alerting."
---

# Application Logging

## Overview

A log record has two readers: a human tailing stdout, and a pipeline that parses, indexes, and correlates it with traces. This skill serves both with one rule set and **two appenders**. The **console appender** writes one readable line per event to stdout (or one JSON line when `LOG_FORMAT=json`). The **OTel appender** turns the same call into an OpenTelemetry log record shipped over OTLP with the active trace and span attached. Every log call goes through the logging library; neither appender is optional once the project has OTel, and the console appender is never optional.

This skill owns what is logged, at which level, in which shape, the console appender, and the denylist. The [`opentelemetry`](../../../opentelemetry/skills/opentelemetry/SKILL.md) skill owns the pipeline: the OTel log appender, how records leave the process, and how trace context reaches them. **When both are loaded on a logging question, `application-logging` governs the content of a record and `opentelemetry` governs its transport and correlation fields.**

The skill stands alone. A project without OTel still gets the console appender, the level rules, the field rules, and the denylist; add the pipeline appender through `opentelemetry` when the project needs it. The body is stack-neutral; Logback and pino wiring live in [references/jvm.md](references/jvm.md) and [references/node.md](references/node.md).

## When to use

- Adding logging to a new service, handler, job, or client.
- Adding or changing error handling (every `catch` is a logging decision).
- Writing a filter, interceptor, or middleware that sets per-request context.
- Configuring the logging library or its appenders.
- Reviewing a PR that adds or changes log calls.
- Answering "why is this log line unhelpful" or "why can't the platform parse our logs".
- Symptoms:
  - Values interpolated into the message (`"order " + id + " fetched"`, template strings) instead of passed as fields.
  - The same exception logged by the repository, the service, and the handler.
  - `println`, `System.out`, `printStackTrace`, or `console.log` in server code.
  - A token, password, cookie, or `Authorization` header in a message or field.
  - Multi-line records: a stack trace or pretty-printed JSON spread over several lines.
  - Bespoke level use: `ERROR` for a handled 404, `INFO` for every loop iteration, `WARN` as "important info".
  - A message that says what happened but not to what (`"fetch failed"` with no order ID).

## Level meanings

Levels are a contract with whoever is paged and whoever filters. Use them by meaning, never by mood.

| Level | Meaning | Example |
|---|---|---|
| `ERROR` | A request or job failed and someone may need to act. | `GET /orders/boom` returned 500; `AuditJob.record` gave up after retries. |
| `WARN` | Degraded but handled. | `PricingClient.quote` timed out, served the cached price; a swallowed exception (see [Exception once](#exception-once)). |
| `INFO` | A business-relevant state change, one per unit of work, not per step. | `order fetched` with `order.id`, once per request. |
| `DEBUG` | For developers; off in production. | Cache key computed, branch taken, retry attempt 2 of 3. |
| `TRACE` | Per-item detail inside loops. | Each line item priced inside `OrderService.getOrder`. |

Consequences of the definitions:

- A handled 404 is not an `ERROR`. Nothing failed; the caller asked for something that is not there. Log it at `DEBUG` or not at all; the server span and access log already record it.
- `INFO` budget is one record per unit of work. Three `INFO` lines for one request ("loading", "loaded", "returning") are two too many; demote the steps to `DEBUG`.
- If an `ERROR` would not justify someone looking, it is a `WARN`. If a `WARN` happens on every request, it is not degraded, it is the design; fix it or demote it.

## Field rules

**Pass fields as arguments, never interpolate them into the message.** The message is a stable, human-readable sentence; the fields carry the values. A stable message groups and counts; an interpolated one produces a distinct string per order and defeats every search. Fields become typed record attributes on the pipeline path and `key=value` pairs on the console.

```text
Bad:   log.info("Fetched order " + id + " for user " + userId)
Good:  log.info("order fetched", fields { order.id = id, user.id = userId })
```

The syntax differs per library (SLF4J key-value API, pino's merge object); the shape does not. See the stack references.

**One event per record.** No multi-line messages. Stack traces go in the exception field, which both appenders render appropriately (the console prints the trace after the line; the JSON and OTel paths carry it in one field). Never format a stack trace or a pretty-printed object into the message yourself: a pipeline that splits on newlines turns one event into forty fragments.

**Say what happened and to what.** `"pricing failed"` is useless at 3 a.m.; `"pricing failed"` with `order.id` and `error.type` is a lead.

**A field keeps one type across all records.** `order.id` is always a string, or always a number, never both. Backends index the first type they see and reject or drop the rest.

**Standard fields on every record:**

| Field | Source |
|---|---|
| `timestamp` | Logging library; RFC 3339 with milliseconds and offset, or epoch nanoseconds on the OTel path. |
| `level` | The call (`severity_text` in JSON and OTel). |
| `logger` | The class or module name. |
| `message` | The stable sentence (`body` in JSON and OTel). |
| `trace_id` | Active span, attached by the OTel instrumentation; never set by hand. Absent when no span is active. |
| `span_id` | Active span, attached by the OTel instrumentation; never set by hand. Absent when no span is active. |
| `service.name` | `OTEL_SERVICE_NAME` / resource, the same value spans and metrics carry. |

**Standard names for common values** follow OTel semantic conventions, so logs and spans share one vocabulary and a query on one works on the other:

| Value | Field name | Not |
|---|---|---|
| Opaque user identifier | `user.id` | `userId`, `uid`, `user` |
| HTTP method | `http.request.method` | `method`, `verb` |
| Route template | `http.route` | `path`, `url` (and never the raw URL with IDs and query string) |
| Exception class or error code | `error.type` | `errorClass`, `err` |

Domain fields use the same dotted lowercase style: `order.id`, `pricing.currency`.

## Never log

These never appear in a message or a field, at any level, in any environment:

| Never | Log instead |
|---|---|
| Credentials (passwords, API keys, client secrets, private keys) | Nothing, or which credential was used by name (`pricing.client = default`). |
| Tokens (bearer, refresh, reset, signed URLs, JWTs) | Nothing; at most the token's type or expiry. |
| Session IDs, cookies, `Authorization` headers | Nothing; `user.id` once the session is resolved. |
| Full request or response bodies | The IDs and counts that matter (`order.id`, `line_items = 3`). |
| Card numbers | Nothing; the payment or order ID. |
| Personal data beyond an opaque user ID (email, name, phone, address, IP, date of birth) | `user.id`. |

**Review-failure rule:** any new field name containing `password`, `token`, `secret`, `authorization`, or `cookie` (case-insensitive, anywhere in the name) is a review failure, whatever the value claims to be. `token_count` and `has_cookie` get renamed; the rule is mechanical so nobody argues about which ones are safe. The same words appearing in a message string get the same scrutiny.

DEBUG is not an exemption. Debug logging gets switched on in production during an incident, which is exactly when the denylisted value leaks.

## Exception once

**Log an exception once, at the boundary that handles it.** The handling boundary is the place that turns the failure into an outcome: the HTTP error handler that returns 500, the job runner that marks the job failed, the consumer that dead-letters the message.

- **Layers that rethrow do not log.** `OrderRepository` throws, `OrderService` wraps and rethrows, the handler logs once. Logging at each layer turns one failure into three `ERROR` records, triples the alert count, and hides which layer actually decided the outcome. Add context by wrapping the exception (with `order.id` in the message or cause), not by logging it.
- **Layers that swallow must log at `WARN` or higher with the reason.** A `catch` that returns a fallback is the handling boundary for that failure, so it owns the record: `"pricing unavailable, using cached price"` at `WARN` with `order.id` and `error.type`. A silent swallow is a bug report that nobody will ever read.
- **The record carries the exception object**, not `e.message` concatenated into the text, so the stack trace lands in the exception field and `error.type` is set.

## Two appenders

**Console appender, for humans.** Single-line pattern on stdout, in this order: timestamp, level, logger, message, short trace ID, key-value fields. Dev default.

```text
2026-10-22T14:03:11.482Z INFO  OrderService [4bf92f35] order fetched order.id=42 user.id=u-7f3a
```

The short trace ID is a prefix of `trace_id` (the first 8 hex characters), enough to grep for the full trace; the slot is empty when no span is active.

**`LOG_FORMAT=json`** switches the same console appender to one-line JSON, for platforms that scrape stdout. This is a deployment choice, not the OTel path. The shape mirrors the OTel log data model: a flat object, `timestamp` in RFC 3339, `severity_text`, `body`, `trace_id`, `span_id`, `service.name`, `logger`, and every structured argument as a top-level key.

```json
{"timestamp":"2026-10-22T14:03:11.482Z","severity_text":"INFO","body":"order fetched","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","service.name":"orders","logger":"OrderService","order.id":"42","user.id":"u-7f3a"}
```

Exceptions in JSON go in `exception.type`, `exception.message`, and `exception.stacktrace`, the stack trace as one escaped string so the record stays one line. Platform-specific shapes (ECS, GCP) are a documented override in the stack reference, never the default.

**OTel appender, for the pipeline.** Each log call becomes an OTel log record over OTLP. The appender attaches the active trace and span context; structured key-value arguments become record attributes. On the JVM this is the OTel Logback appender; on Node it is pino with the OTel pino instrumentation. Its configuration, export, and correlation belong to [`opentelemetry`](../../../opentelemetry/skills/opentelemetry/SKILL.md).

The two appenders are fed by the same log call. Never write a second log statement for the pipeline, and never hand-build JSON strings for either appender: the library renders fields; code only passes them.

## Request-scoped context

Values that belong to every record in a request (`user.id`, `request.id`, tenant) are **set once in a filter or middleware and inherited**, never passed to each log call by hand.

- **JVM, thread-per-request (servlet):** put them in the MDC in a servlet filter and clear them in a `finally`. A pooled thread that keeps the last request's MDC attributes the next request's records to the wrong user.
- **JVM, reactive (WebFlux):** do not use MDC plus `finally` in a WebFilter. The `finally` runs as soon as the `Mono` is assembled, before the request executes, and reactive operators hop threads anyway. Write the values into the Reactor Context in the WebFilter; context propagation copies them into the MDC around each log call. Wiring is in [references/jvm.md](references/jvm.md).
- **Node (pino):** create a child logger per request with the fields bound, and hand that child down through the request context, not a module-level logger.

Rules:

- Set context at the outermost point where the value is known: `request.id` at entry, `user.id` right after authentication resolves it.
- `trace_id` and `span_id` are not request-scoped context you manage. The OTel instrumentation attaches them; hand-copying them into MDC or a child logger goes stale when a child span starts.
- Outside the request's own pipeline, context still does not cross async hops by itself. Coroutines, executors, and background jobs need the propagation the stack reference describes; a background job such as `AuditJob.record` gets its own context, with the triggering `order.id` as a field.
- Request-scoped fields obey [Never log](#never-log): the tenant and `user.id` are opaque identifiers, never an email.

## Red flags

- `println`, `System.out`, `System.err`, `printStackTrace()`, or `console.log`/`console.error` in server code. Bypasses levels, fields, both appenders, and correlation.
- String concatenation, template literals, or `String.format` building a log message that contains variable values.
- The same exception logged in two or more layers of one call path.
- An empty `catch`, or a `catch` that swallows and logs below `WARN` or without a reason.
- `log.error(e.getMessage())` or `logger.error(err.message)`: the stack trace and type are discarded.
- A field or message containing a password, token, secret, `Authorization` header, cookie, session ID, card number, email, or full request body.
- A new field name containing `password`, `token`, `secret`, `authorization`, or `cookie`.
- Multi-line messages, or objects pretty-printed into the message.
- A hand-built JSON string passed as the message.
- `ERROR` for a handled 404 or a validation failure; `INFO` inside a loop; `WARN` on every request.
- A field that is a number on some lines and a string on others.
- camelCase or ad-hoc names where a semantic-convention name exists (`userId` for `user.id`, `path` for `http.route`).
- `trace_id` copied into MDC or a child logger by hand.
- MDC set in a filter and never cleared.
- A message that names the event but not the entity (`"update failed"` with no ID).
- A second log statement written only to feed the pipeline.

## Common rationalizations

| Rationalization | Reality |
|---|---|
| "Interpolating is more readable." | It reads the same on the console, where fields print as `key=value`, and it is unsearchable everywhere else. The stable message is what you group and alert on. |
| "Logging at every layer means we never miss it." | You never miss it with one log at the boundary either; you just stop paging three times for one failure and stop guessing which layer decided the outcome. |
| "It's only at DEBUG, it's fine to log the token." | DEBUG gets enabled in production during incidents. The denylist has no level exemption. |
| "`console.log` is fine for now, we'll switch later." | Later is after the incident where those lines had no level, no trace ID, and never reached the pipeline. The logger costs one import today. |
| "We'll log the whole request body so we have everything." | You will have every password, card number, and email ever posted. Log the IDs that let you find the rest. |
| "It's `token_count`, not a token." | The rule is mechanical so nobody has to judge. Rename it for what it counts; a rename costs nothing, a judgment call costs a leak. |
| "ERROR is for anything that went wrong, including the 404." | ERROR means someone may need to act. A missing order is a normal answer; at ERROR it trains everyone to ignore ERROR. |
| "We have OTel now, so we don't need the console appender." | Humans still tail stdout locally and in containers, and the pipeline can be down. The console appender is the one that always works. |
| "Pretty-printing the object makes it easier to read." | On the console for one line, maybe; on the pipeline it is twenty records with no level. Pass the fields. |
| "Swallowing this exception is fine, it's expected." | Then the swallow is the handling boundary; log it once at WARN with the reason, or the next unexpected cause is invisible. |

## Verification

Before reporting logging work done:

**Content**
- [ ] No variable values interpolated into messages; every value is a field.
- [ ] Every message names the event and its fields name the entity (`order.id`, `user.id`).
- [ ] Levels match [Level meanings](#level-meanings): one `INFO` per unit of work, no `ERROR` for handled outcomes, nothing per-item above `TRACE`.
- [ ] Each exception is logged once, at the boundary that handles it; rethrowers do not log; swallowers log at `WARN`+ with a reason and the exception object.
- [ ] Field names use the standard and semantic-convention names; each field has one type.

**Safety**
- [ ] Denylist grep is clean, run over changed source and over captured log output from a test run:

```bash
grep -rniE '(log|logger|mdc)[^;]*(password|passwd|token|secret|authorization|cookie|session)' src/
```

- [ ] No new field name contains `password`, `token`, `secret`, `authorization`, or `cookie`.
- [ ] No full request bodies, emails, card numbers, or session IDs in any field.

**Shape**
- [ ] No `println`, `System.out`, `printStackTrace`, or `console.log` in server code.
- [ ] Console appender readable: one line per event, timestamp, level, logger, message, short trace ID, fields.
- [ ] `LOG_FORMAT=json` produces one-line JSON with `timestamp` (RFC 3339), `severity_text`, `body`, `trace_id`, `span_id`, `service.name`, and fields as top-level keys; a thrown exception still yields one line.
- [ ] Request-scoped context is set once in a filter or middleware and cleared or scoped per request.

**Pipeline (when the project has OTel)**
- [ ] The OTel log appender is on and fed by the same log calls.
- [ ] A record emitted inside a request carries `trace_id` and `span_id` equal to the active span. The test that proves it is in `opentelemetry`'s verification layer.

## How to present findings

When this skill drives an audit, review, or design answer, three guardrails apply:

1. **Don't cite this skill in the output.** Argue from consequences in your own voice: "this logs the bearer token on every 401" beats "the skill's denylist forbids tokens".
2. **Stay in lane: record content, level, shape, the console appender, the denylist.** Exporter setup, propagation, span coverage, and correlation wiring belong to `opentelemetry`; log aggregation, retention, dashboards, and alerting are out of scope. Name an out-of-lane issue in one sentence and defer.
3. **Tag every finding with severity** so the reader can triage down the left margin.

For the canonical findings format (preamble, severity-tagged findings with file:line citations, source of truth per finding, a formal answer even with no findings), compose with [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md). That skill governs how to present; this one governs what to flag.

Severity ladder, shared with `opentelemetry`:

| Severity | Criterion | Logging examples |
|---|---|---|
| **Critical** | Secrets or PII in logs; context lost across a process boundary. | Token, password, cookie, card number, email, or full body in a record; a new field named `*token*`. |
| **High** | Tier 1 or Tier 2 span missing; log without trace context; metric with an ID attribute. | `println` / `console.log` in server code; a record emitted under an active span without `trace_id` and `span_id`; multi-line records on the pipeline path. |
| **Medium** | Naming or unit convention miss; exception logged at multiple layers; missing resource attribute. | Same exception logged per layer; interpolated fields; non-semconv field names; a swallowed exception with no `WARN`; a field that changes type. |
| **Low** | Level nit; message wording. | `INFO` that should be `DEBUG`; a message that could name its entity more clearly. |

## See also

- [`opentelemetry`](../../../opentelemetry/skills/opentelemetry/SKILL.md): owns the pipeline log appender, export, and the `trace_id` / `span_id` correlation this skill relies on.
- [references/jvm.md](references/jvm.md): Logback with both appenders, MDC setup, the Spring Boot profile switch for `LOG_FORMAT`.
- [references/node.md](references/node.md): pino with `pino-pretty` in dev and JSON in prod, child loggers per request, Nitro integration.
- [`structured-code-review`](../../../structured-code-review/skills/structured-code-review/SKILL.md): the findings format this skill's reviews compose with.
