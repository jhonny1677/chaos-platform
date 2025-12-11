"""
SchedulerClient — HTTP client for the Chaos Engine REST API.

The Chaos Engine exposes:
  POST /experiments   — create and immediately start a new experiment

Request body:
  {
    "type":             "pod-kill" | "network-delay" | "cpu-stress" | "memory-stress",
    "targetNamespace":  "chaos-engine",
    "targetLabel":      "app=target-app",
    "durationSeconds":  300,
    "blastRadius":      0.5
  }

Response (202 Accepted):
  {
    "experimentId": "exp-20260127-abc1234",
    "status":       "running"
  }

The Lambda runs inside the same VPC as the EKS cluster, so it can reach
the Chaos Engine's internal ClusterIP service directly without going through
an Ingress or public load balancer.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)


class SchedulerClient:
    def __init__(self, base_url: str) -> None:
        # e.g. http://chaos-engine.chaos-engine.svc.cluster.local:8001
        self._base_url = base_url.rstrip("/")

    def trigger(self, experiment: dict) -> dict:
        """
        POST /experiments to trigger an experiment.

        Args:
            experiment: DynamoDB record for the experiment

        Returns:
            Dict with experimentId and status from the API response

        Raises:
            urllib.error.HTTPError on non-2xx responses
            urllib.error.URLError on network errors
        """
        payload = {
            "type":             experiment.get("type", "pod-kill"),
            "targetNamespace":  experiment.get("targetNamespace", "chaos-engine"),
            "targetLabel":      experiment.get("targetLabel", "app=target-app"),
            "durationSeconds":  int(experiment.get("durationSeconds", 300)),
            "blastRadius":      float(experiment.get("blastRadius", 0.5)),
        }

        logger.info(
            "POST %s/experiments type=%s target=%s/%s",
            self._base_url,
            payload["type"],
            payload["targetNamespace"],
            payload["targetLabel"],
        )

        body = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            f"{self._base_url}/experiments",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept":       "application/json",
                "User-Agent":   "chaos-platform-scheduler/1.0",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode("utf-8")

        response_data = json.loads(response_body)
        logger.info(
            "Chaos Engine responded: experimentId=%s status=%s",
            response_data.get("experimentId"),
            response_data.get("status"),
        )
        return response_data
