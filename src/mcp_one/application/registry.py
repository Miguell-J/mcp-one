import asyncio
from dataclasses import replace
from time import monotonic
from types import MappingProxyType

from mcp_one.application.ports import MCPTransportClient, Metrics
from mcp_one.config import GatewayConfig
from mcp_one.domain.errors import ErrorCode, GatewayError
from mcp_one.domain.models import CatalogSnapshot, ServerCatalog, ServerState, ToolRoute
from mcp_one.domain.naming import qualified_name
from mcp_one.domain.schema import bounded_json, validate_schema


class Registry:
    def __init__(self, config: GatewayConfig, client: MCPTransportClient, metrics: Metrics):
        self.config, self.client, self.metrics = config, client, metrics
        self.snapshot = CatalogSnapshot(
            servers=MappingProxyType({s.id: ServerCatalog(s) for s in config.servers if s.enabled})
        )
        self.initialized = False
        self._refresh_lock = asyncio.Lock()
        self._last_refresh = float("-inf")

    async def refresh(self) -> CatalogSnapshot:
        async with self._refresh_lock:
            if monotonic() - self._last_refresh < self.config.registry.minimum_refresh_seconds:
                self.metrics.increment("catalog_cache", outcome="hit")
                return self.snapshot
            self.metrics.increment("catalog_cache", outcome="miss")
            previous = self.snapshot
            catalogs = await asyncio.gather(*(self._discover(s) for s in previous.servers.values()))
            routes: dict[str, ToolRoute] = {}
            servers: dict[str, ServerCatalog] = {}
            size = 0
            for catalog in catalogs:
                # Every per-server candidate is validated before a single atomic publication.
                candidate_size = bounded_json(
                    [r.tool.model_dump(mode="json", by_alias=True) for r in catalog.routes],
                    self.config.registry.max_catalog_bytes,
                )
                if len(routes) + len(catalog.routes) > self.config.registry.max_tools or (
                    size + candidate_size > self.config.registry.max_catalog_bytes
                ):
                    catalog = replace(
                        catalog, state=ServerState.OFFLINE, routes=(), error="CATALOG_LIMIT"
                    )
                else:
                    size += candidate_size
                for route in catalog.routes:
                    if route.upstream_name in routes:
                        raise RuntimeError("namespace invariant violated")
                    routes[route.upstream_name] = route
                servers[catalog.config.id] = catalog
            self.snapshot = CatalogSnapshot(
                previous.generation + 1,
                MappingProxyType(servers),
                MappingProxyType(dict(sorted(routes.items()))),
            )
            self._last_refresh = monotonic()
            self.initialized = True
            self.metrics.gauge("catalog_tools", len(routes))
            self.metrics.gauge("catalog_bytes", size)
            return self.snapshot

    async def _discover(self, previous: ServerCatalog) -> ServerCatalog:
        server = previous.config
        started = monotonic()
        error = GatewayError(ErrorCode.DISCOVERY_FAILED, infrastructure=True)
        for attempt in range(server.retry.discovery_attempts):
            try:
                discovery = await self.client.discover(server)
                names: set[str] = set()
                routes = []
                for tool in discovery.tools:
                    validate_schema(tool.input_schema, self.config.limits)
                    if tool.output_schema is not None:
                        validate_schema(tool.output_schema, self.config.limits)
                    name = qualified_name(server.namespace, tool.name)
                    if name in names:
                        raise ValueError("duplicate normalized tool name")
                    names.add(name)
                    routes.append(
                        ToolRoute(
                            name,
                            tool.name,
                            server.id,
                            server.namespace,
                            tool.model_copy(update={"name": name}),
                        )
                    )
                bounded_json(
                    [r.tool.model_dump(mode="json", by_alias=True) for r in routes],
                    self.config.registry.max_catalog_bytes,
                )
                self.metrics.increment("registry_refresh", server.id, "success")
                self.metrics.observe("registry_refresh_seconds", monotonic() - started, server.id)
                return ServerCatalog(
                    server, ServerState.ONLINE, discovery, tuple(routes), monotonic(), monotonic()
                )
            except GatewayError as exc:
                error = exc
            except (ValueError, RecursionError):
                error = GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)
            except Exception:
                # A schema library error is safe to diagnose by stable category, never its payload.
                error = GatewayError(ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True)
            if not error.retryable or attempt + 1 == server.retry.discovery_attempts:
                break
            await asyncio.sleep(server.retry.backoff_seconds * (attempt + 1))
        self.metrics.increment("registry_refresh", server.id, "failure")
        keep = previous.last_success is not None and (
            monotonic() - previous.last_success <= self.config.registry.stale_seconds
        )
        # Retain stale definitions only for transient transport outages. Invalid replacement
        # contracts may change meaning; keep diagnostic discovery but withdraw those routes.
        retained_routes = previous.routes if keep and error.retryable else ()
        return replace(
            previous,
            routes=retained_routes,
            state=ServerState.DEGRADED if retained_routes else ServerState.OFFLINE,
            last_refresh=monotonic(),
            error=error.code.value,
        )

    def usable(self, catalog: ServerCatalog) -> bool:
        return (
            catalog.last_success is not None
            and (
                monotonic() - catalog.last_success
                <= self.config.registry.stale_seconds
                + self.config.registry.refresh_interval_seconds
            )
            and bool(catalog.routes)
        )
