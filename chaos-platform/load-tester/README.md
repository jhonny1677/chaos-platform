# Load Tester

HTTP load testing service for the Chaos Engineering Platform. Floods the target app with realistic traffic using async Python + httpx, and produces results to Kafka for analysis.

## Architecture

```
FastAPI API (port 8002)
├── POST /tests              → create + run test
├── GET  /tests              → list tests
├── GET  /tests/:id          → get test
├── DELETE /tests/:id        → delete test
├── POST /tests/:id/stop     → graceful stop
├── POST /tests/:id/abort    → immediate abort
├── GET  /results/live/:id   → live Redis stats (real-time)
├── GET  /results/:id        → per-second DB snapshots
├── GET  /workers            → K8s worker heartbeats
├── GET  /workers/:test_id   → active workers for a test
├── GET  /health/live        → liveness probe
├── GET  /health/ready       → readiness probe
└── GET  /metrics            → Prometheus metrics

LoadEngine (internal asyncio)
├── WorkerPool           → N async coroutines, each firing HTTP requests
├── ResultCollector      → drains Queue, computes stats, publishes every 1s
├── RampController       → adjusts worker count over time
└── CommandConsumer      → Kafka listener for stop/pause/scale commands

K8s Worker (separate pod — worker-deployment.yaml)
└── worker_main.py       → reads config from Redis, fires requests, reports to Kafka
    KEDA ScaledObject    → scales worker replicas based on Kafka lag
```

## Scenario Types

| type | VUs | duration | ramp | pass criteria |
|------|-----|----------|------|---------------|
| `smoke` | 10 | 60s | instant | error_rate ≤ 1% |
| `stress` | 10→200 | until break | step (+10 every 30s) | finds breaking point (error > 20%) |
| `spike` | 10→100→10 | ~4.5 min | custom | measures recovery time after spike |
| `soak` | 20 | 30 min | linear | p99 drift ≤ 50% from baseline |

## Request Distribution

| endpoint | method | weight | notes |
|----------|--------|--------|-------|
| `/products` | GET | 60% | random page/limit params |
| `/orders` | GET | 20% | |
| `/orders` | POST | 10% | random user_id, product_id, quantity |
| `/stress` | GET | 10% | chaos endpoint — intentionally slow |

## Quick Start

```bash
# Local dev (SQLite, no Kafka/Redis needed — graceful degradation)
DATABASE_URL=sqlite+aiosqlite:///./loadtest.db uvicorn app.main:app --port 8002 --reload

# Run a smoke test
curl -X POST http://localhost:8002/tests \
  -H 'Content-Type: application/json' \
  -d '{"name": "Quick smoke", "target_url": "http://localhost:8000", "scenario_type": "smoke"}'

# Check live stats
curl http://localhost:8002/results/live/<test_id>

# Run tests
pytest tests/ -v
```

## Kubernetes Deployment

```bash
# Build images
docker build -t load-tester:latest .
docker build -f Dockerfile.worker -t load-tester-worker:latest .

# Apply manifests (order matters)
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/keda-scaledobject.yaml   # requires KEDA installed

# Create DB secret
kubectl create secret generic load-tester-db \
  --from-literal=url='postgresql+asyncpg://user:REPLACE_WITH_DB_PASSWORD@host:5432/load_tester' \
  -n load-tester
```

## Kafka Topics

| topic | produced by | consumed by | content |
|-------|-------------|-------------|---------|
| `load-test-results` | workers, main app | KEDA (lag), analytics | per-request records |
| `load-test-stats` | result collector | dashboard | 1-second aggregated stats |
| `load-test-commands` | external | command consumer | stop/pause/scale/resume |

## Redis Keys

| key | TTL | content |
|-----|-----|---------|
| `loadtest:stats:{test_id}` | 60s | live stats JSON |
| `loadtest:config:{test_id}` | 1h | test config (for K8s workers) |
| `loadtest:status:{test_id}` | 1h | running / stopped / paused |
| `loadtest:heartbeat:worker:{id}` | 15s | last heartbeat timestamp |

## KEDA Autoscaling

Workers scale based on `load-test-results` Kafka topic lag:
- Scale up when lag > **1000** messages (more workers needed)
- Scale down when lag < **100** messages (production slowing)
- Min: **1** replica, Max: **20** replicas
- Scale-up adds max 5 pods per 15s; scale-down removes max 2 pods per 30s

## Prometheus Metrics

| metric | type | labels |
|--------|------|--------|
| `loadtest_tests_total` | counter | scenario_type, status |
| `loadtest_tests_running` | gauge | — |
| `loadtest_requests_total` | counter | endpoint, method, status |
| `loadtest_request_duration_ms` | histogram | endpoint |
| `loadtest_active_workers` | gauge | — |
| `loadtest_kafka_messages_produced_total` | counter | topic |
| `loadtest_current_rps` | gauge | — |
| `loadtest_error_rate_percent` | gauge | — |

## Ramp Strategies

| strategy | behaviour |
|----------|-----------|
| `instant` | Jump to full VU count immediately |
| `linear` | Interpolate from start_users → target over ramp_duration_seconds |
| `step` | Add step_size users every step_interval_seconds |
| `custom` | Follow [[time, users]] waypoints with linear interpolation |
