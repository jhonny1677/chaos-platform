"""Load Tester — FastAPI application entry point.

Startup sequence:
  1. Structured JSON logging
  2. OpenTelemetry tracing (instrument httpx for outbound request spans)
  3. Database init (create tables)
  4. Redis connection
  5. Kafka producer start
  6. Kafka command consumer start (background loop)

Shutdown:
  1. Stop Kafka consumer
  2. Stop Kafka producer
  3. Close Redis
  4. Dispose DB engine
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.api.routers import health, tests, results, workers
from app.database.connection import engine, init_db
from app.messaging.kafka_producer import KafkaProducer
from app.messaging.kafka_consumer import CommandConsumer
from app.messaging.redis_aggregator import RedisAggregator
from app.observability.logger import setup_logging
from app.observability.tracing import setup_tracing

_KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.kafka:9092")
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis.redis:6379/0")

_kafka: KafkaProducer = KafkaProducer(bootstrap_servers=_KAFKA_SERVERS)
_redis: RedisAggregator = RedisAggregator(redis_url=_REDIS_URL)
_cmd_consumer: CommandConsumer = CommandConsumer(bootstrap_servers=_KAFKA_SERVERS)
_consumer_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_task

    setup_logging()
    setup_tracing("load-tester")
    HTTPXClientInstrumentor().instrument()

    await init_db()
    await _redis.connect()
    await _kafka.start()
    await _cmd_consumer.start()
    _consumer_task = asyncio.create_task(_cmd_consumer.consume_loop(), name="kafka-cmd-consumer")

    yield

    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
    await _cmd_consumer.stop()
    await _kafka.stop()
    await _redis.close()
    await engine.dispose()


app = FastAPI(
    title="Load Tester",
    description="HTTP load testing service — smoke, stress, spike, and soak tests against K8s workloads",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FastAPIInstrumentor.instrument_app(app)

app.include_router(health.router)
app.include_router(tests.router)
app.include_router(results.router)
app.include_router(workers.router)
