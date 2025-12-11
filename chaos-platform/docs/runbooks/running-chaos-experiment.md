# Running a Chaos Experiment

## Before You Start

**Check that the target app is healthy:**
```bash
kubectl get pods -n chaos-platform -l app=target-app
# All pods should be Running, all READY columns should show 1/1
```

**Check circuit breaker status:**
```bash
curl http://localhost:8001/health | jq '.circuitBreaker'
# Should be: {"state": "closed", "failureCount": 0}
```

If the circuit breaker is `open`, do not run chaos experiments. Investigate and recover first.

---

## Option 1: Dashboard UI

1. Open the dashboard at `http://localhost:8080` (or the ingress URL if configured)
2. Click **"New Experiment"** in the top-right
3. Fill in the form:
   - **Type**: Pod Kill / Network Delay / CPU Stress / Memory Stress
   - **Target Namespace**: `chaos-platform`
   - **Target Label**: `app=target-app`
   - **Blast Radius**: 0.5 (50% — cannot exceed this)
   - **Duration**: 300 seconds
   - **Hypothesis**: Set a hypothesis threshold (e.g., error rate < 5%)
4. Click **"Start Experiment"**
5. Watch the live metric chart update every 2 seconds

---

## Option 2: REST API (CLI)

### Run a pod-kill experiment:
```bash
curl -X POST http://localhost:8001/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "type": "pod-kill",
    "targetNamespace": "chaos-platform",
    "targetLabel": "app=target-app",
    "durationSeconds": 300,
    "blastRadius": 0.5,
    "hypothesis": {
      "metric": "error_rate",
      "threshold": 0.05,
      "operator": "lt"
    }
  }'
```

### Run a network delay experiment:
```bash
curl -X POST http://localhost:8001/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "type": "network-delay",
    "targetNamespace": "chaos-platform",
    "targetLabel": "app=target-app",
    "durationSeconds": 300,
    "blastRadius": 0.5,
    "params": {
      "delayMs": 200,
      "jitterMs": 50
    },
    "hypothesis": {
      "metric": "p99_latency_ms",
      "threshold": 500,
      "operator": "lt"
    }
  }'
```

### Check experiment status:
```bash
EXPERIMENT_ID="exp-20260127-abc1234"  # from the POST response
curl http://localhost:8001/experiments/$EXPERIMENT_ID | jq '.'
```

### List all experiments:
```bash
curl http://localhost:8001/experiments | jq '.experiments[] | {id, type, status, hypothesisPassed}'
```

---

## Option 3: Scheduled Experiments

To schedule a recurring experiment, add it to DynamoDB directly:

```bash
aws dynamodb put-item \
  --table-name chaos-platform-experiments \
  --item '{
    "experimentId": {"S": "scheduled-pod-kill-daily"},
    "scheduleExpression": {"S": "daily"},
    "enabled": {"BOOL": true},
    "targetNamespace": {"S": "chaos-platform"},
    "targetLabel": {"S": "app=target-app"},
    "type": {"S": "pod-kill"},
    "durationSeconds": {"N": "300"},
    "blastRadius": {"N": "0.5"},
    "lastRunAt": {"N": "0"}
  }'
```

The `experiment-scheduler` Lambda runs at 02:00 UTC Mon–Fri and will trigger this experiment. The 23-hour cooldown prevents duplicate runs.

---

## Interpreting Results

### Hypothesis Evaluation

After the experiment completes, check the result:

```bash
curl http://localhost:8001/experiments/$EXPERIMENT_ID | jq '{
  status,
  hypothesisPassed,
  "errorRateDuring": .metrics.during.errorRate,
  "hypothesisThreshold": .hypothesis.threshold
}'
```

**PASS** means the system maintained its SLO during the fault injection — the experiment validated your resilience.

**FAIL** means the system degraded below acceptable levels. This is valuable — it tells you exactly where the resilience gap is. The PDF report will include automatic recommendations.

### Reading the Grafana Dashboard

Open Grafana (`http://localhost:3000`) and navigate to **Chaos Platform Overview**.

Key panels to watch during an experiment:

| Panel | What to Look For |
|---|---|
| Error Rate | Should spike during pod kill, then recover within 30s |
| P99 Latency | Should stay below hypothesis threshold |
| Available Pod Count | Should drop by blast radius %, then recover |
| Circuit Breaker State | Should stay Closed; if it opens, something is wrong |
| Requests Per Second | Should dip briefly on pod kill (failover), then recover |

### Reading the PDF Report

The report is generated automatically and posted to `#chaos-reports` in Slack. It contains:

1. **Executive Summary** — one-paragraph verdict: did the system behave as expected?
2. **Timeline** — exact timestamps for experiment start, chaos injection, hypothesis evaluation, recovery
3. **Metrics** — before/during/after table for error rate and latency
4. **Hypothesis Evaluation** — pass/fail with the exact values compared
5. **Recommendations** — specific action items if the hypothesis failed

---

## Stopping an Experiment Early

```bash
curl -X DELETE http://localhost:8001/experiments/$EXPERIMENT_ID
```

The chaos engine will immediately stop injecting chaos and allow the system to recover naturally.

---

## After the Experiment

1. Verify all pods are healthy: `kubectl get pods -n chaos-platform`
2. Verify error rate is back to baseline in Grafana
3. If the hypothesis failed, file a ticket with the specific recommendation from the PDF report
4. Update the hypothesis threshold if you deliberately changed your SLO
