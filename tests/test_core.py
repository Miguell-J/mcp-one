import asyncio
from dataclasses import replace
from types import MappingProxyType

import httpx2
import pytest
from mcp import MCPError
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ServerCapabilities,
    TextContent,
    Tool,
    ToolAnnotations,
)
from pydantic import ValidationError

from mcp_one.application.circuit import CircuitBreaker, CircuitState
from mcp_one.application.policy import PolicyEngine
from mcp_one.application.service import Gateway
from mcp_one.config import CircuitBreakerPolicy, GatewayConfig, Limits, PolicyConfig
from mcp_one.domain.errors import ERROR_META, GATEWAY_META, ErrorCode, GatewayError
from mcp_one.domain.models import Discovery
from mcp_one.domain.naming import qualified_name
from mcp_one.domain.schema import bounded_json, validate_schema
from mcp_one.infrastructure.client import classify
from mcp_one.observability.metrics import PrometheusMetrics


def configuration(**updates):
    return GatewayConfig.model_validate(
        {
            "registry": {"minimum_refresh_seconds": 0.001},
            "servers": [
                {
                    "id": "test",
                    "namespace": "demo",
                    "transport": {"url": "http://localhost:1/mcp"},
                    **updates,
                }
            ],
        }
    )


class StubClient:
    def __init__(self):
        self.tools = (
            Tool(
                name="echo",
                input_schema={"type": "object"},
                annotations=ToolAnnotations(read_only_hint=True),
            ),
        )
        self.results = []
        self.calls = 0
        self.discoveries = 0
        self.closed = False
        self.error = None
        self.wait = None

    async def discover(self, server):
        self.discoveries += 1
        if self.wait:
            await self.wait.wait()
        if self.error:
            raise self.error
        return Discovery(self.tools, ServerCapabilities(), "2026-07-28")

    async def probe(self, server):
        if self.error:
            raise self.error

    async def call(self, server, route, params, discovery):
        self.calls += 1
        if self.wait:
            await self.wait.wait()
        result = self.results.pop(0) if self.results else CallToolResult(content=[])
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "name,expected",
    [
        ("echo", "demo.echo"),
        ("demo.echo", "demo.echo"),
        ("A_B", "demo.A_B"),
        ("system.echo", "demo.system.echo"),
    ],
)
def test_namespace(name, expected):
    assert qualified_name("demo", name) == expected


@pytest.mark.parametrize("name", ["", "bad name", "x/y", "x" * 129])
def test_invalid_names(name):
    with pytest.raises(ValueError):
        qualified_name("demo", name)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://u:secret@host/",
        "http://host/?token=x",
        "http://host/#fragment",
    ],
)
def test_config_rejects_secret_urls(url):
    with pytest.raises(ValidationError):
        configuration(transport={"url": url})


def test_config_defaults_duplicates_and_old_keys():
    data = configuration().model_dump()
    data["servers"] = [data["servers"][0], data["servers"][0]]
    with pytest.raises(ValidationError, match="duplicate"):
        GatewayConfig.model_validate(data)
    with pytest.raises(ValidationError):
        configuration(response_map={})
    with pytest.raises(ValidationError):
        configuration(timeout={"call_seconds": -1})
    config = GatewayConfig.model_validate(
        {
            "defaults": {"timeout": {"call_seconds": 120}},
            "servers": [
                {
                    "id": "x",
                    "namespace": "x",
                    "transport": {"url": "http://localhost/mcp"},
                    "timeout": {"connect_seconds": 2},
                }
            ],
        }
    )
    assert config.servers[0].timeout.call_seconds == 120
    assert config.servers[0].timeout.connect_seconds == 2


def test_policy_deny_wins():
    policy = PolicyEngine(PolicyConfig(allow=("demo.*",), deny=("*.mutate",)))
    assert policy.permits("demo.echo")
    assert not policy.permits("demo.mutate")
    assert not policy.permits("other.echo")


def test_circuit_single_probe_and_late_success_cannot_close():
    breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=1, reset_seconds=1))
    first = breaker.acquire(now=0)
    late = breaker.acquire(now=0)
    assert breaker.settle(first, failed=True, now=0)
    breaker.settle(late, failed=False)
    assert breaker.state == CircuitState.OPEN
    with pytest.raises(GatewayError):
        breaker.acquire(now=0.5)
    probe = breaker.acquire(now=1)
    with pytest.raises(GatewayError):
        breaker.acquire(now=1)
    breaker.abandon(probe)
    probe = breaker.acquire(now=1)
    breaker.settle(probe, failed=False)
    assert breaker.state == CircuitState.CLOSED


def test_circuit_failed_probe_and_disabled():
    breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=1, reset_seconds=1))
    breaker.settle(breaker.acquire(now=0), failed=True, now=0)
    assert breaker.settle(breaker.acquire(now=1), failed=True, now=1)
    assert breaker.state == CircuitState.OPEN
    disabled = CircuitBreaker(CircuitBreakerPolicy(enabled=False))
    assert not disabled.settle(disabled.acquire(), failed=True)
    assert disabled.can_attempt


@pytest.mark.parametrize(
    "error,code,infra",
    [
        (TimeoutError(), ErrorCode.CALL_TIMEOUT, True),
        (httpx2.ConnectTimeout("secret"), ErrorCode.CONNECT_TIMEOUT, True),
        (ConnectionRefusedError(), ErrorCode.SERVER_UNAVAILABLE, True),
        (MCPError(-32602, "caller"), ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, False),
        (MCPError(-32001, "timeout"), ErrorCode.CALL_TIMEOUT, True),
        (ValueError("payload secret"), ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, True),
        (ExceptionGroup("nested", [TimeoutError()]), ErrorCode.CALL_TIMEOUT, True),
    ],
)
def test_failure_classification(error, code, infra):
    classified = classify(error)
    assert classified.code == code and classified.infrastructure == infra
    assert "secret" not in classified.result().model_dump_json()


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "$ref": "https://evil.invalid"},
        {"type": "object", "$id": "https://evil.invalid"},
        {"type": "invalid"},
        {"type": "array"},
    ],
)
def test_schema_safety(schema):
    with pytest.raises(ValueError):
        validate_schema(schema, Limits())


def test_json_limits():
    with pytest.raises(ValueError):
        bounded_json({"secret": "a" * 100}, 10)
    with pytest.raises(ValueError):
        bounded_json({"a": {"b": 1}}, 100, 1)
    with pytest.raises(ValueError):
        bounded_json(float("nan"), 100)


@pytest.mark.parametrize(
    "authorized,readonly,expected", [(False, True, 1), (True, False, 1), (True, True, 2)]
)
async def test_retry_requires_operator_permission_and_safe_annotation(
    authorized, readonly, expected
):
    client = StubClient()
    if not readonly:
        client.tools = (client.tools[0].model_copy(update={"annotations": None}),)
    client.results = [
        GatewayError(ErrorCode.CALL_TIMEOUT, infrastructure=True, retryable=True),
        CallToolResult(content=[]),
    ]
    gateway = Gateway(
        configuration(
            retry={
                "call_attempts": 2,
                "safe_tools": ["echo"] if authorized else [],
                "backoff_seconds": 0,
            }
        ),
        client,
        PrometheusMetrics(),
    )
    async with gateway.lifespan():
        result = await gateway.router.call(CallToolRequestParams(name="demo.echo", arguments={}))
        assert result.meta[GATEWAY_META]["attempts"] == expected
        assert client.calls == expected
        assert result.is_error == (expected == 1)
    assert client.closed


async def test_snapshot_swap_collision_and_stale_expiry():
    client = StubClient()
    gateway = Gateway(configuration(retry={"discovery_attempts": 1}), client, PrometheusMetrics())
    async with gateway.lifespan():
        old = gateway.registry.snapshot
        client.wait = asyncio.Event()
        await asyncio.sleep(0.002)
        pending = asyncio.create_task(gateway.refresh())
        await asyncio.sleep(0.002)
        assert gateway.registry.snapshot is old
        client.tools = (client.tools[0].model_copy(update={"name": "new"}),)
        client.wait.set()
        await pending
        assert "demo.echo" in old.routes
        assert set(gateway.registry.snapshot.routes) == {"demo.new"}
        assert isinstance(old.routes, MappingProxyType)
        client.wait = None
        client.error = GatewayError(
            ErrorCode.SERVER_UNAVAILABLE, infrastructure=True, retryable=True
        )
        await asyncio.sleep(0.002)
        await gateway.refresh()
        assert set(gateway.registry.snapshot.routes) == {"demo.new"}
        catalog = gateway.registry.snapshot.servers["test"]
        assert not gateway.registry.usable(replace(catalog, last_success=-10000))


async def test_domain_error_preserved_without_retries_and_validation_rejected():
    client = StubClient()
    result = CallToolResult(
        content=[TextContent(type="text", text="domain")],
        structured_content={"opaque": [1]},
        is_error=True,
        _meta={"other.example/result": True},
    )
    client.results = [result]
    gateway = Gateway(
        configuration(retry={"call_attempts": 3, "safe_tools": ["echo"]}),
        client,
        PrometheusMetrics(),
    )
    async with gateway.lifespan():
        returned = await gateway.router.call(CallToolRequestParams(name="demo.echo", arguments={}))
        assert (
            returned.content == result.content
            and returned.structured_content == result.structured_content
        )
        assert returned.meta["other.example/result"] is True
        assert GATEWAY_META not in result.meta
        assert returned.is_error and client.calls == 1
        assert gateway.router.circuits["test"].failures == 0


async def test_lifecycle_cancels_background_and_inflight_probe():
    client = StubClient()
    gateway = Gateway(
        configuration(circuit_breaker={"failure_threshold": 1, "reset_seconds": 0.01}),
        client,
        PrometheusMetrics(),
    )
    async with gateway.lifespan():
        breaker = gateway.router.circuits["test"]
        breaker.settle(breaker.acquire(), failed=True, now=0)
        client.wait = asyncio.Event()
        task = asyncio.create_task(gateway.router.call(CallToolRequestParams(name="demo.echo")))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert gateway.router.active == 0 and breaker.can_attempt
    assert client.closed
    assert not any(t.get_name() == "mcp-one-refresh" for t in asyncio.all_tasks())


async def test_policy_blocks_list_and_router_without_execution():
    client = StubClient()
    data = configuration().model_dump()
    data["policy"] = {"deny": ["demo.*"]}
    gateway = Gateway(GatewayConfig.model_validate(data), client, PrometheusMetrics())
    async with gateway.lifespan():
        result = await gateway.router.call(CallToolRequestParams(name="demo.echo"))
        assert result.meta[ERROR_META]["code"] == "POLICY_DENIED"
        assert client.calls == 0 and not gateway.ready


async def test_unnegotiated_continuation_never_executes_an_implicit_second_round():
    client = StubClient()
    client.results = [CallToolResult(content=[], result_type="input_required")]
    gateway = Gateway(configuration(), client, PrometheusMetrics())
    async with gateway.lifespan():
        result = await gateway.router.call(CallToolRequestParams(name="demo.echo"))
        assert result.meta[ERROR_META]["code"] == "POLICY_DENIED"
        assert client.calls == 1 and gateway.router.circuits["test"].failures == 0


async def test_refresh_coalesces_and_partial_catalog_remains_ready():
    class PartialClient(StubClient):
        async def discover(self, server):
            if server.id == "offline":
                raise GatewayError(ErrorCode.SERVER_UNAVAILABLE, infrastructure=True)
            return await super().discover(server)

    client = PartialClient()
    data = configuration().model_dump()
    data["registry"]["minimum_refresh_seconds"] = 1
    data["servers"] = [*data["servers"], {**data["servers"][0], "id": "offline", "namespace": "x"}]
    gateway = Gateway(GatewayConfig.model_validate(data), client, PrometheusMetrics())
    async with gateway.lifespan():
        await asyncio.gather(*(gateway.refresh() for _ in range(5)))
        assert client.discoveries == 1
        assert gateway.ready and set(gateway.registry.snapshot.routes) == {"demo.echo"}
        assert gateway.registry.snapshot.servers["offline"].error == "SERVER_UNAVAILABLE"


async def test_automatic_refresh_probe_recovery_and_overload():
    client = StubClient()
    data = configuration(health={"interval_seconds": 0.05}).model_dump()
    data["registry"]["refresh_interval_seconds"] = 0.05
    data["limits"]["concurrent_calls"] = 1
    gateway = Gateway(GatewayConfig.model_validate(data), client, PrometheusMetrics())
    async with gateway.lifespan():
        client.error = GatewayError(ErrorCode.SERVER_UNAVAILABLE, infrastructure=True)
        await gateway._probe("test")
        assert not gateway.ready
        client.error = None
        for _ in range(50):
            await asyncio.sleep(0.01)
            if client.discoveries > 1 and gateway.ready:
                break
        assert client.discoveries > 1 and gateway.ready
        client.wait = asyncio.Event()
        call = asyncio.create_task(gateway.router.call(CallToolRequestParams(name="demo.echo")))
        await asyncio.sleep(0)
        result = await gateway.router.call(CallToolRequestParams(name="demo.echo"))
        assert result.meta[ERROR_META]["code"] == "OVERLOADED"
        client.wait.set()
        assert not (await call).is_error
    assert client.closed
