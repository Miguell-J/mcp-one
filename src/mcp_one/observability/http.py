"""HTTP trace ingress; MCP message propagation remains owned by the SDK."""

from opentelemetry import propagate, trace
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send


class TraceMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        parent = propagate.extract(Headers(scope=scope))
        with trace.get_tracer("mcp_one.http").start_as_current_span(
            "mcp-one.http",
            context=parent,
            kind=trace.SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ):
            await self.app(scope, receive, send)
