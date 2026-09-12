"""Official SDK operations over reusable bounded HTTP pools.

The SDK owns discovery, negotiation, JSON-RPC, tracing and HTTP framing. The
public typed send_request path avoids Client.call_tool's automatic multi-round
execution and implicit tools/list after successful calls. The registry owns the
validated tool snapshot, so output validation happens in the application layer.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

import httpx2
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.inbound import mcp_param_headers, x_mcp_header_map
from mcp.types import CallToolRequest, CallToolRequestParams, CallToolResult

from mcp_one.config import GatewayConfig, ServerConfig
from mcp_one.domain.errors import ErrorCode, GatewayError
from mcp_one.domain.models import Discovery, ToolRoute

_parameter_headers: ContextVar[dict[str, str] | None] = ContextVar(
    "mcp_parameter_headers", default=None
)


def classify(error: Exception) -> GatewayError:
    if isinstance(error, GatewayError):
        return error
    if isinstance(error, ExceptionGroup):
        children = [classify(child) for child in error.exceptions]
        return next((e for e in children if e.retryable), children[0])
    if isinstance(error, httpx2.ConnectTimeout):
        return GatewayError(ErrorCode.CONNECT_TIMEOUT, infrastructure=True, retryable=True)
    if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
        return GatewayError(ErrorCode.CALL_TIMEOUT, infrastructure=True, retryable=True)
    if isinstance(error, httpx2.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return GatewayError(ErrorCode.AUTH_FAILED)
        if error.response.status_code >= 500:
            return GatewayError(ErrorCode.SERVER_UNAVAILABLE, infrastructure=True, retryable=True)
        return GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)
    if isinstance(error, (httpx2.TransportError, ConnectionError, OSError)):
        return GatewayError(ErrorCode.SERVER_UNAVAILABLE, infrastructure=True, retryable=True)
    if isinstance(error, MCPError):
        if error.code in {-32600, -32601, -32602}:
            return GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR)
        if error.code == -32001:
            return GatewayError(ErrorCode.CALL_TIMEOUT, infrastructure=True, retryable=True)
        if error.code == -32000:
            return GatewayError(ErrorCode.SERVER_UNAVAILABLE, infrastructure=True, retryable=True)
    return GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)


def bearer_headers(env: str | None) -> dict[str, str]:
    if env is None:
        return {}
    token = os.environ.get(env)
    if not token:
        raise GatewayError(ErrorCode.AUTH_FAILED)
    return {"Authorization": "Bearer " + token}


class LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, stream: httpx2.AsyncByteStream, limit: int):
        self.stream, self.limit = stream, limit

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > self.limit:
                raise GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


class LimitedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, limit: int, connections: int):
        self.limit = limit
        self.transport = httpx2.AsyncHTTPTransport(
            retries=0,
            limits=httpx2.Limits(max_connections=connections),
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self.transport.handle_async_request(request)
        # Retain HTTP failure categories before SDK fallback folds non-RPC bodies
        # into INTERNAL_ERROR. No response body or MCP framing is interpreted here.
        if response.status_code in {401, 403}:
            await response.aclose()
            raise GatewayError(ErrorCode.AUTH_FAILED)
        if response.status_code >= 500:
            await response.aclose()
            raise GatewayError(ErrorCode.SERVER_UNAVAILABLE, infrastructure=True, retryable=True)
        if response.is_redirect:
            await response.aclose()
            raise GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)
        if response.headers.get("content-encoding", "identity") != "identity":
            await response.aclose()
            raise GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)
        assert isinstance(response.stream, httpx2.AsyncByteStream)
        response.stream = LimitedStream(response.stream, self.limit)
        return response

    async def aclose(self) -> None:
        await self.transport.aclose()


class SDKClientPool:
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.clients: dict[str, httpx2.AsyncClient] = {}

    def _http(self, server: ServerConfig) -> httpx2.AsyncClient:
        if server.id not in self.clients:

            async def headers(request: httpx2.Request) -> None:
                # Per-operation context; never mutate shared client headers during a call.
                request.headers.pop("cookie", None)
                request.headers.update(bearer_headers(server.auth.bearer_token_env))
                if request.headers.get("mcp-method") == "tools/call":
                    request.headers.update(_parameter_headers.get() or {})

            async def discard_cookies(response: httpx2.Response) -> None:
                # HTTP pooling must not create implicit semantic sessions across callers.
                self.clients[server.id].cookies.clear()

            self.clients[server.id] = httpx2.AsyncClient(
                transport=LimitedTransport(
                    self.config.limits.response_bytes,
                    self.config.limits.concurrent_calls,
                ),
                timeout=httpx2.Timeout(
                    max(server.timeout.call_seconds, server.timeout.discovery_seconds),
                    connect=server.timeout.connect_seconds,
                ),
                headers={"Accept-Encoding": "identity"},
                event_hooks={"request": [headers], "response": [discard_cookies]},
                trust_env=False,
                follow_redirects=False,
            )
        return self.clients[server.id]

    @asynccontextmanager
    async def _client(
        self,
        server: ServerConfig,
        seconds: float,
        discovery: Discovery | None = None,
    ) -> AsyncIterator[Client]:
        try:
            async with asyncio.timeout(seconds):
                async with Client(
                    streamable_http_client(server.transport.url, http_client=self._http(server)),
                    mode="2026-07-28"
                    if discovery and discovery.protocol_version == "2026-07-28"
                    else "auto",
                    prior_discover=discovery.discover if discovery else None,
                    read_timeout_seconds=seconds,
                    cache=None,
                ) as client:
                    yield client
        except Exception as exc:
            raise classify(exc) from None

    async def discover(self, server: ServerConfig) -> Discovery:
        async with self._client(server, server.timeout.discovery_seconds) as client:
            tools = []
            cursor = None
            cursors: set[str] = set()
            ttl = 0
            for _ in range(self.config.registry.max_pages):
                page = await client.list_tools(cursor=cursor)
                tools.extend(page.tools)
                ttl = min(ttl, page.ttl_ms) if cursor else page.ttl_ms
                if len(tools) > self.config.registry.max_tools:
                    raise GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)
                cursor = page.next_cursor
                if cursor is None:
                    return Discovery(
                        tuple(tools),
                        client.server_capabilities,
                        client.protocol_version,
                        client.session.discover_result,
                        ttl,
                    )
                if cursor in cursors:
                    break
                cursors.add(cursor)
            raise GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)

    async def probe(self, server: ServerConfig) -> None:
        # Opening auto-mode performs SDK server/discover (or free legacy fallback).
        async with self._client(server, server.timeout.health_seconds):
            pass

    async def call(
        self,
        server: ServerConfig,
        route: ToolRoute,
        params: CallToolRequestParams,
        discovery: Discovery,
    ) -> CallToolResult:
        token = _parameter_headers.set(
            mcp_param_headers(x_mcp_header_map(route.tool.input_schema), params.arguments or {})
        )
        try:
            async with self._client(server, server.timeout.call_seconds, discovery) as client:
                return await client.session.send_request(
                    CallToolRequest(
                        params=params.model_copy(update={"name": route.downstream_name})
                    ),
                    CallToolResult,
                    request_read_timeout_seconds=server.timeout.call_seconds,
                )
        finally:
            _parameter_headers.reset(token)

    async def close(self) -> None:
        for client in self.clients.values():
            await client.aclose()
        self.clients.clear()
