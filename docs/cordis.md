# Cordis as a native MCP consumer

Cordis (formerly Codex Orchestrator) connects through the official SDK to this
gateway's `/mcp` endpoint. MCP One remains the owner of registry/discovery/lifecycle,
transport, routing, circuit policy and telemetry. Cordis owns task contracts, agent
coordination, workflow gates and the selection of permitted capabilities.

Cordis requires explicit endpoint enrollment and exact per-tool grants. It searches
its offline catalog before requesting permitted tool summaries, then loads an
individual schema when needed. It preserves native `content`, `structuredContent`,
`isError` and `_meta`; its separate operation evidence carries only names, timing
and status. It never retries a downstream call automatically.

Use the same endpoint and public protocol as any official SDK client; there is no
Cordis-specific gateway route or dependency. A trusted local manifest can enroll:

```json
{
  "version": 1,
  "servers": {
    "gateway": {
      "url": "http://127.0.0.1:8000/mcp",
      "enabled": true,
      "allow_tools": ["example.echo"],
      "read_only_tools": ["example.echo"]
    }
  }
}
```

Then use `cordis --manifest project.json mcp doctor` and `mcp tools gateway`.
Configure actual downstreams here using the existing public server configuration;
the Cordis manifest cannot create/update gateway configuration. Gateway policies
and least-privilege downstream credentials still apply. Never enroll the Cordis
facade behind the same gateway that Cordis consumes, to avoid call cycles.

Cordis's optional sibling integration test launches this unmodified gateway and a
controlled real native downstream, then verifies an end-to-end SDK call. Set
`CORDIS_MCP_ONE_PYTHON` to this checkout's locked virtualenv Python and execute
`tests/integration/test_mcp_one_native.py` from the Cordis checkout. The test does
not use private repositories, production data or externally installed MCP servers.
