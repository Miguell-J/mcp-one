"""Main FastAPI application."""

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from typing import List
import yaml
import structlog
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.models.schemas import (
    MCPServerConfig,
    ToolCallRequest,
    ToolCallResponse,
    ListToolsResponse,
    HubStatus,
    ErrorResponse,
    ServerStatus,
)
from app.core.registry import MCPRegistry
from app.core.router import MCPRouter

from pathlib import Path

# Caminho absoluto até a pasta deste arquivo
BASE_DIR = Path(__file__).resolve().parent
# Volta uma pasta (de app/ para src/)
CONFIG_PATH = BASE_DIR.parent / "config.yaml"

config = {}


def load_runtime_config() -> Dict[str, Any]:
    """Load runtime configuration from CONFIG_PATH."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("config_file_not_found", path=str(CONFIG_PATH))
        return {}


# Configurar logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Variáveis globais
registry: MCPRegistry
router: MCPRouter
start_time: float = time.time()
config: Dict[str, Any] = load_runtime_config()


# in-memory runtime controls
_request_buckets: Dict[str, deque] = defaultdict(deque)
_metrics: Dict[str, int] = defaultdict(int)


def _authorize_request(request: Request) -> None:
    """Authorize incoming request when API key is configured."""
    hub = config.get("hub", {})
    api_key = hub.get("api_key")
    bearer_token = hub.get("bearer_token")

    if api_key:
        provided = request.headers.get("x-api-key")
        if provided != api_key:
            raise HTTPException(status_code=401, detail="unauthorized")

    if bearer_token:
        auth_header = request.headers.get("authorization", "")
        expected = f"Bearer {bearer_token}"
        if auth_header != expected:
            raise HTTPException(status_code=401, detail="unauthorized")


def _enforce_rate_limit(request: Request) -> None:
    """Apply simple in-memory per-client rate limiting."""
    rl = config.get("rate_limit", {})
    if not rl.get("enabled", False):
        return

    limit = int(rl.get("requests_per_minute", 100))
    now = time.time()
    client = request.client.host if request.client else "unknown"
    bucket = _request_buckets[client]

    while bucket and now - bucket[0] > 60:
        bucket.popleft()



# in-memory runtime controls
_request_buckets: Dict[str, deque] = defaultdict(deque)
_metrics: Dict[str, int] = defaultdict(int)


def _authorize_request(request: Request) -> None:
    """Authorize incoming request when API key is configured."""
    api_key = config.get("hub", {}).get("api_key")
    if not api_key:
        return
    provided = request.headers.get("x-api-key")
    if provided != api_key:
        raise HTTPException(status_code=401, detail="unauthorized")


def _enforce_rate_limit(request: Request) -> None:
    """Apply simple in-memory per-client rate limiting."""
    rl = config.get("rate_limit", {})
    if not rl.get("enabled", False):
        return

    limit = int(rl.get("requests_per_minute", 100))
    now = time.time()
    client = request.client.host if request.client else "unknown"
    bucket = _request_buckets[client]

    while bucket and now - bucket[0] > 60:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")

    bucket.append(now)


def protect_request(request: Request) -> None:
    """Run request protections: auth then rate limit."""
    _authorize_request(request)
    _enforce_rate_limit(request)



@asynccontextmanager
async def lifespan(_app: FastAPI):


# in-memory runtime controls
_request_buckets: Dict[str, deque] = defaultdict(deque)
_metrics: Dict[str, int] = defaultdict(int)


def _authorize_request(request: Request) -> None:
    """Authorize incoming request when API key is configured."""
    api_key = config.get("hub", {}).get("api_key")
    if not api_key:
        return
    provided = request.headers.get("x-api-key")
    if provided != api_key:
        raise HTTPException(status_code=401, detail="unauthorized")


def _enforce_rate_limit(request: Request) -> None:
    """Apply simple in-memory per-client rate limiting."""
    rl = config.get("rate_limit", {})
    if not rl.get("enabled", False):
        return

    limit = int(rl.get("requests_per_minute", 100))
    now = time.time()
    client = request.client.host if request.client else "unknown"
    bucket = _request_buckets[client]

    while bucket and now - bucket[0] > 60:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")

    bucket.append(now)


def protect_request(request: Request) -> None:
    """Run request protections: auth then rate limit."""
    _authorize_request(request)
    _enforce_rate_limit(request)



@asynccontextmanager
async def lifespan(_app: FastAPI):
@asynccontextmanager
async def lifespan(_app: FastAPI):
config: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down shared application resources."""
    global registry, router, start_time, config
    
    start_time = time.time()

    # Carrega configuração
    config = load_runtime_config()

    
    # Inicializa registry e router
    registry = MCPRegistry()
    router = MCPRouter(registry)
    
    # Registra servidores MCP
    for server_config in config.get("servers", []):
        mcp_config = MCPServerConfig(**server_config)
        await registry.register_server(mcp_config)
    
    # Inicia refresh automático
    await registry.start_background_refresh(interval=60)
    
    logger.info(
        "mcp_hub_started",
        version=__version__,
        servers_count=len(config.get("servers", [])),
        port=config.get("hub", {}).get("port", 8000)
    )
    
    yield
    
    # Cleanup
    await registry.shutdown()
    await router.shutdown()
    
    logger.info("mcp_hub_shutdown_complete")


# Criar aplicação FastAPI
app = FastAPI(
    title="MCP one",
    description="Central hub for managing multiple MCP servers",
    version=__version__,
    lifespan=lifespan
)

# Configurar CORS
if config.get("hub", {}).get("cors_enabled", True):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.get("hub", {}).get("cors_origins", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Dependency para obter registry
def get_registry() -> MCPRegistry:
    return registry


def get_router() -> MCPRouter:
    return router


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="http_error",
            message=exc.detail,
            timestamp=datetime.now(UTC).isoformat()
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            message="Internal server error",
            timestamp=datetime.now(UTC).isoformat()
        ).model_dump()
    )


# Endpoints
@app.get("/")
async def root(request: Request):
    protect_request(request)
async def root():
    """Return basic metadata and health of the hub service."""
    return {
        "name": "MCP one",
        "version": __version__,
        "description": "Central hub for managing multiple MCP servers",
        "status": "online"
    }


@app.get("/health")
async def health_check(request: Request):
    protect_request(request)
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": time.time() - start_time
    }


@app.get("/status", response_model=HubStatus)
async def get_status(request: Request, reg: MCPRegistry = Depends(get_registry)):
    protect_request(request)
    """Retorna status detalhado do Hub."""
    servers = await reg.list_servers()
    tools = await reg.list_tools()
    
    return HubStatus(
        version=__version__,
        uptime_seconds=time.time() - start_time,
        servers_count=len(servers),
        servers_online=len([s for s in servers if s.status == ServerStatus.ONLINE]),
        tools_count=len(tools),
        last_refresh=datetime.now(UTC).isoformat()
    )


@app.get("/tools", response_model=ListToolsResponse)
async def list_tools(
    request: Request,
    server: Optional[str] = None,
    reg: MCPRegistry = Depends(get_registry)
):
    protect_request(request)
    """Lista todas as ferramentas disponíveis."""
    tools = await reg.list_tools(server_name=server)
    servers = await reg.list_servers()
    
    return ListToolsResponse(
        tools=tools,
        total_count=len(tools),
        servers_online=len([s for s in servers if s.status == ServerStatus.ONLINE]),
        last_updated=datetime.now(UTC).isoformat()
    )


@app.post("/call", response_model=ToolCallResponse)
async def call_tool(
    request: ToolCallRequest,
    http_request: Request,
    rt: MCPRouter = Depends(get_router)
):
    """Executa uma ferramenta em um servidor MCP."""
    protect_request(http_request)
    _metrics["call_requests_total"] += 1
    response = await rt.execute_tool(request)
    if response.success:
        _metrics["call_success_total"] += 1
    else:
        _metrics["call_failure_total"] += 1
    return response


@app.get("/servers")
async def list_servers(request: Request, reg: MCPRegistry = Depends(get_registry)):
    protect_request(request)
    """Lista todos os servidores registrados."""
    servers = await reg.list_servers()
    return {"servers": servers}


@app.post("/servers/refresh")
async def refresh_servers(request: Request, reg: MCPRegistry = Depends(get_registry)):
    protect_request(request)
    """Force refresh de todos os servidores."""
    await reg.refresh_all_servers()
    return {"message": "Servers refreshed successfully"}


@app.get("/ready")
async def readiness(request: Request):
    """Readiness probe based on upstream MCP availability."""
    protect_request(request)
    servers = await registry.list_servers()
    online = len([s for s in servers if s.status == ServerStatus.ONLINE])
    return {
        "ready": online > 0 if servers else True,
        "servers_online": online,
        "servers_total": len(servers),
    }


@app.get("/metrics")
async def metrics(request: Request):
    """Basic operational metrics endpoint (JSON)."""
    protect_request(request)
    return {
        "uptime_seconds": time.time() - start_time,
        "call_requests_total": _metrics.get("call_requests_total", 0),
        "call_success_total": _metrics.get("call_success_total", 0),
        "call_failure_total": _metrics.get("call_failure_total", 0),
        "tracked_clients": len(_request_buckets),
        "open_circuits": len(getattr(router, "_circuit_open_until", {})) if "router" in globals() else 0,
    }


@app.get("/metrics/prometheus")
async def metrics_prometheus(request: Request):
    """Prometheus-compatible plaintext metrics endpoint."""
    protect_request(request)
    lines = [
        "# HELP mcp_one_uptime_seconds Uptime in seconds",
        "# TYPE mcp_one_uptime_seconds gauge",
        f"mcp_one_uptime_seconds {time.time() - start_time}",
        "# HELP mcp_one_call_requests_total Total call requests",
        "# TYPE mcp_one_call_requests_total counter",
        f"mcp_one_call_requests_total {_metrics.get('call_requests_total', 0)}",
        "# HELP mcp_one_call_success_total Total successful call requests",
        "# TYPE mcp_one_call_success_total counter",
        f"mcp_one_call_success_total {_metrics.get('call_success_total', 0)}",
        "# HELP mcp_one_call_failure_total Total failed call requests",
        "# TYPE mcp_one_call_failure_total counter",
        f"mcp_one_call_failure_total {_metrics.get('call_failure_total', 0)}",
        "# HELP mcp_one_open_circuits Number of open upstream circuits",
        "# TYPE mcp_one_open_circuits gauge",
        f"mcp_one_open_circuits {len(getattr(router, '_circuit_open_until', {})) if 'router' in globals() else 0}",
    ]
    return "\n".join(lines) + "\n"


def main():
    """Run the service using runtime hub configuration."""
    import uvicorn

    runtime_config = load_runtime_config()
    hub_config = runtime_config.get("hub", {})

    
    # Carrega configuração
    try:
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ config.yaml file not found!")
        return
    
    hub_config = config.get("hub", {})
    
    uvicorn.run(
        "app.main:app",
        host=hub_config.get("host", "0.0.0.0"),
        port=hub_config.get("port", 8000),
        reload=False,
        log_level=hub_config.get("log_level", "info").lower(),
    )


if __name__ == "__main__":
    main()