# Troubleshooting

| Symptom | Action |
| --- | --- |
| /ready is 503, /health is 200 | Inspect /status; configure at least one available, permitted tool |
| TOOL_NOT_FOUND | Refresh discovery; inspect namespace/original name; invalid catalogs are withdrawn |
| AUTH_FAILED | Check the configured environment reference; upstream/admin/downstream credentials are separate |
| CALL_TIMEOUT / CONNECT_TIMEOUT | Check the relevant budget and downstream state; execution outcome may be unknown |
| CIRCUIT_OPEN | Wait reset_seconds; one call will probe; discovery alone does not close the circuit |
| DOWNSTREAM_PROTOCOL_ERROR | Check downstream SDK/schema/catalog; logs intentionally omit returned payloads |
| Catalog becomes stale | Inspect refresh error and downstream availability; last good routes have an explicit expiry |
| Host/Origin rejected | Use a configured local hostname/origin; do not disable rebinding protection |
| HTTP 410 on /call or /tools | Migrate to an official MCP client and /mcp |
| No result-cache hits | Result caching does not exist; only catalog refresh is cached/coalesced |
| Configuration rejected | Use --check and generated JSON Schema; unknown old REST fields are errors |
| Integration tests cannot bind | Grant loopback/process permissions to the test environment |
| Old default branch does not import | Use the native ref; the historical merge damage is removed in the rewrite |

For recovery checks run make test-integration. Fault fixtures run in private test
processes and restore/terminate them in finally blocks. Never inject faults into
unrelated downstream workloads. Readiness degradation should not restart a live
hub; keep liveness and readiness probes separate.
