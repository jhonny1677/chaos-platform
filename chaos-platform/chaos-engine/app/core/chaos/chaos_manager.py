"""Chaos Manager — orchestrates the full experiment lifecycle.

Lifecycle:
  1. Validate steady state (pre-chaos hypothesis check)
  2. If pre-check passes, dispatch the chaos action
  3. Wait for the action to complete (or timeout)
  4. Validate steady state again (post-chaos hypothesis check)
  5. Persist result to DB and emit Kafka events at each step

Circuit breaker: if 3 consecutive experiments fail the post-chaos hypothesis
check, the circuit opens and all new experiments are rejected until manually
reset via the emergency-stop endpoint.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.chaos import cpu_stressor, memory_stressor, network_degrader, pod_killer
from app.core.steady_state.validator import SteadyStateValidator
from app.database.models import Experiment, ExperimentResult
from app.database.repositories.experiment_repo import ExperimentRepository
from app.database.repositories.result_repo import ResultRepository
from app.messaging.event_publisher import EventPublisher
from app.observability.metrics import (
    CIRCUIT_BREAKER_OPEN,
    EXPERIMENTS_RUNNING,
    EXPERIMENTS_TOTAL,
    HYPOTHESIS_FAILED_TOTAL,
    HYPOTHESIS_PASSED_TOTAL,
)
from app.observability.tracing import get_tracer

logger = logging.getLogger("chaos-engine.manager")
tracer = get_tracer("chaos-engine.manager")

_consecutive_failures = 0
_CIRCUIT_BREAKER_THRESHOLD = 3
_circuit_open = False


def is_circuit_open() -> bool:
    return _circuit_open


def reset_circuit_breaker() -> None:
    global _circuit_open, _consecutive_failures
    _circuit_open = False
    _consecutive_failures = 0
    CIRCUIT_BREAKER_OPEN.set(0)
    logger.info("Circuit breaker manually reset")


class ChaosManager:
    def __init__(
        self,
        experiment_repo: ExperimentRepository,
        result_repo: ResultRepository,
        publisher: EventPublisher,
        validator: SteadyStateValidator,
    ):
        self.experiment_repo = experiment_repo
        self.result_repo = result_repo
        self.publisher = publisher
        self.validator = validator

    async def run_experiment(self, experiment: Experiment) -> Optional[ExperimentResult]:
        global _consecutive_failures, _circuit_open

        experiment_id = experiment.experiment_id

        # ── Circuit breaker check ─────────────────────────────────────────────
        if _circuit_open:
            logger.warning(
                "Circuit breaker OPEN — rejecting experiment %s", experiment_id,
                extra={"experiment_id": experiment_id},
            )
            await self.publisher.experiment_aborted(experiment_id, "circuit_breaker_open")
            await self.experiment_repo.update_status(experiment_id, "aborted")
            return None

        with tracer.start_as_current_span("chaos_manager.run_experiment") as span:
            span.set_attribute("experiment_id", experiment_id)
            span.set_attribute("chaos_type", experiment.chaos_type)

            EXPERIMENTS_RUNNING.inc()
            try:
                return await self._execute(experiment)
            finally:
                EXPERIMENTS_RUNNING.dec()

    async def _execute(self, experiment: Experiment) -> ExperimentResult:
        global _consecutive_failures, _circuit_open
        experiment_id = experiment.experiment_id

        # ── Mark started ──────────────────────────────────────────────────────
        started_at = datetime.now(timezone.utc)
        await self.experiment_repo.update_status(
            experiment_id, "running", started_at=started_at
        )
        await self.publisher.experiment_started(
            experiment_id, experiment.name, experiment.chaos_type, experiment.target_namespace
        )

        result = await self.result_repo.create(
            experiment_id=experiment_id,
            started_at=started_at,
        )

        thresholds = experiment.steady_state_thresholds or {}

        # ── Pre-chaos steady state ────────────────────────────────────────────
        logger.info("Checking pre-chaos steady state for experiment %s", experiment_id,
                   extra={"experiment_id": experiment_id})
        pre_metrics = await self.validator.measure(experiment.target_namespace)
        pre_ok = self.validator.check(pre_metrics, thresholds)

        await self.publisher.hypothesis_checked(experiment_id, "before", pre_ok, pre_metrics)
        await self.result_repo.complete(
            result.result_id,
            error_rate_before=pre_metrics.get("error_rate", 0.0),
            latency_p99_before_ms=pre_metrics.get("latency_p99_ms", 0.0),
        )

        if not pre_ok:
            logger.warning(
                "Pre-chaos hypothesis FAILED for %s — system already unhealthy, aborting",
                experiment_id, extra={"experiment_id": experiment_id},
            )
            await self.experiment_repo.update_status(
                experiment_id, "aborted",
                completed_at=datetime.now(timezone.utc),
                result_summary={"reason": "pre_chaos_hypothesis_failed", "pre_metrics": pre_metrics},
            )
            await self.publisher.experiment_aborted(experiment_id, "pre_chaos_hypothesis_failed")
            return result

        # ── Dispatch chaos action ─────────────────────────────────────────────
        params = experiment.parameters or {}
        action_result = await self._dispatch_action(
            chaos_type=experiment.chaos_type,
            namespace=experiment.target_namespace,
            label_selector=experiment.target_label_selector,
            params=params,
            experiment_id=experiment_id,
        )

        killed_pods = getattr(action_result, "killed_pods", [])
        await self.publisher.action_executed(
            experiment_id, experiment.chaos_type, killed_pods, experiment.target_namespace
        )
        await self.result_repo.complete(
            result.result_id,
            pods_killed=killed_pods,
            actions_taken=[{"type": experiment.chaos_type, "result": str(action_result)}],
            timeline=getattr(action_result, "timeline", []),
            recovery_time_seconds=getattr(action_result, "recovery_time_seconds", None),
        )

        # ── Post-chaos steady state ───────────────────────────────────────────
        logger.info("Checking post-chaos steady state for experiment %s", experiment_id,
                   extra={"experiment_id": experiment_id})
        post_metrics = await self.validator.measure(experiment.target_namespace)
        post_ok = self.validator.check(post_metrics, thresholds)

        await self.publisher.hypothesis_checked(experiment_id, "after", post_ok, post_metrics)

        # Update circuit breaker state
        if post_ok:
            _consecutive_failures = 0
            HYPOTHESIS_PASSED_TOTAL.inc()
        else:
            _consecutive_failures += 1
            HYPOTHESIS_FAILED_TOTAL.inc()
            if _consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                _circuit_open = True
                CIRCUIT_BREAKER_OPEN.set(1)
                logger.error(
                    "Circuit breaker OPENED after %d consecutive hypothesis failures",
                    _consecutive_failures,
                )

        # ── Finalise ──────────────────────────────────────────────────────────
        status = "completed" if post_ok else "failed"
        completed_at = datetime.now(timezone.utc)
        result_summary = {
            "hypothesis_passed": post_ok,
            "pods_killed": len(killed_pods),
            "pre_metrics": pre_metrics,
            "post_metrics": post_metrics,
            "recovery_time_seconds": getattr(action_result, "recovery_time_seconds", None),
        }

        await self.result_repo.complete(
            result.result_id,
            hypothesis_passed=post_ok,
            hypothesis_result={"passed": post_ok, "post_metrics": post_metrics},
            error_rate_during=post_metrics.get("error_rate", 0.0),
            error_rate_after=post_metrics.get("error_rate", 0.0),
            latency_p99_after_ms=post_metrics.get("latency_p99_ms", 0.0),
        )
        await self.experiment_repo.update_status(
            experiment_id, status,
            completed_at=completed_at,
            result_summary=result_summary,
        )
        await self.publisher.experiment_completed(experiment_id, post_ok, result_summary)

        EXPERIMENTS_TOTAL.labels(chaos_type=experiment.chaos_type, status=status).inc()
        logger.info(
            "Experiment %s %s (hypothesis_passed=%s)",
            experiment_id, status, post_ok,
            extra={"experiment_id": experiment_id},
        )

        return result

    async def _dispatch_action(
        self,
        chaos_type: str,
        namespace: str,
        label_selector: Optional[str],
        params: Dict[str, Any],
        experiment_id: str,
    ) -> Any:
        chaos_type = chaos_type.lower()
        logger.info("Dispatching %s action for experiment %s", chaos_type, experiment_id,
                   extra={"experiment_id": experiment_id})

        if chaos_type == "pod_kill":
            return await pod_killer.execute(
                namespace=namespace,
                label_selector=label_selector,
                kill_percentage=float(params.get("kill_percentage", 20.0)),
                recovery_timeout_seconds=int(params.get("recovery_timeout_seconds", 120)),
                experiment_id=experiment_id,
            )

        if chaos_type == "cpu_stress":
            return await cpu_stressor.execute(
                namespace=namespace,
                cpu_percentage=int(params.get("cpu_percentage", 80)),
                duration_seconds=int(params.get("duration_seconds", 60)),
                experiment_id=experiment_id,
            )

        if chaos_type == "memory_stress":
            return await memory_stressor.execute(
                namespace=namespace,
                memory_mb=int(params.get("memory_mb", 256)),
                duration_seconds=int(params.get("duration_seconds", 60)),
                experiment_id=experiment_id,
            )

        if chaos_type == "network_delay":
            label_dict = params.get("label_selector", {"app": "target-app"})
            return await network_degrader.execute(
                namespace=namespace,
                label_selector=label_dict,
                latency_ms=int(params.get("latency_ms", 200)),
                jitter_ms=int(params.get("jitter_ms", 50)),
                duration=params.get("duration", "5m"),
                experiment_id=experiment_id,
            )

        raise ValueError(f"Unknown chaos_type: {chaos_type!r}")
