"""Main FastAPI application."""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List
import yaml
import structlog
from fastapi import FastAPI, HTTPException, Depends
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
)
from app.core.registry import MCPRegistry
from app.core.router import MCPRouter

from pathlib import Path

# Caminho absoluto até a pasta deste arquivo
BASE_DIR = Path(__file__).resolve().parent
# Volta uma pasta (de app/ para src/)
CONFIG_PATH = BASE_DIR.parent / "config.yaml"

try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print(f"❌ config.yaml file not in {CONFIG_PATH}")
    config = {}

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
start_time: float
config: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    """_summary_

    Args:
        app (FastAPI): _description_
    """
    global registry, router, start_time, config
    
    start_time = time.time()
    
    # Carrega configuração
    try:
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ config.yaml file not in {CONFIG_PATH}")
        config = {}

    
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
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="http_error",
            message=exc.detail,
            timestamp=datetime.utcnow().isoformat()
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            message="Internal server error",
            timestamp=datetime.utcnow().isoformat()
        ).dict()
    )


# Endpoints
@app.get("/")
async def root():
    """_summary_

    Returns:
        _type_: _description_
    """
    return {
        "name": "MCP one",
        "version": __version__,
        "description": "Central hub for managing multiple MCP servers",
        "status": "online"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - start_time
    }


@app.get("/status", response_model=HubStatus)
async def get_status(reg: MCPRegistry = Depends(get_registry)):
    """Retorna status detalhado do Hub."""
    servers = await reg.list_servers()
    tools = await reg.list_tools()
    
    return HubStatus(
        version=__version__,
        uptime_seconds=time.time() - start_time,
        servers_count=len(servers),
        servers_online=len([s for s in servers if s.status == "online"]),
        tools_count=len(tools),
        last_refresh=datetime.utcnow().isoformat()
    )


@app.get("/tools", response_model=ListToolsResponse)
async def list_tools(
    server: str = None,
    reg: MCPRegistry = Depends(get_registry)
):
    """Lista todas as ferramentas disponíveis."""
    tools = await reg.list_tools(server_name=server)
    servers = await reg.list_servers()
    
    return ListToolsResponse(
        tools=tools,
        total_count=len(tools),
        servers_online=len([s for s in servers if s.status == "online"]),
        last_updated=datetime.utcnow().isoformat()
    )


@app.post("/call", response_model=ToolCallResponse)
async def call_tool(
    request: ToolCallRequest,
    rt: MCPRouter = Depends(get_router)
):
    """Executa uma ferramenta em um servidor MCP."""
    return await rt.execute_tool(request)


@app.get("/servers")
async def list_servers(reg: MCPRegistry = Depends(get_registry)):
    """Lista todos os servidores registrados."""
    servers = await reg.list_servers()
    return {"servers": servers}


@app.post("/servers/refresh")
async def refresh_servers(reg: MCPRegistry = Depends(get_registry)):
    """Force refresh de todos os servidores."""
    await reg.refresh_all_servers()
    return {"message": "Servers refreshed successfully"}


def main():
    """Função principal para executar o servidor."""
    import uvicorn
    
    # Carrega configuração
    try:
        with open("src/config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ config.yaml file not found!")
        return
    
    hub_config = config.get("hub", {})
    
    uvicorn.run(
        "app.main:app",
        host=hub_config.get("host", "0.0.0.0"),
        port=hub_config.get("port", 8000),
        reload=hub_config.get("debug", False),
        log_level=hub_config.get("log_level", "info").lower()
    )


if __name__ == "__main__":
    main()