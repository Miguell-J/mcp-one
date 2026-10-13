"""Deterministic admission, snapshot and cancellation regression tests."""

import asyncio

import pytest
from mcp.types import CallToolRequestParams, CallToolResult, Tool
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client.parser import text_string_to_metric_families

from mcp_one.application.service import Gateway
from mcp_one.config import GatewayConfig
from mcp_one.domain.errors import ERROR_META, GATEWAY_META, ErrorCode, GatewayError
from mcp_one.observability.metrics import PrometheusMetrics
from tests.test_core import StubClient, configuration


def value(metrics, name, **labels):
    return sum(
        sample.value
        for family in text_string_to_metric_families(metrics.render().decode())
        for sample in family.samples
        if sample.name == name and all(sample.labels.get(k) == v for k, v in labels.items())
    )


class BlockingClient(StubClient):
    def __init__(self, target=1):
        super().__init__()
        self.target = target
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.routes = []

    async def call(self, server, route, params, discovery):
        self.calls += 1
        self.routes.append(route)
        if self.calls >= self.target:
            self.entered.set()
        await self.release.wait()
        return CallToolResult(content=[], structured_content={"generation": "old"})


async def test_high_concurrency_is_bounded_and_cancelled_slots_are_reusable():
    client = BlockingClient(target=8)
    data = configuration().model_dump()
    data["limits"]["concurrent_calls"] = 8
    metrics = PrometheusMetrics()
    gateway = Gateway(GatewayConfig.model_validate(data), client, metrics)
    async with gateway.lifespan():
        tasks = [
            asyncio.create_task(gateway.router.call(CallToolRequestParams(name="demo.echo")))
            for _ in range(8)
        ]
        try:
            await asyncio.wait_for(client.entered.wait(), 2)
            rejected = await asyncio.gather(
                *(gateway.router.call(CallToolRequestParams(name="demo.echo")) for _ in range(64))
            )
            assert client.calls == 8
            assert all(r.meta[ERROR_META]["code"] == "OVERLOADED" for r in rejected)
            assert all(r.meta[GATEWAY_META]["attempts"] == 0 for r in rejected)
            assert value(metrics, "mcp_one_active_calls") == 8
            for task in tasks[:4]:
                task.cancel()
            await asyncio.gather(*tasks[:4], return_exceptions=True)
            assert gateway.router.active == 4
            assert value(metrics, "mcp_one_active_calls") == 4
            client.release.set()
            assert all(not r.is_error for r in await asyncio.gather(*tasks[4:]))
            assert not (await gateway.router.call(CallToolRequestParams(name="demo.echo"))).is_error
            assert gateway.router.active == value(metrics, "mcp_one_active_calls") == 0
            assert value(metrics, "mcp_one_tool_calls_total", outcome="cancelled") == 4
            assert gateway.router.circuits["test"].failures == 0
        finally:
            client.release.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    assert client.closed


async def test_admitted_call_keeps_schema_and_generation_during_catalog_swap():
    client = BlockingClient()
    client.tools = (
        Tool(
            name="echo",
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "properties": {"generation": {"const": "old"}},
                "required": ["generation"],
            },
        ),
    )
    gateway = Gateway(configuration(), client, PrometheusMetrics())
    async with gateway.lifespan():
        original = gateway.registry.snapshot
        pending = asyncio.create_task(gateway.router.call(CallToolRequestParams(name="demo.echo")))
        try:
            await asyncio.wait_for(client.entered.wait(), 2)
            client.tools = (
                client.tools[0].model_copy(
                    update={
                        "output_schema": {
                            "type": "object",
                            "properties": {"generation": {"const": "new"}},
                            "required": ["generation"],
                        }
                    }
                ),
            )
            gateway.registry._last_refresh = float("-inf")
            await gateway.refresh()
            assert gateway.registry.snapshot.generation > original.generation
            client.release.set()
            result = await pending
            assert not result.is_error
            assert result.meta[GATEWAY_META]["route"]["catalogGeneration"] == original.generation
            assert client.routes[0] is original.routes["demo.echo"]
            newer = await gateway.router.call(CallToolRequestParams(name="demo.echo"))
            assert newer.meta[ERROR_META]["code"] == "DOWNSTREAM_PROTOCOL_ERROR"
        finally:
            client.release.set()
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_cancel_during_authorized_backoff_does_not_replay_or_settle_failure(monkeypatch):
    sleeping = asyncio.Event()

    async def backoff(seconds):
        sleeping.set()
        await asyncio.Event().wait()

    client = StubClient()
    client.results = [GatewayError(ErrorCode.CALL_TIMEOUT, infrastructure=True, retryable=True)]
    gateway = Gateway(
        configuration(retry={"call_attempts": 3, "safe_tools": ["echo"]}),
        client,
        PrometheusMetrics(),
    )
    async with gateway.lifespan():
        # Patch the router's reference only, without changing asyncio globally.
        import types

        monkeypatch.setattr(
            "mcp_one.application.router.asyncio",
            types.SimpleNamespace(
                sleep=backoff,
                CancelledError=asyncio.CancelledError,
            ),
        )
        task = asyncio.create_task(gateway.router.call(CallToolRequestParams(name="demo.echo")))
        try:
            await asyncio.wait_for(sleeping.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert client.calls == 1 and gateway.router.active == 0
            assert gateway.router.circuits["test"].failures == 0
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_cancelled_trace_and_log_have_no_payload(monkeypatch, capsys):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr("mcp_one.application.router.trace.get_tracer", provider.get_tracer)
    client = BlockingClient()
    metrics = PrometheusMetrics()
    gateway = Gateway(configuration(), client, metrics)
    try:
        async with gateway.lifespan():
            task = asyncio.create_task(
                gateway.router.call(
                    CallToolRequestParams(
                        name="demo.echo",
                        arguments={"private": "sensitive-test-value"},
                    )
                )
            )
            try:
                await asyncio.wait_for(client.entered.wait(), 2)
                task.cancel("sensitive-cancel-reason")
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["mcp_one.outcome"] == "cancelled"
        assert spans[0].attributes["mcp_one.attempts"] == 1
        assert value(metrics, "mcp_one_tool_calls_total", outcome="cancelled") == 1
        output = capsys.readouterr().out
        assert "gateway_call" in output and "cancelled" in output
        assert "sensitive-test-value" not in output + str(spans[0].attributes)
        assert "sensitive-cancel-reason" not in output + str(spans[0].events)
        assert value(metrics, "mcp_one_active_calls") == 0
        assert value(metrics, "mcp_one_process_resident_memory_bytes") > 0
    finally:
        provider.shutdown()
