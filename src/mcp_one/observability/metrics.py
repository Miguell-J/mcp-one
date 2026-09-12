from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class PrometheusMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.counters = {
            name: Counter(
                f"mcp_one_{name}_total", name, ["server", "outcome"], registry=self.registry
            )
            for name in (
                "tool_calls",
                "infra_failures",
                "timeouts",
                "circuit_opens",
                "registry_refresh",
                "catalog_cache",
                "health_probes",
            )
        }
        self.histograms = {
            name: Histogram(f"mcp_one_{name}", name, ["server"], registry=self.registry)
            for name in (
                "tool_latency_seconds",
                "registry_refresh_seconds",
            )
        }
        self.gauges = {
            name: Gauge(f"mcp_one_{name}", name, ["server"], registry=self.registry)
            for name in ("catalog_tools", "catalog_bytes", "server_health", "circuit_open")
        }

    def increment(self, name: str, server: str = "", outcome: str = "") -> None:
        self.counters[name].labels(server, outcome).inc()

    def observe(self, name: str, seconds: float, server: str) -> None:
        self.histograms[name].labels(server).observe(seconds)

    def gauge(self, name: str, value: float, server: str = "") -> None:
        self.gauges[name].labels(server).set(value)

    def render(self) -> bytes:
        return generate_latest(self.registry)
