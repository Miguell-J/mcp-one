# Observability

Every known routed call produces a JSON `gateway_call` event with requestId (UUID),
server, upstream tool, durationMs, actual attempts, cached=false, route generation,
outcome, isError, traceId and spanId. Unknown calls use a stable metric label and
carry a correlation ID in their SDK protocol error. No input/output bodies, raw
exception messages, tokens or arbitrary user identifiers are logged.

The official SDK emits MCP client/server OpenTelemetry spans and propagates W3C
Trace Context through MCP `_meta`. HTTP ingress also extracts `traceparent` and
`tracestate` using OpenTelemetry; an explicit valid MCP trace context takes precedence
inside the SDK. The router adds an `mcp_one.route` span; its downstream SDK calls
inherit that context. Namespaced gateway metadata correlates the trace and request
without changing downstream scientific provenance or reserved protocol metadata.
An existing gateway key is preserved by adding a numbered hop key.

A TracerProvider supplies trace IDs even without export. Set
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` to enable a bounded batch HTTP exporter;
unset means no telemetry export. Shutdown drains the exporter and closes its worker.
The standalone process owns one telemetry lifecycle. No tracing collector
is required to route calls. The scientific stack optionally provides one.

`GET /metrics` returns real Prometheus text with the correct content type:

- mcp_one_tool_calls_total by configured server and bounded outcome, including domain_error.
- mcp_one_tool_latency_seconds histogram.
- mcp_one_infra_failures_total and mcp_one_timeouts_total by stable error code.
- mcp_one_circuit_opens_total and mcp_one_circuit_open gauge.
- mcp_one_registry_refresh_total and mcp_one_registry_refresh_seconds.
- mcp_one_health_probes_total and mcp_one_server_health.
- mcp_one_catalog_tools and mcp_one_catalog_bytes.
- mcp_one_catalog_cache_total by hit/miss for refresh coalescing.

No label contains tool arguments, user IDs, request IDs, tokens or arbitrary tool
names. Configured server count and fixed outcome vocabulary bound cardinality.
Result-cache metrics are absent because no result-cache mechanism exists.
Administrative diagnostics are snapshots, not network probes at scrape time.
