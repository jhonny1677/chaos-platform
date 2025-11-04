"""Worker Pool — manages N asyncio coroutines that independently send HTTP requests.

Design:
  - Each worker is an asyncio Task running an infinite loop (generate → send → queue result)
  - Workers share a single httpx.AsyncClient (connection pool is shared, saves sockets)
  - Dynamic scaling: add_workers(n) and remove_workers(n) can be called at any time
  - Dead worker detection: cancelled tasks are replaced automatically
  - The pool respects a stop_event so workers can be halted without cancellation noise
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Optional, Set

import httpx

from app.core.engine import request_generator as rg
from app.core.engine.result_collector import RequestResult
from app.observability.metrics import ACTIVE_WORKERS
from app.observability.tracing import get_tracer

logger = logging.getLogger("load-tester.worker-pool")
tracer = get_tracer("load-tester.worker-pool")

_REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class WorkerPool:
    def __init__(
        self,
        test_id: str,
        target_url: str,
        result_queue: asyncio.Queue,
        think_time_ms: int = 100,
        stop_event: Optional[asyncio.Event] = None,
        pause_event: Optional[asyncio.Event] = None,
    ):
        self.test_id = test_id
        self.target_url = target_url
        self._queue = result_queue
        self._think_time = think_time_ms / 1000.0
        self._stop = stop_event or asyncio.Event()
        self._pause = pause_event or asyncio.Event()
        self._pause.set()   # not paused by default

        self._client: Optional[httpx.AsyncClient] = None
        self._workers: Dict[str, asyncio.Task] = {}  # worker_id → Task
        self._target_count = 0

    async def start(self, initial_workers: int = 1) -> None:
        self._client = httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            http2=True,
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=200),
            follow_redirects=True,
        )
        self._target_count = initial_workers
        for _ in range(initial_workers):
            self._spawn_worker()
        logger.info(
            "Worker pool started with %d workers for test %s",
            initial_workers, self.test_id,
            extra={"test_id": self.test_id},
        )

    async def stop(self) -> None:
        self._stop.set()
        tasks = list(self._workers.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._workers.clear()
        if self._client:
            await self._client.aclose()
            self._client = None
        ACTIVE_WORKERS.set(0)
        logger.info("Worker pool stopped for test %s", self.test_id)

    def set_target(self, count: int) -> None:
        """Called by RampController to adjust worker count during the test."""
        count = max(1, count)
        current = len(self._workers)
        if count > current:
            for _ in range(count - current):
                self._spawn_worker()
        elif count < current:
            to_remove = current - count
            for wid in list(self._workers.keys())[:to_remove]:
                task = self._workers.pop(wid, None)
                if task:
                    task.cancel()
        self._target_count = count
        ACTIVE_WORKERS.set(len(self._workers))
        logger.debug("Worker pool target set to %d (actual=%d)", count, len(self._workers))

    def active_count(self) -> int:
        return sum(1 for t in self._workers.values() if not t.done())

    def _spawn_worker(self) -> None:
        worker_id = str(uuid.uuid4())[:8]
        task = asyncio.create_task(
            self._worker_loop(worker_id),
            name=f"worker-{worker_id}",
        )
        task.add_done_callback(lambda t: self._on_worker_done(worker_id, t))
        self._workers[worker_id] = task
        ACTIVE_WORKERS.set(len(self._workers))

    def _on_worker_done(self, worker_id: str, task: asyncio.Task) -> None:
        """Restart crashed workers unless the pool is stopping."""
        self._workers.pop(worker_id, None)
        if not self._stop.is_set() and len(self._workers) < self._target_count:
            if not task.cancelled() and task.exception() is not None:
                logger.warning(
                    "Worker %s crashed: %s — restarting", worker_id, task.exception(),
                    extra={"test_id": self.test_id},
                )
            self._spawn_worker()
        ACTIVE_WORKERS.set(len(self._workers))

    async def _worker_loop(self, worker_id: str) -> None:
        logger.debug("Worker %s started", worker_id, extra={"test_id": self.test_id})
        while not self._stop.is_set():
            # Honour pause
            await self._pause.wait()
            if self._stop.is_set():
                break

            request = rg.generate(self.target_url, self.test_id)
            result = await self._execute(request, worker_id)
            await self._queue.put(result)

            if self._think_time > 0:
                await asyncio.sleep(self._think_time)

    async def _execute(self, req: rg.HttpRequest, worker_id: str) -> RequestResult:
        start = time.monotonic()
        status_code = 0
        success = False
        error = None

        with tracer.start_as_current_span(f"loadtest.request") as span:
            span.set_attribute("http.method", req.method)
            span.set_attribute("http.url", req.url)
            span.set_attribute("load_test.id", self.test_id)

            try:
                resp = await self._client.request(
                    method=req.method,
                    url=req.url,
                    headers=req.headers,
                    json=req.json_payload,
                )
                status_code = resp.status_code
                success = status_code < 500
                span.set_attribute("http.status_code", status_code)
            except httpx.TimeoutException as exc:
                error = f"timeout: {exc}"
                span.set_attribute("error", True)
            except httpx.RequestError as exc:
                error = f"request_error: {type(exc).__name__}"
                span.set_attribute("error", True)

        latency_ms = (time.monotonic() - start) * 1000

        return RequestResult(
            test_id=self.test_id,
            worker_id=worker_id,
            timestamp=__import__("datetime").datetime.utcnow().isoformat(),
            endpoint=req.endpoint,
            method=req.method,
            status_code=status_code,
            latency_ms=round(latency_ms, 2),
            success=success,
            error=error,
        )

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()
