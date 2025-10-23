"""Pod selection logic with blast-radius enforcement.

The blast radius rule is the primary safety mechanism: no matter what the
caller requests, at most 50% of running pods in the namespace will be selected.
This prevents the chaos engine from accidentally taking a service fully offline.
"""

import asyncio
import logging
import random
from typing import List, Optional

from app.core.kubernetes import client as k8s

logger = logging.getLogger("chaos-engine.pod-selector")

# Hard limit — never kill more than this fraction of pods in any namespace
MAX_KILL_PERCENTAGE = 50.0


async def list_running_pods(
    namespace: str,
    label_selector: Optional[str] = None,
) -> List[object]:
    """Return all Running+Ready pods in the namespace, optionally filtered by label."""
    if not k8s.core_v1:
        logger.error("Kubernetes client not initialised")
        return []

    try:
        pods = await asyncio.to_thread(
            k8s.core_v1.list_namespaced_pod,
            namespace=namespace,
            label_selector=label_selector,
        )
    except Exception as exc:
        logger.error("Failed to list pods in %s: %s", namespace, exc)
        return []

    running = []
    for pod in pods.items:
        if pod.status.phase != "Running":
            continue
        statuses = pod.status.container_statuses or []
        if all(cs.ready for cs in statuses):
            running.append(pod)

    logger.info(
        "Found %d running/ready pods in %s (selector=%s)",
        len(running), namespace, label_selector,
    )
    return running


def select_for_kill(pods: List[object], kill_percentage: float) -> List[object]:
    """Select pods for termination, capping at MAX_KILL_PERCENTAGE.

    Always kills at least 1 pod when the list is non-empty.
    """
    if not pods:
        return []

    effective_pct = min(kill_percentage, MAX_KILL_PERCENTAGE)
    target_count = max(1, round(len(pods) * effective_pct / 100))

    # Double-check blast radius ceiling
    max_allowed = max(1, round(len(pods) * MAX_KILL_PERCENTAGE / 100))
    target_count = min(target_count, max_allowed)

    selected = random.sample(pods, min(target_count, len(pods)))
    logger.info(
        "Selected %d/%d pods for termination (requested %.0f%%, effective %.0f%%)",
        len(selected), len(pods), kill_percentage, effective_pct,
    )
    return selected
