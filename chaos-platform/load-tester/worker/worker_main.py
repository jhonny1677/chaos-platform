"""Standalone K8s Worker — reads test config from Redis, executes HTTP requests.

This process runs inside the worker-deployment pods. KEDA scales the number of
replicas based on the Kafka load-test-results topic lag. Each worker:

  1. Reads LOAD_TEST_ID from env (set by the controller or CronJob)
  2. Fetches test config from Redis (stored by the main app when test starts)
  3. Executes HTTP requests in a loop, reporting to Kafka via ResultReporter
  4. Sends a Redis heartbeat every 5 seconds so dead workers can be detected
  5. Stops when:  Redis status for the test_id becomes "stopped" OR test duration elapses

This worker is intentionally stateless: it can crash and be restarted by K8s
without losing data (results go to Kafka, state lives in Redis).
"""

import asyncio
import logging
import os
import sys
import time
import uuid

import httpx

from app.messaging.kafka_producer import KafkaProducer
from app.messaging.redis_aggregator import RedisAggregator
from app.observability.logger import setup_logging
from app.observability.tracing import setup_tracing
from worker.request_executor import execute_one
from worker.result_reporter import ResultReporter

logger = logging.getLogger("load-tester.worker.main")

_KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.kafka:9092")
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis.redis:6379/0")
_LOAD_TEST_ID = os.getenv("LOAD_TEST_ID", "")
_THINK_TIME_MS = int(os.getenv("THINK_TIME_MS", "100"))
_HEARTBEAT_INTERVAL = 5.0
_POLL_INTERVAL = 2.0


async def run() -> None:
    setup_logging()
    setup_tracing("load-tester-worker")

    if not _LOAD_TEST_ID:
        logger.error("LOAD_TEST_ID env var not set — worker exiting")
        sys.exit(1)

    worker_id = f"k8s-{str(uuid.uuid4())[:8]}"
    logger.info("Worker %s starting for test %s", worker_id, _LOAD_TEST_ID)

    kafka = KafkaProducer(bootstrap_servers=_KAFKA_SERVERS)
    redis = RedisAggregator(redis_url=_REDIS_URL)

    await kafka.start()
    await redis.connect()

    config = await redis.get_config(_LOAD_TEST_ID)
    if not config:
        logger.error("No config found in Redis for test %s — exiting", _LOAD_TEST_ID)
        await kafka.stop()
        await redis.close()
        sys.exit(1)

    target_url = config["target_url"]
    duration = config.get("duration_seconds", 300)
    think_time = config.get("think_time_ms", _THINK_TIME_MS) / 1000.0

    reporter = ResultReporter(kafka, redis, _LOAD_TEST_ID, worker_id)

    # Import request generator from app (shared logic)
    from app.core.engine import request_generator as rg

    start_time = time.monotonic()
    heartbeat_last = time.monotonic()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        follow_redirects=True,
    ) as client:
        while True:
            elapsed = time.monotonic() - start_time

            # Check stop signal from Redis
            if elapsed % _POLL_INTERVAL < 0.1:
                status = await redis.get_status(_LOAD_TEST_ID)
                if status in ("stopped", "aborted", "stopping"):
                    logger.info("Worker %s stopping: test status=%s", worker_id, status)
                    break

            # Duration exceeded
            if elapsed >= duration:
                logger.info("Worker %s: test duration elapsed (%.0fs)", worker_id, elapsed)
                break

            # Send heartbeat
            if time.monotonic() - heartbeat_last >= _HEARTBEAT_INTERVAL:
                await redis.send_heartbeat(worker_id)
                heartbeat_last = time.monotonic()

            # Execute one request
            req = rg.generate(target_url, _LOAD_TEST_ID)
            result = await execute_one(
                client=client,
                method=req.method,
                url=req.url,
                headers=req.headers,
                json_payload=req.json_payload,
                endpoint=req.endpoint,
                test_id=_LOAD_TEST_ID,
                worker_id=worker_id,
            )
            await reporter.add(result)

            if think_time > 0:
                await asyncio.sleep(think_time)

    await reporter.flush()
    await kafka.stop()
    await redis.close()
    logger.info("Worker %s finished for test %s", worker_id, _LOAD_TEST_ID)


if __name__ == "__main__":
    asyncio.run(run())
