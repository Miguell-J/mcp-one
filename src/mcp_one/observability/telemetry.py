import logging
import os

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_provider: TracerProvider | None = None


def configure() -> TracerProvider:
    global _provider
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # SDK diagnostics can interpolate exceptions containing payloads or credentials.
    # Operational errors are reported by the sanitized application boundary instead.
    for name in ("httpx2", "httpcore2", "mcp"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    if _provider is None:
        _provider = TracerProvider(resource=Resource.create({"service.name": "mcp-one"}))
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        if endpoint:
            _provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=endpoint, timeout=3),
                    max_queue_size=512,
                    max_export_batch_size=128,
                    export_timeout_millis=3000,
                )
            )
        trace.set_tracer_provider(_provider)
    return _provider
