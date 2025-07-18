"""Registry para gerenciar servidores MCP."""

import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
import httpx
import structlog
from app.models.schemas import (
    MCPServerConfig,
    MCPServerInfo,
    ServerStatus,
    ToolSchema,
)

logger = structlog.get_logger(__name__)


class MCPRegistry:
    """Registry central para gerenciar servidores MCP."""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerInfo] = {}
        self.tools: Dict[str, ToolSchema] = {}  # full_name -> ToolSchema
        self.server_tools: Dict[str, Set[str]] = {}  # server_name -> set of tool names
        self._client = httpx.AsyncClient(timeout=30.0)
        self._refresh_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
    async def register_server(self, config: MCPServerConfig) -> bool:
        """Registra um novo servidor MCP."""
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
        """Remove um servidor do registry."""
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
        """Retorna informações de um servidor."""
        return self.servers.get(server_name)
    
    async def list_servers(self) -> List[MCPServerInfo]:
        """Lista todos os servidores registrados."""
        return list(self.servers.values())
    
    async def get_tool(self, tool_full_name: str) -> Optional[ToolSchema]:
        """Retorna informações de uma ferramenta."""
        return self.tools.get(tool_full_name)
    
    async def list_tools(self, server_name: Optional[str] = None) -> List[ToolSchema]:
        """Lista todas as ferramentas disponíveis."""
        if server_name:
            return [
                tool for tool in self.tools.values()
                if tool.server_name == server_name
            ]
        return list(self.tools.values())
    
    async def refresh_all_servers(self) -> None:
        """Atualiza informações de todos os servidores."""
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
        """Verifica saúde de um servidor específico."""
        server_info = self.servers.get(server_name)
        if not server_info:
            return
            
        config = server_info.config
        if not config.enabled:
            server_info.status = ServerStatus.OFFLINE
            return
            
        start_time = time.time()
        
        try:
            # Tenta conectar no servidor
            response = await self._client.get(
                f"{config.url}/health",
                timeout=config.timeout
            )
            
            if response.status_code == 200:
                server_info.status = ServerStatus.ONLINE
                server_info.response_time_ms = (time.time() - start_time) * 1000
                server_info.last_seen = datetime.utcnow().isoformat()
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
        """Atualiza lista de ferramentas de um servidor."""
        server_info = self.servers.get(server_name)
        if not server_info or server_info.status != ServerStatus.ONLINE:
            return
            
        try:
            response = await self._client.get(
                f"{server_info.config.url}/tools",
                timeout=server_info.config.timeout
            )
            
            if response.status_code == 200:
                tools_data = response.json()
                
                # Remove ferramentas antigas do servidor
                if server_name in self.server_tools:
                    for tool_name in self.server_tools[server_name]:
                        full_name = f"{server_name}.{tool_name}"
                        self.tools.pop(full_name, None)
                
                # Adiciona novas ferramentas
                tool_names = set()
                for tool_data in tools_data.get('tools', []):
                    tool_schema = ToolSchema(
                        name=tool_data['name'],
                        description=tool_data.get('description', ''),
                        parameters=tool_data.get('parameters', {}),
                        server_name=server_name
                    )
                    
                    self.tools[tool_schema.full_name] = tool_schema
                    tool_names.add(tool_data['name'])
                
                self.server_tools[server_name] = tool_names
                server_info.tools_count = len(tool_names)
                
                logger.info(
                    "server_tools_refreshed",
                    server_name=server_name,
                    tools_count=len(tool_names)
                )
                
        except Exception as e:
            logger.error(
                "server_tools_refresh_failed",
                server_name=server_name,
                error=str(e)
            )
    
    async def start_background_refresh(self, interval: int = 60) -> None:
        """Inicia refresh automático dos servidores."""
        if self._refresh_task and not self._refresh_task.done():
            return
            
        self._refresh_task = asyncio.create_task(
            self._background_refresh_loop(interval)
        )
        
        logger.info("background_refresh_started", interval=interval)
    
    async def _background_refresh_loop(self, interval: int) -> None:
        """Loop de refresh em background."""
        while not self._shutdown:
            try:
                await self.refresh_all_servers()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error("background_refresh_error", error=str(e))
                await asyncio.sleep(5)  # Retry em 5 segundos
    
    async def shutdown(self) -> None:
        """Finaliza o registry."""
        self._shutdown = True
        
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        await self._client.aclose()
        logger.info("registry_shutdown_complete")
