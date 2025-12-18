# Chaos Engineering and Load Testing Platform

![Last Commit](https://img.shields.io/github/last-commit/jhonny1677/chaos-platform)
![Repo Size](https://img.shields.io/github/repo-size/jhonny1677/chaos-platform)
![License](https://img.shields.io/badge/license-MIT-blue)

A production-grade chaos engineering and load testing platform built on AWS EKS. The platform deliberately injects faults into running Kubernetes workloads — killing pods, introducing network latency, exhausting CPU and memory — and measures whether the system maintains its defined reliability thresholds. A companion load testing engine generates configurable traffic profiles to determine service capacity limits and validate autoscaling behaviour under sustained and peak load. Every experiment concludes with an automated PDF report delivered to Slack, containing before-and-after metrics, hypothesis evaluation, and remediation recommendations.

---

## Architecture

```
                           +--- GitHub ---+
                           |  CI/CD push  |
                           +------+-------+
                                  | ArgoCD GitOps
                    +-------------v--------------------------------------+
                    |         AWS EKS Cluster (t3.medium nodes)          |
                    |                                                     |
                    |  +-------------+  +-----------------+              |
                    |  | Chaos Engine|  |   Load Tester   |              |
                    |  | pod-kill    |  |  ramp/spike/soak|              |
                    |  | net-delay   +--+  KEDA 1-20 pods |              |
                    |  | cpu/memory  |  |  httpx + HTTP/2 |              |
                    |  +------+------+  +--------+--------+              |
                    |         |                  |                       |
                    |         v                  v                       |
                    |  +------------------------------------------+      |
                    |  |          Target App (FastAPI)             |      |
                    |  |          The system under test            |      |
                    |  +-----------------------+------------------+      |
                    |                          |                         |
                    |  +-----------------------v------------------+      |
                    |  |  Kafka (MSK)  |  Redis (ElastiCache)    |      |
                    |  |  event stream |  live stats cache        |      |
                    |  +------------------------------------------+      |
                    |                                                     |
                    |  +------------------------------------------+      |
                    |  |  Prometheus  Grafana  Loki  Tempo        |      |
                    |  |  Alertmanager  OpenTelemetry Collector   |      |
                    |  +------------------------------------------+      |
                    |                                                     |
                    |  +------------------------------------------+      |
                    |  |  Vault  OPA/Gatekeeper  Kyverno  Falco   |      |
                    |  |  cert-manager  Sealed Secrets             |      |
                    |  +------------------------------------------+      |
                    +-------------+--------------------------------------+
                                  |
              +-------------------+---------------------+
              |                   |                     |
    +---------+------+  +---------+------+  +-----------+------+
    |  DynamoDB      |  |   S3 Buckets   |  |  Lambda + SNS    |
    |  experiments   |  |  state/reports |  |  report-gen      |
    |  state lock    |  |  results/logs  |  |  slack-notifier  |
    +----------------+  +----------------+  |  exp-scheduler   |
                                            +------------------+
                                                     |
                                            +--------v--------+
                                            |  Slack          |
                                            |  notifications  |
                                            |  PDF reports    |
                                            +-----------------+
```

---

## Tech Stack

| Tool | Role |
|---|---|
| Terraform | Provisions all AWS infrastructure: EKS, VPC, MSK, RDS, ElastiCache, S3, IAM |
| AWS EKS | Managed Kubernetes cluster running all platform workloads |
| Python 3.11 | Backend language for chaos engine, load tester, and target application |
| FastAPI | REST API framework for the chaos engine and target application |
| asyncio + httpx | Async HTTP client for concurrent load generation (HTTP/2 support) |
| React 18 + Vite | Real-time dashboard with WebSocket-based live metric updates |
| Redux Toolkit | Client-side state management for experiment and test state |
| Recharts | Live metric charting in the dashboard |
| Apache Kafka (MSK) | Ordered event streaming between chaos engine, dashboard, and observers |
| Redis (ElastiCache) | Sub-second load test stat aggregation and KEDA queue trigger |
| PostgreSQL (RDS) | Persistent experiment configuration storage |
| DynamoDB | Experiment results and scheduled job state |
| KEDA | Event-driven autoscaling for load tester worker pods (1 to 20 replicas) |
| ArgoCD | GitOps continuous delivery with App-of-Apps pattern and sync waves |
| GitHub Actions | CI pipelines: build, test, security scan, ECR push |
| Jenkins | Kubernetes-native pipeline runner with seed job DSL |
| Helmfile | Declarative multi-chart Helm release management |
| Prometheus | Metrics collection via ServiceMonitor CRDs, 15-day retention |
| Grafana | Six pre-built dashboards covering chaos, load test, SLO, and security |
| Loki | Log aggregation with S3 backend and 30-day retention |
| Grafana Tempo | Distributed tracing with trace-to-log correlation |
| Alertmanager | SLO-based alerting with fast-burn and slow-burn rules |
| OpenTelemetry Collector | Unified telemetry pipeline routing traces and metrics |
| HashiCorp Vault | Dynamic database credentials, Kubernetes auth, audit logging |
| OPA/Gatekeeper | Admission control with six Rego policies and unit tests |
| Kyverno | Kubernetes-native policy engine for validation and mutation |
| Falco | eBPF-based runtime security monitoring with custom rule set |
| cert-manager | Automatic TLS certificate issuance via Let's Encrypt ACME |
| Sealed Secrets | Asymmetric encryption for secrets safe to commit to git |
| Dependency Track | Continuous SBOM ingestion and CVE monitoring |
| AWS Lambda | Serverless report generation, Slack notification, experiment scheduling |
| WeasyPrint | HTML-to-PDF rendering inside Lambda for experiment reports |
| SNS + EventBridge | Event routing and cron-based experiment scheduling |
| ECR | Private container image registry for all platform services |
| IRSA | Pod-level AWS IAM via ServiceAccount annotation, no static credentials |

---

## Project Structure

```
chaos-platform/
├── terraform/
│   ├── modules/            vpc, eks, rds, msk, elasticache, ecr, s3, iam
│   └── environments/dev/   main.tf, variables.tf, outputs.tf, versions.tf
│
├── apps/
│   ├── target-app/         FastAPI e-commerce service (the system under test)
│   ├── chaos-engine/       Fault injection engine: pod-kill, network-delay, cpu, memory
│   ├── load-tester/        Load generation: ramp, spike, soak, breaking-point scenarios
│   └── dashboard/          React 18 real-time dashboard
│
├── k8s/
│   ├── base/               Kustomize base manifests for all services
│   ├── overlays/dev/       Environment-specific patches
│   └── monitoring/         ServiceMonitors, PrometheusRules, Grafana dashboards
│
├── helm/
│   ├── helmfile.yaml       Unified release definitions for all Helm charts
│   └── values/             Per-chart values files
│
├── argocd/
│   ├── apps/               App-of-Apps: one Application manifest per service
│   └── projects/           ArgoCD Projects with RBAC constraints
│
├── monitoring/
│   ├── prometheus/         SLO alert rules and chaos-specific recording rules
│   ├── grafana/            Six dashboard JSON definitions
│   ├── loki/               Loki configuration and Promtail DaemonSet
│   └── tempo/              Grafana Tempo deployment
│
├── security/
│   ├── vault/              StatefulSet, Raft config, four policies, operational scripts
│   ├── opa/                Six Rego policies, ConstraintTemplates, unit tests
│   ├── kyverno/            Six namespace policies, two ClusterPolicies
│   ├── falco/              Seven custom rules, DaemonSet, eBPF driver loader
│   ├── sealed-secrets/     Example SealedSecrets and seal/verify scripts
│   ├── cert-manager/       ClusterIssuers and certificate resources
│   └── dependency-track/   Deployment and SBOM upload scripts
│
├── lambda/
│   ├── report-generator/   WeasyPrint PDF generation, S3 upload, presigned URL
│   ├── slack-notifier/     Block Kit formatter, channel routing, SSM webhook
│   ├── experiment-scheduler/ DynamoDB scan, cooldown enforcement, retry logic
│   └── terraform/          IAM roles, EventBridge rules, SNS subscriptions
│
├── .github/workflows/      CI, Release, Terraform plan/apply, security scan
├── jenkins/                Jenkinsfile, seed job DSL, Kubernetes agent pod templates
│
└── docs/
    ├── architecture/       System overview, ASCII diagram, data flow, decision log
    ├── runbooks/           Getting started, chaos, load test, troubleshooting, cost
    └── adr/                Five Architecture Decision Records
```

---

## How to Deploy

### Prerequisites

- AWS CLI v2 configured with admin credentials
- Terraform 1.7 or later
- kubectl 1.29 or later
- Helm 3.14 and Helmfile 0.162
- Docker 24 or later
- ArgoCD CLI 2.10 or later

### Step 1: Provision AWS Infrastructure

```bash
cd terraform/environments/dev
terraform init
terraform apply
```

This creates the EKS cluster, VPC, MSK Kafka cluster, ElastiCache Redis, RDS PostgreSQL, S3 buckets, DynamoDB tables, and all IAM roles. Expect approximately 20 minutes.

### Step 2: Configure kubectl

```bash
aws eks update-kubeconfig --region us-east-1 --name chaos-platform-dev
kubectl cluster-info
```

### Step 3: Bootstrap the Platform

```bash
./scripts/bootstrap.sh
```

The script installs ArgoCD via Helm, then creates the root App-of-Apps Application. ArgoCD takes over and deploys all remaining components in sync wave order: monitoring infrastructure first, then security components, then application workloads.

### Step 4: Initialize Vault

```bash
./security/vault/scripts/init-vault.sh
```

Initialises Vault with a 5-of-3 Shamir key split, stores the unseal keys as a Kubernetes Secret, performs the initial unseal, and applies all four access policies.

### Step 5: Build and Push Container Images

```bash
REGISTRY=$(aws ecr describe-repositories \
  --query 'repositories[0].repositoryUri' --output text | cut -d/ -f1)
aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY

for service in target-app chaos-engine load-tester dashboard; do
  docker build -t $REGISTRY/$service:latest apps/$service/
  docker push $REGISTRY/$service:latest
done
```

### Step 6: Deploy Lambda Functions

```bash
cd lambda/terraform
terraform init
terraform apply \
  -var="results_bucket=chaos-platform-dev-results" \
  -var="reports_bucket=chaos-platform-dev-reports" \
  -var="experiments_table=chaos-platform-experiments"
```

### Step 7: Verify

```bash
kubectl get applications -n argocd
kubectl get pods --all-namespaces
kubectl port-forward svc/dashboard 8080:8080 -n chaos-platform
```

Open http://localhost:8080 for the dashboard and http://localhost:3000 for Grafana (after port-forwarding that service separately).

Full deployment reference: [docs/runbooks/getting-started.md](docs/runbooks/getting-started.md)

---

## What This Project Demonstrates

**Infrastructure as Code**: The entire AWS environment is defined in Terraform using a modular structure. Each AWS service is an independent module with its own variables, outputs, and resource definitions. Remote state is stored in S3 with DynamoDB locking.

**Kubernetes and GitOps**: All workloads run on EKS and are managed exclusively through ArgoCD. No `kubectl apply` in the deployment path. Sync waves enforce deployment ordering across namespaces. Drift detection reverts any manual changes.

**Distributed Systems Design**: The platform uses Kafka for ordered, replayable event streaming, Redis for sub-second metric aggregation, and a circuit breaker to halt chaos automatically if the system cannot recover. Partitioning by experiment ID ensures event ordering per experiment.

**Observability**: Every service emits Prometheus metrics via ServiceMonitor CRDs, structured JSON logs collected by Promtail into Loki, and OpenTelemetry traces forwarded to Grafana Tempo. Six pre-built Grafana dashboards cover every layer of the platform.

**Security Engineering**: Vault provides dynamic database credentials that expire after one hour. OPA and Kyverno enforce admission control policies at the Kubernetes API level. Falco monitors system calls at the kernel level using eBPF. All credentials are stored in Vault or AWS SSM; nothing is hardcoded.

**Serverless and Event-Driven Architecture**: Three Lambda functions handle report generation, Slack notification routing, and scheduled experiment triggering. They are wired together via SNS, EventBridge, and S3 event notifications, with no polling or direct coupling.

**CI/CD Pipelines**: GitHub Actions runs four workflow types (build and test, image release, Terraform plan, weekly security scan). Jenkins provides a Kubernetes-native pipeline runner with dynamically provisioned agent pods.

**Python Backend Engineering**: The chaos engine uses asyncio for concurrent fault injection across multiple pods. The load tester uses httpx with HTTP/2 support to maintain thousands of concurrent connections from a single process. Both services expose OpenAPI-documented REST APIs via FastAPI.

---

## Documentation

| Document | Description |
|---|---|
| [Architecture Overview](docs/architecture/README.md) | Detailed description of every component and how they interconnect |
| [Architecture Diagram](docs/architecture/architecture-diagram.md) | Full ASCII diagram with all services and data flows annotated |
| [Data Flow](docs/architecture/data-flow.md) | Step-by-step trace of a chaos experiment and a load test from trigger to report |
| [Decision Log](docs/architecture/decision-log.md) | Summary of all 26 major technical decisions with rationale |
| [Getting Started](docs/runbooks/getting-started.md) | Full prerequisites, setup steps, and common error resolutions |
| [Running Chaos Experiments](docs/runbooks/running-chaos-experiment.md) | Dashboard and API usage, hypothesis configuration, result interpretation |
| [Running Load Tests](docs/runbooks/running-load-test.md) | Scenario types, live statistics, breaking point analysis |
| [Troubleshooting](docs/runbooks/troubleshooting.md) | Seven common failure modes with diagnosis commands and resolution steps |
| [Cost Management](docs/runbooks/cost-management.md) | Cost breakdown, reduction strategies, billing alerts, full teardown |
| [ADR-001: Python](docs/adr/ADR-001-python-over-java.md) | Why Python over Go or Java for backend services |
| [ADR-002: Kafka](docs/adr/ADR-002-kafka-over-sqs.md) | Why Kafka over SQS or EventBridge for event streaming |
| [ADR-003: ArgoCD](docs/adr/ADR-003-argocd-gitops.md) | Why GitOps over CI-driven Helm upgrades |
| [ADR-004: Vault](docs/adr/ADR-004-vault-over-secrets-manager.md) | Why HashiCorp Vault over AWS Secrets Manager |
| [ADR-005: OPA and Kyverno](docs/adr/ADR-005-kyverno-and-opa.md) | Why both admission controllers are used together |
| [Deployment Guide](DEPLOYMENT.md) | Step-by-step deployment, verification, and teardown reference |

---

## License

MIT License

Copyright (c) 2025 Ankit

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
