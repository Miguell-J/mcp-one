# Configuration

`config.yaml` is loaded once at startup, bounded to 1 MiB and validated by frozen
Pydantic models with unknown fields rejected. Secrets are environment references.
The generated [JSON Schema](config.schema.json) lists every field, default and
bound. Generate it with `make schema`; CI checks drift. Validate an operator file
with `mcp-one --config path.yaml --check`. Generate schema with `mcp-one --schema`.

```yaml
version: 1
hub:
  host: 127.0.0.1
  port: 8000
  minimum_ready_servers: 1
  auth: {bearer_token_env: MCP_ONE_TOKEN}
  admin_auth: {bearer_token_env: MCP_ONE_ADMIN_TOKEN}
registry:
  refresh_interval_seconds: 30
  minimum_refresh_seconds: 1
  stale_seconds: 300
  max_tools: 1024
  max_pages: 100
  max_catalog_bytes: 8388608
defaults:
  timeout: {connect_seconds: 3, discovery_seconds: 10, call_seconds: 60, health_seconds: 3}
  retry: {discovery_attempts: 3, health_attempts: 1, call_attempts: 1}
  circuit_breaker: {enabled: true, failure_threshold: 5, reset_seconds: 30}
  health: {interval_seconds: 30}
policy:
  allow: ['*']
  deny: ['example.delete_*']
servers:
  - id: example
    display_name: Example server
    namespace: example
    enabled: true
    transport: {type: streamable_http, url: 'http://example:8080/mcp'}
    timeout: {call_seconds: 120}
    auth: {bearer_token_env: EXAMPLE_TOKEN}
```

Nested timeout/retry/circuit/health overrides merge over global defaults. Server
IDs and namespaces must be unique, including disabled entries. IDs/namespaces
use lowercase ASCII identifiers up to 40 characters. Display names never route.
Streamable HTTP is the supported downstream transport. No `/health` endpoint is
required downstream; health uses native server discovery through the SDK.

Request limit defaults to 1 MiB; response limit 8 MiB; each schema 128 KiB with
depth 32; active routed calls 64. The schema documents upper bounds. Catalogs
that exceed bounds are rejected explicitly, never silently truncated. The active
call cap rejects overload immediately instead of allocating an unbounded queue.
Connect/discovery/call/health budgets are separate. The call budget is per attempt;
explicit retries add their budgets and backoff. Client outer deadlines should
cover the desired end-to-end budget.

`--host` and `--port` override the listener only. Containers bind 0.0.0.0 internally;
Compose publishes only 127.0.0.1. Add trusted names to `hub.allowed_hosts` and
browser origins to `hub.allowed_origins` explicitly; SDK rebinding checks stay on.
Configuration is code: add/remove/disable servers and restart. `POST /refresh`
refreshes discovery for the current configuration; it does not reread YAML.
