"""Composition root. The official SDK owns the MCP wire protocol."""

import argparse
import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.server.caching import CacheHint
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams

from mcp_one import __version__
from mcp_one.admin.routes import routes
from mcp_one.application.service import Gateway
from mcp_one.config import GatewayConfig, load_config
from mcp_one.infrastructure.client import SDKClientPool
from mcp_one.observability.http import TraceMiddleware
from mcp_one.observability.metrics import PrometheusMetrics
from mcp_one.observability.telemetry import configure
from mcp_one.transport.security import SecurityMiddleware


def create_app(config: GatewayConfig | None = None) -> SecurityMiddleware:
    config = config or load_config(Path(os.getenv("MCP_ONE_CONFIG", "config.yaml")))
    metrics = PrometheusMetrics()
    gateway = Gateway(config, SDKClientPool(config), metrics)

    @asynccontextmanager
    async def lifespan(server: Server[Any]) -> AsyncIterator[Gateway]:
        telemetry = configure()
        try:
            async with gateway.lifespan():
                yield gateway
        finally:
            await asyncio.to_thread(telemetry.shutdown)

    async def listing(
        ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        if params and params.cursor:
            raise MCPError(-32602, "Invalid catalog cursor")
        snapshot = gateway.registry.snapshot
        tools = [
            route.tool
            for route in snapshot.routes.values()
            if gateway.registry.usable(snapshot.servers[route.server_id])
            and gateway.router.policy.permits(route.upstream_name)
        ]
        # Operational snapshots can outlive downstream hints; advertise zero freshness.
        return ListToolsResult(tools=tools, ttl_ms=0, cache_scope="private")

    async def call(
        ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult:
        return await gateway.router.call(params)

    server: Server[Any] = Server(
        "mcp-one",
        version=__version__,
        instructions="Native MCP tool gateway. Inspect isError and namespaced gateway metadata.",
        on_list_tools=listing,
        on_call_tool=call,
        lifespan=lifespan,
        cache_hints={"server/discover": CacheHint(ttl_ms=0), "tools/list": CacheHint(ttl_ms=0)},
    )
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=config.limits.request_bytes,
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(config.hub.allowed_hosts),
            allowed_origins=list(config.hub.allowed_origins),
        ),
        custom_starlette_routes=routes(gateway, metrics),
    )
    app.state.gateway = gateway
    return SecurityMiddleware(TraceMiddleware(app), config.hub)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path(os.getenv("MCP_ONE_CONFIG", "config.yaml"))
    )
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.schema:
        schema = GatewayConfig.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        print(json.dumps(schema, indent=2))
        return
    config = load_config(args.config)
    if args.check:
        print("Configuration valid")
        return
    uvicorn.run(
        create_app(config),
        host=args.host or config.hub.host,
        port=args.port or config.hub.port,
        access_log=False,
        timeout_graceful_shutdown=15,
    )


if __name__ == "__main__":
    main()
