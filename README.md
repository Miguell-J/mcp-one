# MCP One

A native MCP gateway and control plane. MCP One aggregates tools from independently
operated MCP servers, routes calls, applies policy/timeouts/circuit breaking, and
preserves downstream schemas and results. No domain libraries are imported.

```text
Codex / official MCP client
            |
       MCP One /mcp
       registry + router
            |
     native MCP servers
```

Targets MCP **2026-07-28**, official Python SDK **2.2.0**, Python **3.12–3.14**.
The native API is the proposed 1.0 contract; the current build is a release candidate.
See [migration](docs/migration-to-native-mcp.md) for the breaking change from 0.1 REST.

## Start

```bash
uv sync --locked
# Edit config.yaml to enroll your native downstream /mcp endpoints.
uv run --locked mcp-one --check
uv run --locked mcp-one
```

The default endpoint is `http://127.0.0.1:8000/mcp`. Empty configuration starts a
live gateway with an empty catalog and HTTP 503 readiness. Configuration is trusted
operator input; editing servers requires restart. `POST /refresh` refreshes discovery.

```yaml
servers:
  - id: example
    namespace: example
    transport:
      type: streamable_http
      url: http://127.0.0.1:8080/mcp
    timeout:
      discovery_seconds: 5
      call_seconds: 60
```

```python
import asyncio
from mcp import Client


async def main():
    async with Client("http://127.0.0.1:8000/mcp", cache=None) as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])
        # result = await client.call_tool("example.echo", {"message": "hello"})


asyncio.run(main())
```

For Codex: `codex mcp add mcp-one --url http://127.0.0.1:8000/mcp`.
This is an operator command; no repository script changes your Codex configuration.

## Operations

| Interface | Purpose |
| --- | --- |
| `/mcp` | Native discovery, tools/list, tools/call; SDK-managed compatibility |
| `GET /health` | Process/lifecycle liveness |
| `GET /ready` | Useful permitted routes available; 503 otherwise |
| `GET /status`, `GET /servers` | Administrative catalog, readiness and circuit diagnostics |
| `POST /refresh` | Coalesced administrative discovery refresh |
| `GET /metrics` | Prometheus text, bounded labels |
| `/tools`, `/call` | HTTP 410 migration notice, no execution |

HTTP connections are pooled, while protocol operation contexts are explicit and
short lived. Catalogs and circuits are process-local operational state. Tool
results are never cached. Domain `isError` results never trip the circuit.

```bash
make check                  # Ruff, strict mypy, tests and >=80% coverage
make test-contract test-integration test-e2e
make schema                 # Generate the configuration JSON Schema
uv build --no-sources
docker build --target runtime -t mcp-one:local .
docker compose up --build -d
```

The runtime is non-root, uses locked dependencies and needs no database, Redis,
Docker socket or privileged mode. Only loopback is published in Compose.

## Documentation

[Architecture](docs/architecture.md) · [Configuration](docs/configuration.md) ·
[Routing](docs/routing.md) · [Health](docs/health.md) · [Retries](docs/retries.md) ·
[Circuit breaker](docs/circuit-breaker.md) · [Security](docs/security.md) ·
[Observability](docs/observability.md) · [Migration](docs/migration-to-native-mcp.md) ·
[Scientific stack integration](docs/mcp-stack-integration.md) ·
[Troubleshooting](docs/troubleshooting.md) · [ADRs](docs/adr/0001-native-mcp.md).

[Validation evidence](docs/validation.md) · [Adversarial review](docs/adversarial-review.md).

Tools-only federation is intentional. Resources/artifacts remain opaque references;
resource federation, subscriptions, tasks, sampling, elicitation and multi-round
continuations are not advertised. Local bearer security is available; a public
OAuth deployment requires a separate resource-server integration.
