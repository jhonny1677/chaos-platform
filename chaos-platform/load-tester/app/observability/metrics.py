"""Prometheus metrics for the load tester."""

from prometheus_client import Counter, Histogram, Gauge

TESTS_TOTAL = Counter(
    "loadtest_tests_total",
    "Total load tests executed",
    ["scenario_type", "status"],
)

TESTS_RUNNING = Gauge(
    "loadtest_tests_running",
    "Currently running load tests",
)

REQUESTS_TOTAL = Counter(
    "loadtest_requests_total",
    "Total HTTP requests sent to target",
    ["endpoint", "method", "status"],   # status: success | error | timeout
)

REQUEST_LATENCY = Histogram(
    "loadtest_request_duration_ms",
    "HTTP request latency in milliseconds",
    ["endpoint"],
    buckets=[10, 50, 100, 250, 500, 1000, 2000, 5000, 10000],
)

ACTIVE_WORKERS = Gauge(
    "loadtest_active_workers",
    "Number of active virtual user workers",
)

KAFKA_MESSAGES_PRODUCED = Counter(
    "loadtest_kafka_messages_produced_total",
    "Kafka messages produced",
    ["topic"],
)

CURRENT_RPS = Gauge(
    "loadtest_current_rps",
    "Current requests per second",
)

ERROR_RATE = Gauge(
    "loadtest_error_rate_percent",
    "Current error rate percentage",
)
