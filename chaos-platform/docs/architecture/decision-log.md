# Decision Log

Summary of every major technical decision made during the build of the Chaos Platform.

| # | Decision Area | Options Considered | Chosen | Reason | Phase |
|---|---|---|---|---|---|
| 1 | Backend language | Python, Go, Java | Python | Fast iteration, strong asyncio support, rich Kubernetes ecosystem (kubernetes-client, httpx). Team familiar with it. | 1 |
| 2 | IaC tool | Terraform, Pulumi, CDK | Terraform | Largest community, best AWS provider, most tutorials. Pulumi considered but adds language dependency. | 1 |
| 3 | Kubernetes distribution | EKS, GKE, AKS, k3s | EKS | AWS ecosystem integration (IAM, MSK, ElastiCache). IRSA for fine-grained pod IAM. S3 remote state. | 1 |
| 4 | Node type | On-demand t3.medium, SPOT t3.medium | SPOT t3.medium | Dev environment — ~70% cost savings. Single NAT GW acceptable for dev (would use one per AZ in prod). | 1 |
| 5 | Helm management | Raw helm, helmfile, ArgoCD | helmfile + ArgoCD | helmfile for local dev/bootstrap; ArgoCD for GitOps CD. Two tools but serve different purposes. | 2 |
| 6 | State backend | Local, S3+DynamoDB, Terraform Cloud | S3 + DynamoDB | Free, integrates with existing AWS account, locking via DynamoDB prevents concurrent applies. | 1 |
| 7 | App framework | FastAPI, Django, Flask | FastAPI | Async by default, automatic OpenAPI docs, pydantic validation, Python 3.11 native. | 3 |
| 8 | Message streaming | Kafka (MSK), SQS, EventBridge | Kafka | Persistent ordered log, consumer groups, replay capability. Chaos events need ordering guarantees. See ADR-002. | 4 |
| 9 | Circuit breaker implementation | External library, custom | Custom (asyncio) | Libraries added complexity for this use case. Simple failure count + state machine in ~50 lines. | 4 |
| 10 | HTTP client for load tester | requests, httpx, aiohttp | httpx[http2] | Native HTTP/2 support (important for testing gRPC services), async-native, connection pooling. | 5 |
| 11 | Live stats cache | Redis, Memcached, in-memory | Redis | Supports pub/sub for WebSocket push, sorted sets for percentiles, KEDA trigger support. | 5 |
| 12 | Frontend framework | React, Vue, Svelte | React 18 | Largest ecosystem, Redux Toolkit for state, Recharts for Prometheus data. | 6 |
| 13 | Frontend build tool | Webpack, Vite, Parcel | Vite | Fast HMR, native ESM, minimal config. Webpack too heavy for this project size. | 6 |
| 14 | CI provider | GitHub Actions, Jenkins, CircleCI | GitHub Actions (primary) | Free for public repos, tight GitHub integration, parallel matrix jobs. Jenkins for K8s-native jobs. | 7 |
| 15 | CD model | Argo CD, Flux, Helm Upgrade script | ArgoCD | App-of-Apps pattern, sync waves for ordered deployment, UI for visibility. See ADR-003. | 7 |
| 16 | Metrics | Prometheus, Datadog, New Relic | Prometheus | Open source, K8s native (ServiceMonitor CRD), integrates with Grafana, no agent cost. | 8 |
| 17 | Log aggregation | Loki, Elasticsearch/ELK, Datadog | Loki | Native Grafana integration, no schema (raw log lines), S3 backend for cheap storage. | 8 |
| 18 | Tracing | Tempo, Jaeger, Zipkin | Grafana Tempo | Pairs with Loki + Prometheus in the Grafana stack, trace-to-logs correlation. | 8 |
| 19 | Secret management | Vault, AWS Secrets Manager, K8s Secrets | Vault | Dynamic credentials, fine-grained policies, audit logging, not vendor-locked. See ADR-004. | 9 |
| 20 | Admission control | OPA alone, Kyverno alone, both | Both OPA + Kyverno | Different strengths: OPA for complex Rego logic, Kyverno for K8s-native YAML policies. See ADR-005. | 9 |
| 21 | Runtime security | Falco, Aqua, Sysdig | Falco | Open source, eBPF-based, custom rules, Falcosidekick for fan-out. | 9 |
| 22 | Certificate management | cert-manager, manual certs, AWS ACM | cert-manager | Automatic ACME renewals, CRD-based declarative config, Let's Encrypt integration. | 9 |
| 23 | Supply chain scanning | Dependency Track, Snyk, Trivy only | Dependency Track + Trivy | Trivy in CI at build time; DTrack for ongoing monitoring of deployed SBOMs. Defense in depth. | 9 |
| 24 | Lambda PDF generation | WeasyPrint, wkhtmltopdf, Puppeteer | WeasyPrint | Pure Python, no browser process, better CSS support for dark themes. Native libraries via Lambda layer. | 10 |
| 25 | Lambda notification | Direct Slack HTTP, SNS → Lambda | SNS → Lambda | Decoupled — multiple subscribers possible. SNS provides retry, dead-letter queue, fan-out. | 10 |
| 26 | Report format | JSON only, HTML, PDF | PDF | PDFs are shareable, printable, and look professional in Slack previews and email attachments. | 10 |
