"""Cross-SDK smoke tests using the pinned, official Inspector CLI."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mcp_one.domain.errors import ERROR_META, GATEWAY_META

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.inspector,
    pytest.mark.skipif(
        os.getenv("MCP_INSPECTOR_TESTS") != "1", reason="make test-inspector opts in"
    ),
]


async def invoke(url, storage, method, *args, expected=0):
    binary = ROOT / "tooling/node_modules/.bin/mcp-inspector"
    assert binary.is_file(), "Run npm ci --ignore-scripts --prefix tooling first"
    command = [
        str(binary),
        "--cli",
        "--transport",
        "http",
        "--server-url",
        url,
        "--protocol-era",
        "modern",
        "--connect-timeout",
        "5000",
        "--method",
        method,
        "--format",
        "json",
        *args,
    ]
    result = await asyncio.to_thread(
        subprocess.run,
        command,
        cwd=ROOT,
        timeout=20,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "MCP_INSPECTOR_SECRET_STORE": "memory",
            "MCP_STORAGE_DIR": str(storage),
            "MCP_INSPECTOR_OAUTH_STATE_PATH": str(storage / "oauth.json"),
        },
    )
    assert result.returncode == expected, result.stderr
    if expected and not result.stdout.strip():
        return json.loads(result.stderr.strip().splitlines()[-1])
    return json.loads(result.stdout)["result"]


async def test_official_inspector_modern_discovery_calls_and_errors(topology, tmp_path):
    storage = tmp_path / "inspector"
    connected = await invoke(topology.url, storage, "initialize")
    assert connected["protocolVersion"] == "2026-07-28"
    routed = await invoke(topology.url, storage, "tools/list", "--strict")
    direct = await invoke(topology.downstream, storage, "tools/list", "--strict")
    originals = {t["name"]: t for t in direct["tools"]}
    for tool in routed["tools"]:
        assert {**tool, "name": tool["name"].removeprefix("demo.")} == originals[
            tool["name"].removeprefix("demo.")
        ]
    assert len(routed["tools"]) == 3
    args = ["--tool-name", "demo.echo", "--tool-args-json", '{"message":"inspector"}']
    result = await invoke(topology.url, storage, "tools/call", *args)
    assert not result.get("isError", False)
    assert result["structuredContent"] == {"message": "inspector"}
    schema = next(t["outputSchema"] for t in routed["tools"] if t["name"] == "demo.echo")
    Draft202012Validator(schema).validate(result["structuredContent"])
    assert result["_meta"]["test.example/opaque"] == {"list": [1, {"two": True}]}
    assert result["_meta"][GATEWAY_META]["attempts"] == 1
    domain = await invoke(
        topology.url,
        storage,
        "tools/call",
        "--tool-name",
        "demo.domain",
        "--tool-args-json",
        '{"message":"domain"}',
        expected=5,
    )
    assert domain["isError"] and domain["_meta"]["test.example/domain"]["code"] == "DOMAIN"
    invalid = await invoke(
        topology.url,
        storage,
        "tools/call",
        "--tool-name",
        "demo.echo",
        "--tool-args-json",
        '{"message":42}',
        expected=5,
    )
    # Inspector may reject schema-invalid arguments before sending the call.
    if "_meta" in invalid:
        assert invalid["_meta"][ERROR_META]["code"] == "INVALID_ARGUMENT"
        assert invalid["_meta"][GATEWAY_META]["attempts"] == 0
    else:
        assert "error" in invalid
