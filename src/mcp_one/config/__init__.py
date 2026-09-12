"""Validated configuration. Secret values never belong in this model."""

from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]
EnvName = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")]
Seconds = Annotated[float, Field(gt=0, le=3600)]


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TransportConfig(ConfigModel):
    type: Literal["streamable_http"] = "streamable_http"
    url: str

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("absolute HTTP(S) endpoint required")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("endpoint cannot contain credentials, query or fragment")
        if any(ord(c) < 33 for c in value):
            raise ValueError("endpoint contains whitespace/control characters")
        return value


class TimeoutPolicy(ConfigModel):
    connect_seconds: Seconds = 3
    discovery_seconds: Seconds = 10
    call_seconds: Seconds = 60
    health_seconds: Seconds = 3


class RetryPolicy(ConfigModel):
    discovery_attempts: int = Field(default=3, ge=1, le=5)
    health_attempts: int = Field(default=1, ge=1, le=3)
    call_attempts: int = Field(default=1, ge=1, le=3)
    safe_tools: tuple[str, ...] = ()
    backoff_seconds: float = Field(default=0.2, ge=0, le=5)


class CircuitBreakerPolicy(ConfigModel):
    enabled: bool = True
    failure_threshold: int = Field(default=5, ge=1, le=100)
    reset_seconds: Seconds = 30


class HealthPolicy(ConfigModel):
    interval_seconds: Seconds = 30


class AuthReference(ConfigModel):
    bearer_token_env: EnvName | None = None


class ServerConfig(ConfigModel):
    id: Identifier
    display_name: str | None = Field(default=None, max_length=128)
    namespace: Identifier
    enabled: bool = True
    transport: TransportConfig
    timeout: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    circuit_breaker: CircuitBreakerPolicy = Field(default_factory=CircuitBreakerPolicy)
    health: HealthPolicy = Field(default_factory=HealthPolicy)
    auth: AuthReference = Field(default_factory=AuthReference)


class ServerDefaults(ConfigModel):
    timeout: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    circuit_breaker: CircuitBreakerPolicy = Field(default_factory=CircuitBreakerPolicy)
    health: HealthPolicy = Field(default_factory=HealthPolicy)


class RegistryConfig(ConfigModel):
    refresh_interval_seconds: Seconds = 30
    stale_seconds: float = Field(default=300, ge=0, le=86400)
    minimum_refresh_seconds: Seconds = 1
    max_tools: int = Field(default=1024, ge=1, le=10000)
    max_pages: int = Field(default=100, ge=1, le=1000)
    max_catalog_bytes: int = Field(default=8_388_608, ge=1024, le=67_108_864)


class Limits(ConfigModel):
    request_bytes: int = Field(default=1_048_576, ge=1024, le=16_777_216)
    response_bytes: int = Field(default=8_388_608, ge=1024, le=67_108_864)
    schema_bytes: int = Field(default=131_072, ge=1024, le=1_048_576)
    schema_depth: int = Field(default=32, ge=4, le=64)
    concurrent_calls: int = Field(default=64, ge=1, le=1024)


class PolicyConfig(ConfigModel):
    allow: tuple[str, ...] = ("*",)
    deny: tuple[str, ...] = ()


class HubConfig(ConfigModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    allowed_hosts: tuple[str, ...] = (
        "127.0.0.1",
        "localhost",
        "[::1]",
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
        "mcp-one:*",
    )
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1",
        "http://localhost",
        "http://127.0.0.1:*",
        "http://localhost:*",
    )
    auth: AuthReference = Field(default_factory=AuthReference)
    admin_auth: AuthReference = Field(default_factory=AuthReference)
    minimum_ready_servers: int = Field(default=1, ge=1, le=100)


class GatewayConfig(ConfigModel):
    version: Literal[1] = 1
    hub: HubConfig = Field(default_factory=HubConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    limits: Limits = Field(default_factory=Limits)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    defaults: ServerDefaults = Field(default_factory=ServerDefaults)
    servers: tuple[ServerConfig, ...] = Field(default=(), max_length=100)

    @model_validator(mode="before")
    @classmethod
    def apply_defaults(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        defaults = ServerDefaults.model_validate(data.get("defaults", {})).model_dump()
        entries = data.get("servers", ())
        if not isinstance(entries, (list, tuple)):
            return data
        servers = []
        for entry in entries:
            if isinstance(entry, dict):
                entry = dict(entry)
                for key, default in defaults.items():
                    override = entry.get(key, {})
                    if isinstance(override, dict):
                        entry[key] = {**default, **override}
            servers.append(entry)
        data["servers"] = servers
        return data

    @model_validator(mode="after")
    def unique_servers(self) -> Self:
        for field in ("id", "namespace"):
            values = [getattr(s, field) for s in self.servers]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate server {field}")
        return self


def load_config(path: Path) -> GatewayConfig:
    if path.stat().st_size > 1_048_576:
        raise ValueError("configuration exceeds 1 MiB")
    return GatewayConfig.model_validate(yaml.safe_load(path.read_text()))
