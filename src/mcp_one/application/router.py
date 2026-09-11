import asyncio
from time import monotonic
from typing import Any
from uuid import uuid4

import structlog
from jsonschema import ValidationError
from mcp import MCPError
from mcp.types import CallToolRequestParams, CallToolResult
from opentelemetry import trace

from mcp_one.application.circuit import CircuitBreaker
from mcp_one.application.policy import PolicyEngine
from mcp_one.application.ports import MCPTransportClient, Metrics
from mcp_one.application.registry import Registry
from mcp_one.config import GatewayConfig
from mcp_one.domain.errors import GATEWAY_META, ErrorCode, GatewayError
from mcp_one.domain.models import ServerState
from mcp_one.domain.schema import bounded_json, validate_instance

log = structlog.get_logger()


def attach_metadata(result: CallToolResult, metadata: dict[str, Any]) -> CallToolResult:
    meta = dict(result.meta or {})
    if GATEWAY_META not in meta:
        meta[GATEWAY_META] = metadata
    else:
        # Nested gateways must not overwrite even their own namespace at an earlier hop.
        index = 1
        while f"{GATEWAY_META}/hop-{index}" in meta:
            index += 1
        meta[f"{GATEWAY_META}/hop-{index}"] = metadata
    return result.model_copy(update={"meta": meta})


class Router:
    def __init__(
        self,
        config: GatewayConfig,
        registry: Registry,
        client: MCPTransportClient,
        metrics: Metrics,
    ):
        self.config, self.registry, self.client, self.metrics = config, registry, client, metrics
        self.policy = PolicyEngine(config.policy)
        self.circuits = {
            s.id: CircuitBreaker(s.circuit_breaker) for s in config.servers if s.enabled
        }
        self.reachable: dict[str, bool] = {}
        self.active = 0

    async def call(self, params: CallToolRequestParams) -> CallToolResult:
        started = monotonic()
        request_id = str(uuid4())
        snapshot = self.registry.snapshot
        route = snapshot.routes.get(params.name)
        if route is None:
            self.metrics.increment("tool_calls", outcome="unknown_tool")
            raise MCPError(-32602, "TOOL_NOT_FOUND", data={"requestId": request_id})
        server = snapshot.servers[route.server_id]
        circuit = self.circuits[route.server_id]
        attempts = 0
        outcome = "success"
        permit = None
        admitted = False
        with trace.get_tracer(__name__).start_as_current_span("mcp_one.route"):
            try:
                if not self.policy.permits(route.upstream_name):
                    raise GatewayError(ErrorCode.POLICY_DENIED)
                bounded_json(params.arguments or {}, self.config.limits.request_bytes)
                try:
                    validate_instance(route.tool.input_schema, params.arguments or {})
                except ValidationError:
                    raise GatewayError(ErrorCode.INVALID_ARGUMENT) from None
                if params.request_state is not None or params.input_responses is not None:
                    raise GatewayError(ErrorCode.POLICY_DENIED)
                if not self.registry.usable(server) or server.discovery is None:
                    raise GatewayError(ErrorCode.SERVER_UNAVAILABLE, infrastructure=True)
                if self.active >= self.config.limits.concurrent_calls:
                    raise GatewayError(ErrorCode.OVERLOADED)
                permit = circuit.acquire()
                self.active += 1
                admitted = True
                annotations = route.tool.annotations
                safe = (
                    route.downstream_name in server.config.retry.safe_tools
                    and annotations is not None
                    and (annotations.read_only_hint is True or annotations.idempotent_hint is True)
                )
                maximum = server.config.retry.call_attempts if safe and not permit.probe else 1
                for attempt in range(maximum):
                    attempts += 1
                    try:
                        result = await self.client.call(
                            server.config, route, params, server.discovery
                        )
                        if result.result_type != "complete":
                            # This edge does not negotiate continuations or result extensions.
                            raise GatewayError(ErrorCode.POLICY_DENIED)
                        try:
                            bounded_json(
                                result.model_dump(mode="json", by_alias=True),
                                self.config.limits.response_bytes,
                            )
                            if not result.is_error and route.tool.output_schema is not None:
                                validate_instance(
                                    route.tool.output_schema, result.structured_content
                                )
                        except Exception:
                            raise GatewayError(
                                ErrorCode.DOWNSTREAM_PROTOCOL_ERROR, infrastructure=True
                            ) from None
                        self.reachable[route.server_id] = True
                        # Domain errors still mean the downstream completed the operation.
                        assert permit is not None
                        circuit.settle(permit, failed=False)
                        permit = None
                        outcome = "domain_error" if result.is_error else "success"
                        break
                    except GatewayError as exc:
                        if exc.code == ErrorCode.AUTH_FAILED:
                            self.reachable[route.server_id] = False
                        if exc.infrastructure:
                            self.metrics.increment(
                                "infra_failures", route.server_id, exc.code.value
                            )
                            self.reachable[route.server_id] = False
                        if exc.code in {ErrorCode.CALL_TIMEOUT, ErrorCode.CONNECT_TIMEOUT}:
                            self.metrics.increment("timeouts", route.server_id, exc.code.value)
                        if not exc.retryable or attempt + 1 == maximum:
                            assert permit is not None
                            if circuit.settle(permit, failed=exc.infrastructure):
                                self.metrics.increment("circuit_opens", route.server_id)
                            permit = None
                            raise
                        await asyncio.sleep(server.config.retry.backoff_seconds * (attempt + 1))
            except GatewayError as exc:
                result = exc.result()
                outcome = exc.code.value
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except Exception:
                result = GatewayError(ErrorCode.INTERNAL_ERROR).result()
                outcome = "INTERNAL_ERROR"
            finally:
                if permit is not None:
                    circuit.abandon(permit)
                if admitted:
                    self.active -= 1
                self.metrics.increment("tool_calls", route.server_id, outcome)
                self.metrics.observe("tool_latency_seconds", monotonic() - started, route.server_id)
            context = trace.get_current_span().get_span_context()
            metadata = {
                "requestId": request_id,
                "server": route.server_id,
                "tool": route.upstream_name,
                "durationMs": round((monotonic() - started) * 1000, 3),
                "attempts": attempts,
                "cache": "disabled",
                "cached": False,
                "route": {
                    "serverId": route.server_id,
                    "downstreamName": route.downstream_name,
                    "catalogGeneration": snapshot.generation,
                },
                "traceId": f"{context.trace_id:032x}",
                "spanId": f"{context.span_id:016x}",
            }
            log.info("gateway_call", **metadata, isError=result.is_error, outcome=outcome)
            return attach_metadata(result, metadata)

    def ready_servers(self) -> int:
        return sum(
            self.registry.usable(server)
            and server.state == ServerState.ONLINE
            and self.reachable.get(server_id, True)
            and self.circuits[server_id].can_attempt
            and any(self.policy.permits(r.upstream_name) for r in server.routes)
            for server_id, server in self.registry.snapshot.servers.items()
        )
