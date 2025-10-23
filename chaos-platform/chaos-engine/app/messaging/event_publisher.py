"""Typed business-event publishing methods.

Each method corresponds to one Kafka event type that consumers can filter on.
All calls are fire-and-forget — Kafka failures don't abort chaos experiments.
"""

import logging
from typing import Any, Dict, Optional

from app.messaging.kafka_producer import KafkaProducer
from app.observability.metrics import KAFKA_EVENTS_PUBLISHED

logger = logging.getLogger("chaos-engine.events")


class EventPublisher:
    def __init__(self, producer: KafkaProducer):
        self.producer = producer

    async def _publish(self, event_type: str, data: Dict[str, Any], key: Optional[str] = None) -> None:
        ok = await self.producer.send(event_type, data, key=key)
        if ok:
            KAFKA_EVENTS_PUBLISHED.labels(event_type=event_type).inc()

    async def experiment_started(self, experiment_id: str, name: str, chaos_type: str, namespace: str) -> None:
        await self._publish(
            "experiment.started",
            {
                "experiment_id": experiment_id,
                "name": name,
                "chaos_type": chaos_type,
                "target_namespace": namespace,
            },
            key=experiment_id,
        )

    async def action_executed(
        self,
        experiment_id: str,
        chaos_type: str,
        pods_killed: list,
        namespace: str,
    ) -> None:
        await self._publish(
            "experiment.action.executed",
            {
                "experiment_id": experiment_id,
                "chaos_type": chaos_type,
                "pods_killed": pods_killed,
                "target_namespace": namespace,
                "pods_killed_count": len(pods_killed),
            },
            key=experiment_id,
        )

    async def hypothesis_checked(
        self,
        experiment_id: str,
        phase: str,
        passed: bool,
        metrics: Dict[str, Any],
    ) -> None:
        """phase is 'before' or 'after'."""
        await self._publish(
            "experiment.hypothesis.checked",
            {
                "experiment_id": experiment_id,
                "phase": phase,
                "passed": passed,
                "metrics": metrics,
            },
            key=experiment_id,
        )

    async def experiment_completed(
        self,
        experiment_id: str,
        hypothesis_passed: bool,
        result_summary: Dict[str, Any],
    ) -> None:
        await self._publish(
            "experiment.completed",
            {
                "experiment_id": experiment_id,
                "hypothesis_passed": hypothesis_passed,
                "result_summary": result_summary,
            },
            key=experiment_id,
        )

    async def experiment_aborted(self, experiment_id: str, reason: str) -> None:
        await self._publish(
            "experiment.aborted",
            {"experiment_id": experiment_id, "reason": reason},
            key=experiment_id,
        )
