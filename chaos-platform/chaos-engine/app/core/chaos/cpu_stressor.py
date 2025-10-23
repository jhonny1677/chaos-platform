"""CPU Stressor — deploys a stress-ng pod to generate CPU load in a namespace.

The stress pod runs in the target namespace alongside the application pods,
so it competes for CPU on the same nodes. When the pod's CPU requests push
the node above 70% utilisation, the HPA on the target-app triggers scale-out.

The stress pod is always deleted after the experiment, even on failure,
via a finally block in execute(). If cleanup fails (e.g. the chaos engine pod
was killed mid-experiment), a Kubernetes Job TTL or manual `kubectl delete pod`
is needed — documented in README.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes.client.exceptions import ApiException

from app.core.kubernetes import client as k8s
from app.observability.tracing import get_tracer

logger = logging.getLogger("chaos-engine.cpu-stressor")
tracer = get_tracer("chaos-engine.cpu-stressor")

_STRESS_IMAGE = "progrium/stress"
_STRESS_LABEL = "chaos-engine-stress-pod"


@dataclass
class CpuStressResult:
    pod_name: str = ""
    cpu_percentage: int = 0
    duration_seconds: int = 0
    status: str = "unknown"
    cleaned_up: bool = False
    timeline: List[dict] = field(default_factory=list)
    error: Optional[str] = None

    def add_event(self, event: str, **kwargs) -> None:
        self.timeline.append(
            {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
        )


async def execute(
    namespace: str,
    cpu_percentage: int = 80,
    duration_seconds: int = 60,
    experiment_id: str = "",
) -> CpuStressResult:
    """Deploy a stress-ng pod that loads the CPU for a fixed duration.

    Args:
        cpu_percentage:  CPU load target (0-100). stress-ng --cpu-load flag.
        duration_seconds: How long to run the stress pod.
    """
    pod_name = f"chaos-cpu-{experiment_id[:8]}"
    result = CpuStressResult(
        pod_name=pod_name,
        cpu_percentage=cpu_percentage,
        duration_seconds=duration_seconds,
    )

    with tracer.start_as_current_span("cpu_stressor.execute") as span:
        span.set_attribute("namespace", namespace)
        span.set_attribute("cpu_percentage", cpu_percentage)
        span.set_attribute("duration_seconds", duration_seconds)
        span.set_attribute("experiment_id", experiment_id)

        if not k8s.core_v1:
            result.status = "skipped"
            result.error = "Kubernetes client not available"
            return result

        pod_manifest = _build_pod_manifest(pod_name, namespace, cpu_percentage, duration_seconds, experiment_id)

        try:
            # ── Create stress pod ─────────────────────────────────────────────
            await asyncio.to_thread(
                k8s.core_v1.create_namespaced_pod,
                namespace=namespace,
                body=pod_manifest,
            )
            result.status = "running"
            result.add_event("stress_pod_created", pod=pod_name, cpu_pct=cpu_percentage)
            logger.info(
                "CPU stress pod %s/%s created (%d%% load for %ds)",
                namespace, pod_name, cpu_percentage, duration_seconds,
                extra={"experiment_id": experiment_id},
            )

            # ── Wait for pod to complete ──────────────────────────────────────
            await _wait_for_completion(namespace, pod_name, duration_seconds + 30, result, experiment_id)

        except ApiException as exc:
            result.status = "failed"
            result.error = str(exc)
            result.add_event("create_failed", error=str(exc))
            logger.error(
                "Failed to create CPU stress pod in %s: %s", namespace, exc,
                extra={"experiment_id": experiment_id},
            )
        finally:
            result.cleaned_up = await _cleanup(namespace, pod_name, experiment_id)

    return result


async def _wait_for_completion(
    namespace: str,
    pod_name: str,
    timeout: int,
    result: CpuStressResult,
    experiment_id: str,
) -> None:
    """Poll until the stress pod Completes or times out."""
    elapsed = 0
    poll = 10
    while elapsed < timeout:
        await asyncio.sleep(poll)
        elapsed += poll
        try:
            pod = await asyncio.to_thread(
                k8s.core_v1.read_namespaced_pod, name=pod_name, namespace=namespace
            )
            phase = pod.status.phase
            result.add_event("pod_status_check", phase=phase, elapsed_seconds=elapsed)
            if phase in ("Succeeded", "Failed"):
                result.status = "completed" if phase == "Succeeded" else "stress_failed"
                return
        except ApiException:
            return  # pod may have been deleted already


async def _cleanup(namespace: str, pod_name: str, experiment_id: str) -> bool:
    """Delete the stress pod — called in finally block to guarantee cleanup."""
    try:
        await asyncio.to_thread(
            k8s.core_v1.delete_namespaced_pod,
            name=pod_name,
            namespace=namespace,
        )
        logger.info("CPU stress pod %s/%s deleted", namespace, pod_name,
                   extra={"experiment_id": experiment_id})
        return True
    except ApiException as exc:
        if exc.status == 404:
            return True  # already gone
        logger.error("Failed to delete stress pod %s: %s", pod_name, exc,
                    extra={"experiment_id": experiment_id})
        return False


def _build_pod_manifest(
    pod_name: str,
    namespace: str,
    cpu_percentage: int,
    duration_seconds: int,
    experiment_id: str,
) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {
                "app": _STRESS_LABEL,
                "chaos-engine": "true",
                "experiment-id": experiment_id[:36],
            },
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [{
                "name": "stress-ng",
                "image": _STRESS_IMAGE,
                "args": [
                    "--cpu", "1",
                    "--cpu-load", str(cpu_percentage),
                    "--timeout", str(duration_seconds),
                ],
                "resources": {
                    "requests": {"cpu": "500m", "memory": "64Mi"},
                    "limits": {"cpu": "1000m", "memory": "128Mi"},
                },
                "securityContext": {"allowPrivilegeEscalation": False},
            }],
        },
    }
