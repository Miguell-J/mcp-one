"""Router para executar ferramentas MCP."""

import time
from typing import Any, Dict, Optional
import httpx
import structlog
from app.models.schemas import ToolCallRequest, ToolCallResponse
from app.core.registry import MCPRegistry
from app.models.schemas import MCPServerConfig

logger = structlog.get_logger(__name__)


class MCPRouter:
    """_summary_
    """
    
    def __init__(self, registry: MCPRegistry):
        self.registry = registry
        self._client = httpx.AsyncClient(timeout=60.0)
    
    async def execute_tool(self, request: ToolCallRequest) -> ToolCallResponse:
        """_summary_

        Args:
            request (ToolCallRequest): _description_

        Returns:
            ToolCallResponse: _description_
        """
        start_time = time.time()
        
        try:
            # Busca informações da ferramenta
            tool = await self.registry.get_tool(request.tool)
            if not tool:
                return ToolCallResponse(
                    success=False,
                    error="tool_not_found",
                    server_name="unknown",
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            # Busca informações do servidor
            server_info = await self.registry.get_server_info(tool.server_name)
            if not server_info:
                return ToolCallResponse(
                    success=False,
                    error="server_not_found",
                    server_name=tool.server_name,
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            # Verifica se servidor está online
            if server_info.status != "online":
                return ToolCallResponse(
                    success=False,
                    error="server_offline",
                    server_name=tool.server_name,
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            # Executa a ferramenta
            response = await self._call_mcp_tool(
                server_info.config,
                tool.name,
                request.arguments
            )

            
            execution_time = (time.time() - start_time) * 1000
            
            logger.info(
                "tool_executed",
                tool_name=request.tool,
                server_name=tool.server_name,
                execution_time_ms=execution_time,
                success=response.success
            )
            
            response.execution_time_ms = execution_time
            response.server_name = tool.server_name
            
            return response
            
        except Exception as e:
            logger.error(
                "tool_execution_failed",
                tool_name=request.tool,
                error=str(e)
            )
            
            return ToolCallResponse(
                success=False,
                error="execution_failed",
                server_name=tool.server_name if 'tool' in locals() else "unknown",
                execution_time_ms=(time.time() - start_time) * 1000
            )
    
    async def _call_mcp_tool(
        self,
        config: MCPServerConfig,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> ToolCallResponse:
        """_summary_

        Args:
            config (MCPServerConfig): _description_
            tool_name (str): _description_
            arguments (Dict[str, Any]): _description_

        Returns:
            ToolCallResponse: _description_
        """
        base_url = str(config.url).rstrip("/")
        call_endpoint = config.endpoints.get("call", "/call")

        tool_field = config.payload_map.get("tool_field", "tool")
        args_field = config.payload_map.get("args_field", "arguments")

        payload = {
            tool_field: tool_name,
            args_field: arguments
        }

        try:
            response = await self._client.post(
                f"{base_url}{call_endpoint}",
                json=payload,
                timeout=config.timeout
            )

            if response.status_code == 200:
                data = response.json()
                return ToolCallResponse(
                    success=True,
                    result=data.get("result"),
                    server_name=""  # será preenchido em execute_tool
                )
            else:
                return ToolCallResponse(
                    success=False,
                    error=f"http_error_{response.status_code}",
                    server_name=""
                )
        except httpx.TimeoutException:
            return ToolCallResponse(
                success=False,
                error="timeout",
                server_name=""
            )
        except Exception as e:
            return ToolCallResponse(
                success=False,
                error=str(e),
                server_name=""
            )

    
    async def shutdown(self) -> None:
        """_summary_
        """
        await self._client.aclose()
        logger.info("router_shutdown_complete")
