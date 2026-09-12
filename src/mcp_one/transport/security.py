import hmac
import os

from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_one.config import HubConfig


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, config: HubConfig):
        self.app = app
        self.transport_security = TransportSecurityMiddleware(
            TransportSecuritySettings(
                allowed_hosts=list(config.allowed_hosts),
                allowed_origins=list(config.allowed_origins),
            )
        )
        self.tokens = {
            "mcp": self._token(config.auth.bearer_token_env),
            "admin": self._token(config.admin_auth.bearer_token_env),
        }

    @staticmethod
    def _token(env: str | None) -> bytes | None:
        if env is None:
            return None
        value = os.environ.get(env)
        if not value:
            raise ValueError("configured authentication secret is missing")
        return ("Bearer " + value).encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            rejection = await self.transport_security.validate_request(Request(scope))
            if rejection is not None:
                await rejection(scope, receive, send)
                return
        if scope["type"] == "http" and scope["path"] not in {"/health", "/ready"}:
            token = self.tokens["mcp" if scope["path"].rstrip("/") == "/mcp" else "admin"]
            if token is not None:
                headers = dict(scope["headers"])
                if not hmac.compare_digest(headers.get(b"authorization", b""), token):
                    await JSONResponse(
                        {"error": "AUTH_FAILED"},
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )(scope, receive, send)
                    return
        await self.app(scope, receive, send)
