# Architecture Overview

## Purpose

The Chaos Engineering and Load Testing Platform addresses a fundamental gap in how engineering teams validate system reliability. Most systems are tested under normal conditions during development, but real failures occur under abnormal conditions: a pod dies during peak traffic, network latency spikes between two services, or a memory leak causes gradual degradation over hours. This platform creates those abnormal conditions deliberately, in a controlled environment, so teams can observe system behaviour, verify recovery mechanisms, and fix weaknesses before they affect users.

The platform has two primary capabilities:

**Chaos Engineering**: The chaos engine injects specific, bounded faults into running Kubernetes workloads. Before each experiment, an operator defines a hypothesis: a quantitative assertion about what the system's behaviour should be during the fault. After the experiment, the platform evaluates whether the system met that threshold and generates a structured report.

**Load Testing**: The load tester generates configurable HTTP traffic profiles against the target service. It can model gradual traffic ramp-up, sudden spikes, sustained soak loads, and stepwise increases to find the exact request rate at which errors begin. KEDA scales the worker pool automatically during tests.

---

## System Components

### Application Layer

**Target Application**

A representative e-commerce REST API built with FastAPI and Python 3.11. It exposes endpoints for product listing, cart management, and order processing, backed by PostgreSQL via SQLAlchemy. The target application is deliberately realistic: it uses connection pooling, performs multi-table joins, and has configurable artificial latency to simulate a real service. It is the primary subject of all chaos experiments and load tests.

**Chaos Engine**

A Python asyncio service exposing a REST API. When an experiment is triggered, the engine queries the Kubernetes API to list pods matching the target label selector, selects a subset according to the blast radius parameter (maximum 50%), and applies the requested fault type. Fault types include pod termination, network delay via the tc/netem kernel module, CPU stress via a busy-loop process, and memory stress via allocation-and-hold. The engine polls Kubernetes every five seconds throughout the experiment to track pod health and collects Prometheus metrics at regular intervals.

A software circuit breaker prevents runaway experiments. If three consecutive experiments fail to reach full pod recovery within the configured timeout, the circuit breaker opens and the engine refuses to start new experiments until an operator explicitly resets it.

**Load Tester**

A Python asyncio service using httpx with HTTP/2 support. Workers maintain connection pools to the target service and send requests at the target rate using a token-bucket algorithm. Each worker aggregates per-second statistics including request rate, p50 and p99 latency, error rate, and status code distribution, and pushes these to Redis. KEDA monitors the Redis queue depth and scales the worker Deployment between one and twenty replicas to match the workload.

**Dashboard**

A React 18 single-page application built with Vite. It uses Redux Toolkit for client-side state and maintains a WebSocket connection to the chaos engine and load tester APIs for live metric updates. Recharts renders real-time charts that update every two seconds during active experiments and tests. The dashboard provides experiment management, load test configuration, and live metric visualisation without requiring access to Grafana or the CLI.

---

### Data and Event Layer

**Apache Kafka (AWS MSK)**

The primary event streaming backbone. All chaos events — experiment started, pod killed, metrics collected, hypothesis evaluated, experiment completed — are published to the `chaos-events` topic by the chaos engine. Events are partitioned by experiment ID, which guarantees that all events for a single experiment are processed in order by each consumer. The dashboard and the Slack notifier are separate consumer groups, so both receive every event independently regardless of the other's availability. Events are retained for seven days, enabling replay for debugging past experiments.

**Redis (ElastiCache)**

Used for two purposes. First, the load tester workers push per-second aggregated metrics to Redis hash structures during tests; the load tester controller reads these and exposes them via the stats API. Second, KEDA uses a Redis list as the scaling trigger: the load tester pushes work items to the list, and KEDA scales the worker Deployment proportionally to the list length.

**PostgreSQL (RDS)**

Stores experiment configuration and target application data. The chaos engine writes experiment records with full metadata on creation and updates them with results and metrics on completion. The target application uses PostgreSQL for its fake product catalogue and order data.

**DynamoDB**

Stores the scheduled experiment definitions read by the Lambda experiment scheduler. Each record contains the experiment configuration, a schedule expression, an enabled flag, and the timestamp of the last run. The 23-hour cooldown logic is enforced by comparing the current time against the last run timestamp before triggering.

---

### Observability Layer

**Prometheus**

Scrapes metrics from all platform services via ServiceMonitor custom resources. Every service exposes a `/metrics` endpoint in Prometheus exposition format. Prometheus evaluates PrometheusRules for SLO alerting using both fast-burn (one-hour window) and slow-burn (six-hour window) error budget calculations. Metrics are retained for 15 days with a 50 GB storage allocation.

**Grafana**

Six pre-built dashboards are provisioned automatically via the Grafana sidecar and ConfigMap discovery. The dashboards cover: chaos experiment overview (live experiment state, hypothesis tracking, circuit breaker status), load test overview (RPS, latency percentiles, KEDA scaling), SLO burn rate (error budget consumption), Kubernetes node health (CPU, memory, disk), Kafka consumer lag (per-topic, per-consumer-group), and security events (Falco alert frequency by rule and severity).

**Loki and Promtail**

Promtail runs as a DaemonSet on every node and tails all container log files from the Kubernetes node filesystem. It adds Kubernetes metadata labels (namespace, pod, container) and forwards structured JSON log lines to Loki. Loki stores log chunks in S3 with a 30-day retention policy. Grafana datasource federation allows correlating log lines with Prometheus metrics and Tempo traces on the same timeline.

**Grafana Tempo**

Receives OpenTelemetry traces from the OTel Collector. The chaos engine and load tester instrument all experiment and test operations with spans using the OpenTelemetry Python SDK. Tempo supports trace lookup by trace ID and exposes a TraceQL query interface. The Grafana datasource integration allows navigating from a Loki log line directly to the trace that produced it, and from a trace span to the correlated Prometheus metrics at that timestamp.

**Alertmanager**

Receives firing alerts from Prometheus and routes them to Slack via webhook. Alert routing groups by alertname and namespace to reduce notification noise. Critical severity alerts bypass grouping intervals and notify immediately.

---

### Security Layer

**HashiCorp Vault**

Deployed as a Kubernetes StatefulSet with Raft integrated storage. Each pod authenticates to Vault using its Kubernetes ServiceAccount JWT via the Kubernetes auth method — no static credentials exist in the pod environment. The database secrets engine generates unique PostgreSQL credentials for each pod with a one-hour TTL; credentials are automatically rotated by Vault when they expire. All secret reads and writes are logged to stdout in JSON format and captured by Promtail.

**OPA/Gatekeeper**

An admission webhook that evaluates Rego policies against every resource creation and update request to the Kubernetes API. Six policies are enforced: container images must originate from the project ECR registry, containers must not run as root, Services of type LoadBalancer are denied outside approved namespaces, all containers must specify CPU and memory limits, the latest image tag is denied, and containers must use a read-only root filesystem. All policies have accompanying Rego unit tests.

**Kyverno**

A complementary admission controller using YAML-native policy syntax. Eight policies handle cases where Kyverno's pattern-matching approach is simpler than Rego: requiring resource limits, validating image tags, mutating pods to inject standard labels, and enforcing read-only root filesystems. Kyverno also handles mutation policies, which OPA/Gatekeeper does not support natively.

**Falco**

A DaemonSet that uses an eBPF program loaded into the kernel to monitor system calls from every container on every node. Seven custom rules detect significant events: a shell being spawned inside an application container, writes to sensitive filesystem paths, network connections to Vault from unauthorised containers, privilege escalation attempts, and container drift (new executables appearing in running containers). Alerts are forwarded via gRPC to Falcosidekick, which publishes them to SNS.

**cert-manager**

Manages TLS certificates as Kubernetes custom resources. A self-signed ClusterIssuer bootstraps an internal CA certificate, which a CA ClusterIssuer then uses to sign service certificates. For external-facing services, an ACME ClusterIssuer obtains and automatically renews certificates from Let's Encrypt using HTTP-01 challenges. Certificate rotation is entirely automated.

**Sealed Secrets**

The Sealed Secrets controller holds an RSA private key in the cluster. Operators use the kubeseal CLI to encrypt Kubernetes Secret manifests using the corresponding public key. The encrypted SealedSecret resources are safe to commit to the git repository; only the controller can decrypt them. This eliminates the need for a separate secret distribution mechanism for non-dynamic secrets.

---

### Serverless Layer

**report-generator Lambda**

Triggered by S3 ObjectCreated events when the chaos engine writes an experiment result JSON file, and by SNS messages for on-demand report generation. Reads the full experiment record from DynamoDB, constructs an HTML report using a template engine, renders it to a PDF using WeasyPrint (which requires a custom Lambda layer with native libpango and libcairo libraries), uploads the PDF to S3, generates a presigned URL with a seven-day expiry, and publishes the URL to SNS for downstream notification.

**slack-notifier Lambda**

Subscribes to the chaos-notifications SNS topic. Formats Slack Block Kit payloads for four event types: experiment started, experiment completed (with pass/fail verdict), report generated (with PDF download button), and security alert fired. Routes each event type to the appropriate Slack channel. The Slack webhook URL is stored as a SecureString in SSM Parameter Store and retrieved at invocation time.

**experiment-scheduler Lambda**

Triggered by EventBridge on a cron schedule (02:00 UTC, Monday through Friday). Scans the DynamoDB scheduled experiments table, evaluates each enabled experiment against its schedule expression, enforces a 23-hour cooldown by comparing against the last run timestamp, and calls the chaos engine API to trigger qualifying experiments. Failed API calls are retried up to three times with exponential backoff.

---

## Design Principles

**GitOps as the single source of truth**: Every Kubernetes resource is defined in git. ArgoCD reconciles the cluster state to match git continuously. The cluster state is always derivable from the repository, enabling reproducible deployments and complete audit history.

**Least privilege throughout**: Each service has its own Kubernetes ServiceAccount, Vault policy, and IRSA role scoped to only the resources it needs. A compromised chaos engine pod cannot read dashboard secrets, create Vault tokens, or access other namespaces.

**Observe before acting**: Prometheus metrics, structured logs, and distributed traces are instrumented from the start of the project, not added later. Every significant operation produces a trace span, a log line, and a Prometheus counter update.

**Fail safely**: The 50% blast radius cap, the circuit breaker, and the 23-hour experiment cooldown are all safety mechanisms that prevent the platform from causing a self-inflicted production incident. The OPA and Kyverno admission policies ran in Audit mode for two weeks before switching to Enforce, which prevented policy misconfiguration from blocking legitimate workloads.

**Automated reporting closes the feedback loop**: The automatic PDF report, generated within 60 seconds of experiment completion and delivered to Slack, ensures that results are reviewed promptly. The report includes specific remediation recommendations when a hypothesis fails, making the next action clear without requiring the operator to interpret raw metrics.
