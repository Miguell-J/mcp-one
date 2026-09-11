from time import monotonic
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from mcp_one import __version__
from mcp_one.application.circuit import CircuitState
from mcp_one.application.service import Gateway
from mcp_one.domain.models import ServerState
from mcp_one.observability.metrics import PrometheusMetrics


def routes(gateway: Gateway, metrics: PrometheusMetrics) -> list[Route]:
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"alive": gateway.running}, status_code=200 if gateway.running else 503)

    async def ready(request: Request) -> JSONResponse:
        return JSONResponse(
            {"ready": gateway.ready, "readyServers": gateway.router.ready_servers()},
            status_code=200 if gateway.ready else 503,
        )

    def status() -> dict[str, Any]:
        snapshot = gateway.registry.snapshot
        servers = {}
        for key, catalog in snapshot.servers.items():
            circuit = gateway.router.circuits[key]
            state = catalog.state
            usable = gateway.registry.usable(catalog)
            if not usable:
                state = ServerState.OFFLINE
            if not gateway.router.reachable.get(key, True):
                state = ServerState.DEGRADED if usable else ServerState.OFFLINE
            if circuit.state != CircuitState.CLOSED:
                state = ServerState.CIRCUIT_OPEN
            metrics.gauge("server_health", float(state == ServerState.ONLINE), key)
            metrics.gauge("circuit_open", float(circuit.state != CircuitState.CLOSED), key)
            servers[key] = {
                "state": state.value,
                "catalogAvailable": bool(catalog.routes),
                "readyToRoute": usable and circuit.can_attempt,
                "stale": catalog.error is not None or not usable,
                "catalogAgeSeconds": round(monotonic() - catalog.last_success, 3)
                if catalog.last_success is not None
                else None,
                "error": catalog.error,
                "tools": len(catalog.routes),
                "namespace": catalog.config.namespace,
                "circuit": circuit.state.value,
                "capabilities": catalog.discovery.capabilities.model_dump(
                    by_alias=True, exclude_none=True
                )
                if catalog.discovery
                else None,
            }
        return {
            "version": __version__,
            "ready": gateway.ready,
            "generation": snapshot.generation,
            "tools": len(snapshot.routes),
            "servers": servers,
        }

    async def get_status(request: Request) -> JSONResponse:
        return JSONResponse(status())

    async def refresh(request: Request) -> JSONResponse:
        await gateway.refresh()
        return JSONResponse(status())

    async def scrape(request: Request) -> Response:
        status()
        return Response(metrics.render(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    async def removed(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "error": "REST_EXECUTION_REMOVED",
                "endpoint": "/mcp",
                "migration": "docs/migration-to-native-mcp.md",
            },
            status_code=410,
        )

    return [
        Route("/health", health),
        Route("/ready", ready),
        Route("/status", get_status),
        Route("/servers", get_status),
        Route("/refresh", refresh, methods=["POST"]),
        Route("/metrics", scrape),
        Route("/tools", removed),
        Route("/call", removed, methods=["POST"]),
    ]
