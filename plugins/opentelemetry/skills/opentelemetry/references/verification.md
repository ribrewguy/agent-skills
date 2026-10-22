# Verification

Three layers prove the wiring. The agent runs the first two before reporting done; the third is for humans. This file holds the assertion list and the assets; the stack references hold the runnable test code.

## Three layers

1. **Component tests, in-process.** Fast, no containers. An in-memory span exporter, log record exporter, and metric reader replace the OTLP exporters, and the test drives a request through the real application. Catches broken parentage, lost context, missing correlation, wrong metric attributes.
2. **Integration test, real collector.** One per project. Testcontainers starts the official contrib collector with [assets/collector-test.yaml](../assets/collector-test.yaml); the app is configured only through `OTEL_*` variables pointed at the container. Catches what in-memory exporters cannot: protocol and endpoint mistakes, a signal that is never exported, log records that arrive without the trace ID.
3. **Local compose file, for humans.** [assets/docker-compose.otel.yaml](../assets/docker-compose.otel.yaml). Not a gate.

The stack references carry the templates: the Spring test references for the JVM Micrometer path, the non-Spring JVM reference for the direct SDK path, and the Node references for Nitro.

## Component test assertions

Each assertion maps to an anti-goal. Write one test per line.

- A server span exists for a request; Tier 2 service and repository spans are its descendants in the expected order (repository under service). Anti-goal: broken traces.
- An outbound call made during the request produces a client span, and the receiving side (an in-process stub server) reports a server span with the same trace ID. Anti-goal: broken traces.
- A coroutine or async hop inside the service keeps the parent span. Anti-goal: broken traces.
- A log emitted inside the request carries `trace_id` and `span_id` equal to the active span. Anti-goal: uncorrelated logs.
- The default service metrics `app.service.calls` and `app.service.duration` were recorded with the expected attributes (`code.function.name`, `outcome`). Goal: consistent metrics.
- No span has an `ERROR` status on the happy path, and on the failure path the failing operation's span carries the exception event and `ERROR`. Ancestors the failure propagated out of carry `ERROR` too (an auto-instrumented server span may also record the exception); ancestors that handled it stay `UNSET`. A handled 404 is not an error.
- A background job triggered during the request starts its own trace and carries a span link back to the triggering span.

## Integration test with a real collector

1. Start the collector container with the config from `assets/collector-test.yaml`: OTLP receivers on 4317 (gRPC) and 4318 (HTTP), a `file` exporter writing JSON lines to `/out/telemetry.jsonl`, pipelines for traces, metrics, and logs.
2. Wait for the HTTP receiver port, not a fixed sleep.
3. Start the app with only environment variables: `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT` set to the mapped HTTP port, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_RESOURCE_ATTRIBUTES` carrying `service.version` and `deployment.environment.name`.
4. Make one request that exercises the service, repository, an outbound call, a log line, and a background job.
5. Shut the app down gracefully (this exercises the flush hook), then read the file.
6. Assert that spans, log records, and metrics are all present; that the resource carries the `OTEL_SERVICE_NAME` you set (not `unknown_service`); and that a log record carries the `trace_id` of a span in the same file.

Pin the collector image tag in the project; skills name artifacts, not versions.

Also run the app once with the endpoint pointing at nothing (a closed port). It must start, serve the request within 30 seconds, and log at most one export-failure WARN. An SDK that crashes or blocks the app when the collector is down fails verification.

## Local compose for humans

Copy `assets/docker-compose.otel.yaml` into the project. It runs one `grafana/otel-lgtm` service that accepts OTLP and bundles a viewer. Host ports come from `OTEL_GRPC_PORT`, `OTEL_HTTP_PORT`, and `GRAFANA_PORT` with the standard defaults (4317, 4318, 3000), so a repo that allocates ports per worktree can override them without a second template.

What to look at:

1. Start it, then point the app at it: `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`.
2. Make a request, then open the viewer on the Grafana port and the Explore view for traces. The request should show one trace: server span, service and repository spans, client span, the far-side server span.
3. Open the logs view and filter on the trace ID: the request's log lines appear.
4. Look for `app.service.calls` and `app.service.duration` in the metrics view.

## Checklist before reporting done

- [ ] Every component-test assertion above exists as a passing test.
- [ ] The integration test passes against the real collector container.
- [ ] The no-collector run starts and serves within 30 seconds with at most one export WARN.
- [ ] `service.name` is the configured name, not `unknown_service`; `service.version` and `deployment.environment.name` are present.
- [ ] No endpoint or sampler in code; no vendor SDK imports.
- [ ] Shutdown hook flushes with a bounded timeout (or the handler flushes per invocation on serverless).
- [ ] Denylist grep is clean (see `application-logging`).
- [ ] The compose file is in the repo.
