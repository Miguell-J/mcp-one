"""Registry para gerenciar servidores MCP."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Dict, List, Optional, Set
import httpx
from httpx import HTTPStatusError, RequestError
import structlog
from app.models.schemas import (
    MCPServerConfig,
    MCPServerInfo,
    ServerStatus,
    ToolSchema,
)

logger = structlog.get_logger(__name__)


class MCPRegistry:
    """Maintain MCP server registrations, status, and tool catalogs."""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerInfo] = {}
        self.tools: Dict[str, ToolSchema] = {} 
        self.server_tools: Dict[str, Set[str]] = {}  
        self._client = httpx.AsyncClient(timeout=30.0)
        self._refresh_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
    async def register_server(self, config: MCPServerConfig) -> bool:
        """Register a server and perform initial health/tool discovery."""
        try:
            server_info = MCPServerInfo(
                config=config,
                status=ServerStatus.CONNECTING
            )
            self.servers[config.name] = server_info
            
            # Tenta conectar imediatamente
            await self._check_server_health(config.name)
            
            logger.info(
                "server_registered",
                server_name=config.name,
                url=str(config.url),
                status=server_info.status
            )
            return True
            
        except Exception as e:
            logger.error(
                "server_registration_failed",
                server_name=config.name,
                error=str(e)
            )
            return False
    
    async def unregister_server(self, server_name: str) -> bool:
        """Unregister a server and remove all its indexed tools."""
        if server_name not in self.servers:
            return False
            
        # Remove ferramentas do servidor
        if server_name in self.server_tools:
            for tool_name in self.server_tools[server_name]:
                full_name = f"{server_name}.{tool_name}"
                self.tools.pop(full_name, None)
            del self.server_tools[server_name]
        
        # Remove servidor
        del self.servers[server_name]
        
        logger.info("server_unregistered", server_name=server_name)
        return True
    
    async def get_server_info(self, server_name: str) -> Optional[MCPServerInfo]:
        """Return metadata for a registered server by name."""
        return self.servers.get(server_name)
    
    async def list_servers(self) -> List[MCPServerInfo]:
        """List all registered MCP servers."""
        return list(self.servers.values())
    
    async def get_tool(self, tool_full_name: str) -> Optional[ToolSchema]:
        """Return a tool schema by its fully qualified name."""
        return self.tools.get(tool_full_name)
    
    async def list_tools(self, server_name: Optional[str] = None) -> List[ToolSchema]:
        """List tool schemas, optionally filtered by server."""
        if server_name:
            return [
                tool for tool in self.tools.values()
                if tool.server_name == server_name
            ]
        return list(self.tools.values())
    
    async def refresh_all_servers(self) -> None:
        """Refresh health and tool catalogs for all servers."""
        tasks = [
            self._check_server_health(server_name)
            for server_name in self.servers.keys()
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        logger.info(
            "servers_refreshed",
            total_servers=len(self.servers),
            online_servers=len([s for s in self.servers.values() if s.status == ServerStatus.ONLINE])
        )
    
    async def _check_server_health(self, server_name: str) -> None:
        """Update health state for a server and refresh its tools when online."""
        server_info = self.servers.get(server_name)
        if not server_info:
            return
            
        config = server_info.config
        if not config.enabled:
            server_info.status = ServerStatus.OFFLINE
            return
            
        start_time = time.time()
        
        try:
            endpoints = config.endpoints
            health_endpoint = endpoints.get("health", "/health")
            base_url = str(config.url).rstrip("/")
            response = None
            for attempt in range(max(1, config.retry_attempts)):
                try:
                    response = await self._client.get(f"{base_url}{health_endpoint}", timeout=config.timeout)
                    response.raise_for_status()
                    break
                except (RequestError, HTTPStatusError) as exc:
                    if attempt == config.retry_attempts - 1:
                        raise exc
                    await asyncio.sleep(min(0.2 * (attempt + 1), 1.0))

            if response and response.status_code == 200:
                server_info.status = ServerStatus.ONLINE
                server_info.response_time_ms = (time.time() - start_time) * 1000
                server_info.last_seen = datetime.now(UTC).isoformat()
                server_info.error_message = None
                
                # Atualiza ferramentas
                await self._refresh_server_tools(server_name)
                
            else:
                server_info.status = ServerStatus.ERROR
                server_info.error_message = f"HTTP {response.status_code}"
                
        except Exception as e:
            server_info.status = ServerStatus.ERROR
            server_info.error_message = str(e)
            
            logger.warning(
                "server_health_check_failed",
                server_name=server_name,
                error=str(e)
            )
    
    async def _refresh_server_tools(self, server_name: str) -> None:
        """Fetch and normalize tools from a specific online MCP server."""
        server_info = self.servers.get(server_name)
        if not server_info or server_info.status != ServerStatus.ONLINE:
            return
            
        try:
            # Pega endpoints configurados
            endpoints = server_info.config.endpoints
            base_url = str(server_info.config.url).rstrip("/")
            tools_endpoint = endpoints.get("tools", "/tools")

            response = await self._client.get(f"{base_url}{tools_endpoint}", timeout=server_info.config.timeout)
                        
            if response.status_code == 200:
                raw = response.json()

                # pega as configurações de mapeamento do servidor
                resp_map = server_info.config.response_map
                tools_key = resp_map.get("tools_key", "tools")
                name_field = resp_map.get("tool_name_field", "name")
                desc_field = resp_map.get("tool_desc_field", "description")

                # decide se a resposta é lista direta ou se precisa acessar uma chave
                if tools_key:
                    raw_tools = raw.get(tools_key, [])
                else:
                    raw_tools = raw  # já é uma lista

                # limpa ferramentas antigas
                if server_info.config.name in self.server_tools:
                    for t in self.server_tools[server_info.config.name]:
                        self.tools.pop(f"{server_info.config.name}.{t}", None)

                # adiciona novas ferramentas
                tool_names = set()
                for tool in raw_tools:
                    t_name = tool.get(name_field)
                    t_desc = tool.get(desc_field, "")
                    if not t_name:
                        continue
                    schema = ToolSchema(
                    name=t_name,
                    description=t_desc,
                    parameters=tool.get("parameters", {}),
                    server_name=server_name,
                    full_name=f"{server_name}.{t_name}"  # 👈 aqui!
                    )

                    self.tools[schema.full_name] = schema
                    tool_names.add(t_name)

                self.server_tools[server_info.config.name] = tool_names
                server_info.tools_count = len(tool_names)

                
        except Exception as e:
            logger.error(
                "server_tools_refresh_failed",
                server_name=server_name,
                error=str(e)
            )
    
    async def start_background_refresh(self, interval: int = 60) -> None:
        """Start periodic background refresh for server health and tools."""
        if self._refresh_task and not self._refresh_task.done():
            return
            
        self._refresh_task = asyncio.create_task(
            self._background_refresh_loop(interval)
        )
        
        logger.info("background_refresh_started", interval=interval)
    
    async def _background_refresh_loop(self, interval: int) -> None:
        """Run periodic refresh loop until shutdown is requested."""
        while not self._shutdown:
            try:
                await self.refresh_all_servers()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error("background_refresh_error", error=str(e))
                await asyncio.sleep(5)  # Retry em 5 segundos
    
    async def shutdown(self) -> None:
        """Stop background tasks and close HTTP resources."""
        self._shutdown = True
        
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        await self._client.aclose()
        logger.info("registry_shutdown_complete")
