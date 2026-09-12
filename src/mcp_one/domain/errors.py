from enum import StrEnum

from mcp.types import CallToolResult, TextContent

ERROR_META = "io.github.miguell-j.mcp-one/error"
GATEWAY_META = "io.github.miguell-j.mcp-one/gateway"


class ErrorCode(StrEnum):
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    SERVER_UNAVAILABLE = "SERVER_UNAVAILABLE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    CALL_TIMEOUT = "CALL_TIMEOUT"
    CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
    DISCOVERY_FAILED = "DISCOVERY_FAILED"
    DOWNSTREAM_PROTOCOL_ERROR = "DOWNSTREAM_PROTOCOL_ERROR"
    AUTH_FAILED = "AUTH_FAILED"
    POLICY_DENIED = "POLICY_DENIED"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONFIG_INVALID = "CONFIG_INVALID"
    OVERLOADED = "OVERLOADED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class GatewayError(Exception):
    def __init__(self, code: ErrorCode, *, infrastructure: bool = False, retryable: bool = False):
        super().__init__(code.value)
        self.code = code
        self.infrastructure = infrastructure
        self.retryable = retryable

    def result(self) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=self.code.value)],
            is_error=True,
            _meta={
                ERROR_META: {
                    "code": self.code.value,
                    "category": "infrastructure" if self.infrastructure else "gateway",
                    "retryable": self.retryable,
                }
            },
        )
