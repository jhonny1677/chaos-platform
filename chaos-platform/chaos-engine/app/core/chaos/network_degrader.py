"""Network Degrader — injects latency via Chaos Mesh NetworkChaos CRD.

Requires Chaos Mesh to be installed in the cluster (not included in Phase 2
helmfile — add it for Phase 5 or later). If the CRD doesn't exist, the action
logs a warning and returns a skipped result rather than crashing.

Chaos Mesh docs: https://chaos-mesh.org/docs/simulate-network-chaos-on-kubernetes/
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from kubernetes.client.exceptions import ApiException

from app.core.kubernetes import client as k8s
from app.observability.tracing import get_tracer

logger = logging.getLogger("chaos-engine.network-degrader")
tracer = get_tracer("chaos-engine.network-degrader")

_CHAOS_MESH_GROUP = "chaos-mesh.org"
_CHAOS_MESH_VERSION = "v1alpha1"
_NETWORK_CHAOS_PLURAL = "networkchaos"


@dataclass
class NetworkDegradeResult:
    chaos_resource_name: str = ""
    status: str = "unknown"
    latency_ms: int = 0
    jitter_ms: int = 0
    duration: str = ""
    cleaned_up: bool = False
    timeline: List[dict] = field(default_factory=list)
    error: Optional[str] = None

    def add_event(self, event: str, **kwargs) -> None:
        self.timeline.append(
            {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
        )


async def execute(
    namespace: str,
    label_selector: Dict[str, str],
    latency_ms: int = 200,
    jitter_ms: int = 50,
    duration: str = "5m",
    experiment_id: str = "",
) -> NetworkDegradeResult:
    """Inject network latency using a Chaos Mesh NetworkChaos resource.

    Args:
        label_selector: dict of k8s label key→value pairs to target specific pods
        latency_ms:     added network delay in milliseconds
        jitter_ms:      random variance on top of latency_ms
        duration:       Chaos Mesh duration string (e.g. '5m', '30s')
    """
    result = NetworkDegradeResult(
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
        duration=duration,
    )
    chaos_name = f"chaos-net-{experiment_id[:8]}"
    result.chaos_resource_name = chaos_name

    with tracer.start_as_current_span("network_degrader.execute") as span:
        span.set_attribute("namespace", namespace)
        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("duration", duration)
        span.set_attribute("experiment_id", experiment_id)

        if not k8s.custom_objects:
            result.status = "skipped"
            result.error = "Kubernetes custom objects client not available"
            logger.warning("K8s custom objects client unavailable — skipping network chaos")
            return result

        body = {
            "apiVersion": f"{_CHAOS_MESH_GROUP}/{_CHAOS_MESH_VERSION}",
            "kind": "NetworkChaos",
            "metadata": {
                "name": chaos_name,
                "namespace": namespace,
                "labels": {"chaos-engine": "true", "experiment-id": experiment_id[:36]},
            },
            "spec": {
                "action": "delay",
                "mode": "all",
                "selector": {
                    "namespaces": [namespace],
                    "labelSelectors": label_selector,
                },
                "delay": {
                    "latency": f"{latency_ms}ms",
                    "jitter": f"{jitter_ms}ms",
                    "correlation": "25",
                },
                "duration": duration,
            },
        }

        # ── Create NetworkChaos resource ──────────────────────────────────────
        try:
            await asyncio.to_thread(
                k8s.custom_objects.create_namespaced_custom_object,
                group=_CHAOS_MESH_GROUP,
                version=_CHAOS_MESH_VERSION,
                namespace=namespace,
                plural=_NETWORK_CHAOS_PLURAL,
                body=body,
            )
            result.status = "injected"
            result.add_event("network_chaos_created", name=chaos_name, latency_ms=latency_ms)
            logger.info(
                "NetworkChaos '%s' created in %s (+%dms latency)",
                chaos_name, namespace, latency_ms,
                extra={"experiment_id": experiment_id},
            )
        except ApiException as exc:
            result.status = "failed"
            result.error = str(exc)
            result.add_event("create_failed", error=str(exc))
            logger.error(
                "Failed to create NetworkChaos in %s: %s",
                namespace, exc,
                extra={"experiment_id": experiment_id},
            )
            return result

        # ── Wait for duration then clean up ──────────────────────────────────
        # Parse duration string to seconds for asyncio.sleep
        duration_secs = _parse_duration(duration)
        logger.info(
            "Network chaos active for %s (%ds) — waiting before cleanup",
            duration, duration_secs,
            extra={"experiment_id": experiment_id},
        )
        await asyncio.sleep(duration_secs)

        result.cleaned_up = await _cleanup(namespace, chaos_name, experiment_id)

    return result


async def _cleanup(namespace: str, chaos_name: str, experiment_id: str) -> bool:
    """Delete the NetworkChaos resource to stop the latency injection."""
    try:
        await asyncio.to_thread(
            k8s.custom_objects.delete_namespaced_custom_object,
            group=_CHAOS_MESH_GROUP,
            version=_CHAOS_MESH_VERSION,
            namespace=namespace,
            plural=_NETWORK_CHAOS_PLURAL,
            name=chaos_name,
        )
        logger.info(
            "NetworkChaos '%s' deleted (cleanup complete)", chaos_name,
            extra={"experiment_id": experiment_id},
        )
        return True
    except ApiException as exc:
        logger.error(
            "Failed to delete NetworkChaos '%s': %s", chaos_name, exc,
            extra={"experiment_id": experiment_id},
        )
        return False


def _parse_duration(duration: str) -> int:
    """Convert Chaos Mesh duration string to seconds (e.g. '5m' → 300)."""
    duration = duration.strip()
    if duration.endswith("m"):
        return int(duration[:-1]) * 60
    if duration.endswith("h"):
        return int(duration[:-1]) * 3600
    if duration.endswith("s"):
        return int(duration[:-1])
    return 300  # default 5 minutes if unparseable
