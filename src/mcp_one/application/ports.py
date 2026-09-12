from typing import Protocol

from mcp.types import CallToolRequestParams, CallToolResult

from mcp_one.config import ServerConfig
from mcp_one.domain.models import Discovery, ToolRoute


class MCPTransportClient(Protocol):
    async def discover(self, server: ServerConfig) -> Discovery: ...
    async def probe(self, server: ServerConfig) -> None: ...
    async def call(
        self,
        server: ServerConfig,
        route: ToolRoute,
        params: CallToolRequestParams,
        discovery: Discovery,
    ) -> CallToolResult: ...
    async def close(self) -> None: ...


class Metrics(Protocol):
    def increment(self, name: str, server: str = "", outcome: str = "") -> None: ...
    def observe(self, name: str, seconds: float, server: str) -> None: ...
    def gauge(self, name: str, value: float, server: str = "") -> None: ...
