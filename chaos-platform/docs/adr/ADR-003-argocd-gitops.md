# ADR-003: ArgoCD and GitOps Deployment Model

**Status:** Accepted  
**Date:** 2026-02-01  
**Deciders:** Platform Team

---

## Context

We needed a continuous deployment strategy for a platform with 6 application services, 5 infrastructure namespaces (monitoring, security, vault, falco, cert-manager), and ordering requirements between them. Specifically:

- Monitoring must be deployed before applications (applications need to be scraped by Prometheus from day one)
- Security (Vault, OPA) must be deployed before applications (applications need secrets and policy enforcement)
- Applications can deploy in any order relative to each other

We also needed auditability: who deployed what, when, and what changed in each deployment?

---

## Decision

We chose **ArgoCD with the App-of-Apps pattern** and GitOps as the deployment model.

All Kubernetes manifests are stored in git. ArgoCD continuously reconciles the cluster state to match the git state. Deployment is done by merging a PR — not by running a command.

Sync waves ensure correct ordering:
- Wave -2: monitoring stack (Prometheus, Grafana)
- Wave -1: security stack (Vault, OPA, Kyverno, cert-manager)  
- Wave 1: target-app
- Wave 2: chaos-engine
- Wave 3: load-tester
- Wave 4: dashboard

---

## Consequences

**Good:**
- **Auditability**: Every deployment is a git commit. `git log --oneline` tells you exactly what was deployed and when. ArgoCD UI shows the diff for each sync.
- **Rollback**: Rolling back is `git revert` — the same process as any code change, reviewed and merged through the PR process.
- **Drift detection**: ArgoCD continuously compares the cluster to git. If someone makes a manual `kubectl apply`, ArgoCD marks the app as OutOfSync and can auto-revert it.
- **Self-healing**: If a pod is manually deleted or a namespace is accidentally modified, ArgoCD restores the desired state within 3 minutes (default reconciliation interval).
- **App-of-Apps**: A single root ArgoCD Application watches the `argocd/apps/` directory. Adding a new service is as simple as adding a new YAML file to that directory.

**Bad / Trade-offs:**
- Initial setup is more complex than `helm upgrade --install`.
- ArgoCD needs to be bootstrapped before it can manage itself (chicken-and-egg solved by `scripts/bootstrap.sh`).
- The `[skip ci]` commit pattern in GitHub Actions (for manifest patches) can confuse engineers unfamiliar with GitOps.
- ArgoCD adds latency to deployments: CI builds the image, pushes to ECR, patches the manifest, and then ArgoCD polls and syncs (adds ~3 min vs immediate `helm upgrade`).

---

## Alternatives Considered

**Flux CD:**  
- Similar GitOps model, lighter weight, good Helm support  
- Rejected because: smaller community, less mature UI, fewer tutorials  

**Helm + CI Upgrade:**  
- Simple pipeline: build → test → `helm upgrade`  
- Rejected because: no drift detection, no rollback via git, no auditability (helm history is local to the cluster), ordering between deployments is complex to implement  

**Argo Rollouts (canary deployments):**  
- Would add canary and blue/green deployment strategies  
- Not implemented in this phase — would add on top of ArgoCD in a future phase  
