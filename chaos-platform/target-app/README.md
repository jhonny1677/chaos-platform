# Chaos Platform — Target App

A fake e-commerce FastAPI application built to be deliberately broken during chaos engineering experiments. It is intentionally simple so that failure behavior is easy to observe, but realistic enough to generate meaningful Prometheus metrics and distributed traces.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe — always 200 while process is alive |
| GET | `/ready` | Readiness probe — 200 only if DB is reachable |
| GET | `/metrics` | Prometheus metrics scrape endpoint |
| GET | `/products` | List all 20 seeded products |
| GET | `/products/{id}` | Single product by ID |
| POST | `/orders` | Create order (100ms simulated write latency) |
| GET | `/orders` | List recent orders |
| GET | `/users` | List all 10 seeded users |
| GET | `/stress` | **CHAOS** — saturates CPU for 2 seconds |
| GET | `/memory` | **CHAOS** — allocates 50MB for 5 seconds |
| GET | `/slow` | **CHAOS** — random 1–5 second delay |
| GET | `/error` | **CHAOS** — returns 500 with 30% probability |

All endpoints return the same JSON envelope:
```json
{
  "status": "ok",
  "data": { ... },
  "timestamp": "2024-01-01T00:00:00.000000+00:00"
}
```

---

## Local Development

### Prerequisites
- Python 3.11+
- Docker
- PostgreSQL 15 (or use the Docker command below)

### Start a local PostgreSQL

```bash
docker run -d \
  --name chaos-postgres \
  -e POSTGRES_USER=chaos \
  -e POSTGRES_PASSWORD=chaos \
  -e POSTGRES_DB=chaos_platform \
  -p 5432:5432 \
  postgres:15
```

### Run the app

```bash
cd target-app
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # review and adjust if needed
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for the Swagger UI.

### Run tests

```bash
pytest                         # runs against SQLite in-memory — no PostgreSQL needed
pytest -v                      # verbose
pytest tests/test_health.py    # single file
```

---

## Docker

```bash
# Build
docker build -t target-app:latest .

# Run (requires PostgreSQL — use the docker run command above first)
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://chaos:chaos@host.docker.internal:5432/chaos_platform \
  target-app:latest

# Push to ECR (replace ACCOUNT_ID and REGION)
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker tag target-app:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/target-app:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/target-app:latest
```

---

## Deploy to Kubernetes

```bash
# Prerequisites: kubectl configured for your EKS cluster (Phase 1)
# Namespaces already created (Phase 2)

# Apply in order
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/ingress.yaml

# Verify
kubectl get pods -n target-app
kubectl get hpa -n target-app
kubectl logs -n target-app -l app=target-app -f
```

---

## Chaos Experiment Recipes

### Recipe 1 — CPU saturation + HPA scale-out
```bash
# Flood /stress with 20 concurrent requests for 60 seconds
for i in $(seq 1 20); do
  while true; do curl -s http://target-app.chaos-platform.local/stress > /dev/null; done &
done
# Watch: kubectl get hpa -n target-app -w
# Expected: pod count increases from 3 toward 10
```

### Recipe 2 — Memory exhaustion + OOMKilled
```bash
# 10 concurrent /memory calls = 500MB > 512Mi limit
for i in $(seq 1 10); do
  curl -s http://target-app.chaos-platform.local/memory &
done
# Watch: kubectl get pods -n target-app -w
# Expected: pod shows OOMKilled, then Kubernetes restarts it
```

### Recipe 3 — Error rate alerting
```bash
# Flood /error — 30% will return 500
ab -n 1000 -c 20 http://target-app.chaos-platform.local/error
# Watch: Grafana → chaos_errors_total panel
# Expected: AlertManager fires 'error_rate_high' after 5 minutes
```

### Recipe 4 — Chaos engine pod kill
```bash
# The chaos engine (Phase 4) does this automatically, but you can simulate it:
kubectl delete pod -n target-app -l app=target-app --wait=false
# Watch: kubectl get pods -n target-app -w
# Expected: PDB prevents both remaining pods from being killed simultaneously
```

---

## Observability

| Signal | Where to view |
|--------|--------------|
| Metrics | Grafana → http_requests_total, http_request_duration_seconds, chaos_errors_total |
| Logs | Grafana → Loki → `{namespace="target-app"}` |
| Traces | Jaeger/Tempo → service: target-app |
| Alerts | AlertManager → http://alertmanager.monitoring.svc.cluster.local:9093 |
