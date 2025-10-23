"""Pod Killer — the primary chaos action.

Kill cycle:
  1. List running pods in target namespace
  2. Select a subset (blast radius ≤ 50%)
  3. Record pre-kill restart counts
  4. Delete selected pods via K8s API
  5. Poll until replacement pods are Running/Ready or timeout expires
  6. Return detailed PodKillResult for hypothesis evaluation

Recovery detection: pod names change after recreation. We consider the kill
"recovered" when the total Running+Ready pod count returns to ≥ the original
count. This correctly handles Deployments (which create new pods with new names)
and StatefulSets (which reuse the same names).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from kubernetes.client.exceptions import ApiException

from app.core.kubernetes import client as k8s
from app.core.kubernetes import pod_selector
from app.observability.metrics import PODS_KILLED_TOTAL, RECOVERY_TIME_SECONDS
from app.observability.tracing import get_tracer

logger = logging.getLogger("chaos-engine.pod-killer")
tracer = get_tracer("chaos-engine.pod-killer")


@dataclass
class PodKillResult:
    targeted_pods: List[str] = field(default_factory=list)
    killed_pods: List[str] = field(default_factory=list)
    failed_to_kill: List[str] = field(default_factory=list)
    pre_kill_restart_counts: Dict[str, int] = field(default_factory=dict)
    recovery_times: Dict[str, float] = field(default_factory=dict)
    all_recovered: bool = False
    recovery_time_seconds: Optional[float] = None
    timeline: List[dict] = field(default_factory=list)

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_event(self, event: str, **kwargs) -> None:
        self.timeline.append({"timestamp": self._ts(), "event": event, **kwargs})


async def execute(
    namespace: str,
    label_selector: Optional[str] = None,
    kill_percentage: float = 20.0,
    recovery_timeout_seconds: int = 120,
    experiment_id: str = "",
) -> PodKillResult:
    """Execute a pod-kill chaos action and wait for recovery."""
    result = PodKillResult()

    with tracer.start_as_current_span("pod_killer.execute") as span:
        span.set_attribute("namespace", namespace)
        span.set_attribute("kill_percentage", kill_percentage)
        span.set_attribute("experiment_id", experiment_id)

        # ── 1. Discover targets ──────────────────────────────────────────────
        pods = await pod_selector.list_running_pods(namespace, label_selector)
        if not pods:
            logger.warning(
                "No running pods in %s (selector=%s) — skipping kill",
                namespace, label_selector,
                extra={"experiment_id": experiment_id},
            )
            result.add_event("no_pods_found", namespace=namespace)
            return result

        original_count = len(pods)
        targets = pod_selector.select_for_kill(pods, kill_percentage)
        result.targeted_pods = [p.metadata.name for p in targets]
        result.add_event("targets_selected", pods=result.targeted_pods, total_pods=original_count)

        # ── 2. Record pre-kill state ─────────────────────────────────────────
        for pod in targets:
            statuses = pod.status.container_statuses or []
            result.pre_kill_restart_counts[pod.metadata.name] = sum(
                cs.restart_count for cs in statuses
            )

        # ── 3. Kill pods ─────────────────────────────────────────────────────
        for pod in targets:
            name = pod.metadata.name
            try:
                await asyncio.to_thread(
                    k8s.core_v1.delete_namespaced_pod,
                    name=name,
                    namespace=namespace,
                )
                result.killed_pods.append(name)
                result.add_event("pod_killed", pod=name, namespace=namespace)
                PODS_KILLED_TOTAL.labels(namespace=namespace).inc()
                logger.info(
                    "Killed pod %s/%s", namespace, name,
                    extra={"experiment_id": experiment_id},
                )
            except ApiException as exc:
                result.failed_to_kill.append(name)
                result.add_event("kill_failed", pod=name, error=str(exc))
                logger.error(
                    "Failed to kill pod %s/%s: %s", namespace, name, exc,
                    extra={"experiment_id": experiment_id},
                )

        # ── 4. Wait for recovery ─────────────────────────────────────────────
        if result.killed_pods:
            result = await _wait_for_recovery(
                namespace=namespace,
                original_count=original_count,
                result=result,
                timeout=recovery_timeout_seconds,
                experiment_id=experiment_id,
            )

        span.set_attribute("pods_killed", len(result.killed_pods))
        span.set_attribute("recovered", result.all_recovered)

    return result


async def _wait_for_recovery(
    namespace: str,
    original_count: int,
    result: PodKillResult,
    timeout: int,
    experiment_id: str,
) -> PodKillResult:
    """Poll until running pod count ≥ original_count or timeout expires."""
    start = time.monotonic()
    poll_interval = 5

    logger.info(
        "Waiting up to %ds for %d pods to recover in %s",
        timeout, original_count, namespace,
        extra={"experiment_id": experiment_id},
    )

    while (elapsed := time.monotonic() - start) < timeout:
        await asyncio.sleep(poll_interval)

        try:
            pods = await asyncio.to_thread(
                k8s.core_v1.list_namespaced_pod,
                namespace=namespace,
            )
        except Exception as exc:
            logger.warning("Pod list error during recovery check: %s", exc)
            continue

        ready_count = sum(
            1 for p in pods.items
            if p.status.phase == "Running"
            and all(cs.ready for cs in (p.status.container_statuses or []))
        )

        result.add_event(
            "recovery_check",
            ready_pods=ready_count,
            needed=original_count,
            elapsed_seconds=round(elapsed, 1),
        )

        if ready_count >= original_count:
            result.all_recovered = True
            result.recovery_time_seconds = round(elapsed, 2)
            RECOVERY_TIME_SECONDS.observe(elapsed)
            result.add_event(
                "recovery_complete",
                recovery_time_seconds=result.recovery_time_seconds,
            )
            logger.info(
                "All pods recovered in %.1fs (namespace=%s)",
                elapsed, namespace,
                extra={"experiment_id": experiment_id},
            )
            break

    if not result.all_recovered:
        result.add_event("recovery_timeout", timeout_seconds=timeout)
        logger.warning(
            "Pods did not recover within %ds (namespace=%s)",
            timeout, namespace,
            extra={"experiment_id": experiment_id},
        )

    return result
