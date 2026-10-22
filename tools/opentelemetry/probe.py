"""Pure checks over the collector file exporter's OTLP JSON lines. No Docker."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

KINDS = {0: "UNSPECIFIED", 1: "INTERNAL", 2: "SERVER", 3: "CLIENT", 4: "PRODUCER", 5: "CONSUMER"}
STATUSES = {0: "UNSET", 1: "OK", 2: "ERROR"}


@dataclass
class Telemetry:
    spans: list[dict] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)


def _value(v: dict):
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in v:
            return v[key]
    if "arrayValue" in v:
        return [_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _attrs(items) -> dict:
    return {a["key"]: _value(a.get("value", {})) for a in items or []}


def _enum(value, table, prefix):
    if isinstance(value, int):
        return table.get(value, str(value))
    if isinstance(value, str):
        return value.removeprefix(prefix)
    return table[0]


def parse(path: Path) -> Telemetry:
    t = Telemetry()
    path = Path(path)
    if not path.exists():
        return t
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        for rs in doc.get("resourceSpans", []):
            res = _attrs(rs.get("resource", {}).get("attributes"))
            for ss in rs.get("scopeSpans", []):
                for s in ss.get("spans", []):
                    t.spans.append({
                        "name": s.get("name", ""),
                        "kind": _enum(s.get("kind", 0), KINDS, "SPAN_KIND_"),
                        "trace_id": s.get("traceId", ""),
                        "span_id": s.get("spanId", ""),
                        "parent_span_id": s.get("parentSpanId", ""),
                        "status": _enum(s.get("status", {}).get("code", 0), STATUSES, "STATUS_CODE_"),
                        "attributes": _attrs(s.get("attributes")),
                        "links": [{"trace_id": l.get("traceId", ""), "span_id": l.get("spanId", "")} for l in s.get("links", [])],
                        "events": [e.get("name", "") for e in s.get("events", [])],
                        "resource": res,
                    })
        for rl in doc.get("resourceLogs", []):
            res = _attrs(rl.get("resource", {}).get("attributes"))
            for sl in rl.get("scopeLogs", []):
                for r in sl.get("logRecords", []):
                    t.logs.append({
                        "name": str(_value(r.get("body", {}))),
                        "kind": "LOG",
                        "trace_id": r.get("traceId", ""),
                        "span_id": r.get("spanId", ""),
                        "parent_span_id": "",
                        "status": r.get("severityText", ""),
                        "attributes": _attrs(r.get("attributes")),
                        "links": [],
                        "resource": res,
                    })
        for rm in doc.get("resourceMetrics", []):
            res = _attrs(rm.get("resource", {}).get("attributes"))
            for sm in rm.get("scopeMetrics", []):
                for m in sm.get("metrics", []):
                    for kind in ("sum", "gauge", "histogram", "exponentialHistogram", "summary"):
                        for dp in m.get(kind, {}).get("dataPoints", []):
                            t.metrics.append({
                                "name": m.get("name", ""),
                                "kind": kind.upper(),
                                "trace_id": "", "span_id": "", "parent_span_id": "", "status": "",
                                "attributes": _attrs(dp.get("attributes")),
                                "links": [],
                                "resource": res,
                            })
    return t


def _route(span: dict) -> str:
    a = span["attributes"]
    parts = [span["name"]] + [str(a.get(k, "")) for k in ("http.route", "url.path", "http.target", "uri", "http.url", "url.full")]
    return " ".join(parts)


def _ancestors(span: dict, by_id: dict) -> list[dict]:
    out, seen = [], set()
    cur = span
    while cur["parent_span_id"] and cur["parent_span_id"] in by_id and cur["parent_span_id"] not in seen:
        seen.add(cur["parent_span_id"])
        cur = by_id[cur["parent_span_id"]]
        out.append(cur)
    return out


def _server(spans, marker):
    return [s for s in spans if s["kind"] == "SERVER" and marker in _route(s)]


def check(t: Telemetry, service_name: str) -> list[tuple[str, bool, str]]:
    by_id = {s["span_id"]: s for s in t.spans}
    traces: dict[str, list[dict]] = {}
    for s in t.spans:
        traces.setdefault(s["trace_id"], []).append(s)

    error_traces = {tid for tid, ss in traces.items() if any(s["status"] == "ERROR" for s in ss)}
    happy_id = next(
        (tid for tid, ss in traces.items()
         if _server(ss, "/orders/") and _server(ss, "/pricing/") and tid not in error_traces),
        None,
    ) or next(
        (tid for tid, ss in traces.items() if _server(ss, "/orders/") and _server(ss, "/pricing/")), None
    )
    happy = traces.get(happy_id, [])
    orders_server = (_server(happy, "/orders/") or [None])[0]
    out: list[tuple[str, bool, str]] = []

    # server-spans-same-trace
    if happy_id:
        out.append(("server-spans-same-trace", True, f"orders and pricing server spans share trace {happy_id}"))
    else:
        orders_any = any(_server(ss, "/orders/") for ss in traces.values())
        pricing_any = any(_server(ss, "/pricing/") for ss in traces.values())
        out.append(("server-spans-same-trace", False,
                    f"no trace holds both server spans (orders server span seen: {orders_any}, pricing: {pricing_any}, spans: {len(t.spans)})"))

    # client-span-under-server
    clients = [s for s in happy if s["kind"] == "CLIENT"]
    ok = bool(orders_server) and any(orders_server["span_id"] in {a["span_id"] for a in _ancestors(c, by_id)} for c in clients)
    out.append(("client-span-under-server", ok,
                "client span descends from the orders server span" if ok else f"{len(clients)} client span(s) in the request trace, none under the orders server span"))

    # tier2-spans
    svc = [s for s in happy if s["name"] == "OrderService.getOrder"]
    repo = [s for s in happy if s["name"] == "OrderRepository.findById"]
    ok = False
    detail = f"missing spans (service: {len(svc)}, repository: {len(repo)})"
    if svc and repo and orders_server:
        s, r = svc[0], repo[0]
        under_server = all(orders_server["span_id"] in {a["span_id"] for a in _ancestors(x, by_id)} for x in (s, r))
        repo_under_service = s["span_id"] in {a["span_id"] for a in _ancestors(r, by_id)}
        named = bool(s["attributes"].get("code.function.name")) and bool(r["attributes"].get("code.function.name"))
        ok = under_server and repo_under_service and named
        detail = f"under_server={under_server} repo_under_service={repo_under_service} code.function.name_set={named}"
    out.append(("tier2-spans", ok, detail))

    # job-root-with-link
    ok, detail = False, "no AuditJob.record span"
    happy_ids = {s["span_id"] for s in happy}
    for j in (s for s in t.spans if s["name"] == "AuditJob.record"):
        linked = any(l["trace_id"] == happy_id and l["span_id"] in happy_ids for l in j["links"])
        if j["trace_id"] != happy_id and not j["parent_span_id"] and linked:
            ok, detail = True, "AuditJob.record is a root span in its own trace and links to the request"
            break
        detail = (f"AuditJob.record found but trace_differs={j['trace_id'] != happy_id} "
                  f"root={not j['parent_span_id']} linked_to_request={linked}")
    out.append(("job-root-with-link", ok, detail))

    # log-correlated
    logs = [l for l in t.logs if l["name"] == "order fetched" and str(l["attributes"].get("order.id")) == "42"]
    ok = bool(logs) and bool(happy_id) and any(l["trace_id"] == happy_id and l["span_id"] in happy_ids for l in logs)
    out.append(("log-correlated", ok,
                "order fetched log carries the request trace and a span id from it" if ok
                else f"{len(logs)} matching log(s); trace ids: {[l['trace_id'] for l in logs]}"))

    # default-metrics
    names = {m["name"] for m in t.metrics if m["attributes"].get("code.function.name") == "getOrder"}
    ok = {"app.service.calls", "app.service.duration"} <= names
    out.append(("default-metrics", ok,
                "both default metrics present with code.function.name=getOrder" if ok
                else f"metrics with code.function.name=getOrder: {sorted(names)}"))

    # resource-service-name
    resources = [s["resource"] for s in t.spans] + [l["resource"] for l in t.logs] + [m["resource"] for m in t.metrics]
    seen = sorted({str(r.get("service.name")) for r in resources})
    ok = bool(resources) and seen == [service_name]
    out.append(("resource-service-name", ok, f"service.name values seen: {seen or 'none'}"))

    # no-error-on-happy-path
    ok = bool(happy_id) and happy_id not in error_traces and len(error_traces) <= 1
    out.append(("no-error-on-happy-path", ok,
                "request and 404 traces carry no ERROR span" if ok
                else f"happy trace found={bool(happy_id)}, traces with ERROR spans={len(error_traces)}"))

    # error-on-boom
    ok, detail = False, f"expected exactly one trace with ERROR spans, found {len(error_traces)}"
    if len(error_traces) == 1:
        ss = traces[next(iter(error_traces))]
        server = _server(ss, "/orders/")
        service = [s for s in ss if s["name"] == "OrderService.getOrder"]
        exceptions = sum(s["events"].count("exception") for s in ss if s["kind"] != "SERVER")
        server_err = bool(server) and server[0]["status"] == "ERROR"
        service_err = bool(service) and service[0]["status"] == "ERROR"
        ok = server_err and service_err and exceptions == 1
        detail = f"server_error={server_err} service_error={service_err} non-server exception events={exceptions}"
    out.append(("error-on-boom", ok, detail))
    return out
