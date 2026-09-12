# Migration from REST 0.1 to native MCP 1.0

This is a deliberate breaking protocol and packaging change. The earlier software
version was 0.1.0; there was no existing 1.x release/tag to preserve. The new native
API is proposed as 1.0 after validation; pre-release builds remain release candidates.
The broken default-branch revision and the legacy Phase 4 behavior are recorded in
the mcp-stack historical audit, not retained as duplicate executable code.

| Old | New |
| --- | --- |
| src/config.yaml | config.yaml, or MCP_ONE_CONFIG / --config |
| servers[].name | stable servers[].id and explicit namespace |
| servers[].url + endpoint maps | transport.type=streamable_http, transport.url ending at native endpoint |
| endpoints, response_map, payload_map | removed; SDK MCP discovery/results |
| timeout | connect/discovery/call/health seconds |
| retry_attempts (health) | separate discovery_attempts, health_attempts, call_attempts |
| circuit_breaker_failures/reset | circuit_breaker.failure_threshold/reset_seconds |
| inline api_key/bearer_token | hub.auth.bearer_token_env; separate hub.admin_auth |
| configurable but unimplemented cache | removed; catalog snapshot only, no result cache |
| per-IP legacy rate_limit | active-call admission bound; no false distributed-rate-limit claim |
| GET /tools | native tools/list on /mcp |
| POST /call {tool, arguments} | native tools/call {name, arguments} via SDK |
| success/result/error envelope | full native CallToolResult |
| POST /servers/refresh | administrative POST /refresh |
| JSON /metrics | Prometheus text /metrics |
| app.main:app | mcp_one.server:create_app --factory or mcp-one CLI |

Example old server `name: demo, url: http://bridge:8080` becomes:

```yaml
servers:
  - id: backend
    namespace: demo
    transport: {type: streamable_http, url: 'http://backend:8080/mcp'}
```

There is no generic way to infer a native endpoint from arbitrary old REST mappings.
The operator must enroll the actual native server and verify its catalog. Unknown
legacy YAML fields fail validation rather than being silently ignored. GET /tools
and POST /call return HTTP 410 with a migration notice; they do not execute tools.
The tombstones are retained for the 1.x migration and may be removed in 2.0.
Administrative /servers and /status remain, with documented new response shapes.

Upgrade procedure: install locked dependencies; translate config; run --check;
start on an alternate loopback port; compare schemas and results with a real SDK
client; update clients to /mcp; then switch the listener. Keep the old deployment
separately for rollback if needed. SDK-managed legacy MCP handshakes remain
available; arbitrary legacy REST execution is no longer supported.

For mcp-stack, update its immutable upstream commit only after native protocol,
scientific transparency and Docker validation. Bootstrap verifies official origin,
clean working tree and exact commit. Render native endpoints, remove gateway-edge
and legacy-bridge from Compose, and point Codex directly to MCP One /mcp. Scientific
contracts and domain libraries require no changes.
