# Chaos Engine

Core service of the Chaos Engineering Platform. Kills pods, injects network latency, and stresses CPU/memory on a schedule — then validates that the system recovered using Prometheus metrics (Steady State Hypothesis pattern).

## Architecture

```
FastAPI (port 8001)
├── POST /experiments          → create + run experiment
├── GET  /experiments          → list all experiments
├── GET  /experiments/:id      → get one experiment
├── DELETE /experiments/:id    → delete experiment
├── GET  /results              → list all results
├── GET  /results/:id          → get one result
├── GET  /results/experiment/:id → result for a specific experiment
├── POST /schedules            → create recurring schedule
├── GET  /schedules            → list all schedules
├── PATCH /schedules/:id       → enable/disable or update cron
├── DELETE /schedules/:id      → delete schedule
├── GET  /health/live          → liveness probe
├── GET  /health/ready         → readiness probe
└── GET  /metrics              → Prometheus metrics
```

## Chaos Types

| type | description | key parameters |
|------|-------------|----------------|
| `pod_kill` | Randomly delete pods in the target namespace | `kill_percentage` (default 20), `recovery_timeout_seconds` (default 120) |
| `cpu_stress` | Deploy a stress-ng pod that consumes CPU | `cpu_percentage` (default 80), `duration_seconds` (default 60) |
| `memory_stress` | Deploy a stress-ng pod that allocates memory | `memory_mb` (default 256), `duration_seconds` (default 60) |
| `network_delay` | Inject latency via Chaos Mesh NetworkChaos CRD | `latency_ms` (default 200), `jitter_ms` (default 50), `duration` (default "5m") |

## Steady State Hypothesis

Every experiment checks these thresholds before and after chaos:

| metric | default threshold |
|--------|------------------|
| HTTP 5xx error rate | ≤ 5% |
| p99 response time | ≤ 2000ms |
| Ready pod count | ≥ 1 |

Override per-experiment via `steady_state_thresholds` in the request body.

## Circuit Breaker

After 3 consecutive experiments where the post-chaos hypothesis fails, the circuit breaker opens and all new experiments are rejected (HTTP 503). Reset it with:

```
POST /experiments/circuit-breaker/reset
```

## Safety Controls

- **Blast radius cap**: The engine never kills more than 50% of pods in any namespace — enforced in `pod_selector.py` regardless of requested `kill_percentage`.
- **Pre-chaos abort**: If the target system is already unhealthy before chaos is injected, the experiment is aborted (status: `aborted`).
- **Stress pod cleanup**: CPU and memory stress pods are deleted in `finally` blocks, even if the chaos engine crashes mid-experiment.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with SQLite (no PostgreSQL needed)
DATABASE_URL=sqlite+aiosqlite:///./chaos.db uvicorn app.main:app --port 8001 --reload

# Run tests
pytest tests/ -v
```

## Kubernetes Deployment

```bash
# Build image
docker build -t chaos-engine:latest .

# Apply manifests
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/cronjob.yaml

# Create DB secret (replace placeholders)
kubectl create secret generic chaos-engine-db \
  --from-literal=url='postgresql+asyncpg://user:REPLACE_WITH_DB_PASSWORD@host:5432/chaos_platform' \
  -n chaos-engine
```

## Kafka Events

The engine publishes to the `chaos-events` topic. Event types:

| event | fired when |
|-------|-----------|
| `experiment.started` | experiment begins |
| `experiment.action.executed` | chaos action completes (pods killed, etc.) |
| `experiment.hypothesis.checked` | before/after steady state measured |
| `experiment.completed` | experiment finishes (pass or fail) |
| `experiment.aborted` | experiment aborted (pre-chaos fail, circuit breaker) |

## Observability

| signal | where |
|--------|-------|
| Logs | JSON → stdout → Loki (scraped by Promtail) |
| Metrics | `/metrics` → Prometheus → Grafana |
| Traces | OTel SDK → OTel Collector → Tempo/Jaeger |

Key Prometheus metrics:
- `chaos_experiments_total{chaos_type,status}` — counter
- `chaos_experiments_running` — gauge
- `chaos_pods_killed_total{namespace}` — counter
- `chaos_recovery_time_seconds` — histogram
- `chaos_hypothesis_passed_total` / `chaos_hypothesis_failed_total` — counters
- `chaos_circuit_breaker_open` — gauge (1 = open)
