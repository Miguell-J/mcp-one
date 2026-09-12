import asyncio
import json

import httpx
import httpx2
import pytest
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client

from mcp_one.domain.errors import ERROR_META, GATEWAY_META

pytestmark = [pytest.mark.contract, pytest.mark.integration, pytest.mark.e2e]


async def refresh(topology):
    await asyncio.sleep(0.02)  # Respect the configured anti-hammering refresh floor.
    async with httpx.AsyncClient() as http:
        response = await http.post(topology.url.removesuffix("/mcp") + "/refresh")
        assert response.status_code == 200
        return response.json()


async def test_full_native_transparency_and_discovery(topology):
    sent = []

    async def observe(request):
        sent.append(dict(request.headers))

    async with httpx2.AsyncClient(event_hooks={"request": [observe]}) as http:
        async with Client(
            streamable_http_client(topology.url, http_client=http), cache=None
        ) as client:
            assert client.protocol_version == "2026-07-28"
            assert client.session.discover_result is not None
            assert client.server_capabilities.tools is not None
            assert client.server_capabilities.resources is None
            listing = await client.list_tools()
            assert listing.ttl_ms == 0 and listing.cache_scope == "private"
            async with Client(topology.downstream, cache=None) as direct:
                downstream_tools = {t.name: t for t in (await direct.list_tools()).tools}
                for tool in listing.tools:
                    original = downstream_tools[tool.name.removeprefix("demo.")]
                    assert tool.model_copy(update={"name": original.name}) == original
                original_result = await direct.call_tool("echo", {"message": "transparent"})
            result = await client.call_tool("demo.echo", {"message": "transparent"})
            assert result.content == original_result.content
            assert result.structured_content == original_result.structured_content
            assert result.is_error == original_result.is_error
            assert result.meta["test.example/opaque"] == original_result.meta["test.example/opaque"]
            assert result.meta[GATEWAY_META]["traceId"] == result.meta["test.example/trace"]
            assert result.meta[GATEWAY_META]["attempts"] == 1
            assert "success" not in result.model_dump()
    assert any(h.get("mcp-method") == "server/discover" for h in sent)
    call = next(h for h in sent if h.get("mcp-method") == "tools/call")
    assert call["mcp-name"] == "demo.echo"
    assert call["mcp-protocol-version"] == "2026-07-28"
    assert "mcp-session-id" not in call


async def test_domain_errors_do_not_open_circuit(topology):
    async with Client(topology.url, cache=None) as client:
        for _ in range(4):
            result = await client.call_tool("demo.domain", {"message": "domain"})
            assert result.is_error and result.meta["test.example/domain"] == {"code": "DOMAIN"}
        assert not (await client.call_tool("demo.echo", {"message": "works"})).is_error
    async with httpx.AsyncClient() as http:
        status = (await http.get(topology.url.removesuffix("/mcp") + "/status")).json()
        assert status["servers"]["fixture"]["circuit"] == "CLOSED"


async def test_timeout_no_mutation_retry_and_half_open_recovery(topology):
    topology.mode("slow")
    async with Client(topology.url, cache=None) as client:
        for _ in range(2):
            result = await client.call_tool("demo.mutate", {"message": "once"})
            assert result.meta[ERROR_META]["code"] == "CALL_TIMEOUT"
            assert result.meta[GATEWAY_META]["attempts"] == 1
        assert json.loads(topology.state.read_text())["calls"] == 2
        blocked = await client.call_tool("demo.echo", {"message": "blocked"})
        assert blocked.meta[ERROR_META]["code"] == "CIRCUIT_OPEN"
        assert blocked.meta[GATEWAY_META]["attempts"] == 0
        topology.mode("healthy")
        await asyncio.sleep(0.25)
        assert not (await client.call_tool("demo.echo", {"message": "recovered"})).is_error


@pytest.mark.parametrize(
    "mode", ["duplicate", "invalid_schema", "external_ref", "repeated_cursor", "discovery_failure"]
)
async def test_invalid_catalog_withdrawn_and_recovered(topology, mode):
    topology.mode(mode)
    status = await refresh(topology)
    assert status["servers"]["fixture"]["stale"]
    async with Client(topology.url, cache=None) as client:
        assert (await client.list_tools()).tools == []
        topology.mode("healthy")
        await refresh(topology)
        assert len((await client.list_tools()).tools) == 3
        assert not (await client.call_tool("demo.echo", {"message": "recovered"})).is_error


@pytest.mark.parametrize("mode", ["bad_output", "malformed", "failing"])
async def test_bad_response_is_infrastructure(topology, mode):
    topology.mode(mode)
    async with Client(topology.url, cache=None) as client:
        result = await client.call_tool("demo.echo", {"message": "bad"})
        assert result.is_error
        assert result.meta[ERROR_META]["category"] == "infrastructure"
        assert result.meta[GATEWAY_META]["attempts"] == 1


async def test_offline_catalog_retained_and_readiness_recovers(topology):
    topology.stop("downstream")
    status = await refresh(topology)
    assert status["tools"] == 3 and not status["ready"]
    async with Client(topology.url, cache=None) as client:
        result = await client.call_tool("demo.echo", {"message": "offline"})
        assert result.meta[ERROR_META]["code"] == "SERVER_UNAVAILABLE"
        topology.start("downstream")
        assert (await refresh(topology))["ready"]
        assert not (await client.call_tool("demo.echo", {"message": "recovered"})).is_error


async def test_unknown_invalid_and_metadata_collision(topology):
    async with Client(topology.url, cache=None) as client:
        with pytest.raises(MCPError) as error:
            await client.call_tool("demo.missing", {})
        assert error.value.code == -32602
        invalid = await client.call_tool("demo.echo", {"message": 5})
        assert invalid.meta[ERROR_META]["code"] == "INVALID_ARGUMENT"
        assert invalid.meta[GATEWAY_META]["attempts"] == 0
        topology.mode("nested_gateway")
        result = await client.call_tool(
            "demo.echo",
            {"message": "nested"},
            meta={"test.example/request": "preserve"},
        )
        assert result.meta[GATEWAY_META] == {"earlier": True}
        assert result.meta[GATEWAY_META + "/hop-1"]["attempts"] == 1
        assert result.meta["test.example/request-meta"]["test.example/request"] == "preserve"


async def test_sdk_legacy_and_administrative_endpoints(topology):
    async with Client(topology.url, mode="legacy", cache=None) as client:
        assert client.protocol_version != "2026-07-28"
        assert not (await client.call_tool("demo.echo", {"message": "legacy"})).is_error
    async with httpx.AsyncClient() as http:
        base = topology.url.removesuffix("/mcp")
        assert (await http.get(base + "/ready")).status_code == 200
        assert (await http.get(base + "/tools")).status_code == 410
        assert (await http.post(base + "/call", json={})).status_code == 410
        metrics = await http.get(base + "/metrics")
        assert "text/plain" in metrics.headers["content-type"]
        assert "mcp_one_tool_calls_total" in metrics.text


async def test_real_safe_retry_is_opt_in(topology):
    topology.stop("gateway")
    topology.config["servers"][0]["retry"] = {
        "discovery_attempts": 1,
        "call_attempts": 2,
        "safe_tools": ["echo"],
        "backoff_seconds": 0,
    }
    topology.start("gateway")
    topology.mode("once_slow")
    async with Client(topology.url, cache=None) as client:
        result = await client.call_tool("demo.echo", {"message": "safe retry"})
        assert not result.is_error
        assert result.meta[GATEWAY_META]["attempts"] == 2
        assert json.loads(topology.state.read_text())["calls"] == 2
        topology.mode("once_slow")
        mutation = await client.call_tool("demo.mutate", {"message": "no retry"})
        assert mutation.is_error
        assert mutation.meta[GATEWAY_META]["attempts"] == 1
        assert json.loads(topology.state.read_text())["calls"] == 1


async def test_process_dies_during_call_and_no_duplicate_execution(topology):
    topology.mode("slow")
    async with Client(topology.url, cache=None) as client:
        call = asyncio.create_task(client.call_tool("demo.mutate", {"message": "once"}))
        for _ in range(50):
            if json.loads(topology.state.read_text())["calls"]:
                break
            await asyncio.sleep(0.01)
        process = topology.processes["downstream"]
        process.kill()
        await asyncio.to_thread(process.wait, timeout=3)
        result = await call
        assert result.is_error and result.meta[ERROR_META]["category"] == "infrastructure"
        assert result.meta[GATEWAY_META]["attempts"] == 1
        assert json.loads(topology.state.read_text())["calls"] == 1


async def test_explicit_w3c_parent_reaches_downstream(topology):
    trace_id = "1234567890abcdef1234567890abcdef"
    async with httpx2.AsyncClient(
        headers={"traceparent": f"00-{trace_id}-1234567890abcdef-01"}
    ) as http:
        async with Client(
            streamable_http_client(topology.url, http_client=http), cache=None
        ) as client:
            result = await client.call_tool("demo.echo", {"message": "trace"})
            assert result.meta[GATEWAY_META]["traceId"] == trace_id
            assert result.meta["test.example/trace"] == trace_id


async def test_http_pool_does_not_share_cookie_sessions(topology):
    topology.mode("cookies")
    await refresh(topology)
    for _ in range(2):
        async with Client(topology.url, cache=None) as client:
            result = await client.call_tool("demo.echo", {"message": "independent caller"})
            assert not result.is_error
    assert json.loads(topology.state.read_text())["calls"] == 2


async def test_downstream_auth_reference_and_safe_diagnostics(topology, monkeypatch):
    topology.mode("auth")
    async with Client(topology.url, cache=None) as client:
        denied = await client.call_tool("demo.echo", {"message": "private payload"})
        assert denied.meta[ERROR_META]["code"] == "AUTH_FAILED"
        assert denied.meta[GATEWAY_META]["attempts"] == 1
    async with httpx.AsyncClient() as http:
        base = topology.url.removesuffix("/mcp")
        status = (await http.get(base + "/status")).json()
        assert status["servers"]["fixture"]["circuit"] == "CLOSED"
        assert (await http.get(base + "/ready")).status_code == 503
    topology.stop("gateway")
    monkeypatch.setenv("FIXTURE_DOWNSTREAM_TOKEN", "fixture-downstream")
    topology.config["servers"][0]["auth"] = {"bearer_token_env": "FIXTURE_DOWNSTREAM_TOKEN"}
    topology.start("gateway")
    async with Client(topology.url, cache=None) as client:
        assert not (await client.call_tool("demo.echo", {"message": "private payload"})).is_error
    topology.stop("gateway")
    logs = (topology.directory / "gateway.log").read_text()
    assert "fixture-downstream" not in logs and "private payload" not in logs
