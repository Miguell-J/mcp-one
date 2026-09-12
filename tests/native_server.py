"""Real official SDK fixture. Faults are confined to test processes."""

import asyncio
import json
import os
from pathlib import Path

from mcp import MCPError
from mcp.server import Server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations
from opentelemetry import trace
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_one.observability.telemetry import configure


def create_app():
    configure()
    state = Path(os.environ["FIXTURE_STATE"])

    def read():
        return json.loads(state.read_text())

    schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }
    tool = Tool(
        name="echo",
        description="Preserve native definitions.",
        input_schema=schema,
        output_schema=schema,
        annotations=ToolAnnotations(read_only_hint=True),
        _meta={"test.example/definition": {"nested": [1, 2]}},
    )

    async def listing(ctx, params):
        mode = read().get("mode")
        if mode == "discovery_failure":
            raise MCPError(-32603, "fixture discovery failure")
        if mode == "duplicate":
            return ListToolsResult(tools=[tool, tool.model_copy(update={"name": "demo.echo"})])
        if mode == "invalid_schema":
            return ListToolsResult(
                tools=[tool.model_copy(update={"input_schema": {"type": "invalid"}})]
            )
        if mode == "external_ref":
            return ListToolsResult(
                tools=[
                    tool.model_copy(
                        update={
                            "input_schema": {
                                "type": "object",
                                "$ref": "http://127.0.0.1:1/secret",
                            }
                        }
                    )
                ]
            )
        if mode == "repeated_cursor":
            return ListToolsResult(tools=[], next_cursor="same")
        tools = [
            tool,
            tool.model_copy(update={"name": "mutate", "annotations": None}),
            tool.model_copy(update={"name": "domain"}),
        ]
        return ListToolsResult(tools=tools, ttl_ms=0)

    async def call(ctx, params):
        data = read()
        data["calls"] = data.get("calls", 0) + 1
        state.write_text(json.dumps(data))
        mode = data.get("mode")
        if mode == "slow" or (mode == "once_slow" and data["calls"] == 1):
            await asyncio.sleep(5)
        if mode == "failing":
            raise MCPError(-32603, "fixture infrastructure failure")
        if mode == "invalid_arguments":
            raise MCPError(-32602, "fixture caller failure")
        if params.name == "domain":
            return CallToolResult(
                content=[TextContent(type="text", text="domain failed")],
                is_error=True,
                _meta={"test.example/domain": {"code": "DOMAIN"}},
            )
        context = trace.get_current_span().get_span_context()
        result = CallToolResult(
            content=[TextContent(type="text", text="preserved content")],
            structured_content={"message": 42} if mode == "bad_output" else params.arguments,
            _meta={
                "test.example/opaque": {"list": [1, {"two": True}]},
                "test.example/trace": f"{context.trace_id:032x}",
                "test.example/request-meta": params.meta or {},
            },
        )
        if mode == "nested_gateway":
            result.meta["io.github.miguell-j.mcp-one/gateway"] = {"earlier": True}
        return result

    async def health(request):
        return JSONResponse({"alive": True})

    app = Server("native-test", on_list_tools=listing, on_call_tool=call).streamable_http_app(
        stateless_http=True,
        json_response=True,
        custom_starlette_routes=[Route("/health", health)],
    )

    async def corruptible(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            mode = read().get("mode")
            headers = dict(scope["headers"])
            if (mode == "cookies" and b"cookie" in headers) or (
                mode == "auth" and headers.get(b"authorization") != b"Bearer fixture-downstream"
            ):
                await JSONResponse({"error": "fixture rejected"}, status_code=401)(
                    scope, receive, send
                )
                return

        async def corrupt(message):
            if read().get("mode") == "cookies" and message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [*message["headers"], (b"set-cookie", b"session=forbidden; Path=/")],
                }
            if read().get("mode") == "malformed" and message["type"] == "http.response.body":
                message = {**message, "body": b"{broken"}
            if read().get("mode") == "malformed" and message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [(k, v) for k, v in message["headers"] if k != b"content-length"],
                }
            await send(message)

        await app(scope, receive, corrupt)

    return corruptible
