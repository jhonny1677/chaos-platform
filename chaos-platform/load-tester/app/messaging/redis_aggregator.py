"""Redis integration for live stats, worker heartbeats, and pub/sub dashboard feed.

Key schema:
  loadtest:stats:{test_id}          → JSON live stats, TTL 60s
  loadtest:config:{test_id}         → JSON test config (for workers to read)
  loadtest:heartbeat:worker:{id}    → timestamp string, TTL 15s
  loadtest:status:{test_id}         → running | stopped | paused

Pub/sub channel:
  live-stats                        → JSON stats broadcast every second
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("load-tester.redis")

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

_STATS_TTL = 60
_HEARTBEAT_TTL = 15
_CONFIG_TTL = 3600


class RedisAggregator:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client = None
        self._pubsub_client = None

    async def connect(self) -> None:
        if not _REDIS_AVAILABLE:
            logger.warning("redis-py unavailable — Redis features disabled")
            return
        try:
            self._client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_connect_timeout=5,
            )
            await self._client.ping()
            logger.info("Redis connected at %s", self.redis_url)
        except Exception as exc:
            logger.error("Redis connect failed: %s — live stats disabled", exc)
            self._client = None

    async def publish_stats(self, test_id: str, stats: Dict[str, Any]) -> None:
        if not self._client:
            return
        payload = json.dumps(stats, default=str)
        try:
            pipe = self._client.pipeline()
            pipe.setex(f"loadtest:stats:{test_id}", _STATS_TTL, payload)
            pipe.publish("live-stats", payload)
            await pipe.execute()
        except Exception as exc:
            logger.debug("Redis publish_stats failed: %s", exc)

    async def store_config(self, test_id: str, config: Dict[str, Any]) -> None:
        if not self._client:
            return
        try:
            await self._client.setex(
                f"loadtest:config:{test_id}", _CONFIG_TTL,
                json.dumps(config, default=str),
            )
        except Exception as exc:
            logger.debug("Redis store_config failed: %s", exc)

    async def get_config(self, test_id: str) -> Optional[Dict[str, Any]]:
        if not self._client:
            return None
        try:
            raw = await self._client.get(f"loadtest:config:{test_id}")
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def get_stats(self, test_id: str) -> Optional[Dict[str, Any]]:
        if not self._client:
            return None
        try:
            raw = await self._client.get(f"loadtest:stats:{test_id}")
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def set_status(self, test_id: str, status: str) -> None:
        if not self._client:
            return
        try:
            await self._client.setex(f"loadtest:status:{test_id}", _CONFIG_TTL, status)
        except Exception as exc:
            logger.debug("Redis set_status failed: %s", exc)

    async def get_status(self, test_id: str) -> Optional[str]:
        if not self._client:
            return None
        try:
            return await self._client.get(f"loadtest:status:{test_id}")
        except Exception:
            return None

    async def send_heartbeat(self, worker_id: str) -> None:
        if not self._client:
            return
        try:
            await self._client.setex(
                f"loadtest:heartbeat:worker:{worker_id}",
                _HEARTBEAT_TTL,
                datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            pass

    async def list_live_workers(self) -> list:
        if not self._client:
            return []
        try:
            keys = await self._client.keys("loadtest:heartbeat:worker:*")
            return [k.split(":")[-1] for k in keys]
        except Exception:
            return []

    async def cleanup(self, test_id: str) -> None:
        if not self._client:
            return
        try:
            await self._client.delete(
                f"loadtest:stats:{test_id}",
                f"loadtest:config:{test_id}",
                f"loadtest:status:{test_id}",
            )
        except Exception:
            pass

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
