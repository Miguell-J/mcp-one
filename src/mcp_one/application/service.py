import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

import structlog

from mcp_one.application.ports import MCPTransportClient, Metrics
from mcp_one.application.registry import Registry
from mcp_one.application.router import Router
from mcp_one.config import GatewayConfig
from mcp_one.domain.errors import GatewayError


class Gateway:
    def __init__(self, config: GatewayConfig, client: MCPTransportClient, metrics: Metrics):
        self.config, self.client, self.metrics = config, client, metrics
        self.registry = Registry(config, client, metrics)
        self.router = Router(config, self.registry, client, metrics)
        self.started = monotonic()
        self.running = False
        self.background_failed = False

    @property
    def ready(self) -> bool:
        return (
            self.running
            and self.registry.initialized
            and not self.background_failed
            and (self.router.ready_servers() >= self.config.hub.minimum_ready_servers)
        )

    async def refresh(self) -> None:
        before = self.registry.snapshot.generation
        snapshot = await self.registry.refresh()
        if snapshot.generation != before:
            for server_id, catalog in snapshot.servers.items():
                self.router.reachable[server_id] = catalog.error is None

    async def _probe(self, server_id: str) -> None:
        server = self.registry.snapshot.servers[server_id].config
        for attempt in range(server.retry.health_attempts):
            try:
                await self.client.probe(server)
                self.router.reachable[server_id] = True
                self.metrics.increment("health_probes", server_id, "success")
                return
            except GatewayError as exc:
                if not exc.retryable or attempt + 1 == server.retry.health_attempts:
                    break
                await asyncio.sleep(server.retry.backoff_seconds * (attempt + 1))
        self.router.reachable[server_id] = False
        self.metrics.increment("health_probes", server_id, "failure")

    async def _background(self) -> None:
        next_refresh = monotonic() + self.config.registry.refresh_interval_seconds
        next_health = {
            s.id: monotonic() + s.health.interval_seconds for s in self.config.servers if s.enabled
        }
        try:
            while True:
                now = monotonic()
                await asyncio.sleep(max(0.05, min([next_refresh, *next_health.values()]) - now))
                now = monotonic()
                if now >= next_refresh:
                    await self.refresh()
                    next_refresh = monotonic() + self.config.registry.refresh_interval_seconds
                due = [key for key, deadline in next_health.items() if deadline <= now]
                await asyncio.gather(*(self._probe(key) for key in due))
                for key in due:
                    next_health[key] = (
                        monotonic()
                        + self.registry.snapshot.servers[key].config.health.interval_seconds
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            self.background_failed = True
            structlog.get_logger().error("background_refresh_failed", code="INTERNAL_ERROR")

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        task = None
        try:
            await self.refresh()
            self.running = True
            task = asyncio.create_task(self._background(), name="mcp-one-refresh")
            yield
        finally:
            self.running = False
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self.client.close()
