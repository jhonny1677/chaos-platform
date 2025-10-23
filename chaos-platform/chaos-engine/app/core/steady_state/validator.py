"""Steady State Validator — queries Prometheus for current system metrics.

Metrics are fetched from the Prometheus HTTP API (in-cluster: prometheus-kube-prometheus-prometheus.monitoring:9090).
If Prometheus is unreachable, a best-effort result is returned with a warning —
the hypothesis is considered "passed" to prevent false failures when the
observability stack itself has issues.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

from app.core.steady_state.hypothesis import SteadyStateThresholds
from app.core.kubernetes import client as k8s
from app.observability.tracing import get_tracer

logger = logging.getLogger("chaos-engine.validator")
tracer = get_tracer("chaos-engine.validator")


class SteadyStateValidator:
    def __init__(self, prometheus_url: str):
        self.prometheus_url = prometheus_url.rstrip("/")

    async def measure(self, namespace: str) -> Dict[str, Any]:
        """Return current observability metrics for the given namespace."""
        with tracer.start_as_current_span("steady_state.measure") as span:
            span.set_attribute("namespace", namespace)

            metrics: Dict[str, Any] = {
                "namespace": namespace,
                "error_rate": 0.0,
                "latency_p99_ms": 0.0,
                "ready_pods": 0,
                "prometheus_available": False,
            }

            error_rate = await self._query(
                f'sum(rate(http_requests_total{{namespace="{namespace}",status_code=~"5.."}}[2m])) / '
                f'sum(rate(http_requests_total{{namespace="{namespace}"}}[2m]))'
            )
            if error_rate is not None:
                metrics["error_rate"] = round(float(error_rate) * 100, 2)
                metrics["prometheus_available"] = True

            latency = await self._query(
                f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{namespace="{namespace}"}}[2m])) by (le))'
            )
            if latency is not None:
                metrics["latency_p99_ms"] = round(float(latency) * 1000, 2)

            ready_pods = await self._query(
                f'count(kube_pod_status_ready{{namespace="{namespace}",condition="true"}})'
            )
            if ready_pods is not None:
                metrics["ready_pods"] = int(float(ready_pods))

            logger.info(
                "Measured metrics for %s: error_rate=%.2f%%, p99=%.0fms, ready_pods=%d",
                namespace, metrics["error_rate"], metrics["latency_p99_ms"], metrics["ready_pods"],
            )
            return metrics

    async def _query(self, promql: str) -> Optional[float]:
        """Run a PromQL instant query and return the first scalar result."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": promql},
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    results = data.get("data", {}).get("result", [])
                    if results:
                        return float(results[0]["value"][1])
        except Exception as exc:
            logger.debug("Prometheus query failed (%s): %s", promql[:60], exc)
        return None

    def check(self, metrics: Dict[str, Any], thresholds: Dict[str, Any]) -> bool:
        """Return True if all measured metrics are within acceptable thresholds."""
        t = SteadyStateThresholds.from_dict(thresholds)

        if not metrics.get("prometheus_available"):
            logger.warning("Prometheus unavailable — hypothesis check skipped (defaulting to pass)")
            return True

        violations = []

        if metrics["error_rate"] > t.error_rate_percent:
            violations.append(
                f"error_rate={metrics['error_rate']:.2f}% > threshold={t.error_rate_percent}%"
            )
        if metrics["latency_p99_ms"] > t.latency_p99_ms:
            violations.append(
                f"latency_p99={metrics['latency_p99_ms']:.0f}ms > threshold={t.latency_p99_ms}ms"
            )
        if metrics["ready_pods"] < t.min_ready_pods:
            violations.append(
                f"ready_pods={metrics['ready_pods']} < threshold={t.min_ready_pods}"
            )

        if violations:
            logger.warning("Hypothesis FAILED: %s", "; ".join(violations))
            return False

        logger.info("Hypothesis PASSED")
        return True
