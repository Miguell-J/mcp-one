"""Tests for MCP one."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.models.schemas import MCPServerConfig, ToolCallRequest
from app.core.registry import MCPRegistry
from app.core.router import MCPRouter


class TestMCPRegistry:
    """Tests for MCPRegistry."""
    
    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        return MCPRegistry()
    
    @pytest.fixture
    def server_config(self):
        """Create a test server config."""
        return MCPServerConfig(
            name="test_server",
            url="http://localhost:3000",
            description="Test server",
            enabled=True,
            timeout=30,
            retry_attempts=3
        )
    
    @pytest.mark.asyncio
    async def test_register_server(self, registry, server_config):
        """Test server registration."""
        # Mock HTTP client
        registry._client = AsyncMock()
        registry._client.get.return_value.status_code = 200
        registry._client.get.return_value.json.return_value = {"tools": []}
        
        result = await registry.register_server(server_config)
        
        assert result is True
        assert "test_server" in registry.servers
        assert registry.servers["test_server"].config.name == "test_server"
    
    @pytest.mark.asyncio
    async def test_unregister_server(self, registry, server_config):
        """Test server unregistration."""
        # Register first
        registry._client = AsyncMock()
        await registry.register_server(server_config)
        
        # Then unregister
        result = await registry.unregister_server("test_server")
        
        assert result is True
        assert "test_server" not in registry.servers
    
    @pytest.mark.asyncio
    async def test_list_servers(self, registry, server_config):
        """Test listing servers."""
        registry._client = AsyncMock()
        await registry.register_server(server_config)
        
        servers = await registry.list_servers()
        
        assert len(servers) == 1
        assert servers[0].config.name == "test_server"
    
    @pytest.mark.asyncio
    async def test_list_tools(self, registry, server_config):
        """Test listing tools."""
        registry._client = AsyncMock()
        registry._client.get.return_value.status_code = 200
        registry._client.get.return_value.json.return_value = {
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"param1": "string"}
                }
            ]
        }
        
        await registry.register_server(server_config)
        await registry._refresh_server_tools("test_server")
        
        tools = await registry.list_tools()
        
        assert len(tools) == 1
        assert tools[0].name == "test_tool"
        assert tools[0].full_name == "test_server.test_tool"


class TestMCPRouter:
    """Tests for MCPRouter."""
    
    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        return MCPRegistry()
    
    @pytest.fixture
    def router(self, registry):
        """Create a test router."""
        return MCPRouter(registry)
    
    @pytest.mark.asyncio
    async def test_execute_tool_success(self, router, registry):
        """Test successful tool execution."""
        # Mock registry
        registry.get_tool = AsyncMock(return_value=MagicMock(
            name="test_tool",
            server_name="test_server",
            full_name="test_server.test_tool"
        ))
        
        registry.get_server_info = AsyncMock(return_value=MagicMock(
            status="online",
            config=MagicMock(
                url="http://localhost:3000",
                timeout=30
            )
        ))
        
        # Mock HTTP client
        router._client = AsyncMock()
        router._client.post.return_value.status_code = 200
        router._client.post.return_value.json.return_value = {
            "result": "Tool executed successfully"
        }
        
        request = ToolCallRequest(
            tool="test_server.test_tool",
            arguments={"param1": "value1"}
        )
        
        response = await router.execute_tool(request)
        
        assert response.success is True
        assert response.result == "Tool executed successfully"
        assert response.server_name == "test_server"
    
    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self, router, registry):
        """Test tool not found."""
        registry.get_tool = AsyncMock(return_value=None)
        
        request = ToolCallRequest(
            tool="nonexistent.tool",
            arguments={}
        )
        
        response = await router.execute_tool(request)
        
        assert response.success is False
        assert response.error == "tool_not_found"


class TestFastAPIEndpoints:
    """Tests for FastAPI endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "MCP Hub"
        assert "version" in data
    
    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "uptime_seconds" in data
