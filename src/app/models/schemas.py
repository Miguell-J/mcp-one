"""Pydantic models for MCP Hub."""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, HttpUrl, validator
from enum import Enum

class MCPServerConfig(BaseModel):
    name: str
    url: HttpUrl
    description: Optional[str] = None
    enabled: bool = True
    timeout: int = 30
    retry_attempts: int = 3

    endpoints: Dict[str, str] = {
        "health": "/health",
        "tools": "/tools",
        "call": "/call"
    }

    response_map: Dict[str, str] = {
        "tools_key": "tools",
        "tool_name_field": "name",
        "tool_desc_field": "description"
    }

    payload_map: Dict[str, str] = {
        "tool_field": "tool",
        "args_field": "arguments"
    }


class ServerStatus(str, Enum):
    """Status do servidor MCP."""
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    CONNECTING = "connecting"


class MCPServerInfo(BaseModel):
    """Informações de um servidor MCP."""
    config: MCPServerConfig
    status: ServerStatus = ServerStatus.OFFLINE
    last_seen: Optional[str] = None
    error_message: Optional[str] = None
    tools_count: int = 0
    response_time_ms: Optional[float] = None


class ToolSchema(BaseModel):
    """Schema de uma ferramenta MCP."""
    name: str = Field(..., description="Nome da ferramenta")
    description: str = Field("", description="Descrição da ferramenta")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    server_name: str = Field(..., description="Nome do servidor que possui a ferramenta")
    full_name: str = Field(..., description="Nome completo: server.tool")
    
    @validator('full_name', pre=True, always=True)
    def generate_full_name(cls, v, values):
        if 'server_name' in values and 'name' in values:
            return f"{values['server_name']}.{values['name']}"
        return v


class ToolCallRequest(BaseModel):
    """Request para chamar uma ferramenta."""
    tool: str = Field(..., description="Nome completo da ferramenta (server.tool)")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Argumentos da ferramenta")
    
    @validator('tool')
    def validate_tool_name(cls, v):
        if '.' not in v:
            raise ValueError('Nome da ferramenta deve estar no formato: server.tool')
        return v


class ToolCallResponse(BaseModel):
    """Response de uma chamada de ferramenta."""
    success: bool = Field(..., description="Se a chamada foi bem-sucedida")
    result: Any = Field(None, description="Resultado da ferramenta")
    error: Optional[str] = Field(None, description="Mensagem de erro se houver")
    execution_time_ms: Optional[float] = Field(None, description="Tempo de execução")
    server_name: str = Field(..., description="Servidor que executou a ferramenta")


class HubStatus(BaseModel):
    """Status geral do Hub."""
    version: str = Field(..., description="Versão do Hub")
    uptime_seconds: float = Field(..., description="Tempo de execução em segundos")
    servers_count: int = Field(..., description="Número de servidores configurados")
    servers_online: int = Field(..., description="Número de servidores online")
    tools_count: int = Field(..., description="Total de ferramentas disponíveis")
    last_refresh: str = Field(..., description="Último refresh dos servidores")


class ListToolsResponse(BaseModel):
    """Response da listagem de ferramentas."""
    tools: List[ToolSchema] = Field(..., description="Lista de ferramentas disponíveis")
    total_count: int = Field(..., description="Total de ferramentas")
    servers_online: int = Field(..., description="Servidores online")
    last_updated: str = Field(..., description="Última atualização")


class ErrorResponse(BaseModel):
    """Response de erro padronizada."""
    error: str = Field(..., description="Tipo do erro")
    message: str = Field(..., description="Mensagem do erro")
    details: Optional[Dict[str, Any]] = Field(None, description="Detalhes adicionais")
    timestamp: str = Field(..., description="Timestamp do erro")
