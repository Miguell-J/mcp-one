import pytest
from starlette.testclient import TestClient

from mcp_one.config import GatewayConfig, load_config
from mcp_one.server import create_app


def test_separate_upstream_and_admin_auth_fail_closed(monkeypatch):
    monkeypatch.setenv("UPSTREAM_TOKEN", "upstream-fixture")
    monkeypatch.setenv("ADMIN_TOKEN", "admin-fixture")
    config = GatewayConfig.model_validate(
        {
            "hub": {
                "auth": {"bearer_token_env": "UPSTREAM_TOKEN"},
                "admin_auth": {"bearer_token_env": "ADMIN_TOKEN"},
            }
        }
    )
    with TestClient(create_app(config), base_url="http://localhost") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.post("/mcp", json={}).status_code == 401
        assert client.get("/status").status_code == 401
        assert (
            client.get("/status", headers={"Authorization": "Bearer upstream-fixture"}).status_code
            == 401
        )
        response = client.get("/status", headers={"Authorization": "Bearer admin-fixture"})
        assert response.status_code == 200 and "admin-fixture" not in response.text
    monkeypatch.delenv("UPSTREAM_TOKEN")
    with pytest.raises(ValueError, match="secret is missing"):
        create_app(config)


@pytest.mark.parametrize(
    "header,value", [("Host", "attacker.invalid"), ("Origin", "https://attacker.invalid")]
)
def test_host_origin_rejected(header, value):
    with TestClient(create_app(GatewayConfig()), base_url="http://localhost") as client:
        response = client.post("/mcp", json={}, headers={header: value})
        assert response.status_code in {403, 421}


def test_native_payload_limit_and_malformed_protocol():
    config = GatewayConfig.model_validate({"limits": {"request_bytes": 1024}})
    with TestClient(create_app(config), base_url="http://localhost") as client:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        assert client.post("/mcp", content=b"a" * 1025, headers=headers).status_code == 413
        assert client.post("/mcp", content=b"{bad", headers=headers).status_code == 400
        mismatch = client.post(
            "/mcp",
            headers={**headers, "Mcp-Method": "tools/call", "MCP-Protocol-Version": "2026-07-28"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
            },
        )
        assert mismatch.status_code == 400


def test_configuration_schema_and_loading(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("servers: []\n")
    assert load_config(config).servers == ()
    config.write_text("a" * 1_048_577)
    with pytest.raises(ValueError, match="exceeds"):
        load_config(config)
    schema = GatewayConfig.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "timeout" in schema["$defs"]["ServerConfig"]["properties"]
