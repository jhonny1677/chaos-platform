"""Steady State Hypothesis data structures.

A hypothesis defines what "healthy" looks like for a system. Before and after
each chaos experiment, the engine measures actual metrics and checks them against
these thresholds. If the post-chaos check fails, the system did not recover.

Default thresholds (overridable per experiment):
  error_rate_percent   ≤ 5%     (HTTP 5xx / total requests)
  latency_p99_ms       ≤ 2000ms (99th percentile response time)
  min_ready_pods       ≥ 1      (at least one pod must be Ready)
  pod_restart_increase ≤ 5      (max new restarts since experiment start)
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class SteadyStateThresholds:
    error_rate_percent: float = 5.0
    latency_p99_ms: float = 2000.0
    min_ready_pods: int = 1
    pod_restart_increase: int = 5

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SteadyStateThresholds":
        return cls(
            error_rate_percent=float(data.get("error_rate_percent", 5.0)),
            latency_p99_ms=float(data.get("latency_p99_ms", 2000.0)),
            min_ready_pods=int(data.get("min_ready_pods", 1)),
            pod_restart_increase=int(data.get("pod_restart_increase", 5)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_rate_percent": self.error_rate_percent,
            "latency_p99_ms": self.latency_p99_ms,
            "min_ready_pods": self.min_ready_pods,
            "pod_restart_increase": self.pod_restart_increase,
        }
