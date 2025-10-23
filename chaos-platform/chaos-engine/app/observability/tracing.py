"""OpenTelemetry tracer setup.

Every chaos action creates a span so traces show the full kill → wait → verify
cycle. Spans are exported to the OTel Collector in the monitoring namespace.
"""

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(service_name: str = "chaos-engine") -> None:
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("APP_VERSION", "1.0.0"),
        "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
        "k8s.pod.name": os.getenv("POD_NAME", "unknown"),
    })

    provider = TracerProvider(resource=resource)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
        )

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
