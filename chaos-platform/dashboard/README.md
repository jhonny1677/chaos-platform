# Chaos Platform Dashboard — Phase 6

React 18 + Vite frontend for the Chaos Engineering & Load Testing Platform.

## Stack

| Layer | Tech |
|-------|------|
| UI    | React 18, Tailwind CSS (dark theme) |
| State | Redux Toolkit + React-Redux |
| Charts | Recharts |
| Routing | React Router v6 |
| HTTP | Axios (retry on 503, 10 s timeout) |
| Build | Vite 5 |
| Serve | nginx 1.25-alpine (non-root, port 8080) |

## Pages

| Path | Description |
|------|-------------|
| `/` | Dashboard — KPI cards, RPS/error charts, recent activity (5 s auto-refresh) |
| `/chaos` | Chaos Experiments — list, create, detail drawer with timeline |
| `/load-tests` | Load Tests — list, create, live stats panel (1 s polling + WebSocket) |
| `/results` | Results — experiment table + recovery-time chart, stress breaking-point chart |
| `/monitoring` | Monitoring — Prometheus pod health, Alertmanager alerts, correlation timeline |
| `/settings` | Settings — circuit breaker control, API endpoint reference |

## Local Development

```bash
cd dashboard
npm install
npm run dev        # http://localhost:3000
```

## Environment Variables

All variables are `VITE_*` and must be set **at build time**.

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_CHAOS_API_URL` | `http://localhost:8001` | Chaos Engine REST API |
| `VITE_LOADTEST_API_URL` | `http://localhost:8002` | Load Tester REST API |
| `VITE_PROMETHEUS_URL` | `http://localhost:9090` | Prometheus HTTP API |
| `VITE_ALERTMANAGER_URL` | `http://localhost:9093` | Alertmanager API |
| `VITE_WS_URL` | `ws://localhost:8001` | WebSocket (chaos engine) |
| `VITE_TARGET_URL` | `http://target-app.target-app:8000` | Default load-test target |

In-cluster values are in `k8s/configmap.yaml`.

## Docker Build

```bash
docker build -t chaos-platform/dashboard:latest .
```

## Kubernetes Deploy

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

Add to `/etc/hosts` for local access:
```
127.0.0.1  dashboard.chaos-platform.local
```

## WebSocket

The dashboard opens a single WebSocket to `VITE_WS_URL/ws` with exponential-backoff reconnection (max 30 s). The backend must emit JSON messages with `type` field:

| `type` | Action |
|--------|--------|
| `experiment_update` | Refreshes experiment in Redux store |
| `pod_killed` | Adds to killed-pods list, shown in Monitoring |
| `live_stats` | Updates live stats panel in Load Tests |
| `test_update` | Refreshes test in Redux store |
