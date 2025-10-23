"""Prometheus metrics for the chaos engine.

Collected by Prometheus and visualised in Grafana. The most important panel
to build first: experiments_running gauge (should return to 0 between runs)
and recovery_time_seconds to track how fast Kubernetes heals after chaos.
"""

from prometheus_client import Counter, Histogram, Gauge

EXPERIMENTS_TOTAL = Counter(
    "chaos_experiments_total",
    "Total chaos experiments executed",
    ["chaos_type", "status"],       # status: completed | failed | aborted
)

EXPERIMENTS_RUNNING = Gauge(
    "chaos_experiments_running",
    "Number of currently running chaos experiments",
)

PODS_KILLED_TOTAL = Counter(
    "chaos_pods_killed_total",
    "Total pods deleted by the chaos engine",
    ["namespace"],
)

RECOVERY_TIME_SECONDS = Histogram(
    "chaos_recovery_time_seconds",
    "Time in seconds for pods to return to Running/Ready after being killed",
    buckets=[5, 10, 30, 60, 120, 180, 300],
)

HYPOTHESIS_PASSED_TOTAL = Counter(
    "chaos_hypothesis_passed_total",
    "Experiments where the steady state hypothesis passed after chaos",
)

HYPOTHESIS_FAILED_TOTAL = Counter(
    "chaos_hypothesis_failed_total",
    "Experiments where the steady state hypothesis failed after chaos — system did not recover",
)

CIRCUIT_BREAKER_OPEN = Gauge(
    "chaos_circuit_breaker_open",
    "1 when the circuit breaker is open and experiments are paused",
)

KAFKA_EVENTS_PUBLISHED = Counter(
    "chaos_kafka_events_published_total",
    "Total Kafka events published to the chaos-events topic",
    ["event_type"],
)
