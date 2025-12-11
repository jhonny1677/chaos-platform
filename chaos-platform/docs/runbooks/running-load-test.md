# Running a Load Test

## Scenario Types

| Scenario | Pattern | Use Case |
|---|---|---|
| `baseline` | Constant 10 RPS for 5 minutes | Measure normal performance |
| `ramp` | 0 → 100 RPS over 10 minutes | Find when degradation starts |
| `spike` | 10 RPS → 500 RPS instantly → 10 RPS | Test autoscaling and failover |
| `soak` | Constant 50 RPS for 2 hours | Find memory leaks and gradual degradation |
| `breakingpoint` | 10 RPS increasing by 10 every 30s until failure | Find maximum safe throughput |

---

## Option 1: Dashboard UI

1. Open `http://localhost:8080`
2. Click **"New Load Test"**
3. Select scenario type
4. Set target URL (pre-filled with target-app service URL)
5. Click **"Start"**
6. Watch the live chart: RPS, P50, P99, Error Rate update every 2 seconds

The dashboard shows a split view: on the left, the live chart; on the right, the worker pod count from KEDA (you can watch it scale from 1 to up to 20).

---

## Option 2: REST API (CLI)

### Start a ramp test:
```bash
curl -X POST http://localhost:8002/tests \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "ramp",
    "targetUrl": "http://target-app.chaos-platform.svc.cluster.local:8000",
    "startRps": 10,
    "endRps": 100,
    "durationSeconds": 600,
    "successThreshold": 0.99
  }'
```

### Start a spike test:
```bash
curl -X POST http://localhost:8002/tests \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "spike",
    "targetUrl": "http://target-app.chaos-platform.svc.cluster.local:8000",
    "peakRps": 500,
    "durationSeconds": 300,
    "successThreshold": 0.95
  }'
```

### Start a breaking point test:
```bash
curl -X POST http://localhost:8002/tests \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "breakingpoint",
    "targetUrl": "http://target-app.chaos-platform.svc.cluster.local:8000",
    "startRps": 10,
    "stepRps": 10,
    "stepDurationSeconds": 30,
    "failureThreshold": 0.01
  }'
```

### Check live stats:
```bash
TEST_ID="lt-20260127-xyz9999"
curl http://localhost:8002/tests/$TEST_ID/stats | jq '{
  currentRps: .current.rps,
  p50Ms: .current.p50LatencyMs,
  p99Ms: .current.p99LatencyMs,
  errorRate: .current.errorRate,
  activeWorkers: .current.workerCount
}'
```

---

## Watching Live Statistics

### In the terminal:
```bash
# Stream stats every 2 seconds
watch -n 2 'curl -s http://localhost:8002/tests/$TEST_ID/stats | jq ".current"'
```

### In Grafana:
Open the **Load Test Overview** dashboard. Key panels:

| Panel | What to Watch |
|---|---|
| Requests Per Second | Actual RPS delivered vs target |
| P50 Latency | Median response time — should be stable until breakpoint |
| P99 Latency | Tail latency — first indicator of saturation |
| Error Rate | Should be < 1% until you hit capacity |
| Worker Pod Count | Shows KEDA scaling up/down (1–20 pods) |
| Target App CPU | Shows HPA trigger point |
| Target App Pod Count | HPA scaling in response to CPU load |

### Watch KEDA scaling in real time:
```bash
kubectl get hpa -n load-tester --watch
kubectl get pods -n load-tester --watch
```

---

## Interpreting the Final Report

After the test completes, a PDF report appears in `#load-tests` Slack channel. It contains:

### Executive Summary
One paragraph: did the service meet the success threshold? What was the maximum observed RPS before errors exceeded the failure threshold?

### Performance Curve
A table showing RPS → P50 → P99 → Error Rate at each step. Look for the "knee" — the point where P99 starts to diverge from P50 significantly. That knee is the service's safe operating capacity.

### Breaking Point Analysis (for `breakingpoint` scenario)
- **Safe capacity**: highest RPS where error rate was below the threshold
- **Breaking point**: RPS where error rate first exceeded the threshold
- **Recommendation**: set your HPA `targetCPUUtilizationPercentage` to trigger at 70% of safe capacity

### Autoscaling Behavior
Did HPA scale the target app in time to absorb the load? If P99 latency spiked before HPA kicked in, the scale-up trigger threshold may need tuning.

---

## Combining Load Tests with Chaos Experiments

The most valuable tests run both simultaneously. This sequence gives you the most realistic picture:

```bash
# Step 1: Run baseline load test (10 RPS for 5 minutes)
BASELINE=$(curl -s -X POST http://localhost:8002/tests \
  -H "Content-Type: application/json" \
  -d '{"scenario": "baseline", "targetUrl": "http://target-app...", "rps": 10, "durationSeconds": 300}' \
  | jq -r '.testId')

# Wait for baseline to complete
sleep 310

# Step 2: Start steady load (50 RPS)
LOAD=$(curl -s -X POST http://localhost:8002/tests \
  -H "Content-Type: application/json" \
  -d '{"scenario": "baseline", "rps": 50, "durationSeconds": 600}' | jq -r '.testId')

# Step 3: While load is running, trigger chaos after 60 seconds
sleep 60
curl -X POST http://localhost:8001/experiments \
  -d '{"type": "pod-kill", "blastRadius": 0.5, "durationSeconds": 120}'

# The load test report will show exactly what user traffic looked like during the outage
```

---

## Stopping a Load Test Early

```bash
curl -X DELETE http://localhost:8002/tests/$TEST_ID
```

KEDA will scale load tester pods back to 1 within 2 minutes of the test stopping.

---

## Capacity Planning Output

After running breaking point tests, update the capacity estimate in your infrastructure docs:

| Metric | Value |
|---|---|
| Safe RPS (single pod) | ___ RPS |
| Breaking point (3 pods) | ___ RPS |
| Breaking point (20 pods, KEDA max) | ___ RPS |
| Autoscale trigger point | ___ % CPU |
| P99 at safe capacity | ___ ms |
