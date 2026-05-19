"""Router para executar ferramentas MCP."""

import time
from collections import defaultdict
from typing import Any, Dict
import httpx
import structlog
from app.models.schemas import ToolCallRequest, ToolCallResponse, ServerStatus
from app.core.registry import MCPRegistry
from app.models.schemas import MCPServerConfig

logger = structlog.get_logger(__name__)


class MCPRouter:
    """Route tool calls from hub clients to MCP servers."""
    
    def __init__(self, registry: MCPRegistry):
        self.registry = registry
        self._client = httpx.AsyncClient(timeout=60.0)
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._circuit_open_until: Dict[str, float] = {}
    

    def _is_circuit_open(self, server_name: str) -> bool:
        """Return True when circuit breaker is open for a server."""
        return self._circuit_open_until.get(server_name, 0) > time.time()

    def _record_success(self, server_name: str) -> None:
        """Reset failure counters after successful call."""
        self._failure_counts[server_name] = 0
        self._circuit_open_until.pop(server_name, None)

    def _record_failure(self, server_name: str, fail_threshold: int, reset_seconds: int) -> None:
        """Track failures and open the circuit when threshold is reached."""
        self._failure_counts[server_name] += 1
        if self._failure_counts[server_name] >= fail_threshold:
            self._circuit_open_until[server_name] = time.time() + reset_seconds

    async def execute_tool(self, request: ToolCallRequest) -> ToolCallResponse:
        """Execute a tool call request against the resolved MCP server."""
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
            if server_info.status != ServerStatus.ONLINE:
                return ToolCallResponse(
                    success=False,
                    error="server_offline",
                    server_name=tool.server_name,
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            if self._is_circuit_open(tool.server_name):
                return ToolCallResponse(
                    success=False,
                    error="circuit_open",
                    server_name=tool.server_name,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Executa a ferramenta
            response = await self._call_mcp_tool(
                server_info.config,
                tool.name,
                request.arguments
            )

            if response.success:
                self._record_success(tool.server_name)
            else:
                self._record_failure(
                    tool.server_name,
                    server_info.config.circuit_breaker_failures,
                    server_info.config.circuit_breaker_reset_seconds,
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
            
        except (httpx.RequestError, ValueError, TypeError) as e:
            if "tool" in locals() and "server_info" in locals():
                self._record_failure(
                    tool.server_name,
                    server_info.config.circuit_breaker_failures,
                    server_info.config.circuit_breaker_reset_seconds,
                )
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
        """Perform the HTTP request to the target MCP server call endpoint."""
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
        except httpx.RequestError as e:
            return ToolCallResponse(
                success=False,
                error=str(e),
                server_name=""
            )

    
    async def shutdown(self) -> None:
        """Close the shared HTTP client."""
        await self._client.aclose()
        logger.info("router_shutdown_complete")
