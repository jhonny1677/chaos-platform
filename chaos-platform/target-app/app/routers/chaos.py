"""
Chaos endpoint router — every endpoint here is intentionally resource-hungry
or failure-prone. They exist purely as targets for the chaos engine and load
tester. Never expose these in a real production API.

Chaos experiment recipes:
  /stress  — flood concurrently to trigger CPU throttling → CrashLoopBackOff
  /memory  — flood concurrently to trigger OOMKilled → Pod restart
  /slow    — flood concurrently to exhaust DB connections → cascading 503s
  /error   — use in load tests to validate error-rate alerting in AlertManager
"""

import asyncio
import random
import time
from fastapi import APIRouter, HTTPException
from opentelemetry import trace

from app.middleware.metrics import CHAOS_ERRORS
from app.models.schemas import make_response

router = APIRouter(tags=["chaos"])
tracer = trace.get_tracer("target-app.chaos")


@router.get("/stress", summary="CPU saturation endpoint")
async def stress():
    """Runs a tight arithmetic loop for 2 seconds to saturate one CPU core.

    Chaos use: send 4+ concurrent requests to push CPU above the HPA 70% threshold.
    Watch Kubernetes scale the deployment out in Grafana, then observe it scale back
    down after the flood stops. The pod's CPU throttling shows as latency spikes
    on all other endpoints because they share the same container CPU quota.

    Note: `await asyncio.sleep(0)` yields back to the event loop each iteration
    so other coroutines aren't starved while we spin.
    """
    with tracer.start_as_current_span("chaos.stress"):
        deadline = time.monotonic() + 2.0
        result = 0
        iterations = 0

        while time.monotonic() < deadline:
            result += sum(i * i for i in range(10_000))
            iterations += 1
            await asyncio.sleep(0)  # yield so the event loop stays responsive

    return make_response({
        "duration_seconds": 2.0,
        "iterations": iterations,
        "checksum": result % 1_000_000,
        "chaos_note": "CPU was saturated for 2s — check Grafana CPU throttling panel",
    })


@router.get("/memory", summary="Memory pressure endpoint")
async def memory():
    """Allocates 50MB of memory and holds it for 5 seconds before releasing.

    Chaos use: send concurrent requests until the pod's memory limit (512Mi)
    is approached. Kubernetes will OOMKill the pod and restart it. Watch the
    pod restart counter increment in Grafana and observe the readiness probe
    gap during the restart window.

    Each concurrent request holds 50MB for 5s:
      10 concurrent = 500MB > 512Mi limit → OOMKilled
    """
    with tracer.start_as_current_span("chaos.memory"):
        # Allocate a 50MB byte array — Python keeps this alive until del
        blob = bytearray(50 * 1024 * 1024)
        allocated_mb = len(blob) // (1024 * 1024)

        await asyncio.sleep(5)  # hold the allocation for 5 seconds

        del blob  # explicit delete helps the GC collect promptly

    return make_response({
        "allocated_mb": allocated_mb,
        "held_seconds": 5,
        "chaos_note": f"10 concurrent calls = {10 * allocated_mb}MB — exceeds 512Mi limit",
    })


@router.get("/slow", summary="Random latency endpoint")
async def slow():
    """Sleeps for a random duration between 1 and 5 seconds before responding.

    Chaos use: flood this endpoint to exhaust the Uvicorn worker pool. Because
    each request holds an async worker and a DB connection for the full sleep
    duration, latency cascades to other endpoints sharing the same pool.
    Watch p99 latency in Grafana spike across ALL endpoints, not just this one.
    """
    with tracer.start_as_current_span("chaos.slow") as span:
        delay = random.uniform(1.0, 5.0)
        span.set_attribute("chaos.delay_seconds", delay)
        await asyncio.sleep(delay)

    return make_response({
        "delay_seconds": round(delay, 3),
        "chaos_note": "Response time is non-deterministic — good for timeout experiments",
    })


@router.get("/error", summary="Randomly failing endpoint")
async def error():
    """Returns HTTP 500 with 30% probability on each request.

    Chaos use: include this endpoint in load test scenarios to generate a
    sustained error rate. AlertManager fires the 'error_rate_high' alert when
    error rate exceeds 5% over 5 minutes. The chaos_errors_total counter in
    Prometheus lets you graph exactly how many errors were injected.

    chaos_errors_total tracks injected failures separately from real errors
    so you can distinguish chaos noise from genuine bugs in Grafana dashboards.
    """
    with tracer.start_as_current_span("chaos.error") as span:
        if random.random() < 0.30:
            CHAOS_ERRORS.inc()
            span.set_attribute("chaos.error_injected", True)
            raise HTTPException(
                status_code=500,
                detail=make_response(
                    {
                        "message": "Chaos-injected failure",
                        "injected": True,
                        "error_probability": 0.30,
                    },
                    status="error",
                ),
            )

        span.set_attribute("chaos.error_injected", False)

    return make_response({
        "message": "No error this time — you were in the lucky 70%",
        "error_probability": 0.30,
        "chaos_note": "chaos_errors_total counter only increments on the 30% failures",
    })
