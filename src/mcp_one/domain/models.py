from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from mcp.types import DiscoverResult, ServerCapabilities, Tool

from mcp_one.config import ServerConfig


class ServerState(StrEnum):
    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


@dataclass(frozen=True)
class Discovery:
    tools: tuple[Tool, ...]
    capabilities: ServerCapabilities
    protocol_version: str
    discover: DiscoverResult | None = None
    ttl_ms: int = 0


@dataclass(frozen=True)
class ToolRoute:
    upstream_name: str
    downstream_name: str
    server_id: str
    namespace: str
    tool: Tool


@dataclass(frozen=True)
class ServerCatalog:
    config: ServerConfig
    state: ServerState = ServerState.STARTING
    discovery: Discovery | None = None
    routes: tuple[ToolRoute, ...] = ()
    last_success: float | None = None
    last_refresh: float = 0
    error: str | None = None


@dataclass(frozen=True)
class CatalogSnapshot:
    generation: int = 0
    servers: Mapping[str, ServerCatalog] = field(default_factory=lambda: MappingProxyType({}))
    routes: Mapping[str, ToolRoute] = field(default_factory=lambda: MappingProxyType({}))
