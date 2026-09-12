import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yaml


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class NativeTopology:
    def __init__(self, directory):
        self.directory = directory
        self.processes = {}
        self.logs = {}
        self.ports = {name: free_port() for name in ("downstream", "gateway")}
        self.state = directory / "state.json"
        self.state.write_text(json.dumps({"mode": "healthy", "calls": 0}))
        self.url = f"http://127.0.0.1:{self.ports['gateway']}/mcp"
        self.downstream = f"http://127.0.0.1:{self.ports['downstream']}/mcp"
        self.config = {
            "hub": {"port": self.ports["gateway"]},
            "registry": {"refresh_interval_seconds": 60, "minimum_refresh_seconds": 0.01},
            "servers": [
                {
                    "id": "fixture",
                    "namespace": "demo",
                    "transport": {"url": self.downstream},
                    "timeout": {"call_seconds": 0.3, "discovery_seconds": 3, "health_seconds": 0.2},
                    "retry": {"discovery_attempts": 1},
                    "circuit_breaker": {"failure_threshold": 2, "reset_seconds": 0.2},
                }
            ],
        }

    def mode(self, mode):
        self.state.write_text(json.dumps({"mode": mode, "calls": 0}))

    def start(self, name):
        env = {
            **os.environ,
            "FIXTURE_STATE": str(self.state),
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "",
        }
        if name == "gateway":
            config_path = self.directory / "gateway.yaml"
            config_path.write_text(yaml.safe_dump(self.config))
            env["MCP_ONE_CONFIG"] = str(config_path)
        module = "tests.native_server" if name == "downstream" else "mcp_one.server"
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            f"{module}:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.ports[name]),
            "--no-access-log",
        ]
        log = (self.directory / f"{name}.log").open("a")
        self.logs[name] = log
        process = subprocess.Popen(
            command,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.processes[name] = process
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError((self.directory / f"{name}.log").read_text())
            try:
                if (
                    httpx.get(
                        f"http://127.0.0.1:{self.ports[name]}/health", timeout=0.2
                    ).status_code
                    == 200
                ):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        raise RuntimeError(f"{name} startup failed")

    def stop(self, name):
        process = self.processes.pop(name, None)
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            self.logs.pop(name).close()

    def close(self):
        for name in list(reversed(self.processes)):
            self.stop(name)


@pytest.fixture
def topology(tmp_path):
    stack = NativeTopology(tmp_path)
    try:
        stack.start("downstream")
        stack.start("gateway")
        yield stack
    finally:
        stack.close()
