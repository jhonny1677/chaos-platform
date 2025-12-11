# Chaos Engineering & Load Testing Platform

![Infrastructure](https://img.shields.io/badge/Infrastructure-Terraform-7B42BC?style=flat-square&logo=terraform)
![Kubernetes](https://img.shields.io/badge/Kubernetes-EKS_1.29-326CE5?style=flat-square&logo=kubernetes)
![Python](https://img.shields.io/badge/Backend-Python_3.11-3776AB?style=flat-square&logo=python)
![React](https://img.shields.io/badge/Frontend-React_18-61DAFB?style=flat-square&logo=react)
![ArgoCD](https://img.shields.io/badge/CD-ArgoCD_GitOps-EF7B4D?style=flat-square)
![Vault](https://img.shields.io/badge/Secrets-HashiCorp_Vault-FFEC6E?style=flat-square&logo=vault&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Phases](https://img.shields.io/badge/Phases-10_Complete-success?style=flat-square)

A production-grade chaos engineering and load testing platform built on AWS EKS. Deliberately breaks your systems before your customers do, measures how they fail, and tells you exactly what to fix.

---

## What This Is

This platform has two main tools that work together:

**Chaos Engine** — kills pods, adds network delay, exhausts CPU and memory inside your Kubernetes cluster. Runs on a hypothesis: you define acceptable degradation thresholds, the platform measures them, and tells you PASS or FAIL with a PDF report automatically posted to Slack.

**Load Tester** — generates realistic HTTP traffic (ramp, spike, soak, breaking-point scenarios) while KEDA auto-scales workers from 1 to 20 pods. Finds the exact RPS at which your service starts failing so you can set your HPA thresholds correctly.

Run both together: steady load + chaos injection = the most realistic picture of how your system behaves when something breaks in production.

---

## Architecture

```
                           ┌─── GitHub ───┐
                           │  CI/CD push  │
                           └──────┬───────┘
                                  │ ArgoCD GitOps
                    ┌─────────────▼──────────────────────────┐
                    │         AWS EKS (SPOT t3.medium)        │
                    │                                         │
                    │  ┌─────────────┐  ┌─────────────────┐  │
                    │  │ Chaos Engine│  │   Load Tester   │  │
                    │  │ pod-kill    │  │  ramp/spike/soak│  │
                    │  │ net-delay   │◄►│  KEDA 1-20 pods │  │
                    │  │ cpu/memory  │  │  httpx + HTTP/2 │  │
                    │  └──────┬──────┘  └────────┬────────┘  │
                    │         │                   │           │
                    │         ▼                   ▼           │
                    │  ┌─────────────────────────────────┐   │
                    │  │   Target App (FastAPI)           │   │
                    │  │   The system under test          │   │
                    │  └──────────────┬──────────────────┘   │
                    │                 │                       │
                    │  ┌──────────────▼──────────────────┐   │
                    │  │  Kafka (MSK) │ Redis (ElastiCache│   │
                    │  │  events log  │ live stats cache  │   │
                    │  └─────────────────────────────────-┘   │
                    │                                         │
                    │  ┌─────────────────────────────────┐   │
                    │  │  Prometheus · Grafana · Loki     │   │
                    │  │  Tempo · Alertmanager · OTel     │   │
                    │  └─────────────────────────────────-┘   │
                    │                                         │
                    │  ┌─────────────────────────────────┐   │
                    │  │  Vault · OPA · Kyverno · Falco   │   │
                    │  │  cert-manager · Sealed Secrets   │   │
                    │  └─────────────────────────────────-┘   │
                    └─────────────┬───────────────────────────┘
                                  │
              ┌───────────────────┼──────────────────────┐
              │                   │                      │
    ┌─────────▼──────┐  ┌─────────▼──────┐  ┌──────────▼──────┐
    │  DynamoDB      │  │   S3 Buckets   │  │  Lambda + SNS   │
    │  experiments   │  │  state/reports │  │  report-gen     │
    │  state lock    │  │  results/logs  │  │  slack-notifier │
    └────────────────┘  └────────────────┘  │  exp-scheduler  │
                                            └─────────────────┘
                                                     │
                                            ┌────────▼────────┐
                                            │  Slack          │
                                            │  #chaos-reports │
                                            │  PDF + alerts   │
                                            └─────────────────┘
```

---

## Features

### Chaos Engineering
| Feature | Details |
|---|---|
| Pod Kill | Kills N% of pods matching a label selector, respects 50% blast radius cap |
| Network Delay | Injects configurable latency and jitter using tc/netem |
| CPU Stress | Consumes target CPU percentage for the experiment duration |
| Memory Stress | Allocates and holds memory to trigger OOM conditions |
| Hypothesis Testing | Define SLO thresholds before experiments; auto-evaluated on completion |
| Circuit Breaker | Stops all chaos if 3 consecutive experiments fail to recover |
| Blast Radius Cap | Hard limit of 50% — platform refuses experiments above this |

### Load Testing
| Feature | Details |
|---|---|
| Ramp Scenario | Linearly increase RPS from start to end over duration |
| Spike Scenario | Instant jump to peak RPS, tests autoscaling response time |
| Soak Scenario | Constant RPS for hours, finds gradual memory leaks |
| Breaking Point | Increase by step until failure threshold exceeded |
| KEDA Autoscaling | Workers scale 1→20 pods based on Redis queue depth |
| HTTP/2 Support | httpx with HTTP/2 for realistic modern traffic patterns |
| Live Stats | P50/P99/RPS/errors updated every 2 seconds in the dashboard |

### Observability
| Component | Role |
|---|---|
| Prometheus | Scrapes all services via ServiceMonitor CRDs, 15-day retention |
| Grafana | 6 pre-built dashboards: chaos overview, load test, SLO, K8s nodes, Kafka, security |
| Loki | Structured JSON logs from all pods, S3 backend, 30-day retention |
| Grafana Tempo | Distributed traces with trace-to-log correlation |
| Alertmanager | Slack + email alerts with fast-burn (1h window) and slow-burn (6h window) SLO rules |
| OTel Collector | Unified telemetry pipeline: traces → Tempo, metrics → Prometheus |

### Security (10 components)
| Component | What It Does |
|---|---|
| HashiCorp Vault | Dynamic DB credentials (1h TTL), K8s auth, 4 least-privilege policies, audit log |
| OPA/Gatekeeper | 6 Rego policies: registry allowlist, non-root, no public services, resource limits |
| Kyverno | 8 policies: require limits, disallow latest tag, mutate labels, read-only rootfs |
| Falco | 7 custom rules, eBPF syscall monitoring, alerts via Falcosidekick → SNS |
| Sealed Secrets | Asymmetrically encrypted secrets safe to commit to git |
| cert-manager | Automatic TLS cert issuance via Let's Encrypt ACME |
| IRSA | Pod-level AWS IAM via ServiceAccount annotation — no static credentials |
| Dependency Track | CycloneDX SBOM ingestion, ongoing CVE monitoring for deployed images |
| Network Policies | Namespace isolation, default-deny, explicit allow rules |
| Pod Security | Non-root, read-only rootfs, no privilege escalation enforced by admission control |

### CI/CD
| Component | Role |
|---|---|
| GitHub Actions | 4 workflows: CI (build/test/scan), Release (tag + ECR push), IaC (Terraform plan/apply), Security (weekly Trivy scan) |
| ArgoCD | App-of-Apps GitOps, sync waves for ordered deployment, drift detection |
| Jenkins | Kubernetes-native agent pods, seed job DSL, nightly chaos test job |
| Helmfile | Local dev bootstrap and ArgoCD pre-seeding |

### Lambda Automation
| Function | Trigger | What It Does |
|---|---|---|
| report-generator | S3 ObjectCreated, SNS | WeasyPrint PDF generation, S3 upload, presigned URL, Slack post |
| slack-notifier | SNS subscription | Block Kit formatter for 4 event types, channel routing, SSM webhook |
| experiment-scheduler | EventBridge cron 02:00 UTC Mon–Fri | DynamoDB scan, 23h cooldown, 3× exponential backoff retry |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Infrastructure | Terraform 1.7, AWS EKS 1.29, SPOT t3.medium nodes |
| Networking | VPC 10.0.0.0/16, NAT Gateway, ALB Ingress, Network Policies |
| Container Runtime | containerd, ECR, multi-stage Docker builds |
| Backend | Python 3.11, FastAPI, asyncio, httpx[http2], kubernetes-client |
| Frontend | React 18, Vite, Redux Toolkit, Recharts, WebSocket |
| Streaming | Apache Kafka (MSK), SASL/SCRAM-SHA-512 |
| Caching | Redis (ElastiCache), KEDA Redis queue trigger |
| Database | PostgreSQL (RDS), DynamoDB (on-demand) |
| Serverless | AWS Lambda Python 3.11, WeasyPrint layer, X-Ray tracing |
| Events | SNS, EventBridge, S3 bucket notifications |
| Metrics | Prometheus, Grafana, Alertmanager, kube-state-metrics, node-exporter |
| Logs | Loki, Promtail, S3 backend |
| Traces | Grafana Tempo, OpenTelemetry Collector, OTLP |
| Secrets | HashiCorp Vault 1.15, SSM Parameter Store |
| Policy | OPA/Gatekeeper, Kyverno, Pod Security Admission |
| Security | Falco eBPF, Trivy, Dependency Track, Sealed Secrets |
| TLS | cert-manager, Let's Encrypt ACME, ECDSA P-256 |
| CD | ArgoCD 2.10, App-of-Apps, sync waves |
| CI | GitHub Actions, Jenkins (K8s agent pods) |
| Scaling | KEDA 2.13, HPA, Cluster Autoscaler |

---

## Project Structure

```
chaos-platform/
├── terraform/
│   ├── modules/                    # Reusable: vpc, eks, rds, msk, elasticache, ecr, s3, iam
│   └── environments/dev/           # Dev: main.tf, variables.tf, outputs.tf, backend.tf
│
├── apps/
│   ├── target-app/                 # FastAPI e-commerce API (the system under test)
│   ├── chaos-engine/               # Fault injection engine (pod-kill, network, cpu, memory)
│   ├── load-tester/                # Load generation (ramp, spike, soak, breaking-point)
│   └── dashboard/                  # React 18 + Vite real-time dashboard
│
├── k8s/
│   ├── base/                       # Kustomize base manifests for all 4 services
│   ├── overlays/dev/               # Dev patches (SPOT tolerations, resource limits)
│   └── monitoring/                 # ServiceMonitors, PrometheusRules, Grafana dashboards
│
├── helm/
│   ├── helmfile.yaml               # Unified helmfile for all charts
│   └── values/                     # Per-chart values files
│
├── argocd/
│   ├── apps/                       # App-of-Apps: one Application per service
│   └── projects/                   # ArgoCD Projects with RBAC
│
├── monitoring/
│   ├── prometheus/                 # PrometheusRules: SLO alerts, chaos-specific rules
│   ├── grafana/                    # 6 dashboard JSON definitions
│   ├── loki/                       # Loki config + Promtail DaemonSet
│   └── tempo/                      # Grafana Tempo deployment
│
├── security/
│   ├── vault/                      # Vault StatefulSet, Raft config, 4 policies, scripts
│   ├── opa/                        # 6 Rego policies + ConstraintTemplates + tests
│   ├── kyverno/                    # 6 namespace policies + 2 ClusterPolicies
│   ├── falco/                      # 7 custom rules + DaemonSet + eBPF loader
│   ├── sealed-secrets/             # 3 example SealedSecrets + seal/verify scripts
│   ├── cert-manager/               # 3 ClusterIssuers + 2 certificates
│   ├── dependency-track/           # Deployment + SBOM upload/CVE check scripts
│   └── docs/runbooks/              # 4 security runbooks (incident response, etc.)
│
├── lambda/
│   ├── report-generator/           # WeasyPrint PDF, S3 upload, presigned URL
│   ├── slack-notifier/             # Block Kit formatter, 4 event types, channel routing
│   ├── experiment-scheduler/       # DynamoDB scan, 23h cooldown, exponential backoff
│   └── terraform/                  # IAM, EventBridge cron, SNS subscription, S3 trigger
│
├── .github/
│   └── workflows/                  # CI, Release, IaC Terraform, Security scan
│
├── jenkins/
│   ├── Jenkinsfile                 # Main pipeline: build → test → scan → push → deploy
│   ├── jobs/                       # Seed job DSL, nightly chaos job
│   └── k8s/                        # Jenkins StatefulSet + agent pod templates
│
└── docs/
    ├── architecture/               # README, ASCII diagram, data-flow, decision-log
    ├── runbooks/                   # Getting started, chaos, load test, troubleshooting, cost
    └── adr/                        # 5 Architecture Decision Records
```

---

## Quick Start (5 Commands)

```bash
# 1. Clone and configure
git clone https://github.com/YOUR_USERNAME/chaos-platform.git
cd chaos-platform/chaos-platform

# 2. Deploy AWS infrastructure (EKS, VPC, MSK, Redis, RDS)
cd terraform/environments/dev && terraform init && terraform apply

# 3. Bootstrap Kubernetes platform (ArgoCD + all services via GitOps)
aws eks update-kubeconfig --region us-east-1 --name chaos-platform-dev
./scripts/bootstrap.sh

# 4. Initialize Vault (unseal + policies)
./security/vault/scripts/init-vault.sh

# 5. Open the dashboard
kubectl port-forward svc/dashboard 8080:8080 -n chaos-platform &
open http://localhost:8080
```

Full setup guide: [docs/runbooks/getting-started.md](docs/runbooks/getting-started.md)

---

## Running Your First Experiment

```bash
# Check the system is healthy first
kubectl get pods -n chaos-platform

# Run a pod-kill experiment with a 5% error rate hypothesis
curl -X POST http://localhost:8001/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "type": "pod-kill",
    "targetLabel": "app=target-app",
    "blastRadius": 0.5,
    "durationSeconds": 300,
    "hypothesis": {"metric": "error_rate", "threshold": 0.05, "operator": "lt"}
  }'

# Watch in Grafana: http://localhost:3000
# PDF report arrives in Slack #chaos-reports within 60 seconds of completion
```

Full guide: [docs/runbooks/running-chaos-experiment.md](docs/runbooks/running-chaos-experiment.md)

---

## Screenshots

### Dashboard — Live Experiment View
```
┌─────────────────────────────────────────────────────────────────────┐
│  ⚡ Chaos Platform               [New Experiment] [New Load Test]   │
├──────────────────────┬──────────────────────────────────────────────┤
│  Active: exp-abc1234 │  Error Rate ──────────────────────────────   │
│  Type: pod-kill      │  5% ┤                                        │
│  Status: RUNNING     │  4% ┤                              ___       │
│  Pods killed: 3/6    │  3% ┤                         ____/   \___   │
│  Elapsed: 2:14       │  2% ┤      __________________/            \  │
│  Hypothesis:         │  1% ┤_____/                                \ │
│  error_rate < 5%     │  0% └────────────────────────────────────── │
│                      │      0s      60s     120s     180s    240s   │
└──────────────────────┴──────────────────────────────────────────────┘
```

### Grafana — Chaos Platform Overview
```
┌──────────────────────────────────────────────────────────────────────┐
│ Chaos Platform Overview                    Last 1h  [Refresh: 30s]  │
├──────────────┬───────────────┬──────────────┬────────────────────────┤
│ Error Rate   │ P99 Latency   │ Pod Count    │ Circuit Breaker        │
│ 0.02%        │ 124ms         │ 6 / 6 Ready  │ CLOSED ✓               │
├──────────────┴───────────────┴──────────────┴────────────────────────┤
│  Experiments Run: 47  │  Pass Rate: 89%  │  Avg Recovery: 28s       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Build Log — 10 Phases

| Phase | What Was Built | Key Technologies |
|---|---|---|
| 1 | AWS infrastructure | Terraform, EKS, VPC, MSK, RDS, ElastiCache |
| 2 | Helm + Helmfile + ArgoCD bootstrap | Helm 3, Helmfile, ArgoCD App-of-Apps |
| 3 | Target app + chaos engine core | FastAPI, asyncio, kubernetes-client |
| 4 | Chaos experiment types + Kafka | pod-kill, network-delay, cpu-stress, MSK |
| 5 | Load tester + KEDA autoscaling | httpx, Redis, KEDA, HPA |
| 6 | React dashboard | React 18, Vite, Redux Toolkit, WebSocket, Recharts |
| 7 | CI/CD pipelines | GitHub Actions, Jenkins, ArgoCD GitOps |
| 8 | Full observability stack | Prometheus, Grafana, Loki, Tempo, Alertmanager, OTel |
| 9 | Security layer | Vault, OPA, Kyverno, Falco, Sealed Secrets, cert-manager |
| 10 | Lambda automation + documentation | Lambda, WeasyPrint, SNS, EventBridge, this README |

---

## What I Learned

Building this platform across 10 phases taught me things that blog posts don't cover:

**GitOps is non-obvious to bootstrap.** ArgoCD is excellent for managing everything — except itself. Getting the chicken-and-egg right (bootstrapping ArgoCD before it can manage anything) took iterations. The `bootstrap.sh` script is the result.

**Vault's operational burden is real.** Dynamic credentials are a genuine security improvement. But Vault needs to be initialized, unsealed after every pod restart, and monitored. In a production setup, I'd use KMS auto-unseal. The manual 3-of-5 Shamir process is appropriate for small teams with high-security requirements.

**Running both OPA and Kyverno in Audit mode first saved a self-inflicted outage.** Two weeks of audit-only revealed that Falco's DaemonSet and the OTel Collector both needed privileges that the initial policies denied. If I'd gone straight to Enforce, they would never have deployed.

**KEDA's Redis queue trigger makes the load tester elegant.** Instead of manually managing worker counts, the load tester publishes work to a Redis queue and KEDA handles the rest. This pattern is widely applicable.

**Kafka partitioning by experimentId was non-obvious but important.** Without it, events for the same experiment could be processed by different consumers out of order, making the dashboard show nonsensical state transitions.

**WeasyPrint in Lambda needs a custom layer.** The Python package itself is small but depends on libpango and libcairo which aren't available in the Lambda runtime. Building a Lambda layer with the native libraries took longer than expected.

**Chaos engineering surfaced real weaknesses.** During development, the breaking-point load tests consistently showed that the target app's database connection pool exhausted before the HPA could spin up new pods. That's a real bug in the app, found before production.

---

## Future Improvements

1. **Argo Rollouts** — Canary deployments with automatic rollback on SLO violation. The chaos platform already measures error rates; feeding that signal into a rollout controller would make deployments self-healing.

2. **GameDay Orchestration** — A higher-level workflow that runs a sequence of chaos experiments as a scheduled GameDay scenario, generates a single combined report, and tracks resilience trends over time.

3. **Kubernetes Chaos Provider** — Currently the chaos engine uses the Kubernetes client library directly. Replacing the pod-kill implementation with Chaos Mesh or Litmus Chaos would add 20+ additional fault types (disk I/O, DNS failure, HTTP abort) without custom code.

4. **Multi-Cluster** — The platform currently targets a single EKS cluster. Adding a second cluster and running cross-cluster chaos (e.g., failing the connection between clusters) would be a more realistic test of microservice architectures.

5. **Automated Hypothesis Tuning** — After running 50+ experiments, the platform has enough data to suggest hypothesis thresholds statistically (e.g., "your p99 latency is normally 124ms; we suggest a chaos hypothesis of < 400ms based on 3× your typical variance").

---

## Documentation

| Document | Description |
|---|---|
| [Architecture Overview](docs/architecture/README.md) | Plain-English description of how all components work together |
| [Architecture Diagram](docs/architecture/architecture-diagram.md) | Full ASCII diagram of every service and data flow |
| [Data Flow](docs/architecture/data-flow.md) | Step-by-step walkthrough of experiment and load test flows |
| [Decision Log](docs/architecture/decision-log.md) | Summary table of all 26 major technical decisions |
| [Getting Started](docs/runbooks/getting-started.md) | Prerequisites, step-by-step setup, common errors |
| [Running Chaos Experiments](docs/runbooks/running-chaos-experiment.md) | Dashboard + API, hypothesis evaluation, interpreting results |
| [Running Load Tests](docs/runbooks/running-load-test.md) | All scenarios, live stats, breaking point analysis |
| [Troubleshooting](docs/runbooks/troubleshooting.md) | 7 specific problems with exact diagnosis and fix commands |
| [Cost Management](docs/runbooks/cost-management.md) | Cost breakdown, reduction strategies, billing alerts, teardown |
| [ADR-001: Python](docs/adr/ADR-001-python-over-java.md) | Why Python over Go or Java |
| [ADR-002: Kafka](docs/adr/ADR-002-kafka-over-sqs.md) | Why Kafka over SQS or EventBridge |
| [ADR-003: ArgoCD](docs/adr/ADR-003-argocd-gitops.md) | Why GitOps over CI-driven Helm |
| [ADR-004: Vault](docs/adr/ADR-004-vault-over-secrets-manager.md) | Why Vault over AWS Secrets Manager |
| [ADR-005: OPA + Kyverno](docs/adr/ADR-005-kyverno-and-opa.md) | Why both admission controllers |

---

## License

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
