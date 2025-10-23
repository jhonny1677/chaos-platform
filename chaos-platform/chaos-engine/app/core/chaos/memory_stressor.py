"""Memory Stressor — deploys a stress-ng pod to consume memory in a namespace.

Useful for triggering OOMKill events and testing how Kubernetes handles pods
that exceed their memory limits. The stress pod requests a configurable amount
of memory and the kubelet will OOMKill it if it exceeds the node's available
memory, testing the cluster's eviction and rescheduling behaviour.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes.client.exceptions import ApiException

from app.core.kubernetes import client as k8s
from app.observability.tracing import get_tracer

logger = logging.getLogger("chaos-engine.memory-stressor")
tracer = get_tracer("chaos-engine.memory-stressor")

_STRESS_IMAGE = "progrium/stress"


@dataclass
class MemoryStressResult:
    pod_name: str = ""
    memory_mb: int = 0
    duration_seconds: int = 0
    status: str = "unknown"
    oom_killed: bool = False
    cleaned_up: bool = False
    timeline: List[dict] = field(default_factory=list)
    error: Optional[str] = None

    def add_event(self, event: str, **kwargs) -> None:
        self.timeline.append(
            {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
        )


async def execute(
    namespace: str,
    memory_mb: int = 256,
    duration_seconds: int = 60,
    experiment_id: str = "",
) -> MemoryStressResult:
    """Deploy a stress-ng pod that allocates memory_mb for duration_seconds.

    Args:
        memory_mb:       Megabytes of memory to allocate (stress-ng --vm-bytes)
        duration_seconds: How long to hold the allocation
    """
    pod_name = f"chaos-mem-{experiment_id[:8]}"
    result = MemoryStressResult(
        pod_name=pod_name,
        memory_mb=memory_mb,
        duration_seconds=duration_seconds,
    )

    with tracer.start_as_current_span("memory_stressor.execute") as span:
        span.set_attribute("namespace", namespace)
        span.set_attribute("memory_mb", memory_mb)
        span.set_attribute("duration_seconds", duration_seconds)
        span.set_attribute("experiment_id", experiment_id)

        if not k8s.core_v1:
            result.status = "skipped"
            result.error = "Kubernetes client not available"
            return result

        pod_manifest = _build_pod_manifest(pod_name, namespace, memory_mb, duration_seconds, experiment_id)

        try:
            await asyncio.to_thread(
                k8s.core_v1.create_namespaced_pod,
                namespace=namespace,
                body=pod_manifest,
            )
            result.status = "running"
            result.add_event("stress_pod_created", pod=pod_name, memory_mb=memory_mb)
            logger.info(
                "Memory stress pod %s/%s created (%dMB for %ds)",
                namespace, pod_name, memory_mb, duration_seconds,
                extra={"experiment_id": experiment_id},
            )

            await _wait_for_completion(namespace, pod_name, duration_seconds + 60, result, experiment_id)

        except ApiException as exc:
            result.status = "failed"
            result.error = str(exc)
            result.add_event("create_failed", error=str(exc))
            logger.error(
                "Failed to create memory stress pod in %s: %s", namespace, exc,
                extra={"experiment_id": experiment_id},
            )
        finally:
            result.cleaned_up = await _cleanup(namespace, pod_name, experiment_id)

    return result


async def _wait_for_completion(
    namespace: str,
    pod_name: str,
    timeout: int,
    result: MemoryStressResult,
    experiment_id: str,
) -> None:
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
            statuses = pod.status.container_statuses or []
            oom = any(cs.last_state.terminated and cs.last_state.terminated.reason == "OOMKilled"
                      for cs in statuses if cs.last_state)
            if oom:
                result.oom_killed = True
                result.status = "oom_killed"
                result.add_event("oom_killed", elapsed_seconds=elapsed)
                logger.info("Memory stress pod OOMKilled (expected for high memory tests)",
                           extra={"experiment_id": experiment_id})
                return
            if phase in ("Succeeded", "Failed"):
                result.status = "completed" if phase == "Succeeded" else "stress_failed"
                return
        except ApiException:
            return


async def _cleanup(namespace: str, pod_name: str, experiment_id: str) -> bool:
    try:
        await asyncio.to_thread(
            k8s.core_v1.delete_namespaced_pod,
            name=pod_name,
            namespace=namespace,
        )
        logger.info("Memory stress pod %s/%s deleted", namespace, pod_name,
                   extra={"experiment_id": experiment_id})
        return True
    except ApiException as exc:
        if exc.status == 404:
            return True
        logger.error("Failed to delete memory stress pod %s: %s", pod_name, exc,
                    extra={"experiment_id": experiment_id})
        return False


def _build_pod_manifest(
    pod_name: str,
    namespace: str,
    memory_mb: int,
    duration_seconds: int,
    experiment_id: str,
) -> dict:
    memory_limit = f"{int(memory_mb * 1.5)}Mi"
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {
                "app": "chaos-engine-stress-pod",
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
                    "--vm", "1",
                    "--vm-bytes", f"{memory_mb}M",
                    "--vm-keep",
                    "--timeout", str(duration_seconds),
                ],
                "resources": {
                    "requests": {"cpu": "100m", "memory": f"{memory_mb}Mi"},
                    "limits": {"cpu": "200m", "memory": memory_limit},
                },
                "securityContext": {"allowPrivilegeEscalation": False},
            }],
        },
    }
