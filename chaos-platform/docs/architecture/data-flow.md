# Data Flow

## What Happens During a Chaos Experiment

This walkthrough traces every step from the moment a user triggers an experiment to the PDF report arriving in Slack.

### Step 1: Experiment Triggered (t=0)

The user clicks "Start Experiment" in the React dashboard or calls the chaos engine REST API directly:

```
POST http://chaos-engine.chaos-engine.svc.cluster.local:8001/experiments
{
  "type": "pod-kill",
  "targetNamespace": "chaos-engine",
  "targetLabel": "app=target-app",
  "durationSeconds": 300,
  "blastRadius": 0.5
}
```

### Step 2: Chaos Engine Validates and Plans (t=0s–2s)

1. The chaos engine receives the request and generates a unique `experimentId` (e.g., `exp-20260127-abc1234`).
2. It writes the initial record to DynamoDB with status `running`.
3. It queries the Kubernetes API to list all pods matching the `targetLabel` in `targetNamespace`.
4. It calculates the blast radius: if there are 6 matching pods and `blastRadius=0.5`, it selects 3 to kill.
5. **Circuit breaker check**: if the last 3 experiments all failed to recover, the engine refuses to start and returns HTTP 503.

### Step 3: Chaos Injected (t=2s–5s)

1. The chaos engine calls `kubectl delete pod` for each selected pod.
2. Kubernetes immediately marks those pods as `Terminating` and stops sending them traffic via the Service's endpoint slice.
3. New pods are scheduled by the Kubernetes scheduler and begin starting up.
4. The chaos engine publishes a `chaos.pod-killed` event to the Kafka topic `chaos-events`.
5. The chaos engine publishes an `experiment.started` SNS message to `chaos-notifications`.

### Step 4: Slack Notification (t=5s–8s)

The SNS message triggers the `slack-notifier` Lambda:
1. Lambda receives the SNS event.
2. `message_formatter.py` builds a Block Kit payload.
3. `slack_client.py` POSTs to the Slack webhook URL (fetched from SSM Parameter Store).
4. Engineers see the alert in `#chaos-experiments` within 10 seconds of the experiment starting.

### Step 5: Recovery Phase (t=5s–120s)

1. New pods reach `Running` state and pass readiness probes.
2. Kubernetes adds them back to the Service's endpoint slice.
3. Traffic resumes to all pods.
4. The chaos engine polls pod status every 5 seconds.
5. Once all pods are `Ready`, the chaos engine evaluates the hypothesis.

### Step 6: Metrics Collection (throughout)

Every 15 seconds during the experiment, the chaos engine:
1. Queries Prometheus for error rate, p50/p99 latency, and available pod count.
2. Stores the metric snapshot in the DynamoDB record under `metrics.during`.
3. Emits a `chaos.metrics` Kafka event for streaming to the dashboard.
4. The React dashboard receives this via WebSocket and updates the live chart.

### Step 7: Hypothesis Evaluation (t=300s)

After `durationSeconds` elapses:
1. The chaos engine fetches the final metrics from Prometheus.
2. It compares them against the hypothesis thresholds.
3. It writes the final record to DynamoDB: `hypothesisPassed: true/false`.
4. It publishes an `experiment.completed` SNS event with the result.
5. It writes a result JSON file to `s3://chaos-platform-results/results/exp-20260127-abc1234.json`.

### Step 8: Report Generation (t=300s–360s)

The S3 ObjectCreated event triggers the `report-generator` Lambda within seconds:
1. Lambda reads the full experiment record from DynamoDB.
2. `report_builder.py` generates an HTML string with inline CSS.
3. `pdf_generator.py` renders the HTML to PDF bytes using WeasyPrint.
4. `s3_uploader.py` uploads the PDF to `s3://chaos-platform-reports/reports/exp-*.pdf`.
5. Lambda generates a presigned URL valid for 7 days.
6. Lambda publishes a `report.generated` SNS event with the presigned URL.
7. The `slack-notifier` Lambda receives this and posts the download link to `#chaos-reports`.

**Total time from experiment completion to Slack report: typically under 60 seconds.**

---

## What Happens During a Load Test

### Step 1: Load Test Started (t=0)

```
POST http://load-tester.load-tester.svc.cluster.local:8002/tests
{
  "scenario": "spike",
  "targetUrl": "http://target-app.chaos-platform.svc.cluster.local:8000",
  "virtualUsers": 100,
  "durationSeconds": 300
}
```

### Step 2: KEDA Scales Workers (t=0s–30s)

1. The load tester controller creates a `LoadTest` custom resource.
2. KEDA detects the pending work via a Redis queue length trigger.
3. KEDA scales the `load-tester` Deployment from 1 to up to 20 pods.
4. Each worker pod picks up a shard of the virtual user workload.

### Step 3: Traffic Generation (t=30s–330s)

Each worker pod:
1. Sends HTTP/2 requests to the target URL using `httpx`.
2. Records latency, status code, and timestamp for every response.
3. Aggregates stats every second: RPS, p50, p99, error rate.
4. Pushes the aggregated stats to Redis as a time-series hash.

### Step 4: Live Stats (real-time)

1. The load tester controller reads from Redis every 2 seconds.
2. It emits metrics to Prometheus (scraped every 15s by the ServiceMonitor).
3. The dashboard WebSocket polls the load tester API every 2 seconds.
4. The React dashboard renders a live chart showing RPS and latency.

### Step 5: Test Completion (t=330s)

1. Workers drain their request queue and exit cleanly.
2. KEDA scales the Deployment back to 1 replica (minimum).
3. The controller aggregates all worker stats into a final result.
4. The result is written to DynamoDB and `s3://results/load-test-*.json`.
5. The S3 event triggers `report-generator` → PDF → Slack (same as chaos experiments).

---

## Where Data Lives

| Data Type | Created By | Stored In | Expires |
|---|---|---|---|
| Experiment definition | Chaos Engine | DynamoDB | Never (manual delete) |
| Experiment metrics | Chaos Engine | DynamoDB + Prometheus | DynamoDB: never; Prometheus: 15 days |
| Load test results | Load Tester | DynamoDB | Never |
| Logs | All pods | Loki (S3 backend) | 30 days |
| Traces | All pods → OTel Collector | Grafana Tempo | 72 hours |
| PDF Reports | Lambda | S3 (reports bucket) | Never (lifecycle policy optional) |
| Presigned URLs | Lambda | Slack message | 7 days |
| Vault secrets | Vault admin | Vault (Raft on PVC) | TTL-based (1h for dynamic, manual for static) |
| Container images | GitHub Actions | ECR | Last 10 tags kept per repo |
| Terraform state | Terraform | S3 (state bucket) | Never |
